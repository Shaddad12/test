"""Email source abstraction.

The classifier works against a list of `Email` objects and does not care where
they come from. The proof-of-concept ships a `SampleEmailSource`; a real
deployment would add a `GraphEmailSource` (Microsoft 365 / Outlook) that
implements the same `fetch()` method and returns the same `Email` shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Email:
    """A single inbox message, normalized across providers."""

    id: str
    from_name: str
    from_addr: str
    subject: str
    received: str  # ISO 8601
    body: str


class EmailSource:
    """Interface every source implements."""

    def fetch(self) -> list[Email]:
        raise NotImplementedError


class SampleEmailSource(EmailSource):
    """Loads the bundled sample inbox — no credentials required."""

    def fetch(self) -> list[Email]:
        from sample_emails import SAMPLE_EMAILS

        return [Email(**e) for e in SAMPLE_EMAILS]


# --- Future: Microsoft 365 / Outlook -------------------------------------
# To go live, implement this against Microsoft Graph and select it in cli.py.
#
# READ-ONLY BY DESIGN — this source can never send or edit your mailbox:
#   1. SCOPE (the real lock, enforced by Microsoft): request ONLY `Mail.Read`.
#      A token granted Mail.Read is physically incapable of sending, moving,
#      editing, or deleting mail — Graph returns 403 if anything tries. We do
#      NOT request `Mail.ReadWrite` or `Mail.Send`. The sign-in consent screen
#      will show exactly one permission: "Read your mail."
#   2. CODE (defense in depth): this source only ever issues HTTP GET, and the
#      `_get` helper below refuses any non-GET method before it leaves the
#      process — so a future bug can't silently introduce a write.
#
# class GraphEmailSource(EmailSource):
#     """Reads the inbox via Microsoft Graph (Outlook / Microsoft 365)."""
#
#     SCOPES = ["Mail.Read"]  # read-only; never add ReadWrite/Send
#     BASE = "https://graph.microsoft.com/v1.0"
#
#     def __init__(self, access_token: str):
#         self.access_token = access_token
#
#     def _get(self, path: str, **params):
#         """Read-only HTTP. Hard-coded to GET so no caller can write."""
#         import requests
#
#         resp = requests.get(
#             f"{self.BASE}{path}",
#             headers={"Authorization": f"Bearer {self.access_token}"},
#             params=params,
#             timeout=30,
#         )
#         resp.raise_for_status()
#         return resp.json()
#
#     def fetch(self) -> list[Email]:
#         # Docs: https://learn.microsoft.com/graph/api/user-list-messages
#         data = self._get(
#             "/me/messages",
#             **{"$top": 25, "$select": "id,subject,from,receivedDateTime,bodyPreview"},
#         )
#         emails = []
#         for m in data.get("value", []):
#             sender = m.get("from", {}).get("emailAddress", {})
#             emails.append(
#                 Email(
#                     id=m["id"],
#                     from_name=sender.get("name", ""),
#                     from_addr=sender.get("address", ""),
#                     subject=m.get("subject", ""),
#                     received=m.get("receivedDateTime", ""),
#                     body=m.get("bodyPreview", ""),
#                 )
#             )
#         return emails
