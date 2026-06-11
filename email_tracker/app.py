"""Live web dashboard: deal tracker + auto-updating to-do list.

READ-ONLY: this app only ever *reads* email. Every source (sample, Outlook
Graph, MCP export) issues reads only — there is no code path that sends,
drafts, moves, flags, or deletes mail. Marking something "done" writes to the
local tracker database, never to your mailbox.

How it stays current:
  * A background poller fetches email on an interval (POLL_INTERVAL secs),
    classifies any *new* messages with Claude, and persists them. Already-seen
    emails are served from cache (no re-classification).
  * The browser polls /api/state every few seconds and re-renders, so the
    dashboard reflects new mail without a manual refresh.

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    # source: sample (default) | outlook (read-only Graph) | mcp (JSON export)
    EMAIL_SOURCE=sample python app.py
    # open http://localhost:5000
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from classifier import Classification, classify_email
from email_source import SampleEmailSource
from store import DEFAULT_DB, Store

# Pipeline columns, in order. Anything else falls into "unknown".
STAGE_ORDER = ["sourcing", "diligence", "negotiation", "closing", "closed", "passed", "unknown"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_source(name: str):
    """Construct the chosen read-only email source."""
    name = (name or "sample").lower()
    if name == "outlook":
        from graph_source import GraphEmailSource

        return GraphEmailSource.from_env(limit=int(os.environ.get("EMAIL_LIMIT", "25")))
    if name == "mcp":
        from mcp_source import DEFAULT_EXPORT, MCPExportSource

        return MCPExportSource(os.environ.get("EMAIL_EXPORT", DEFAULT_EXPORT))
    return SampleEmailSource()


def get_client():
    """Anthropic client, or None if no key is configured."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    try:
        import anthropic

        return anthropic.Anthropic()
    except Exception:
        return None


class Poller(threading.Thread):
    """Periodically reads email and classifies anything new."""

    def __init__(self, store: Store, source, interval: int):
        super().__init__(daemon=True)
        self.store = store
        self.source = source
        self.interval = interval
        self._stop = threading.Event()
        self.last_updated: str | None = None
        self.last_error: str | None = None
        self.last_new = 0

    def poll_once(self) -> None:
        client = get_client()
        try:
            emails = self.source.fetch()
        except Exception as exc:
            self.last_error = f"fetch failed: {exc}"
            return

        new = 0
        for email in emails:
            if self.store.get_email(email.id) is not None:
                continue  # already classified — cached
            if client is None:
                continue  # can't classify without a key; leave for later
            try:
                c = classify_email(client, email)
            except Exception as exc:
                self.last_error = f"classify failed: {exc}"
                continue
            self.store.save_email(email, c)
            if c.is_deal_related and c.deal_name:
                self.store.upsert_deal(
                    c.deal_name, c.deal_stage and c.deal_stage.value, email.received
                )
            new += 1

        self.last_new = new
        self.last_updated = _now()
        self.last_error = None if client is not None else "no ANTHROPIC_API_KEY — classification paused"

    def run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()


def _todo_from_email(row) -> dict:
    c = Classification.model_validate_json(row["classification"])
    return {
        "id": row["id"],
        "subject": row["subject"],
        "from_name": row["from_name"],
        "from_addr": row["from_addr"],
        "priority": c.priority.value,
        "deal_name": c.deal_name,
        "deadline": c.deadline,
        "summary": c.summary,
        "action": c.suggested_action,
    }


def create_app(start_poller: bool = True) -> Flask:
    app = Flask(__name__)
    store = Store(os.environ.get("TRACKER_DB", DEFAULT_DB))
    source_name = os.environ.get("EMAIL_SOURCE", "sample")
    interval = int(os.environ.get("POLL_INTERVAL", "60"))

    poller = Poller(store, build_source(source_name), interval)
    app.config["STORE"] = store
    app.config["POLLER"] = poller
    app.config["SOURCE_NAME"] = source_name
    if start_poller:
        poller.start()

    PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

    @app.get("/")
    def index():
        return DASHBOARD_HTML

    @app.get("/api/state")
    def state():
        email_todos = sorted(
            (_todo_from_email(r) for r in store.get_to_respond()),
            key=lambda t: PRIORITY_RANK.get(t["priority"], 1),
        )
        manual = [
            {"id": r["id"], "text": r["text"], "done": bool(r["done"])}
            for r in store.get_todos()
        ]

        stages: dict[str, list] = {s: [] for s in STAGE_ORDER}
        for d in store.get_deals():
            stage = d["stage"] if d["stage"] in stages else "unknown"
            stages[stage].append(
                {
                    "name": d["name"],
                    "stage": stage,
                    "email_count": d["email_count"],
                    "awaiting": d["awaiting"],
                    "last_activity": (d["last_activity"] or "")[:10],
                }
            )

        return jsonify(
            {
                "updated_at": poller.last_updated,
                "error": poller.last_error,
                "has_api_key": get_client() is not None,
                "source": source_name,
                "poll_interval": interval,
                "stats": {
                    "to_respond": len(email_todos),
                    "deals": sum(len(v) for v in stages.values()),
                    "total_emails": store.count_emails(),
                    "open_todos": sum(1 for m in manual if not m["done"]),
                },
                "todos": {"from_email": email_todos, "manual": manual},
                "deals": {"order": STAGE_ORDER, "stages": stages},
            }
        )

    @app.post("/api/refresh")
    def refresh():
        threading.Thread(target=poller.poll_once, daemon=True).start()
        return jsonify({"ok": True})

    @app.post("/api/email/<email_id>/done")
    def email_done(email_id: str):
        done = request.json.get("done", True) if request.is_json else True
        ok = store.mark_responded(email_id, bool(done))
        return jsonify({"ok": ok})

    @app.post("/api/todo")
    def add_todo():
        text = (request.json or {}).get("text", "").strip()
        if not text:
            return jsonify({"ok": False, "error": "empty"}), 400
        return jsonify({"ok": True, "id": store.add_todo(text)})

    @app.post("/api/todo/<int:todo_id>/done")
    def todo_done(todo_id: int):
        done = request.json.get("done", True) if request.is_json else True
        return jsonify({"ok": store.set_todo_done(todo_id, bool(done))})

    @app.delete("/api/todo/<int:todo_id>")
    def todo_delete(todo_id: int):
        return jsonify({"ok": store.delete_todo(todo_id)})

    return app


# The single-page dashboard. Vanilla JS, no build step. Polls /api/state.
DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Inbox Tracker</title>
<style>
  :root {
    --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --line:#2a2f3a;
    --txt:#e6e9ef; --dim:#8b93a7; --accent:#5b8cff;
    --high:#ff5d5d; --med:#ffb14e; --low:#6b7280; --ok:#3ddc84;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  header { display:flex; align-items:center; gap:16px; padding:14px 22px;
    border-bottom:1px solid var(--line); background:var(--panel); position:sticky; top:0; z-index:5; }
  header h1 { font-size:16px; margin:0; font-weight:650; }
  .badge { font-size:11px; padding:3px 9px; border-radius:99px; border:1px solid var(--line); color:var(--dim); }
  .badge.ro { color:var(--ok); border-color:#1f3a2b; background:#10221a; }
  .badge.warn { color:var(--med); border-color:#3a2f17; background:#221c10; }
  .spacer { flex:1; }
  .meta { color:var(--dim); font-size:12px; }
  button { font:inherit; cursor:pointer; border:1px solid var(--line);
    background:var(--panel2); color:var(--txt); border-radius:8px; padding:6px 12px; }
  button:hover { border-color:var(--accent); }
  .stats { display:flex; gap:10px; padding:16px 22px 4px; }
  .stat { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px 16px; min-width:120px; }
  .stat .n { font-size:24px; font-weight:700; }
  .stat .l { color:var(--dim); font-size:12px; }
  .grid { display:grid; grid-template-columns:minmax(340px,1fr) 1.4fr; gap:18px; padding:18px 22px 40px; align-items:start; }
  .col h2 { font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--dim); margin:0 0 10px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px 14px; margin-bottom:10px; }
  .todo { display:flex; gap:10px; align-items:flex-start; }
  .todo input[type=checkbox] { margin-top:3px; width:16px; height:16px; accent-color:var(--accent); }
  .todo .body { flex:1; }
  .todo .subj { font-weight:600; }
  .todo .sum { color:var(--dim); font-size:13px; }
  .todo .act { color:var(--ok); font-size:13px; margin-top:3px; }
  .pill { font-size:10px; font-weight:700; padding:2px 7px; border-radius:99px; text-transform:uppercase; }
  .p-high { background:#3a1414; color:var(--high); }
  .p-medium { background:#34270f; color:var(--med); }
  .p-low { background:#23262e; color:var(--low); }
  .due { color:var(--high); font-size:12px; }
  .tag { color:var(--accent); font-size:12px; }
  .addrow { display:flex; gap:8px; margin-bottom:12px; }
  .addrow input { flex:1; background:var(--panel2); border:1px solid var(--line); color:var(--txt);
    border-radius:8px; padding:8px 10px; }
  .manual { display:flex; align-items:center; gap:10px; }
  .manual.done .txt { text-decoration:line-through; color:var(--dim); }
  .manual .del { margin-left:auto; color:var(--dim); border:none; background:none; padding:2px 6px; }
  .pipeline { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:12px; }
  .stage { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:10px; }
  .stage h3 { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--dim); margin:0 0 8px; display:flex; justify-content:space-between; }
  .deal { background:var(--panel2); border:1px solid var(--line); border-radius:9px; padding:8px 10px; margin-bottom:8px; }
  .deal .dn { font-weight:600; }
  .deal .dm { color:var(--dim); font-size:12px; }
  .deal .await { color:var(--high); font-size:12px; }
  .empty { color:var(--dim); font-size:13px; padding:6px 2px; }
</style>
</head>
<body>
<header>
  <h1>📥 Inbox Tracker</h1>
  <span class="badge ro" title="This app only reads email — it never sends, drafts, or edits.">🔒 Read-only</span>
  <span id="srcBadge" class="badge"></span>
  <span class="spacer"></span>
  <span id="status" class="meta"></span>
  <button onclick="refreshNow()">↻ Refresh now</button>
</header>

<div class="stats" id="stats"></div>

<div class="grid">
  <div class="col">
    <h2>✅ To-Do</h2>
    <div class="addrow">
      <input id="todoInput" placeholder="Add a personal to-do…" onkeydown="if(event.key==='Enter')addTodo()" />
      <button onclick="addTodo()">Add</button>
    </div>
    <div id="todos"></div>
  </div>
  <div class="col">
    <h2>💼 Deal Tracker</h2>
    <div class="pipeline" id="pipeline"></div>
  </div>
</div>

<script>
const STAGE_LABELS = {sourcing:"Sourcing",diligence:"Diligence",negotiation:"Negotiation",
  closing:"Closing",closed:"Closed",passed:"Passed",unknown:"Other"};

async function load() {
  let s;
  try { s = await (await fetch('/api/state')).json(); }
  catch (e) { document.getElementById('status').textContent = 'connection lost…'; return; }
  render(s);
}

function render(s) {
  document.getElementById('srcBadge').textContent = 'source: ' + s.source;
  const upd = s.updated_at ? new Date(s.updated_at).toLocaleTimeString() : '—';
  let status = 'updated ' + upd + ' · polling every ' + s.poll_interval + 's';
  document.getElementById('status').textContent = status;
  const sb = document.getElementById('srcBadge');
  sb.className = 'badge' + (s.has_api_key ? '' : ' warn');

  const st = s.stats;
  document.getElementById('stats').innerHTML = [
    ['To respond', st.to_respond],['Open to-dos', st.open_todos],
    ['Deals', st.deals],['Emails tracked', st.total_emails],
  ].map(([l,n])=>`<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('')
   + (s.error ? `<div class="stat" style="border-color:#3a2f17"><div class="l" style="color:var(--med)">⚠ ${s.error}</div></div>` : '');

  // To-do: email-derived items first, then manual.
  let html = '';
  const et = s.todos.from_email;
  if (!et.length && !s.todos.manual.length) html += '<div class="empty">Nothing to do. 🎉</div>';
  for (const t of et) {
    html += `<div class="card todo">
      <input type="checkbox" onchange="emailDone('${t.id}')" title="Mark responded" />
      <div class="body">
        <div><span class="pill p-${t.priority}">${t.priority}</span>
          <span class="subj">${esc(t.subject)}</span>
          ${t.deal_name?`<span class="tag">· ${esc(t.deal_name)}</span>`:''}
          ${t.deadline?`<span class="due">⏰ ${esc(t.deadline)}</span>`:''}</div>
        <div class="sum">${esc(t.from_name)} — ${esc(t.summary)}</div>
        <div class="act">→ ${esc(t.action)}</div>
      </div></div>`;
  }
  for (const m of s.todos.manual) {
    html += `<div class="card manual ${m.done?'done':''}">
      <input type="checkbox" ${m.done?'checked':''} onchange="todoDone(${m.id},this.checked)" />
      <span class="txt">${esc(m.text)}</span>
      <button class="del" onclick="delTodo(${m.id})" title="Delete">✕</button></div>`;
  }
  document.getElementById('todos').innerHTML = html;

  // Deals pipeline
  let pipe = '';
  for (const stage of s.deals.order) {
    const deals = s.deals.stages[stage] || [];
    if (!deals.length) continue;
    pipe += `<div class="stage"><h3><span>${STAGE_LABELS[stage]||stage}</span><span>${deals.length}</span></h3>`;
    for (const d of deals) {
      pipe += `<div class="deal"><div class="dn">${esc(d.name)}</div>
        <div class="dm">${d.email_count} email(s) · ${d.last_activity||''}</div>
        ${d.awaiting?`<div class="await">${d.awaiting} awaiting reply</div>`:''}</div>`;
    }
    pipe += '</div>';
  }
  document.getElementById('pipeline').innerHTML = pipe || '<div class="empty">No deals detected yet.</div>';
}

function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
async function emailDone(id){ await fetch(`/api/email/${id}/done`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{"done":true}'}); load(); }
async function todoDone(id,done){ await fetch(`/api/todo/${id}/done`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({done})}); load(); }
async function delTodo(id){ await fetch(`/api/todo/${id}`,{method:'DELETE'}); load(); }
async function addTodo(){ const i=document.getElementById('todoInput'); const t=i.value.trim(); if(!t)return;
  await fetch('/api/todo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})}); i.value=''; load(); }
async function refreshNow(){ await fetch('/api/refresh',{method:'POST'}); setTimeout(load,800); }

load();
setInterval(load, 5000);  // browser auto-refresh
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", "5000"))
    print(f"Inbox Tracker on http://localhost:{port}  (source={app.config['SOURCE_NAME']}, read-only)")
    app.run(host="0.0.0.0", port=port)
