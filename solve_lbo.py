#!/usr/bin/env python3
"""
Demo CLI: solve the entry multiple/price for a target Sponsor IRR band.

    python3 solve_lbo.py                 # RPI shell, target IRR 20-25%
    python3 solve_lbo.py --low 0.18 --high 0.22

This runs the fast engine. For the Excel deliverable, feed the chosen entry
multiple into lbo_bot.excel_io.write_assumptions + recalc_with_libreoffice.
"""
import argparse

from lbo_bot import rpi_baseline, run, solve_entry_for_irr_band, irr_at_multiple


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--low", type=float, default=0.20, help="target IRR floor")
    ap.add_argument("--high", type=float, default=0.25, help="target IRR ceiling")
    args = ap.parse_args()

    deal = rpi_baseline()
    base = run(deal)
    print(f"=== {deal.company} ===")
    print(f"Base case @ {deal.entry_multiple:.1f}x entry: "
          f"IRR {base.irr:.1%}, MOIC {base.moic:.2f}x, "
          f"sponsor equity ${base.sponsor_equity_invested:,.0f}k\n")

    res = solve_entry_for_irr_band(deal, args.low, args.high)
    print(f"Target Sponsor IRR band: {args.low:.0%} - {args.high:.0%}")
    print(f"  Max entry to clear {args.low:.0%} IRR : "
          f"{res.entry_multiple_at_low_irr:.2f}x  "
          f"(EV ${res.entry_multiple_at_low_irr * deal.entry_ltm_ebitda:,.0f}k)")
    print(f"  Entry to reach    {args.high:.0%} IRR : "
          f"{res.entry_multiple_at_high_irr:.2f}x  "
          f"(EV ${res.entry_multiple_at_high_irr * deal.entry_ltm_ebitda:,.0f}k)")
    print(f"  Midpoint          {res.midpoint_multiple:.2f}x -> "
          f"IRR {res.midpoint_irr:.1%}, MOIC {res.midpoint_moic:.2f}x\n")

    print("Entry multiple -> IRR sweep:")
    for m in [6, 8, 10, 12, 14, 16]:
        print(f"  {m:>2}.0x : IRR {irr_at_multiple(deal, float(m)):.1%}")


if __name__ == "__main__":
    main()
