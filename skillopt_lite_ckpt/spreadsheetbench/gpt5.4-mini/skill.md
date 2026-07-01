# Spreadsheet Manipulation Skill (xlsx)

## Overview
This skill guides agents in manipulating Excel (.xlsx) spreadsheets using Python.

**Primary libraries**: `openpyxl` (structure-preserving read/write), `pandas` (data transformation).
Never use any other third-party libraries.

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

## ⚠️ CRITICAL: Write computed VALUES, not Excel formulas

The grader reads each target cell's **stored value** (as if opened with
`data_only=True`). `openpyxl` **does not evaluate formulas** — when you write a
formula string like `=VLOOKUP(...)`, `=SUMPRODUCT(...)`, `=IF(...)`,
`=SUM(...)`, the saved cell has **no cached result**, so grading reads it as
`None` and the task FAILS.

**Rule**: Even when the instruction says "use a formula", compute the actual
result in Python and write the **literal value** into the cell. Do the lookup /
sum / condition logic yourself with `openpyxl` (or `pandas`) and assign the
plain number / string / date.

```python
# WRONG — cell reads as None during grading (openpyxl never computes it):
ws["E5"] = f'=IFERROR(VLOOKUP(E4,$A$5:$B${last_row},2,FALSE),"")'

# RIGHT — compute in Python, write the literal value:
lookup = {ws[f"A{r}"].value: ws[f"B{r}"].value for r in range(5, last_row + 1)}
ws["E5"] = lookup.get(ws["E4"].value, "")
```

This applies to ALL spreadsheet functions: SUM/AVERAGE/COUNT/COUNTIF →
`sum(...)` / `len([...])`; VLOOKUP/INDEX/MATCH → build a dict and look up;
IF/IFS → Python `if`/conditional; SUMPRODUCT → iterate and accumulate.
Replicate Excel rounding/format only if the instruction demands it.

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

## Verify Before Finishing

After saving, **reload the output and check the target cells** before you
declare success. Catch the `None` trap and off-by-one errors here, then fix
`solution.py` and re-run.

```python
chk = openpyxl.load_workbook(OUTPUT_PATH, data_only=True)
print(chk["SheetName"]["E5"].value)   # must NOT be None if a value is expected
```

If a target cell is `None` when the instruction expects a value, you almost
certainly wrote a formula — switch to computing the literal value.

---

## Output Requirements

- Save the result to `OUTPUT_PATH`.
- Write computed **literal values**, never Excel formula strings (see CRITICAL
  section above) — formulas grade as `None`.
- Do not hardcode row counts or column letters — iterate over actual rows in the workbook.
- Use exact cell coordinates (e.g. `ws["B2"]`); never pass invalid refs like
  `"b2b"`. Build column letters with `openpyxl.utils.get_column_letter`.
- Preserve sheets and cells not mentioned in the instruction.
- Write to the sheet named in the instruction (`wb["<name>"]`), not always `wb.active`.
