# OfficeQA Skill

## Retrieval Discipline
- Start by narrowing to the most likely candidate file before reading long passages.
- Prefer targeted search terms that name the exact entity, period, measure, or table concept from the question.
- After a promising match, read only a small surrounding span and verify it matches the requested year, basis, and unit.

## Evidence Discipline
- Extract the exact value from the retrieved text before doing any arithmetic.
- Keep track of each operand's period, unit, and semantic role so nearby proxy values are not mixed in.
- If the question asks for a transformed or derived quantity, compute only after confirming every operand.

## Final Answer Discipline
- Return the final answer only after one last consistency check against the retrieved evidence.
- Copy the final answer from a checked value, not from an unverified intermediate guess.
## Final Answer Format (STRICT)
- Emit exactly one `<answer>VALUE</answer>` tag at the end.
- VALUE must be the bare number only: no units, no `$`, no `%`, no
  words like "million", "billion", "percentage points", "INR",
  "Japanese yen". Strip them before emitting.
- For multi-value answers: `[v1, v2, ...]` (square brackets, comma
  + space), in the order the question names them.
- Always emit an `<answer>` tag (even your best guess) — a blank
  answer scores 0.

## Scale / Unit Conversion
Before extracting a cell value, re-read the table's header band for
the scale note (e.g. `[In millions of yen]`, `(in thousands)`,
`% of GDP`). If the cell's scale differs from the unit the question
explicitly names, convert before answering. Example: cell shows `49`
under `[In 100 millions of yen]` and question asks "in millions of
yen" → answer `4900`.
