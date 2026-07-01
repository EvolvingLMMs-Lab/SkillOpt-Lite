# OfficeQA Skill

## Minimum Tool-Call Discipline (do NOT skip)
- Every numeric question MUST be answered after at least one `grep` and one
  `read` against the source `.txt` files under `data/officeqa_docs_official/`.
- Never answer from the oracle-parsed-pages excerpt alone — re-open and read
  the cited document. The excerpt is for orientation; the source is ground
  truth.
- If a tool call errors, retry with a corrected term once; never abandon the
  question on a single tool failure.

## Retrieval Discipline
- Start by narrowing to the most likely candidate file before reading long passages.
- Prefer targeted search terms that name the exact entity, period, measure, or table concept from the question.
- After a promising match, read only a small surrounding span and verify it matches the requested year, basis, and unit.

## Evidence Discipline
- Extract the exact value from the retrieved text before doing any arithmetic.
- Keep track of each operand's period, unit, and semantic role so nearby proxy values are not mixed in.
- If the question asks for a transformed or derived quantity, compute only after confirming every operand.
- **Re-read the bracketed scale note** (`[In millions of yen]`,
  `[In billions of dollars]`, etc.) immediately above any value you extract;
  convert to the unit the question asks for *before* arithmetic, not after.

## Common Statistical Formula Pitfalls (apply ONLY when the question uses these terms verbatim)
- **CAGR** (compound annual growth rate) over `Y_end - Y_start` years
  uses `n = Y_end - Y_start` *intervals*, not the *count* of data points.
  Formula: `(V_end / V_start) ** (1 / n) - 1`. Decimal form unless the
  question says "as a percentage".
- **Continuously compounded annual growth rate** uses `ln(V_end / V_start) / n`
  with the same interval-count `n`. Decimal form.
- **Geometric mean of n growth rates** g_1..g_n (each already a decimal,
  e.g. `0.025` for 2.5%): `(prod(1 + g_i)) ** (1 / n) - 1`. Do NOT
  geometric-mean the raw values themselves — only the growth factors.
- **Gini coefficient** with just two ordered values `[L, H]` (e.g. receipts
  vs expenditures) summed to `T = L + H`: `G = (H - L) / T`. Common
  mistake: dividing by `2 * mean` gives a value **half** the correct
  answer (you'd get `0.006` instead of `0.012`).
- **Sample vs population standard deviation**: "sample standard deviation"
  → divide by `n - 1`; "population standard deviation" → divide by `n`.
  Same for variance and coefficient of variation built from them.
- **Period direction**: "from January 1939 to February 1939" means
  `Feb_value - Jan_value`. Re-check sign: if the question says "decrease"
  use absolute value; if it says "signed" or "change", keep the sign.

## Final Answer Discipline
- Return the final answer only after one last consistency check against the retrieved evidence.
- Copy the final answer from a checked value, not from an unverified intermediate guess.
- **Never emit an empty `<answer></answer>` tag.** If still uncertain after
  the tool-call budget, emit the best single-number guess derived from the
  evidence you did retrieve — a guess scores 0 the same as empty, but a
  correct guess scores 1.

## Final Answer Format (STRICT — last thing you read before answering)
- Emit exactly one `<answer>VALUE</answer>` tag at the very end of the reply.
- VALUE is the bare numeric payload — **no units, no currency symbols, no
  words, no parenthetical clarifications**. Strip every one of:
  `$`, `%`, `million`, `millions`, `billion`, `billions`, `thousand`,
  `JPY`, `USD`, `INR`, `EUR`, `DEM`, `yen`, `dollars`, `pounds`,
  `fine pounds`, `percentage points`, `pp`, `(in 1953 dollars)`, etc.
- Use an **ASCII hyphen-minus `-`** for negatives, never the Unicode minus
  `−` (U+2212).
- For list-valued answers use the format `[a, b]` (square brackets,
  comma-space separator), matching the question's example exactly.
- Keep the **same decimal precision** the question asks for ("rounded to the
  hundredths" → exactly 2 decimal places). Do not pad extra trailing zeros
  beyond the requested precision unless the gold convention requires it.
- Keep commas as thousands-separators **only if** the question or the gold
  format used them; when in doubt, strip commas (the scorer normalises
  commas away, but a stray suffix kills the match).
- Worked transforms (apply *before* you emit):
  - `6,758 million dollars`  →  `6758`  (drop suffix, drop commas)
  - `57,615.04 million INR (i.e., 57,615,040,000.00 INR)`  →  `57615.04`
  - `25,258,095.24 fine pounds`  →  `25258095.24`
  - `0.05 percentage points`  →  `0.05`
  - `-1,665.71 million dollars`  →  `-1665.71`
  - `[207.52, −2.43]`  →  `[207.52, -2.43]`  (ASCII minus, no unit suffix)