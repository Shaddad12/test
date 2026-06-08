"""Proof-of-concept CLI: classify the inbox and print a triage dashboard.

Classifications are cached in a local SQLite database (see store.py), so
re-runs are instant and free for emails already seen, deals accumulate across
runs, and you can mark emails as responded.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python cli.py                          # classify (cached) + show dashboard
    python cli.py --mark-responded 1 6     # mark emails as handled
    python cli.py --reset                  # forget everything and start over
    python cli.py --db /path/to/tracker.db # use a specific database file
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import anthropic

from classifier import Classification, Priority, classify_email
from email_source import Email, SampleEmailSource
from store import DEFAULT_DB, Store

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

    items.sort(key=lambda pair: PRIORITY_RANK[pair[1].priority])
    for email, c in items:
        color = PRIORITY_COLOR[c.priority]
        tag = f"{color}[{c.priority.value.upper()}]{RESET}"
        deal = f" {CYAN}· {c.deal_name}{RESET}" if c.deal_name else ""
        deadline = f"  {RED}⏰ {c.deadline}{RESET}" if c.deadline else ""
        print(f"\n  {tag} {BOLD}{email.subject}{RESET}{deal}{deadline}")
        print(f"       {DIM}id {email.id} · from {email.from_name} <{email.from_addr}>{RESET}")
        print(f"       {c.summary}")
        print(f"       {GREEN}→ {c.suggested_action}{RESET}")


def render_deals(store: Store) -> None:
    deals = store.get_deals()
    banner(f"💼  DEALS  ({len(deals)})")
    if not deals:
        print(f"{DIM}  No deal-related email detected yet.{RESET}")
        return

    for d in deals:
        stage = f" {DIM}({d['stage']}){RESET}" if d["stage"] else ""
        flag = f"  {RED}{d['awaiting']} awaiting reply{RESET}" if d["awaiting"] else ""
        count = f"{DIM}{d['email_count']} email(s){RESET}"
        print(f"\n  {BOLD}{d['name']}{RESET}{stage}{flag}")
        print(f"       {count} · {DIM}last activity {d['last_activity'][:10]}{RESET}")


def render_handled(no_reply: list[tuple[Email, Classification]], responded: int) -> None:
    banner(f"✓  HANDLED  ({len(no_reply) + responded})")
    if responded:
        print(f"  {GREEN}{responded} email(s) marked responded.{RESET}")
    for email, c in no_reply:
        print(f"  {DIM}· [{c.category.value}] {email.subject} — {c.summary}{RESET}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Classify the inbox and track deals.")
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite database file.")
    p.add_argument(
        "--source", choices=["sample", "outlook"], default="sample",
        help="Where to read email from. 'outlook' is live, read-only Microsoft "
             "Graph (needs GRAPH_CLIENT_ID; see graph_source.py).",
    )
    p.add_argument(
        "--limit", type=int, default=25,
        help="Max emails to fetch from a live source (default 25).",
    )
    p.add_argument(
        "--mark-responded", nargs="+", metavar="ID", default=[],
        help="Mark one or more email IDs as responded, then show the dashboard.",
    )
    p.add_argument("--reset", action="store_true", help="Erase all stored data.")
    return p


def load_source(args):
    """Build the chosen email source. Outlook deps load only when requested."""
    if args.source == "outlook":
        from graph_source import GraphAuthError, GraphEmailSource

        try:
            return GraphEmailSource.from_env(limit=args.limit)
        except GraphAuthError as exc:
            print(f"{RED}{exc}{RESET}")
            return None
    return SampleEmailSource()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(args.db)

    if args.reset:
        store.reset()
        print(f"{DIM}Store reset — all emails and deals forgotten.{RESET}")

    for email_id in args.mark_responded:
        ok = store.mark_responded(email_id)
        status = f"{GREEN}marked responded{RESET}" if ok else f"{RED}not found{RESET}"
        print(f"{DIM}  email {email_id}: {status}{RESET}")

    source = load_source(args)
    if source is None:
        return 1

    try:
        client = anthropic.Anthropic()
    except Exception as exc:  # missing key, etc.
        print(f"{RED}Could not initialize Anthropic client: {exc}{RESET}")
        print("Set ANTHROPIC_API_KEY in your environment and try again.")
        return 1

    print(f"{DIM}Reading email from: {BOLD}{args.source}{RESET}")
    try:
        emails = source.fetch()
    except Exception as exc:
        print(f"{RED}Failed to fetch email: {exc}{RESET}")
        return 1

    results: list[tuple[Email, Classification, bool]] = []
    new_count = 0
    for email in emails:
        cached = store.get_email(email.id)
        if cached is not None:
            c = Classification.model_validate_json(cached["classification"])
            responded = bool(cached["responded"])
        else:
            print(f"{DIM}  classifying: {email.subject[:50]}...{RESET}")
            try:
                c = classify_email(client, email)
            except anthropic.APIError as exc:
                print(f"{RED}  ! API error on '{email.subject}': {exc}{RESET}")
                continue
            store.save_email(email, c)
            if c.is_deal_related and c.deal_name:
                store.upsert_deal(c.deal_name, c.deal_stage and c.deal_stage.value, email.received)
            responded = False
            new_count += 1
        results.append((email, c, responded))

    cached_count = len(results) - new_count
    print(
        f"{DIM}Processed {len(results)} emails "
        f"({new_count} newly classified, {cached_count} from cache).{RESET}"
    )

    to_respond = [(e, c) for e, c, resp in results if c.needs_reply and not resp]
    handled_resp = sum(1 for _, c, resp in results if c.needs_reply and resp)
    no_reply = [(e, c) for e, c, resp in results if not c.needs_reply]

    render_to_respond(to_respond)
    render_deals(store)
    render_handled(no_reply, handled_resp)
    print()

    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
