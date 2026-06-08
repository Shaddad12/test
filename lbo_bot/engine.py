"""
Faithful Python re-implementation of the RPI Consulting LBO model.

This mirrors the arithmetic on the `LBO` sheet of the pitch workbook cell-for-cell
so that, given the same inputs, it reproduces the workbook's headline outputs
(Sponsor IRR ~25.2%, MOIC ~3.07x). It is the *fast* engine in the hybrid setup:
the solver iterates against this in-memory, and the final, signed-off numbers are
written back into the live workbook and recalculated by LibreOffice (see excel_io.py).

The model has a circular reference (interest -> debt balance -> levered FCF ->
cash sweep -> interest). The workbook resolves it with Excel iterative calc; here
we resolve it with a fixed-point loop in `run()`.

NOTE ON A SHELL BUG: rows 52/53/63 of the LBO sheet add D&A back to EBITDA to
get "EBIT" for years 2026-2030 (the cell pulls a *positive* D&A figure), but the
2031 column pulls a negative D&A from the DCF sheet, so the sign flips. We
replicate this faithfully by default (`faithful_da=True`) so the engine ties to
the workbook. Set `faithful_da=False` to use the accounting-correct convention
(D&A always subtracted to reach EBIT). See README for why this matters before
trusting the bot on a new company.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List


@dataclass
class Financing:
    term_loan_x: float = 4.0              # turns of leveragable EBITDA (LBO!C18)
    term_loan_spread_bps: float = 650.0   # LBO!D18
    term_loan_fee_pct: float = 0.02       # LBO!E18
    term_loan_floor: float = 0.01         # LBO!J18
    mand_amort_pct: float = 0.01          # LBO!I18 (% of initial balance per year)
    revolver_capacity: float = 1000.0     # LBO!E21
    revolver_spread_bps: float = 400.0    # LBO!D17
    revolver_floor: float = 0.01          # LBO!J17
    commitment_fee: float = 0.005         # LBO!E23
    cash_interest: float = 0.01           # LBO!E9
    financing_fee_tenor: int = 7          # LBO!G18


@dataclass
class Deal:
    """Everything needed to price one LBO. Swap these to run a new company."""
    company: str

    # --- Entry / exit ---------------------------------------------------------
    entry_ltm_ebitda: float       # LBO!J5  (avg of 2025E & 2026E EBITDA)
    leveragable_ebitda: float     # LBO!E22 (= entry_ltm_ebitda in the shell)
    entry_multiple: float         # LBO!E6   <-- the solver's knob
    exit_multiple: float          # LBO!E7

    existing_debt: float          # refinanced at close (LBO!J8)
    existing_cash: float          # LBO!J9

    tax_rate: float = 0.21        # LBO!E8
    mgmt_roll: float = 0.20       # LBO!E11
    min_cash: float = 200.0       # LBO!E12
    gross_txn_fees: float = 2000.0  # LBO!E10 = this minus financing fees

    close_date: date = date(2026, 6, 30)
    hold_years: int = 5

    financing: Financing = field(default_factory=Financing)

    # --- Operating projection, close year .. exit year (the driver layer) ------
    # Each list runs from the close/stub year through the exit year (6 entries
    # for a mid-year close + 5-year hold).
    ebitda: List[float] = field(default_factory=list)
    da: List[float] = field(default_factory=list)       # signed as the sheet stores row 52
    capex: List[float] = field(default_factory=list)    # negative
    nwc_change: List[float] = field(default_factory=list)
    sofr_curve: List[float] = field(default_factory=list)

    faithful_da: bool = True

    @property
    def n_years(self) -> int:
        return len(self.ebitda)


@dataclass
class LBOResult:
    irr: float
    moic: float
    sponsor_equity_invested: float
    sponsor_exit_value: float
    entry_ev: float
    exit_ev: float
    exit_net_debt: float
    term_loan_initial: float
    levered_fcf: List[float]
    term_loan_balance: List[float]   # end-of-year
    cash_balance: List[float]


def _term_loan_rate(sofr: float, spread_bps: float, floor: float) -> float:
    # LBO!J98 etc:  MAX(floor, SOFR) + spread/10000
    return max(floor, sofr) + spread_bps / 10000.0


def size_transaction(deal: Deal):
    """Sources & uses (LBO rows 4-41). Returns key entry figures."""
    f = deal.financing
    term_loan_initial = f.term_loan_x * deal.leveragable_ebitda          # E27
    financing_fees = f.term_loan_fee_pct * term_loan_initial             # F18/F19
    txn_fees = deal.gross_txn_fees - financing_fees                      # E10

    entry_ev = deal.entry_multiple * deal.entry_ltm_ebitda               # J7
    purchase_equity = entry_ev - deal.existing_debt + deal.existing_cash  # J10

    uses_total = (purchase_equity + deal.existing_debt + txn_fees
                  + financing_fees + deal.min_cash)                       # E41
    total_sources = uses_total                                            # E33

    cash_on_bs = deal.existing_cash                                       # E28
    revolver_drawn = 0.0                                                  # E26 (C17=0 turns)
    total_equity = total_sources - revolver_drawn - cash_on_bs - term_loan_initial  # E31
    sponsor_equity = total_equity * (1 - deal.mgmt_roll)                  # E29

    return dict(term_loan_initial=term_loan_initial, financing_fees=financing_fees,
                txn_fees=txn_fees, entry_ev=entry_ev, purchase_equity=purchase_equity,
                total_equity=total_equity, sponsor_equity=sponsor_equity)


def _xirr_two_flows(invested: float, proceeds: float, close: date,
                    exit_date: date) -> float:
    """Actual/365 annualized return for a single in/out pair (matches XIRR)."""
    years = (exit_date - close).days / 365.0
    return (proceeds / invested) ** (1.0 / years) - 1.0


def run(deal: Deal, max_iter: int = 200, tol: float = 1e-9) -> LBOResult:
    s = size_transaction(deal)
    f = deal.financing
    n = deal.n_years
    tl0 = s["term_loan_initial"]
    fin_fee_amort = s["financing_fees"] / f.financing_fee_tenor          # H19 / row 57

    # Stub: first and last projection years are half-years (LBO!J68 & O68 * 0.5).
    stub = [1.0] * n
    stub[0] = 0.5
    stub[-1] = 0.5

    mand_amort_amt = f.mand_amort_pct * tl0

    # Fixed-point loop over the circular interest <-> debt <-> FCF <-> cash chain.
    net_interest = [0.0] * n
    tl_end = [0.0] * n
    cash = [0.0] * n
    lfcf = [0.0] * n

    for _ in range(max_iter):
        prev = list(net_interest)

        tl_begin = [0.0] * n
        tl_mand = [0.0] * n
        tl_opt = [0.0] * n
        for t in range(n):
            tl_begin[t] = tl0 if t == 0 else tl_end[t - 1]
            tl_mand[t] = -min(mand_amort_amt, tl_begin[t])               # row 94

        # --- Levered FCF (rows 53-68) using current interest estimate ---------
        for t in range(n):
            ebit = deal.ebitda[t] + (deal.da[t] if deal.faithful_da
                                     else -abs(deal.da[t]))               # row 53
            ebt = ebit - net_interest[t] - fin_fee_amort                 # row 58
            tax = min(0.0, -ebt * deal.tax_rate)                         # row 60
            ni = ebt + tax                                               # row 61
            da_addback = -(deal.da[t] if deal.faithful_da
                           else -abs(deal.da[t]))                        # row 63
            pre = (ni + da_addback + fin_fee_amort + deal.capex[t]
                   + deal.nwc_change[t] + tl_mand[t])                    # rows 63-67
            lfcf[t] = pre * stub[t]                                      # row 68

        # --- Debt schedule sweep (rows 91-96) ---------------------------------
        for t in range(n):
            avail = lfcf[t]                                              # row 91 (revolver=0)
            remaining_after_mand = tl_begin[t] + tl_mand[t]             # SUM(begin, mand)
            tl_opt[t] = -min(remaining_after_mand, avail)               # row 95 (sweep=1)
            tl_end[t] = tl_begin[t] + tl_mand[t] + tl_opt[t]            # row 96

        # --- Cash (row 110) and net interest (rows 99-105) --------------------
        for t in range(n):
            net_cf = lfcf[t] + tl_opt[t]                                 # row 70 (revolver 0)
            cash[t] = (deal.min_cash if t == 0 else cash[t - 1]) + net_cf
        # cash[0] starts from min_cash (I110) then adds J70:
        running = deal.min_cash
        for t in range(n):
            running += lfcf[t] + tl_opt[t]
            cash[t] = running

        for t in range(n):
            tl_rate = _term_loan_rate(deal.sofr_curve[t], f.term_loan_spread_bps,
                                      f.term_loan_floor)
            tl_int = (tl_begin[t] + tl_end[t]) / 2 * tl_rate            # row 99
            prev_cash = deal.min_cash if t == 0 else cash[t - 1]
            cash_int = -(prev_cash + cash[t]) / 2 * f.cash_interest     # row 102
            revolver_line = f.revolver_capacity * f.commitment_fee      # row 103 (undrawn)
            net_interest[t] = cash_int + revolver_line + tl_int         # row 105

        if max(abs(a - b) for a, b in zip(net_interest, prev)) < tol:
            break

    # --- Returns (rows 122-139) -----------------------------------------------
    exit_ltm_ebitda = (deal.ebitda[-2] + deal.ebitda[-1]) / 2           # O123
    exit_ev = deal.exit_multiple * exit_ltm_ebitda                      # O125
    exit_net_debt = tl_end[-1] + 0.0 - cash[-1]                         # O113 (revolver 0)
    exit_equity = exit_ev - exit_net_debt                              # O127
    sponsor_exit = exit_equity * (1 - deal.mgmt_roll)                  # O129

    invested = s["sponsor_equity"]
    exit_date = date(deal.close_date.year + deal.hold_years,
                     deal.close_date.month, deal.close_date.day)
    irr = _xirr_two_flows(invested, sponsor_exit, deal.close_date, exit_date)
    moic = sponsor_exit / invested

    return LBOResult(irr=irr, moic=moic, sponsor_equity_invested=invested,
                     sponsor_exit_value=sponsor_exit, entry_ev=s["entry_ev"],
                     exit_ev=exit_ev, exit_net_debt=exit_net_debt,
                     term_loan_initial=tl0, levered_fcf=lfcf,
                     term_loan_balance=tl_end, cash_balance=cash)
