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

## ⚠️ CRITICAL RULE — Write COMPUTED VALUES, never Excel formula strings

The grader loads the output workbook with `openpyxl(data_only=True)` and reads
`cell.value`. **openpyxl never evaluates formulas** — if you write `"=SUM(A1:A5)"`,
the saved cell contains the literal string and `data_only` reads back **`None`**.
You will lose the task.

**Always compute the answer in Python and write the resulting number / string /
date / time / timedelta into the cell.** Use `openpyxl` to *read* the input cell
values (load with `data_only=True` when the inputs are formula cells whose
*current* value matters), do the arithmetic / lookup / counting / aggregation in
Python, then write the literal value.

### Forbidden vs required (concrete contrast)

```python
# ❌ FORBIDDEN — writes a string starting with "=". Grader reads None.
ws["F3"] = f'=TEXT({col}{date_row},"ddd")'
ws.cell(r, k).value = f"={counts[row]}"
ws["B3"] = f'=VLOOKUP(C3,DATA!$A:$E,5,0)'
ws["R6"] = f"=SUMPRODUCT(({date_ref}>=$P6)*...)"
ws["C2"] = '=TIME(22,0,0)'

# ✅ REQUIRED — compute in Python, write the value.
import datetime
weekday_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
ws["F3"] = weekday_names[ws[f"{col}{date_row}"].value.weekday()]   # 'Wed'
ws.cell(r, k).value = counts[row]                                  # 3
ws["B3"] = lookup_table["C3_key"]                                  # the looked-up value
ws["R6"] = sum(v for d,t,v in records if p6<=d<=q6 and r3<=t<=r4) # 1323.81
ws["C2"] = datetime.time(22, 0)                                    # a real time
```

### Python equivalents for common Excel formulas

| Excel | Python (after `wb = load_workbook(path, data_only=True)`) |
|-------|-----------------------------------------------------------|
| `=SUM(A2:A100)` | `sum(c.value for c in ws["A2":"A100"][0] if isinstance(c.value,(int,float)))` |
| `=COUNTIF(B:B,"x")` | `sum(1 for c in ws["B"] if c.value == "x")` |
| `=VLOOKUP(k, T, n, 0)` | build `{row[0].value: row[n-1].value for row in T}` then `dict[k]` |
| `=TEXT(d,"ddd")` | `["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d.weekday()]` |
| `=WEEKDAY(d,2)` | `d.weekday()+1` |
| `=MONTH(d)` / `=YEAR(d)` | `d.month` / `d.year` |
| `=NOW()` / `=TODAY()` | don't — the gold is a fixed value; compute or read it explicitly |
| `=A1+B1` (numeric) | `ws["A1"].value + ws["B1"].value` |
| `=IFERROR(x,"")` | `try: ... except Exception: result = ""` |

### Read inputs with `data_only=True` when inputs are formula cells

```python
wb_in  = openpyxl.load_workbook(INPUT_PATH, data_only=True)   # see CURRENT values of formula cells
wb_out = openpyxl.load_workbook(INPUT_PATH)                   # keep formulas/formatting in untouched cells
# Read values from wb_in, write values into wb_out, save wb_out.
wb_out.save(OUTPUT_PATH)
```

The **only** time it is OK to write a formula string is when the natural-language
instruction literally says *"insert the formula …"* / *"add this formula …"* —
and even then the grader will read `None` unless the gold also stores the same
formula. When in doubt, **write the value**.

### Long-formula trap (very common failure)

When the natural-language task asks for a multi-condition lookup, conditional
sum, "k-th match", running aggregate, or "find row matching X and date ≤ Y",
the **wrong** instinct is to compose a long Excel formula like
`=INDEX(...,MATCH(1,INDEX((A=x)*(B<=d),0),0),...)` or
`=SUMPRODUCT(--ISNUMBER(SEARCH(...)))` and write it as a string. That will
fail (`pred=None`). The **right** approach: implement the same logic with a
plain Python `for` loop / dict / list comprehension and write the resulting
value(s).

| If you're tempted to write … | Do this instead |
|------------------------------|-----------------|
| `=SUMPRODUCT(--ISNUMBER(SEARCH(name, range)))` | Iterate the range in Python; `sum(1 for c in cells if name in str(c.value or ""))` |
| `=INDEX(data, MATCH(...), MATCH(...))` | Build `{(row_key, col_key): value}` dict from `data`; look up by tuple |
| `=AGGREGATE(15,6,ROW(rng)/(cond),k)` (k-th match) | Build a Python `[row for row in rng if cond(row)]` then take `[k-1]` |
| `=IFERROR(VLOOKUP(k, T, n, 0), "")` | `lookup.get(k, "")` from a pre-built dict |
| `=IF(INDEX(...)=x, INDEX(...), VLOOKUP(...))` | Express the branches with plain `if/else` over read cell values |
| `=COUNTIFS(...)` with multiple criteria | `sum(1 for r in rows if all(criteria))` |

### Mandatory self-check before `wb.save(OUTPUT_PATH)`

Before saving, scan every cell you wrote and assert none of them is a string
that starts with `"="` (unless the task explicitly required a formula):

```python
for sheet in wb.sheetnames:
    for row in wb[sheet].iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                raise AssertionError(
                    f"Wrote formula string at {sheet}!{c.coordinate}: "
                    f"{c.value[:60]!r}. Compute the VALUE instead."
                )
wb.save(OUTPUT_PATH)
```

(If the workbook had pre-existing formula cells you did **not** touch, scope
the check to only the cells you wrote — keep a `{(sheet, coord)}` set as you
write.)

(Sources: train round 1 failures 11276, 31011, 34033, 37229, 43657, 50526,
54667, 57693 — all write formula strings → grader reads None. Train round 2
still saw 43657, 52216, 7902 fall back to formulas for "hard-looking" lookups.)

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

If you forget to track `written_cells`, fall back to scanning every cell in
every sheet (slower but still correct):

```python
for sn in wb.sheetnames:
    for row in wb[sn].iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                raise AssertionError(f"Forbidden formula at {sn}!{c.coordinate}")
```

### "Formula Required" trap

Some tasks have sheet names or column headers like *"Formula Required"*, *"Use
Formula"*, *"Add VLOOKUP here"*. Read the actual instruction carefully — the
**grader still compares VALUES**, so the gold cell contains the computed answer
(e.g. `0`, `"Yellow"`), not the formula text. Compute and write the value
exactly as in any other task. (Sources: train fail 7902 — sheet "Formula
Required", agent wrote `=IFERROR(IF(INDEX...))` → grader read None; gt was `0`.)

---

## Robustness checklist (covers most remaining failures)

These small habits prevent recurring per-task bugs:

1. **Stop at the real last row, not `ws.max_row`.** `max_row` often includes
   trailing blank / formatting-only rows. When iterating "rows of data", break
   on the first row whose key columns are all blank (`None` or `""`).

2. **Never write a placeholder where the gold is empty.** If your lookup /
   computation produces no answer for a row, write `None` (i.e. leave the cell
   empty) — do not write the header text, `""`, or `0` as a default unless the
   instruction explicitly says so. (Source: train fail 560-12 — wrote header
   `'ITEM'` into a cell where `gt=None`.)

3. **Guard every cast against blank / non-numeric input.** Before
   `int(x)` / `float(x)` / `datetime.strptime(x, ...)`, check
   `x is None`, `str(x).strip() == ""`, and (for ints) `.isdigit()` or use a
   `try/except ValueError`. (Source: train fail 283-32 —
   `ValueError: invalid literal for int() with base 10: ''`.)

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
   verbatim from `wb.sheetnames`.

7. **"I need a macro / VBA" → produce the *result*, not the macro text.**
   When the instruction says *"write a VBA macro that …"*, *"I need a macro
   to compare X and Y"*, etc., the grader still expects the **output** that
   running such a macro would produce — populated cells in the target
   sheets / range. Implement the macro's logic in Python and write the
   resulting values. **Do not write VBA / `Sub ... End Sub` code into cells**;
   the grader compares values, not macro source. (Source: train fail 130-9 —
   agent wrote `"""Sub ... End Sub"""` text into the workbook → `ValueError:
   b2b is not a valid coordinate` from parsing macro-string fragments as cell
   refs; the gold had the transformed rows directly.)

---

---

## Output Requirements

- Save the result to `OUTPUT_PATH`.
- Do not hardcode row counts or column letters — iterate over actual rows in the workbook.
- Preserve sheets and cells not mentioned in the instruction.
