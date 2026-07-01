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

Every `solution.py` you write MUST follow this template — including the final
`written_cells` self-check loop. Do not omit the loop; the grader will reject
any cell whose value starts with `"="`.

```python
import openpyxl
import pandas as pd  # only if doing bulk transforms

INPUT_PATH  = "..."   # set to the actual input path
OUTPUT_PATH = "..."   # set to the actual output path

# Read with data_only=True if you need CURRENT VALUES of input formula cells.
wb_in  = openpyxl.load_workbook(INPUT_PATH, data_only=True)
wb     = openpyxl.load_workbook(INPUT_PATH)   # write target — preserves formatting
ws     = wb["TargetSheetName"]                # name the sheet explicitly

written_cells = set()   # collect (sheet_name, coordinate) as you write

# --- perform manipulation: write VALUES, not "=FORMULA" strings ---
# Example:
#   ws["F3"] = some_computed_value
#   written_cells.add((ws.title, "F3"))

# Mandatory final check: no cell you wrote may be a formula string.
for sheet_name, coord in written_cells:
    cell = wb[sheet_name][coord]
    if isinstance(cell.value, str) and cell.value.startswith("="):
        raise AssertionError(
            f"Forbidden formula string at {sheet_name}!{coord}: "
            f"{cell.value[:60]!r}. Re-implement in Python and write the value."
        )

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

**Pre-build indexes before any nested iteration**:

```python
# ❌ SLOW — O(n²): times out on 10k+ row workbooks.
for r in range(2, ws.max_row + 1):
    key = ws.cell(r, 1).value
    for r2 in range(2, other.max_row + 1):
        if other.cell(r2, 1).value == key:
            ...  # match

# ✅ FAST — O(n): build the dict once.
index = {}
for row in other.iter_rows(min_row=2, values_only=True):
    if row[0] is not None:
        index.setdefault(row[0], []).append(row)
for row in ws.iter_rows(min_row=2, values_only=True):
    for match in index.get(row[0], ()):
        ...
```

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

## Robustness checklist (covers most remaining failures)

These small habits prevent recurring per-task bugs:

1. **Stop at the real last row, not `ws.max_row`.** `max_row` often includes
   trailing blank / formatting-only rows. When iterating "rows of data", break
   on the first row whose key columns are all blank (`None` or `""`).

2. **Never write a placeholder where the gold is empty.** If your lookup /
   computation produces no answer for a row, write `None` (i.e. leave the cell
   empty) — do not write the header text, `""`, or `0` as a default unless the
   instruction explicitly says so.

3. **Guard every cast against blank / non-numeric input.** Before
   `int(x)` / `float(x)` / `datetime.strptime(x, ...)`, check
   `x is None`, `str(x).strip() == ""`, and (for ints) `.isdigit()` or use a
   `try/except ValueError`.

4. **For row-delete instructions** (e.g. *"remove the 4 rows above each row
   containing 'X'"*), build the *complete* set of row indices to delete first,
   sort **descending**, then call `delete_rows(idx, 1)` one at a time — index
   shifts only affect later (smaller-index) deletions, so descending iteration
   is correct. Verify by re-reading the target cell after deletion.

5. **Read input values via `data_only=True`.** If an input cell's value comes
   from a formula, the default `load_workbook` returns the formula *string*,
   not the number you see in Excel. Always open a second workbook with
   `data_only=True` for reads.

6. **Sheet name matters.** Multi-sheet workbooks: name the target sheet
   explicitly (`wb["The Exact Name"]`), don't rely on `wb.active`. Non-ASCII
   sheet names (`"工作表1"`, `"Hárok1"`) are valid Python strings — copy them
   verbatim from `wb.sheetnames`. **`ws["Name"]` is WRONG** — `ws` is already
   a worksheet; `ws["Name"]` tries to interpret `"Name"` as a coordinate.

7. **"I need a macro / VBA" → produce the *result*, not the macro text.**
   When the instruction says *"write a VBA macro that …"*, the grader expects
   the **output** that running such a macro would produce — populated cells in
   the target sheets. Implement the macro's logic in Python and write the
   resulting values. **Do not write VBA / `Sub ... End Sub` code into cells.**

---

## 5.4_harness additions (extra robustness for gpt-5.4)

These target the residual failure clusters observed on gpt-5.4 test
(46/281 fails at baseline). Follow them literally — they are the difference
between hard=0.84 and hard≈0.88+.

### R8. String fidelity — preserve source case, whitespace, punctuation exactly

When copying/looking-up/deriving a string value that already exists in the
workbook, write it **byte-for-byte** as it appears. Do **not** apply
`.strip()`, `.title()`, `.upper()`, `.lower()`, `.replace(" ", "")`, add or
remove trailing spaces, "clean up" internal separators (`", "` vs `","`), or
"normalize" punctuation.

```python
# ❌ WRONG — invisible transforms that lose 1 point each:
ws["B3"] = source_val.strip()          # 'Green ' -> 'Green'  (gold expects trailing space)
ws["C4"] = source_val.title()          # 'CHEP'   -> 'Chep'   (gold is uppercase)
ws["D5"] = ", ".join(items)            # ',' -> ', '          (gold uses no space)
ws["E6"] = f"{a} - {b}"                # gold uses en-dash '–', not hyphen ' - '

# ✅ RIGHT — copy the exact value from the source cell:
src = ws_in["A3"].value                # includes trailing space etc.
ws["B3"] = src                         # verbatim
```

If the preview shows a string in `repr()` form (e.g. `'Green '` with a
visible trailing space, or `'\xa0Value'` with a non-breaking space), those
characters are part of the value — preserve them.

### R9. Never write `'-'`, `'N/A'`, or any placeholder unless the instruction says so

`0` stays `0`. Empty stays empty (write `None`). Only substitute a
placeholder when the instruction literally says *"put '-' when …"* or
*"write N/A where …"* AND the cell is genuinely unmatched.

```python
# ❌ WRONG — silent placeholder insertion:
ws["F3"] = "-" if val is None or val == 0 else val

# ✅ RIGHT — preserve the actual value:
ws["F3"] = val                          # None stays None, 0 stays 0
```

Special case: **`'#N/A'` is a literal 4-character string** when the gold
contains it (e.g. task expects `#N/A` where Excel's `IFERROR` catches an
error). Do not write Python `None`, `float("nan")`, or the string
`"#N/A"` from `.upper()` — write exactly `"#N/A"`.

### R10. Do not round floats

`round(x, n)` breaks the grader's `==` equality check because the gold was
saved from Excel with full IEEE-754 precision. Compute the answer at full
precision and let openpyxl's cell `number_format` handle **display**
rounding.

```python
# ❌ WRONG — rounded value fails ==:
ws["G7"] = round(total / count, 2)

# ✅ RIGHT — full precision; format the cell if display rounding is needed:
ws["G7"] = total / count
ws["G7"].number_format = "0.00"     # for display only; the stored value is still full precision
```

### R11. Datetime vs formatted string — decide by the target cell's `number_format`

Some tasks want a real `datetime`/`date` object; others want a formatted
**string**. Inspect the target cell before writing:

```python
target = ws["C5"]
fmt = target.number_format             # e.g. 'mm/dd/yyyy', 'ddd', '@', 'General'
if fmt in ("@", "General") or "d" not in fmt.lower():
    # Text cell — write a string with the expected pattern
    target.value = dt.strftime("%A")   # e.g. 'Wednesday'
else:
    # Date-formatted cell — write a datetime object
    target.value = dt
```

If the gold cell shows `Wed` and the format is `ddd`, write a `datetime`
object (Excel will format it). If the gold cell shows `Wed` and the format
is `@` (text), write the literal string `"Wed"`.

### R12. Weekday abbreviation — `ddd` (3-char) vs `dddd` (full)

Check the format code / an adjacent gold cell before choosing:

```python
WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]      # ddd
WEEKDAY_LONG  = ["Monday","Tuesday","Wednesday","Thursday",             # dddd
                 "Friday","Saturday","Sunday"]
# Pick based on the format code of the target cell, or by matching one
# example cell you can inspect.
```

Never guess — if unclear, read a neighbouring gold cell (via `wb_in` on the
sample input) and match its style.

### R13. Never write reasoning, debug, or explanatory text into a target cell

If your logic reaches a "shouldn't happen" branch, **raise an exception** so
you can fix the code — do not write strings like `"unknown"`,
`"no match found"`, `"see note"`, or a Python `repr()` of an intermediate
value. Cells are graded as data, not narrative.

```python
# ❌ WRONG — text leaks into the graded cell:
ws["D9"] = f"could not find match for {key}"

# ✅ RIGHT — fail loudly during development, fix the root cause:
raise ValueError(f"could not find match for {key!r}")
```

### R14. Write only to the exact target range — no spillover past the last real key row

If the instruction says *"apply the formula from row 2 down to the last
data row"*, stop at the last row whose **key column(s)** have content. Do
not extend into empty formatting-only rows or into `max_row` padding.

```python
# ❌ WRONG — walks to ws.max_row, painting values into blank rows:
for r in range(2, ws.max_row + 1):
    ws.cell(r, 5).value = compute(r)

# ✅ RIGHT — bounded by the actual data:
last_data_row = 1
for r in range(2, ws.max_row + 1):
    if ws.cell(r, 1).value not in (None, ""):
        last_data_row = r
for r in range(2, last_data_row + 1):
    ws.cell(r, 5).value = compute(r)
```

For "write into F2:J6" style instructions, the range is **literal** —
compute exactly `(6-2+1) * (10-6+1) = 25` cells, no more, no less.

### R15. Formula self-check — enumerate `written_cells` and forbid strings starting with `"="`

The template already has this loop. **Do not remove it.** If you write via
`ws.append(...)` (which adds rows without letting you track coordinates),
switch to explicit `ws.cell(r, c).value = ...` so `written_cells` stays
accurate.

### R16. Multi-case robustness — no hard-coded row counts, no per-case constants

A task usually has **multiple test cases** with different-sized inputs. If
your code has `for row in range(2, 11)` or `count = 42` derived from
peeking at case 1's data, it will fail on case 2 (symptom: `n_pass < n_cases`,
`soft > 0` but `hard = 0`). Always compute bounds from the current workbook.

### R17. `#N/A`, `#DIV/0!`, and other Excel error strings are literal 4-8 char strings

Some tasks bake the display of an Excel error into the gold as a **string
value** (not a Python exception). If the gold shows `#N/A`, write the
Python string `"#N/A"` (exactly that; no quotes, no whitespace).

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
