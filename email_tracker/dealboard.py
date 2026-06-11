"""Deal Board: a status dashboard organized by deal/pitch, not by email.

For each active deal or pitch it shows the current status and — the key thing —
**whose court the next move is in**: yours (you owe the next action) vs theirs
(waiting on a counterparty). Produced by one cross-thread analysis over recent
email so it reasons about who owes what.

Read-only: reads an email export, writes a static HTML file. Never touches mail.

    export ANTHROPIC_API_KEY=sk-ant-...
    python dealboard.py            # -> deal_dashboard.html
"""

from __future__ import annotations

import html
import json
import os
from enum import Enum
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from mcp_source import MCPExportSource

MODEL = "claude-opus-4-8"


class Court(str, Enum):
    you = "you"      # Sam / Arcadia owes the next move
    them = "them"    # waiting on a counterparty / client
    none = "none"    # nothing pending (closed, dead, or purely FYI)


class DealType(str, Enum):
    deal = "deal"            # a live sell-side / buy-side engagement
    pitch = "pitch"          # a pitch / new business we're chasing
    fundraise = "fundraise"  # LP / capital raise
    other = "other"


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class DealStatus(BaseModel):
    name: str = Field(description="Deal / pitch / company name (use the codename if that's what's used).")
    type: DealType
    stage: str = Field(description="Short stage label, e.g. 'IOI review', 'LOI drafting', 'diligence', 'CIM prep'.")
    status: str = Field(description="One sentence on where things stand right now.")
    ball_in_court: Court = Field(description="Who owes the next move.")
    next_step: str = Field(description="The specific next action that needs to happen.")
    waiting_on: Optional[str] = Field(default=None, description="If waiting on them: who/what we're waiting for.")
    priority: Priority
    last_activity: Optional[str] = Field(default=None, description="Date of most recent activity (YYYY-MM-DD).")


class DealBoard(BaseModel):
    deals: list[DealStatus]


SYSTEM = (
    "You are chief of staff to Sam, a banker at Arcadia Capital, a sell-side / "
    "strategic M&A advisor. You'll get a chronological digest of recent emails "
    "across multiple deals and pitches. Build a STATUS BOARD grouped by active "
    "deal / pitch / workstream — NOT by email.\n\n"
    "For each one, decide whose court the next move is in:\n"
    "  - 'you'  : Sam/Arcadia owes the next action (send a draft, reply to a "
    "counterparty, give feedback, finalize a document, make a decision).\n"
    "  - 'them' : we're waiting on a counterparty or client to respond, submit "
    "a bid, sign, or provide materials.\n"
    "  - 'none' : nothing is pending (closed, passed, or pure FYI).\n\n"
    "Use the MOST RECENT message in each thread to judge the ball: if a "
    "counterparty asked us something and we haven't answered, it's our court; "
    "if we sent something and await their move, it's theirs; an internal "
    "'I'll handle it' still means Sam's team owes the external move (your "
    "court). Treat *@arcadiacapital.io as Sam's own team (internal). IGNORE "
    "newsletters, marketing, event invites, login links, and pure admin "
    "notifications — they are not deals. Be specific and concrete in next_step.\n\n"
    "'Project Shield' is the codename for the Talview sell-side deal — treat "
    "them as the same underlying deal. For a sell-side / buy-side process with "
    "multiple counterparties, make a SEPARATE card per active counterparty "
    "(name it 'Talview — <Counterparty>') because the ball-in-court differs by "
    "counterparty. Counterparties who have explicitly passed/declined go under "
    "ball_in_court 'none' (closed)."
)


def _digest(emails) -> str:
    def who(addr: str) -> str:
        return "ARCADIA/internal" if addr.endswith("@arcadiacapital.io") else f"EXTERNAL <{addr}>"

    # Oldest -> newest so the model can see how each thread progressed.
    rows = sorted(emails, key=lambda e: e.received)
    lines = []
    for e in rows:
        lines.append(
            f"[{(e.received or '')[:10]}] from {who(e.from_addr)} | {e.subject}\n"
            f"    {e.body.strip()[:300]}"
        )
    return "\n".join(lines)


def build_board(client: anthropic.Anthropic, emails) -> DealBoard:
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": _digest(emails)}],
        output_format=DealBoard,
    )
    return resp.parsed_output


# --- rendering -----------------------------------------------------------

PRIORITY_RANK = {Priority.high: 0, Priority.medium: 1, Priority.low: 2}


def _card(d: DealStatus) -> str:
    e = html.escape
    pri = d.priority.value
    typ = d.type.value
    line2 = (
        f'<div class="next">→ {e(d.next_step)}</div>'
        if d.ball_in_court == Court.you
        else (f'<div class="wait">waiting on: {e(d.waiting_on or d.next_step)}</div>'
              if d.ball_in_court == Court.them else f'<div class="next">{e(d.next_step)}</div>')
    )
    return f"""<div class="card">
      <div class="row1">
        <span class="name">{e(d.name)}</span>
        <span class="pill type-{typ}">{typ}</span>
        <span class="pill p-{pri}">{pri}</span>
      </div>
      <div class="stage">{e(d.stage)} · <span class="dim">{e(d.last_activity or '')}</span></div>
      <div class="status">{e(d.status)}</div>
      {line2}
    </div>"""


def render(board: DealBoard) -> str:
    you = sorted([d for d in board.deals if d.ball_in_court == Court.you], key=lambda d: PRIORITY_RANK[d.priority])
    them = sorted([d for d in board.deals if d.ball_in_court == Court.them], key=lambda d: PRIORITY_RANK[d.priority])
    none = [d for d in board.deals if d.ball_in_court == Court.none]

    def col(cards):
        return "".join(_card(d) for d in cards) or '<div class="empty">Nothing here.</div>'

    high = sum(1 for d in board.deals if d.priority == Priority.high and d.ball_in_court == Court.you)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Deal Board</title>
<style>
  :root {{ --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --line:#2a2f3a; --txt:#e6e9ef;
    --dim:#8b93a7; --you:#ff8a5b; --them:#5b8cff; --high:#ff5d5d; --med:#ffb14e; --low:#6b7280; --ok:#3ddc84; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  header {{ display:flex; align-items:center; gap:14px; padding:16px 24px; border-bottom:1px solid var(--line); background:var(--panel); }}
  header h1 {{ font-size:17px; margin:0; }}
  .badge {{ font-size:11px; padding:3px 9px; border-radius:99px; border:1px solid #1f3a2b; color:var(--ok); background:#10221a; }}
  .spacer {{ flex:1; }} .meta {{ color:var(--dim); font-size:12px; }}
  .stats {{ display:flex; gap:10px; padding:18px 24px 6px; }}
  .stat {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px 18px; min-width:130px; }}
  .stat .n {{ font-size:26px; font-weight:700; }} .stat .l {{ color:var(--dim); font-size:12px; }}
  .stat.you .n {{ color:var(--you); }} .stat.them .n {{ color:var(--them); }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; padding:14px 24px 40px; align-items:start; }}
  .col h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.05em; margin:0 0 12px; display:flex; gap:8px; align-items:center; }}
  .col.you h2 {{ color:var(--you); }} .col.them h2 {{ color:var(--them); }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:13px 15px; margin-bottom:11px; }}
  .col.you .card {{ border-left:3px solid var(--you); }}
  .col.them .card {{ border-left:3px solid var(--them); }}
  .row1 {{ display:flex; align-items:center; gap:8px; }}
  .name {{ font-weight:650; font-size:15px; }}
  .pill {{ font-size:10px; font-weight:700; padding:2px 7px; border-radius:99px; text-transform:uppercase; }}
  .type-deal {{ background:#16261c; color:#7fe0a8; }} .type-pitch {{ background:#241c2e; color:#c79bff; }}
  .type-fundraise {{ background:#1c2233; color:#8fb0ff; }} .type-other {{ background:#23262e; color:var(--dim); }}
  .p-high {{ background:#3a1414; color:var(--high); }} .p-medium {{ background:#34270f; color:var(--med); }} .p-low {{ background:#23262e; color:var(--low); }}
  .stage {{ font-size:12px; color:var(--txt); margin:6px 0 2px; }} .dim {{ color:var(--dim); }}
  .status {{ color:#c7ccd8; font-size:13px; margin:4px 0 6px; }}
  .next {{ color:var(--you); font-size:13px; }} .col.them .next {{ color:var(--dim); }}
  .wait {{ color:var(--them); font-size:13px; }}
  .empty {{ color:var(--dim); font-size:13px; }}
  .closed {{ padding:0 24px 40px; }} .closed h2 {{ font-size:12px; color:var(--dim); text-transform:uppercase; }}
  .closed .card {{ opacity:.6; }}
</style></head><body>
<header>
  <h1>💼 Deal Board</h1>
  <span class="badge">🔒 Read-only</span>
  <span class="spacer"></span>
  <span class="meta">{len(board.deals)} active workstreams</span>
</header>
<div class="stats">
  <div class="stat you"><div class="n">{len(you)}</div><div class="l">In your court</div></div>
  <div class="stat them"><div class="n">{len(them)}</div><div class="l">Waiting on others</div></div>
  <div class="stat"><div class="n">{high}</div><div class="l">High-priority &amp; yours</div></div>
  <div class="stat"><div class="n">{len(board.deals)}</div><div class="l">Total tracked</div></div>
</div>
<div class="grid">
  <div class="col you"><h2>🔴 In your court — you owe the next move</h2>{col(you)}</div>
  <div class="col them"><h2>⏳ Waiting on others</h2>{col(them)}</div>
</div>
<div class="closed"><h2>No action pending</h2>{''.join(_card(d) for d in none) or '<div class="empty">—</div>'}</div>
</body></html>"""


def main() -> None:
    export = os.environ.get("EMAIL_EXPORT", "inbox_export.json")
    out = os.environ.get("OUT", "deal_dashboard.html")
    client = anthropic.Anthropic()

    emails = MCPExportSource(export).fetch()
    print(f"Analyzing {len(emails)} emails into a deal board...")
    board = build_board(client, emails)

    you = [d for d in board.deals if d.ball_in_court == Court.you]
    them = [d for d in board.deals if d.ball_in_court == Court.them]
    for d in board.deals:
        print(f"  [{d.ball_in_court.value:4}] {d.name:28} {d.stage:16} → {d.next_step[:60]}")

    with open(out, "w") as f:
        f.write(render(board))
    print(f"\nWrote {out}  ({len(you)} in your court, {len(them)} waiting, {len(board.deals)} total)")


if __name__ == "__main__":
    main()
