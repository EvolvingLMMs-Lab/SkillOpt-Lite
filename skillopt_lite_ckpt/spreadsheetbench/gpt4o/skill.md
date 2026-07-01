# Spreadsheet Manipulation Skill (xlsx)

## Overview
This skill guides agents in manipulating Excel (.xlsx) spreadsheets using Python.

**Primary libraries**: `openpyxl` (structure-preserving read/write), `pandas` (data transformation).
Never use any other third-party libraries.

---

## Common Workflow

1. **Explore** the input file: list sheets, inspect headers, check dimensions.
2. **Write `solution.py`** that reads `INPUT_PATH` and writes `OUTPUT_PATH`.
   These two variables are **already defined** by the runtime — use them
   directly. **Never reassign them** (do not write `INPUT_PATH = "..."`); that
   overwrites the real path and the script reads/writes the wrong file.
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

## Write COMPUTED VALUES, never formula strings

The grader reads the **computed value** of each target cell. `openpyxl` does
**not** evaluate formulas, so if you write a formula string the saved value is
`None` and the answer is wrong.

- ❌ `ws["B26"] = "=SUMIFS(K2:K100, C2:C100, ...)"`  → cell value reads as `None`.
- ✅ Read the source cells, do the arithmetic / lookup / date logic **in
  Python**, then write the literal result: `ws["B26"] = 1323.82`.

This applies even when the instruction *mentions* an Excel formula (e.g. "my
formula is SUMIFS(...)"): reproduce its logic in Python and write the resulting
number, string, date, or time value — not the `=...` text.

## Reading input cells that already contain formulas

A normal `load_workbook` returns a formula cell's **text** (`'=A1+B1'`), not its
value, so arithmetic on it gives wrong results. When you need the computed value
of an input formula cell, open a second copy with `data_only=True` and read from
it, but keep editing/saving the original workbook (which still has the formulas):

```python
wb   = openpyxl.load_workbook(INPUT_PATH)                  # edit + save this one
vals = openpyxl.load_workbook(INPUT_PATH, data_only=True)  # read computed values here
n = vals["Sheet1"]["B5"].value                             # numeric value, not '=...'
```

```python
# Example: SUMIFS over a date window, computed in Python
total = 0
for r in range(2, ws.max_row + 1):
    d = ws.cell(row=r, column=3).value          # date in column C
    if d is not None and start <= d <= end:
        v = ws.cell(row=r, column=11).value     # value in column K
        total += v or 0
ws["B26"] = total                                # literal value, not a formula
```

## Match the gold exactly

- Preserve the source value's **type** (number stays a number, date stays a
  `datetime`/`time`, text stays text) — don't stringify numbers.
- Preserve **casing and spacing** of copied text exactly (`'Match'` ≠ `'MATCH'`).
- Only write the cells the instruction asks for; leave every other cell
  untouched (don't add stray headers or labels).

---

## solution.py Template

```python
import openpyxl
import pandas as pd

# INPUT_PATH and OUTPUT_PATH are already defined by the runtime — do NOT reassign them.
wb = openpyxl.load_workbook(INPUT_PATH)
ws = wb.active  # or wb["SheetName"] for a specific sheet named in the instruction

# --- perform manipulation (compute values in Python; write literal results) ---

wb.save(OUTPUT_PATH)
```

---

## Output Requirements

- Save the result to `OUTPUT_PATH`.
- Do not hardcode row counts or column letters — iterate over actual rows in the workbook.
- Preserve sheets and cells not mentioned in the instruction.
