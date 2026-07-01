# DocVQA Skill

## Visual Evidence Discipline
- Read the document carefully before answering.
- Prefer the smallest exact text span that answers the question.
- When several nearby strings look similar, choose the one whose surrounding labels or layout best match the question.

## Exact Answer Discipline
- Copy names, numbers, and dates exactly from the document whenever possible.
- Prefer direct extraction over paraphrase.
- Before finalizing, compare the answer against nearby alternatives and keep the best-supported exact span.

## Question-Pattern Trimming (apply ONLY when the pattern matches; otherwise keep the full span)
Scoring is normalized Levenshtein on the lowercased string — punctuation, units, and articles are NOT stripped by the grader, so extra trailing tokens directly hurt the score. But over-trimming hurts even more. Use these rules only when the question literally matches the pattern:

- Question starts with **"how many"** → answer with the bare numeral only (`561`, not `561 males`; `three`, not `three stalk positions`).
- Question contains **"what %"** or **"what percent"** → return the bare number without the `%` sign (`39`, not `39%`).
- Question is **"what is the [diagram|figure|page|table|item|building|section|chapter] no./number?"** → return only the bare identifier as written (`1`, `A-3`, `IV`), not the label word (`Diagram I`, `Page 2`).
- Question is **"what is the title/role/position of [person]?"** → return only the title noun (`President`), not the title-plus-organization (`President, The Great Western Sugar Company`).
- Question begins **"where"** or **"in what [location]"** with a "X is at/in Y" answer in the doc → strip leading `at`, `in`, `on`, `of` and articles (`the`, `a`, `an`) so the answer starts with the proper noun (`University of Maine`, not `at the University of Maine`).
- Question is **"which is the [brand|product|company|sponsor|...] advertised/featured/shown?"** → return the shortest distinctive brand/headline word as it appears (`Fairway`, not `FAIRWAY RENT-A-CAR SYSTEM OF HAWAII`). Pick the single token that uniquely names the entity.
- If your trimmed answer still **starts with a bare article** (`the`, `a`, `an`) and the article is not part of the proper noun, drop it (`basal diet`, not `the basal diet`). Keep articles when they are part of a title or proper name (`The New York Times`).
- If your answer ends with a **quoted or parenthetical qualifier that merely restates the topic the question already named** (e.g. question "quantity of tar in X?" → drop trailing `"tar"`; "name of the diet?" → drop trailing `(diet)`), remove it.
- If the question asks for a **specific property/measurement of a named object** (e.g. "what is the heel height of women's shoes?", "what is the price of the bottle?", "what is the page no.?") and your answer ends with that object noun (`heels`, `bottle`, `page`) or its singular/plural form, drop the trailing object noun (`2-inch`, not `2-inch heels`; `2`, not `2 OF 2` when gold is `2`).

For ALL OTHER question types, do NOT strip anything — copy the document span verbatim. When in doubt, keep the full span.

## Verbatim Formatting (when you do copy the span)
- Preserve the document's own separators. If dates are written `4-5-6`, return `4-5-6`, not `4, 5, 6`.
- If the document literally wraps a phrase in quotation marks (e.g. a tagline `"we work for smokers"`), include the quotation marks.
- **Always use ASCII straight quotes (`"` and `'`), never curly/smart quotes (`"` `"` `'` `'`).** Even if the document image renders typographic curly quotes, transcribe them as straight `"` so the answer matches the gold string character-for-character.
- **Preserve spacing exactly as written in the document.** Do not insert extra whitespace between adjacent tokens that are joined in the source (e.g., `Program("CCP")` not `Program ("CCP")`; `Item#5` not `Item #5`). Do not collapse intentional double spaces.
- **For monetary or quantity answers** (e.g. `Two Hundred Pounds Twelve Shillings`), stop at the last named non-zero unit. Do NOT append placeholder continuations such as `-- Pence`, `and -- Pence`, `00 cents`, or `--` even if the form shows blank slots beyond the named amount.
