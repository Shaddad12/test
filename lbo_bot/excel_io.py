"""
Hybrid bridge: push solved assumptions into the live workbook and recalc.

The fast engine (engine.py) is used for solving. Once an assumption set is
chosen, write it into a copy of the real .xlsx and recalc with LibreOffice so the
deliverable is the actual formatted model the IC expects — not a Python summary.

Cell map below targets the LBO sheet knobs. Extend `KNOB_CELLS` to drive the
operating layer ('Arcadia Financial Summary') for a full company swap.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import openpyxl

# Knob name -> (sheet, cell). The solver's primary knob is the entry multiple.
KNOB_CELLS = {
    "entry_multiple": ("LBO", "E6"),
    "exit_multiple": ("LBO", "E7"),
    "tax_rate": ("LBO", "E8"),
    "mgmt_roll": ("LBO", "E11"),
    "term_loan_x": ("LBO", "C18"),
}

# Output name -> (sheet, cell), read back after recalc.
OUTPUT_CELLS = {
    "irr": ("LBO", "O138"),
    "moic": ("LBO", "O139"),
    "entry_ev": ("LBO", "J7"),
    "dcf_ev_exit_method": ("DCF", "G47"),
}


def write_assumptions(src_xlsx: str, dst_xlsx: str, knobs: dict) -> None:
    """Copy the workbook and overwrite knob cells with solved values."""
    shutil.copyfile(src_xlsx, dst_xlsx)
    wb = openpyxl.load_workbook(dst_xlsx)
    for name, value in knobs.items():
        if name not in KNOB_CELLS:
            raise KeyError(f"Unknown knob {name!r}; add it to KNOB_CELLS.")
        sheet, cell = KNOB_CELLS[name]
        wb[sheet][cell] = value
    wb.save(dst_xlsx)


def recalc_with_libreoffice(xlsx_path: str, timeout: int = 180) -> None:
    """Headless recalc so written formulas resolve (incl. iterative/circular calc).

    Uses LibreOffice's macro-free recalc-on-load via a conversion round-trip.
    Requires `soffice` on PATH. The workbook must have iterative calculation
    enabled (Tools > Options > Calc > Calculate) for the circular interest ref.
    """
    path = Path(xlsx_path)
    subprocess.run(
        ["soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML",
         "--outdir", str(path.parent), str(path)],
        check=True, timeout=timeout,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def read_outputs(xlsx_path: str) -> dict:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    out = {}
    for name, (sheet, cell) in OUTPUT_CELLS.items():
        out[name] = wb[sheet][cell].value
    return out
