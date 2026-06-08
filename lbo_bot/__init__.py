"""LBO bot: research-driven LBO solver built on the RPI Consulting shell model."""
from .engine import Deal, Financing, LBOResult, run, size_transaction
from .shell import rpi_baseline
from .solver import solve_entry_for_irr_band, irr_at_multiple, SolveResult

__all__ = [
    "Deal", "Financing", "LBOResult", "run", "size_transaction",
    "rpi_baseline", "solve_entry_for_irr_band", "irr_at_multiple", "SolveResult",
]
