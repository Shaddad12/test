"""Live Microsoft 365 / Outlook email source via Microsoft Graph.

READ-ONLY BY DESIGN — this source can never send, move, edit, or delete mail:

  1. SCOPE (the real lock, enforced by Microsoft): it requests ONLY `Mail.Read`.
     A token granted Mail.Read is physically incapable of writing — Graph
     returns 403 if anything tries. We never request Mail.ReadWrite or
     Mail.Send. At sign-in you'll see exactly one permission: "Read your mail".
  2. CODE (defense in depth): every Graph call goes through `_get`, which is
     hard-coded to HTTP GET. There is no code path here that can issue a
     write request.

Auth uses the OAuth device-code flow (no redirect server needed): on first run
it prints a short code and URL, you approve in a browser, and the token is
cached to disk so later runs are silent until the refresh token expires.

One-time setup (free):
  1. Register an app at https://entra.microsoft.com → App registrations → New.
     - Supported account types: pick what matches your mailbox (e.g.
       "Accounts in any org directory and personal Microsoft accounts").
     - Under Authentication → Advanced settings, set "Allow public client
       flows" = Yes (required for the device-code flow).
     - Under API permissions, add Microsoft Graph → Delegated → Mail.Read.
       Add nothing else.
  2. Copy the Application (client) ID.
  3. Run:  GRAPH_CLIENT_ID=<id> python cli.py --source outlook
     (optionally GRAPH_TENANT_ID=<tenant>, defaults to "common")

Requires: pip install msal requests
"""

from __future__ import annotations

import os
from pathlib import Path

from email_source import Email, EmailSource

# Read-only. Do NOT add Mail.ReadWrite or Mail.Send — see module docstring.
SCOPES = ["Mail.Read"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_CACHE = str(Path(__file__).with_name(".graph_token_cache.json"))


class GraphAuthError(RuntimeError):
    pass


class GraphEmailSource(EmailSource):
    def __init__(self, client_id: str, tenant_id: str = "common", *, limit: int = 25):
        if not client_id:
            raise GraphAuthError(
                "Missing client id. Set GRAPH_CLIENT_ID (see graph_source.py setup notes)."
            )
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.limit = limit
        self._token: str | None = None

    @classmethod
    def from_env(cls, *, limit: int = 25) -> "GraphEmailSource":
        return cls(
            client_id=os.environ.get("GRAPH_CLIENT_ID", ""),
            tenant_id=os.environ.get("GRAPH_TENANT_ID", "common"),
            limit=limit,
        )

    # --- auth ------------------------------------------------------------

    def _acquire_token(self) -> str:
        """Get an access token, reusing the on-disk cache when possible."""
        try:
            import msal
        except ImportError as exc:  # pragma: no cover - dependency hint
            raise GraphAuthError(
                "The 'msal' package is required for live Outlook. "
                "Run: pip install msal requests"
            ) from exc

        cache = msal.SerializableTokenCache()
        if os.path.exists(_TOKEN_CACHE):
            cache.deserialize(Path(_TOKEN_CACHE).read_text())

        app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=cache,
        )

        result = None
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])

        if not result:
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise GraphAuthError(f"Could not start device flow: {flow.get('error_description')}")
            # flow["message"] tells the user where to go and what code to enter.
            print(flow["message"], flush=True)
            result = app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise GraphAuthError(
                f"Sign-in failed: {result.get('error_description', result)}"
            )

        if cache.has_state_changed:
            path = Path(_TOKEN_CACHE)
            path.write_text(cache.serialize())
            os.chmod(path, 0o600)  # token cache is sensitive — owner-only

        return result["access_token"]

    # --- read-only HTTP --------------------------------------------------

    def _get(self, path: str, **params) -> dict:
        """The only HTTP method this class uses. Hard-coded to GET."""
        import requests

        if self._token is None:
            self._token = self._acquire_token()

        resp = requests.get(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # --- fetch -----------------------------------------------------------

    def fetch(self) -> list[Email]:
        # Docs: https://learn.microsoft.com/graph/api/user-list-messages
        data = self._get(
            "/me/messages",
            **{
                "$top": self.limit,
                "$select": "id,subject,from,receivedDateTime,bodyPreview",
                "$orderby": "receivedDateTime desc",
            },
        )

        emails: list[Email] = []
        for m in data.get("value", []):
            sender = m.get("from", {}).get("emailAddress", {})
            emails.append(
                Email(
                    id=m["id"],
                    from_name=sender.get("name", ""),
                    from_addr=sender.get("address", ""),
                    subject=m.get("subject", "") or "(no subject)",
                    received=m.get("receivedDateTime", ""),
                    body=m.get("bodyPreview", ""),
                )
            )
        return emails
