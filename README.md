# test

## LBO Bot

A research-driven LBO solver built on the RPI Consulting pitch model as a shell.
It reproduces the workbook's returns exactly, then goal-seeks the entry price for
a target Sponsor IRR band. See [`lbo_bot/README.md`](lbo_bot/README.md).

```bash
python3 solve_lbo.py            # solve entry multiple for 20-25% IRR
python3 tests/test_regression.py  # verify the engine ties to the workbook
```
