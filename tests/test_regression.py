"""
Regression test: the Python engine must reproduce the workbook's headline
outputs before we trust it on any new company.

Workbook truth (LBO sheet):  Sponsor IRR = 25.17%  (O138),  MOIC = 3.075x (O139).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lbo_bot import rpi_baseline, run, size_transaction  # noqa: E402

WB_IRR = 0.25173127055168154
WB_MOIC = 3.0748410147093295
WB_SPONSOR_EQUITY = 23785.626076151988
WB_ENTRY_EV = 45886.720991983304
WB_TERM_LOAN = 18354.68839679332


def test_sources_and_uses():
    s = size_transaction(rpi_baseline())
    assert abs(s["entry_ev"] - WB_ENTRY_EV) < 0.5
    assert abs(s["term_loan_initial"] - WB_TERM_LOAN) < 0.5
    assert abs(s["sponsor_equity"] - WB_SPONSOR_EQUITY) < 0.5


def test_returns_match_workbook():
    r = run(rpi_baseline())
    assert abs(r.irr - WB_IRR) < 0.002, f"IRR {r.irr:.4%} vs {WB_IRR:.4%}"
    assert abs(r.moic - WB_MOIC) < 0.01, f"MOIC {r.moic:.4f} vs {WB_MOIC:.4f}"


def test_debt_paid_down_by_exit():
    r = run(rpi_baseline())
    assert r.term_loan_balance[-1] < 1.0      # fully swept by 2031
    assert r.exit_net_debt < 0                 # net cash at exit


if __name__ == "__main__":
    r = run(rpi_baseline())
    print(f"IRR  = {r.irr:.4%}   (workbook {WB_IRR:.4%})")
    print(f"MOIC = {r.moic:.4f}x  (workbook {WB_MOIC:.4f}x)")
    print(f"Sponsor equity invested = {r.sponsor_equity_invested:,.1f}")
    print(f"Sponsor exit value      = {r.sponsor_exit_value:,.1f}")
    print(f"Term loan @ exit        = {r.term_loan_balance[-1]:,.1f}")
    print(f"Levered FCF             = {[round(x,1) for x in r.levered_fcf]}")
    test_sources_and_uses()
    test_returns_match_workbook()
    test_debt_paid_down_by_exit()
    print("\nAll regression checks passed.")
