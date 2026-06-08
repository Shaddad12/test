"""Agent-driven email source: read emails from a normalized JSON export.

Why this exists
---------------
The Microsoft 365 / Outlook **MCP connector** is available to an *agent*
(e.g. Claude Code with the Outlook connector enabled) — not to a standalone
Python process. So instead of the script calling Graph directly (that's what
`graph_source.py` is for), this path lets an agent do the read-only fetch and
hand the results to the classifier:

    agent (MCP outlook_email_search)  →  inbox_export.json  →  MCPExportSource
                                                              →  classifier

The agent calls the connector's read-only search, maps each message to the
`Email` shape, and writes a JSON array to `inbox_export.json`. This source just
reads that file — no credentials, no network, and still read-only (the export
only ever contains data the connector already returned).

Expected JSON shape (a list of objects):

    [
      {
        "id": "AAMk...",
        "from_name": "Kiran Kharat",
        "from_addr": "kiran.kharat@arcadiacapital.io",
        "subject": "Capacity Available",
        "received": "2026-06-08T05:30:53Z",
        "body": "Hi Team, we currently have bandwidth available..."
      },
      ...
    ]

The export file holds real mailbox content, so it is gitignored — never commit
it.
"""

from __future__ import annotations

import json
from pathlib import Path

from email_source import Email, EmailSource

DEFAULT_EXPORT = str(Path(__file__).with_name("inbox_export.json"))

# Keys the connector might use → our normalized field. Lets the agent paste
# connector output with minimal reshaping.
_ALIASES = {
    "from": "from_addr",
    "sender": "from_addr",
    "fromName": "from_name",
    "receivedDateTime": "received",
    "bodyPreview": "body",
    "summary": "body",
}


class MCPExportSource(EmailSource):
    def __init__(self, path: str = DEFAULT_EXPORT):
        self.path = path

    def fetch(self) -> list[Email]:
        p = Path(self.path)
        if not p.exists():
            raise FileNotFoundError(
                f"No export at {self.path}. Have the agent run the Outlook MCP "
                f"search and write results there (see mcp_source.py)."
            )

        raw = json.loads(p.read_text())
        emails: list[Email] = []
        for item in raw:
            rec = {_ALIASES.get(k, k): v for k, v in item.items()}
            emails.append(
                Email(
                    id=str(rec.get("id", "")),
                    from_name=rec.get("from_name", "") or "",
                    from_addr=rec.get("from_addr", "") or "",
                    subject=rec.get("subject", "") or "(no subject)",
                    received=rec.get("received", "") or "",
                    body=rec.get("body", "") or "",
                )
            )
        return emails
