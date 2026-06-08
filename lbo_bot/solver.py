"""
Goal-seek: solve the entry multiple so Sponsor IRR lands in a target band.

Higher entry multiple -> more purchase equity -> lower IRR (exit proceeds are
independent of entry price in this structure), so IRR is monotonically
decreasing in the entry multiple. We bracket and bisect (no scipy dependency).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Tuple

from .engine import Deal, run


@dataclass
class SolveResult:
    target_low: float
    target_high: float
    entry_multiple_at_low_irr: float   # priciest entry that still clears target_low
    entry_multiple_at_high_irr: float  # entry needed to reach target_high
    midpoint_multiple: float
    midpoint_irr: float
    midpoint_moic: float


def irr_at_multiple(deal: Deal, multiple: float) -> float:
    d = copy.deepcopy(deal)
    d.entry_multiple = multiple
    return run(d).irr


def _bisect(fn: Callable[[float], float], target: float,
            lo: float, hi: float, tol: float = 1e-5, max_iter: int = 100) -> float:
    """Solve fn(x) == target on [lo, hi] for a monotonically *decreasing* fn."""
    f_lo, f_hi = fn(lo) - target, fn(hi) - target
    if f_lo * f_hi > 0:
        raise ValueError(
            f"Target IRR {target:.1%} not bracketed on multiples [{lo}, {hi}] "
            f"(IRR ranges {fn(hi):.1%}..{fn(lo):.1%}). Widen the bracket.")
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = fn(mid) - target
        if abs(f_mid) < tol:
            return mid
        # decreasing fn: if fn(mid) > target, we can pay more -> move lo up
        if f_mid > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def solve_entry_for_irr_band(deal: Deal, target_low: float, target_high: float,
                             bracket: Tuple[float, float] = (4.0, 20.0)) -> SolveResult:
    """Find the entry-multiple range that puts Sponsor IRR in [low, high]."""
    fn = lambda m: irr_at_multiple(deal, m)
    lo, hi = bracket
    # IRR decreases with multiple, so target_high -> lower multiple, target_low -> higher.
    mult_at_high = _bisect(fn, target_high, lo, hi)
    mult_at_low = _bisect(fn, target_low, lo, hi)
    mid_mult = (mult_at_high + mult_at_low) / 2
    mid = run(_with_multiple(deal, mid_mult))
    return SolveResult(
        target_low=target_low, target_high=target_high,
        entry_multiple_at_low_irr=mult_at_low,
        entry_multiple_at_high_irr=mult_at_high,
        midpoint_multiple=mid_mult, midpoint_irr=mid.irr, midpoint_moic=mid.moic)


def _with_multiple(deal: Deal, m: float) -> Deal:
    d = copy.deepcopy(deal)
    d.entry_multiple = m
    return d
