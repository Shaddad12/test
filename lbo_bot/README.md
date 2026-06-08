# LBO Bot — research-driven LBO solver

A working prototype of the bot we discussed: take the **RPI Consulting** pitch
model as a *shell*, swap in a researched company, and **goal-seek the entry
price** that lands Sponsor IRR in a target band.

## What it does today

- **Faithful engine** (`engine.py`) reproduces the workbook's LBO sheet exactly —
  Sponsor IRR **25.17%**, MOIC **3.07x**, levered-FCF stream tie out to the cell
  (`tests/test_regression.py`). It also matches the workbook's own IRR sensitivity
  table (8.0x entry → 34.8%).
- **Solver** (`solver.py`) back-solves the entry multiple for a target IRR band.
  IRR is monotonically decreasing in entry price (exit proceeds don't depend on
  what you pay), so a clean bisection nails the range — no scipy needed.
- **Hybrid Excel bridge** (`excel_io.py`) writes chosen assumptions into a copy
  of the real `.xlsx` and recalcs with LibreOffice, so the deliverable stays the
  formatted model an IC expects.

```
$ python3 solve_lbo.py
Base case @ 10.0x entry: IRR 25.2%, MOIC 3.07x, sponsor equity $23,786k
Target Sponsor IRR band: 20% - 25%
  Max entry to clear 20% IRR : 11.52x  (EV $52,877k)
  Entry to reach    25% IRR : 10.04x  (EV $46,093k)
```

## Architecture (the hybrid you chose)

```
Research  ──▶  Driver assumptions  ──▶  Fast Python engine  ──▶  Goal-seek solver
(EDGAR,        (growth %, margins,       (engine.py, ms/run,      (solver.py,
 comps,         capex %, leverage,        reproduces workbook)     entry mult → IRR)
 rates)         entry/exit multiples)                                    │
                                                                         ▼
                                              Write back to .xlsx + LibreOffice recalc
                                                     (excel_io.py)  → IC deliverable
```

The fast engine is the source of truth *for solving*; the workbook is the source
of truth *for the deliverable*. The regression test keeps them honest.

## Onboarding a new company

Copy `rpi_baseline()` in `shell.py` and replace the researched inputs:

| Input | Where it comes from |
|---|---|
| `ebitda`, `da`, `capex`, `nwc_change` (per year) | the driver layer / your research |
| `entry_ltm_ebitda`, `leveragable_ebitda` | LTM financials |
| `existing_debt`, `existing_cash` | balance sheet |
| `sofr_curve` | forward curve at pricing |
| `exit_multiple`, financing terms | comps + lender indications |

Everything else (sources & uses, debt schedule, returns) is computed.

## ⚠️ One thing to confirm before trusting the shell

The LBO sheet's D&A handling is **internally inconsistent**: rows 52/53 *add* a
positive D&A to EBITDA to get "EBIT" for 2026–2030, but the 2031 column pulls a
*negative* D&A from the DCF sheet, so the sign flips (`LBO!O52 = DCF!M21`). The
engine replicates this faithfully (`faithful_da=True`) so it ties to the
workbook — but it means D&A currently *reduces* levered FCF in years 1–5 instead
of providing a tax shield. Before this bot prices a new company, decide whether
that's intended. Set `faithful_da=False` on the `Deal` to use the
accounting-correct convention and compare the impact.

## Roadmap (not yet built)

- DCF reverse-solver (discount rate / exit multiple → target EV band).
- Research agent: EDGAR + comps pull → proposed drivers *with citations* for sign-off.
- Auto-populate the driver sheet (`Arcadia Financial Summary`) cells, not just LBO knobs.
- Football-field output combining LBO and DCF ranges.
```
