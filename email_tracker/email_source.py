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
# class GraphEmailSource(EmailSource):
#     """Reads the inbox via Microsoft Graph (Outlook / Microsoft 365).
#
#     Setup required (one time):
#       1. Register an app in Entra ID (Azure AD) and grant the delegated
#          `Mail.Read` permission.
#       2. Run the OAuth device-code or auth-code flow to get an access token.
#       3. GET https://graph.microsoft.com/v1.0/me/messages?$top=25
#          and map each message to the `Email` shape below.
#
#     Docs: https://learn.microsoft.com/graph/api/user-list-messages
#     """
#
#     def __init__(self, access_token: str):
#         self.access_token = access_token
#
#     def fetch(self) -> list[Email]:
#         import requests
#
#         resp = requests.get(
#             "https://graph.microsoft.com/v1.0/me/messages",
#             headers={"Authorization": f"Bearer {self.access_token}"},
#             params={"$top": 25, "$select": "id,subject,from,receivedDateTime,bodyPreview"},
#             timeout=30,
#         )
#         resp.raise_for_status()
#         emails = []
#         for m in resp.json().get("value", []):
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
