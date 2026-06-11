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
email_source.py   →   classifier.py        →   store.py     →   cli.py
graph_source.py       (Claude turns each        (SQLite:        (renders the
mcp_source.py          email into a              cache + deal    dashboard)
(where emails          validated Classification) memory)
 come from)
```

- `email_source.py` / `graph_source.py` / `mcp_source.py` — a
  provider-agnostic `Email` shape and three sources: `SampleEmailSource`
  (bundled inbox, zero setup), `GraphEmailSource` (live, **read-only**
  Microsoft 365 / Outlook via Graph), and `MCPExportSource` (read email an
  *agent* fetched through the Outlook MCP connector — see below).
- `classifier.py` — calls Claude with **structured outputs**, so each email
  comes back as a validated object (`needs_reply`, `priority`, `deal_name`,
  `deal_stage`, `suggested_action`, …) instead of free text.
- `store.py` — a SQLite store (standard library, no extra deps) that
  **remembers across runs**: classifications are cached so re-runs are instant
  and free, deals accumulate over time, and emails can be marked responded.
- `cli.py` — orchestrates and prints the dashboard.

## Persistence

The first run classifies each email and writes it to `tracker.db`. Every later
run reads the cached classification instead of calling Claude again, so only
genuinely new mail costs an API call. Deals persist in their own table and keep
their latest stage and last-activity date even when they're not in the current
batch — that's the "tracks all deals" memory.

## Live dashboard

A web dashboard with a **deal tracker** and an auto-updating **to-do list**
that stays current as new email arrives. It is **read-only** — a background
poller only *reads* mail, classifies anything new with Claude, and persists it;
the browser auto-refreshes every few seconds. Marking something done writes to
the local tracker DB, never to your mailbox.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
cd email_tracker
EMAIL_SOURCE=sample python app.py          # then open http://localhost:5000
# EMAIL_SOURCE=outlook → live read-only Microsoft Graph (needs GRAPH_CLIENT_ID)
```

Knobs (env vars): `EMAIL_SOURCE` (sample|outlook|mcp), `POLL_INTERVAL` (secs,
default 60), `PORT` (default 5000), `TRACKER_DB`, `EMAIL_LIMIT`.

The dashboard shows:
- **To-Do** — emails needing a reply (priority-sorted, with suggested action
  and deadline) plus personal to-dos you add. Check an email off to mark it
  responded; it drops from the list and its deal's "awaiting reply" count.
- **Deal Tracker** — every deal as a pipeline board grouped by stage, with
  email counts and a flag for deals awaiting your reply.

## Run the CLI

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # from console.anthropic.com
cd email_tracker

python cli.py                       # classify (cached) + show dashboard
python cli.py --mark-responded 1 6  # mark emails handled → drop off the queue
python cli.py --reset               # forget everything and start fresh
python cli.py --db /path/tracker.db # use a specific database file
```

## Agent-driven (MCP connector)

If you're running this inside an agent that has the **Outlook MCP connector**
(e.g. Claude Code), you don't need an Entra app at all. The agent does the
read-only fetch and hands the result to the classifier:

```
agent (outlook_email_search)  →  inbox_export.json  →  python cli.py --source mcp
```

The agent writes the connector's results as a JSON array of normalized emails
to `inbox_export.json` (the source tolerates connector key names like
`bodyPreview`/`receivedDateTime`), then:

```bash
python cli.py --source mcp                 # reads inbox_export.json
python cli.py --source mcp --export x.json  # or a specific file
```

`inbox_export.json` holds real mailbox content, so it's gitignored — never
commit it.

## Live Outlook (read-only)

The `outlook` source reads your real Microsoft 365 / Outlook inbox via
Microsoft Graph. **It can never send or edit your mailbox** — it requests only
the `Mail.Read` scope (enforced by Microsoft) and issues only HTTP GET. At
sign-in you'll see exactly one permission: *"Read your mail."*

One-time setup (free):

1. Register an app at [entra.microsoft.com](https://entra.microsoft.com) →
   **App registrations → New**. Under **Authentication → Advanced**, set
   *Allow public client flows* = **Yes**. Under **API permissions**, add
   **Microsoft Graph → Delegated → `Mail.Read`** (and nothing else).
2. Copy the **Application (client) ID**.
3. Run it — you'll get a code to enter at microsoft.com/devicelogin once; the
   token is then cached locally for later runs:

   ```bash
   export GRAPH_CLIENT_ID=<your-app-client-id>
   # export GRAPH_TENANT_ID=<tenant>   # optional, defaults to "common"
   python cli.py --source outlook --limit 25
   ```

## Taking it to production

This PoC has the classifier, persistence, and a live read-only Outlook source.
A full app would add:

1. **Continuous sync** — Outlook supports Graph webhooks/subscriptions, so an
   always-on server could react to new mail in near-real-time instead of being
   run by hand (the SQLite store would graduate to Postgres).
2. **A richer UI** — the terminal dashboard becomes a web view with a deals
   pipeline board.
