"""The classifier: turns a raw email into a structured triage decision.

Uses Claude with structured outputs so every email comes back as a validated
`Classification` object — no fragile string parsing.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from email_source import Email

MODEL = "claude-opus-4-8"


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Category(str, Enum):
    deal = "deal"            # anything tied to an active or potential deal
    investor = "investor"    # LPs / fundraising
    internal = "internal"    # colleagues, scheduling, ops
    vendor = "vendor"        # billing, services, automated notices
    spam = "spam"
    other = "other"


class DealStage(str, Enum):
    sourcing = "sourcing"
    diligence = "diligence"
    negotiation = "negotiation"
    closing = "closing"
    closed = "closed"
    passed = "passed"


class Classification(BaseModel):
    needs_reply: bool = Field(description="True if this email requires a response from the user.")
    priority: Priority
    category: Category
    is_deal_related: bool = Field(description="True if this relates to a specific deal or investment.")
    deal_name: Optional[str] = Field(
        default=None,
        description="Short name of the company/deal if this is deal-related, else null.",
    )
    deal_stage: Optional[DealStage] = Field(
        default=None,
        description="Best guess at the current stage of the deal, if deal-related.",
    )
    deadline: Optional[str] = Field(
        default=None,
        description="Any explicit or implied deadline mentioned (e.g. 'EOD today'), else null.",
    )
    summary: str = Field(description="One-sentence summary of what the email is about.")
    suggested_action: str = Field(description="The concrete next action the user should take.")


SYSTEM_PROMPT = (
    "You are an executive assistant triaging the inbox of a venture/private "
    "capital investor. For each email, decide whether it needs a reply, how "
    "urgent it is, and whether it relates to a deal. Be decisive: automated "
    "notices, newsletters, and obvious spam do not need replies. A real person "
    "asking a question, requesting a meeting, or awaiting documents does. When "
    "an email concerns a specific company or investment, extract the deal name "
    "and infer its stage from context."
)


def classify_email(client: anthropic.Anthropic, email: Email) -> Classification:
    """Classify a single email and return a validated Classification."""
    content = (
        f"From: {email.from_name} <{email.from_addr}>\n"
        f"Subject: {email.subject}\n"
        f"Received: {email.received}\n\n"
        f"{email.body}"
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_format=Classification,
    )
    return response.parsed_output
