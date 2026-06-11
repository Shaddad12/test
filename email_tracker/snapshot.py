"""Generate a self-contained, static snapshot of the dashboard.

Classifies the emails in an export (default inbox_export.json) with Claude and
writes a single HTML file with the results baked in — openable in any browser
with no server. Read-only: it only reads the export; it never touches email.

    export ANTHROPIC_API_KEY=sk-ant-...
    python snapshot.py            # -> inbox_dashboard.html
"""

from __future__ import annotations

import json
import os
import re
import tempfile

import anthropic

from app import DASHBOARD_HTML, create_app
from classifier import classify_email
from mcp_source import MCPExportSource
from store import Store

_NAME_SKIP = ("no-reply", "noreply", "no_reply", "alerts", "notification",
              "notifications", "service", "support", "donotreply", "do-not-reply")


def pretty_name(addr: str) -> str:
    local = (addr or "").split("@")[0]
    if not local or any(s in local.lower() for s in _NAME_SKIP):
        return addr
    parts = [p for p in re.split(r"[._]", local) if p]
    if parts and all(p.isalpha() for p in parts):
        return " ".join(p.capitalize() for p in parts)
    return addr


def main() -> None:
    export = os.environ.get("EMAIL_EXPORT", "inbox_export.json")
    out = os.environ.get("OUT", "inbox_dashboard.html")
    os.environ["TRACKER_DB"] = tempfile.mktemp(suffix=".db")

    store = Store(os.environ["TRACKER_DB"])
    client = anthropic.Anthropic()

    emails = MCPExportSource(export).fetch()
    print(f"Classifying {len(emails)} emails with Claude...")
    for i, e in enumerate(emails, 1):
        if "@" in (e.from_name or ""):
            e.from_name = pretty_name(e.from_addr)
        if store.get_email(e.id) is not None:
            continue
        c = classify_email(client, e)
        store.save_email(e, c)
        if c.is_deal_related and c.deal_name:
            store.upsert_deal(c.deal_name, c.deal_stage and c.deal_stage.value, e.received)
        print(f"  [{i}/{len(emails)}] {e.subject[:46]:46} "
              f"reply={c.needs_reply!s:5} pri={c.priority.value:6} deal={c.deal_name}")
    store.close()

    # Reuse the live app's /api/state to compute exactly what the dashboard shows.
    app = create_app(start_poller=False)
    state = app.test_client().get("/api/state").get_json()

    # Bake the state into the page and turn off the live polling.
    html = DASHBOARD_HTML
    html = html.replace(
        "load();\nsetInterval(load, 5000);  // browser auto-refresh",
        "render(__STATE__);",
    )
    html = html.replace("<script>", "<script>\nconst __STATE__ = " + json.dumps(state) + ";\n", 1)
    html = html.replace(
        '<button onclick="refreshNow()">↻ Refresh now</button>',
        '<span class="meta">static snapshot</span>',
    )

    with open(out, "w") as f:
        f.write(html)

    s = state["stats"]
    print(f"\nWrote {out}")
    print(f"  to-respond={s['to_respond']}  deals={s['deals']}  "
          f"open-todos={s['open_todos']}  emails={s['total_emails']}")
    os.remove(os.environ["TRACKER_DB"])


if __name__ == "__main__":
    main()
