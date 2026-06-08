# Email Triage — Proof of Concept

A command-line proof of concept that reads a set of emails, classifies each one
with **Claude**, and prints a triage dashboard:

- **To Respond** — emails that need a reply, sorted by priority, with a
  suggested next action and any deadline.
- **Deals** — deal-related email grouped by company, with inferred stage.
- **No Reply Needed** — automated notices, spam, FYIs.

This is the smallest useful slice of the larger idea (continuously track an
inbox, flag what needs a response, and follow every deal). It runs against a
bundled **sample inbox** so you can see it work with zero setup, and it's
structured so the live **Microsoft 365 / Outlook** source drops in without
changing the rest of the pipeline.

## How it works

```
email_source.py   →   classifier.py        →   cli.py
(where emails         (Claude turns each        (renders the
 come from)            email into a              dashboard)
                       validated Classification)
```

- `email_source.py` — a provider-agnostic `Email` shape and sources.
  `SampleEmailSource` ships now; a `GraphEmailSource` for Outlook is stubbed
  with the exact Graph calls needed to go live.
- `classifier.py` — calls Claude with **structured outputs**, so each email
  comes back as a validated object (`needs_reply`, `priority`, `deal_name`,
  `deal_stage`, `suggested_action`, …) instead of free text.
- `cli.py` — orchestrates and prints the dashboard.

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # from console.anthropic.com
cd email_tracker
python cli.py
```

## Taking it to production

This PoC is the classifier only. A full app would add:

1. **Live inbox** — implement `GraphEmailSource` (see the stub in
   `email_source.py`) using Microsoft Graph + OAuth. Outlook supports webhooks
   so you can react to new mail in near-real-time.
2. **Storage** — persist classifications and a deals table (so the tracker
   has memory across runs).
3. **A server** — something always-on to poll/receive mail and run the
   classifier continuously.
4. **A richer UI** — the terminal dashboard becomes a web view with a deals
   pipeline board.
