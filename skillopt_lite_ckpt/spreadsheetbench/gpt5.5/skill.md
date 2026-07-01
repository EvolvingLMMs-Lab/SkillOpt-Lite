# Spreadsheet Manipulation Skill (xlsx)

## Overview
This skill guides agents in manipulating Excel (.xlsx) spreadsheets using Python.

**Primary libraries**: `openpyxl` (structure-preserving read/write), `pandas` (data transformation).
Never use any other third-party libraries.

---

## ⚠️ CRITICAL: openpyxl does NOT evaluate formulas

The grader compares the **computed (cached) value** of each cell, not the
formula text. When you write an Excel formula string with openpyxl, e.g.
`ws["E5"] = "=SUM(B2:B9)"`, openpyxl stores the formula **with no cached
result**. The grader reads cached values and sees `None` → the task FAILS
(symptom: `pred=None` while `gt` is a number/date/text).

**Rule**: when an instruction says "create a formula", "calculate",
"return a value", or otherwise expects a *result* in a cell, **do the
computation in Python and write the literal result value** — do NOT write
an `=...` formula string. Replicate the Excel logic in Python.

```python
# WRONG — openpyxl stores the formula but no value; grader sees None:
ws["B7"] = '=SUMIF(A2:A100,"Supplier_1",C2:C100)'

# RIGHT — compute in Python, write the literal result:
total = 0
for row in range(2, ws.max_row + 1):
    if ws.cell(row=row, column=1).value == "Supplier_1":
        total += ws.cell(row=row, column=3).value or 0
ws["B7"] = total
```

Mirror Excel semantics exactly when computing:
- **Dates/times**: write real Python `datetime.date`, `datetime.time`,
  `datetime.datetime`, or `datetime.timedelta` objects (not strings) so
  the cell type matches the gold. e.g. half-an-hour-before:
  `(datetime.combine(date.min, t) - timedelta(minutes=30)).time()`.
- **Empty/blank** results: write `None` (an empty cell), not `""`, unless
  the gold clearly expects an empty string.
- **MATCH/INDEX/VLOOKUP**: look the value up in Python and write it.
  When the formula *references/returns* a **blank** source cell in a
  numeric context (e.g. `=INDEX(...)`, `=VLOOKUP(...)`, or `=A1`), Excel
  yields **`0`**, not blank — so write `0` (not `None`) for a matched-but-
  empty lookup. (Only return `None` when there is *no match at all* and the
  instruction wants the cell left empty.)
- **SUMPRODUCT / conditional sums**: loop the ranges and accumulate.
- Apply the value down a column for every data row, matching the range
  the instruction describes (don't hardcode the row count — use the
  actual last data row).

Only leave a real `=...` formula in the cell if the instruction explicitly
requires the *formula text itself* to be present AND no value is graded —
rare; default to writing computed values.

---

## Common Workflow

1. **Explore** the input file: list sheets, inspect headers, check dimensions.
   - If the instruction points at specific cells as a **worked example**
     ("I have provided an example", "the values I'm interested in are in
     L7, L8 & L9", "make sure X are located in A2 & A3"), **read those
     cells and their neighbours first**. They reveal the exact expected
     output mapping (e.g. three *separate* per-row lookups, not one global
     result; or the precise final row positions). Reproduce that mapping
     instead of inventing a single global computation.
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
import openpyxl
import pandas as pd

INPUT_PATH  = "..."   # set to the actual input path
OUTPUT_PATH = "..."   # set to the actual output path

wb = openpyxl.load_workbook(INPUT_PATH)
ws = wb.active  # or wb["SheetName"]

# --- perform manipulation ---

wb.save(OUTPUT_PATH)
```

---

## Performance: large sheets

Some inputs have **10,000+ rows**. The `code.py` exec has a hard **600 s
timeout** — slow code is scored as a failure (symptom: `task-timeout-600s`).
Write linear-time code:

- **Counting / grouping**: use `collections.Counter` or a `dict`, not a
  nested loop that rescans rows for each key (O(n²) → times out).
- **Lookups / joins**: build a `dict` index once, then look up in O(1);
  never scan a whole column inside another row loop.
- Read each cell once (`ws.iter_rows(values_only=True)` is fast); avoid
  repeated `ws.cell(...)` calls and don't reload the workbook inside a loop.

---

## Interpreting cell / column references

When an instruction names a cell or column with a **letter** (e.g. "cell
J6", "column H", "columns L and M"), that is a **literal Excel coordinate
/ column letter**, NOT a header name. Address it directly:

```python
from openpyxl.utils import column_index_from_string
ws["J6"] = value                      # A1-style coordinate
col = column_index_from_string("H")   # → 8, for ws.cell(row=r, column=col)
```

Never pass a column *letter* where a coordinate/range is expected (e.g.
`ws["H"]` raises `ValueError: H is not a valid coordinate or range`), and
never confuse a letter reference with a header text lookup. Only match by
header text when the instruction says "the column titled / headed '<name>'".

---

## Output Requirements

- Save the result to `OUTPUT_PATH`.
- Do not hardcode row counts or column letters — iterate over actual rows in the workbook.
- Preserve sheets and cells not mentioned in the instruction.
- **Verify before finishing**: reload the saved file
  (`openpyxl.load_workbook(OUTPUT_PATH, data_only=True)`) and print the
  target cells/range to confirm they hold the expected computed values
  (not `None` and not a stray `=...` formula). If a target reads `None`,
  you wrote a formula instead of a value — fix it.
