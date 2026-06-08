"""
The RPI Consulting deal, extracted from the pitch workbook, used as the shell.

To run a new company, copy `rpi_baseline()` and replace:
  * the operating projection lists (ebitda/da/capex/nwc/sofr) -> from research,
  * entry_ltm_ebitda / leveragable_ebitda / existing_debt / existing_cash,
  * entry_multiple / exit_multiple and any financing terms.

These are the only "knobs"; everything else is computed by engine.py.
"""
from __future__ import annotations

from datetime import date

from .engine import Deal, Financing


def rpi_baseline() -> Deal:
    """Reproduces the workbook's base case (IRR ~25.2%, MOIC ~3.07x)."""
    return Deal(
        company="RPI Consulting",
        entry_ltm_ebitda=4588.67209919833,
        leveragable_ebitda=4588.67209919833,
        entry_multiple=10.0,
        exit_multiple=11.5,
        existing_debt=3181.4522100000004,
        existing_cash=944.6689099999999,
        tax_rate=0.21,
        mgmt_roll=0.20,
        min_cash=200.0,
        gross_txn_fees=2000.0,
        close_date=date(2026, 6, 30),
        hold_years=5,
        financing=Financing(
            term_loan_x=4.0,
            term_loan_spread_bps=650.0,
            term_loan_fee_pct=0.02,
            term_loan_floor=0.01,
            mand_amort_pct=0.01,
            revolver_capacity=1000.0,
            revolver_spread_bps=400.0,
            commitment_fee=0.005,
            cash_interest=0.01,
            financing_fee_tenor=7,
        ),
        # Operating projection: 2026E (stub) .. 2031E. Pulled from the LBO sheet
        # rows 49/52/65/66 and the SOFR curve at row 75.
        ebitda=[5700.670683305118, 6079.088640470368, 6358.453477017468,
                6807.147128505877, 7344.2100021545975, 8085.383573444227],
        da=[310.5401106813793, 349.04115342082247, 388.54627343826206,
            429.85939177527604, 473.2405614941431, -473.2405614941431],
        capex=[-310.5401106813793, -349.04115342082247, -388.54627343826206,
               -429.85939177527604, -473.2405614941431, -520.9997346303718],
        nwc_change=[-94.82812427518274, -35.86334931042575, 24.207023148813278,
                    81.90176949037595, 142.9379795048917, 157.363200558141],
        sofr_curve=[0.0377, 0.0312, 0.0322, 0.0337, 0.0352, 0.037],
    )
