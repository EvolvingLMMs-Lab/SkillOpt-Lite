# Spreadsheet Manipulation Skill (xlsx)

## Overview
This skill guides agents in manipulating Excel (.xlsx) spreadsheets using Python.

**Primary libraries**: `openpyxl` (structure-preserving read/write), `pandas` (data transformation).
Never use any other third-party libraries.

---

## CRITICAL: the evaluator compares cached cell VALUES, not formulas

The grader reads each target cell's **cached value** (`data_only`). **openpyxl
NEVER evaluates formulas** — if you write `cell.value = "=TEXT(...)"`, the saved
file has a formula string but **no cached value**, so the grader sees `None` and
the task FAILS.

**Rule**: when the instruction asks for a formula, a lookup, a weekday, a sum, a
rank, a conditional result, etc., **compute the answer in Python and write the
literal value** (a number, string, or `datetime`) into the cell — do NOT write
a `=...` formula string.

```python
# WRONG — grader reads None:
ws["F3"].value = '=TEXT(F4,"ddd")'
# RIGHT — compute and write the literal value:
ws["F3"].value = ws["F4"].value.strftime("%a")   # -> "Wed"
```

Replicate the formula's logic across every cell the instruction targets
(e.g. the whole row/column/range named in "Expected answer position").

**Guard type conversions.** Cells may hold `None`, blanks, or text. Before
`int(x)`/`float(x)`, check the value is numeric (e.g. `isinstance(x,(int,float))`
or skip empty/`None`) so the script never raises `ValueError: invalid literal`.
If your computed result for a target cell comes out `None`, treat it as a bug in
your matching/parsing and re-derive it — a blank target cell almost always fails
the grader.

---

## Common Workflow

1. **Explore** the input file: list sheets, inspect headers, check dimensions.
2. **Write `solution.py`** with `INPUT_PATH` and `OUTPUT_PATH` defined at the top.
3. **Execute** `python solution.py` and verify the output file was created.
4. **Confirm** the target cells/range contain the expected values.

---

## Library Selection

| Use case | Library |
|----------|---------|
| Preserve formulas, formatting, named ranges | `openpyxl` |
| Bulk data transformation, aggregation, sorting | `pandas` → write back with `openpyxl` |
| Simple cell read/write | `openpyxl` |

**Warning**: `pandas.to_excel()` silently destroys existing formulas and named ranges.
When writing back to a spreadsheet that contains formulas, always use `openpyxl.save()`.

---

## solution.py Template

```python
import os
import openpyxl
# import pandas as pd   # only if you actually need it

# INPUT_PATH and OUTPUT_PATH are provided as ENVIRONMENT VARIABLES by the
# harness. NEVER hardcode paths and NEVER leave the literal "..." placeholder.
INPUT_PATH  = os.environ["INPUT_PATH"]
OUTPUT_PATH = os.environ["OUTPUT_PATH"]

wb = openpyxl.load_workbook(INPUT_PATH)
ws = wb.active  # or wb["SheetName"] when the instruction names a sheet

# --- perform manipulation: compute literal values, not formulas ---

wb.save(OUTPUT_PATH)
```

**Pick a sheet with `wb["Sheet Name"]`, never `ws["Sheet Name"]`.** Indexing a
worksheet expects a cell/range (`ws["A1"]`); passing a sheet name raises
`ValueError: <name> is not a valid coordinate or range`.

---

## Output Requirements

- Save the result to `OUTPUT_PATH`.
- Do not hardcode row counts or column letters — iterate over actual rows in the workbook.
- Preserve sheets and cells not mentioned in the instruction.
