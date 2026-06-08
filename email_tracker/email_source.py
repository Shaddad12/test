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


# --- Microsoft 365 / Outlook ---------------------------------------------
# The live, read-only Graph source lives in `graph_source.py` (kept separate so
# its OAuth dependencies — msal, requests — stay optional). cli.py imports it
# lazily when you pass `--source outlook`. It requests ONLY the `Mail.Read`
# scope and issues only HTTP GET, so it cannot send or edit your mailbox.
