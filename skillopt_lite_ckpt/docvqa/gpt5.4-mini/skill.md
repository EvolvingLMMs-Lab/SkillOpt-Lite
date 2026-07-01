# DocVQA Skill

## Visual Evidence Discipline
- Read the document carefully before answering.
- Prefer the smallest exact text span that answers the question.
- When several nearby strings look similar, choose the one whose surrounding labels or layout best match the question.

## Exact Answer Discipline
- Copy names, numbers, and dates exactly from the document whenever possible.
- Prefer direct extraction over paraphrase.
- Before finalizing, compare the answer against nearby alternatives and keep the best-supported exact span.

## Concise Span Examples
The answer should be the bare value the question asks about. Do not echo the question's noun, prepend "the/at the/a", or add a trailing period.
- Q: "What was the Final Wt?" → `58.5` (not `58.5 lbs.`)
- Q: "What % of women said No?" → `39` (not `39%`)
- Q: "What is the heel height?" → `2-inch` (not `2-inch heels`)
- Q: "Where were sample webs produced?" → `University of Maine` (not `at the University of Maine`)
- Q: "What was the diet fed?" → `basal diet` (not `the basal diet`)
- Q: Yes/No question → `Yes` or `No` (no period, no extra clause)
- Q: "What is the page no / diagram no / exhibit no / figure no?" → return only the bare identifier value, stripping decorative dashes or symbols around it (e.g. `3`, not `-3-`). If the identifier is rendered as a single capital letter that visually doubles as a digit (e.g. `I` for `1`, `O` for `0`) and the surrounding context is numbered, return the digit form.
- When the transcribed span contains curly/smart quote glyphs (`“ ” ‘ ’`), write them as ASCII straight quotes (`"` or `'`). Do not add, drop, or alter any other characters.
