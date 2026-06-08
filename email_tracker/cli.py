"""Proof-of-concept CLI: classify the inbox and print a triage dashboard.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python cli.py
"""

from __future__ import annotations

import sys
from collections import defaultdict

import anthropic

from classifier import Classification, Priority, classify_email
from email_source import Email, SampleEmailSource

# ANSI colors — degrade gracefully if the terminal doesn't support them.
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN = "\033[36m"

PRIORITY_COLOR = {Priority.high: RED, Priority.medium: YELLOW, Priority.low: DIM}
PRIORITY_RANK = {Priority.high: 0, Priority.medium: 1, Priority.low: 2}


def banner(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'━' * 70}{RESET}")
    print(f"{BOLD}{CYAN} {text}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 70}{RESET}")


def render_to_respond(items: list[tuple[Email, Classification]]) -> None:
    banner(f"📨  TO RESPOND  ({len(items)})")
    if not items:
        print(f"{DIM}  Inbox zero — nothing needs a reply.{RESET}")
        return

    # Highest priority first.
    items.sort(key=lambda pair: PRIORITY_RANK[pair[1].priority])
    for email, c in items:
        color = PRIORITY_COLOR[c.priority]
        tag = f"{color}[{c.priority.value.upper()}]{RESET}"
        deal = f" {CYAN}· {c.deal_name}{RESET}" if c.deal_name else ""
        deadline = f"  {RED}⏰ {c.deadline}{RESET}" if c.deadline else ""
        print(f"\n  {tag} {BOLD}{email.subject}{RESET}{deal}{deadline}")
        print(f"       {DIM}from {email.from_name} <{email.from_addr}>{RESET}")
        print(f"       {c.summary}")
        print(f"       {GREEN}→ {c.suggested_action}{RESET}")


def render_no_reply(items: list[tuple[Email, Classification]]) -> None:
    banner(f"✓  NO REPLY NEEDED  ({len(items)})")
    for email, c in items:
        print(f"  {DIM}· [{c.category.value}] {email.subject} — {c.summary}{RESET}")


def render_deals(items: list[tuple[Email, Classification]]) -> None:
    deals: dict[str, list[tuple[Email, Classification]]] = defaultdict(list)
    for email, c in items:
        if c.is_deal_related and c.deal_name:
            deals[c.deal_name].append((email, c))

    banner(f"💼  DEALS  ({len(deals)})")
    if not deals:
        print(f"{DIM}  No deal-related email detected.{RESET}")
        return

    for name, pairs in sorted(deals.items()):
        stages = {c.deal_stage.value for _, c in pairs if c.deal_stage}
        stage = f" {DIM}({', '.join(sorted(stages))}){RESET}" if stages else ""
        needs = sum(1 for _, c in pairs if c.needs_reply)
        flag = f"  {RED}{needs} awaiting reply{RESET}" if needs else ""
        print(f"\n  {BOLD}{name}{RESET}{stage}{flag}")
        for email, c in pairs:
            print(f"       {DIM}· {c.summary}{RESET}")


def main() -> int:
    try:
        client = anthropic.Anthropic()
    except Exception as exc:  # missing key, etc.
        print(f"{RED}Could not initialize Anthropic client: {exc}{RESET}")
        print("Set ANTHROPIC_API_KEY in your environment and try again.")
        return 1

    emails = SampleEmailSource().fetch()
    print(f"{DIM}Classifying {len(emails)} emails with {BOLD}Claude{RESET}{DIM}...{RESET}")

    results: list[tuple[Email, Classification]] = []
    for i, email in enumerate(emails, 1):
        print(f"{DIM}  [{i}/{len(emails)}] {email.subject[:50]}...{RESET}")
        try:
            results.append((email, classify_email(client, email)))
        except anthropic.APIError as exc:
            print(f"{RED}  ! API error on '{email.subject}': {exc}{RESET}")

    to_respond = [r for r in results if r[1].needs_reply]
    no_reply = [r for r in results if not r[1].needs_reply]

    render_to_respond(to_respond)
    render_deals(results)
    render_no_reply(no_reply)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
