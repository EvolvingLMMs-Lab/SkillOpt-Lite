# DocVQA Skill

## Visual Evidence Discipline
- Read the document carefully before answering.
- Prefer the smallest exact text span that answers the question.
- When several nearby strings look similar, choose the one whose surrounding labels or layout best match the question.
- Always attempt an answer. Even if text is small/blurry, give your best literal reading of the relevant span rather than refusing — never reply with "I can't read" or similar.

## Exact Answer Discipline
- Copy names, numbers, and dates exactly from the document whenever possible.
- Prefer direct extraction over paraphrase.
- Before finalizing, compare the answer against nearby alternatives and keep the best-supported exact span.

## Output Format — STRICT
The content inside `<answer>...</answer>` must be the **minimal bare span**, nothing else. The grader is character-level (normalized Levenshtein) — every extra character hurts.

Inside `<answer>`, NEVER include:
- Sentence wrappers or restatements of the question.
  - Q: "Where were sample webs produced?" → `<answer>University of Maine</answer>` (NOT `Sample webs were produced at the University of Maine.`)
  - Q: "...for how many stalk positions?" → `<answer>three</answer>` (NOT `Three stalk positions.`)
- Qualifiers, units, counts, or parenthetical context the document shows next to the value.
  - `<answer>K. N. Grant</answer>` (NOT `K. N. Grant (31 meetings)`)
  - `<answer>561</answer>` (NOT `561 males`)
  - `<answer>281</answer>` (NOT `281 (in 1000s)`)
- Field labels when the question asks for the value.
  - Q: "What is the diagram no.?" → `<answer>1</answer>` (NOT `Diagram 1`)
  - Q: "What is the title of Table 1?" → `<answer>Regional Bureau Activities in NCF</answer>` (NOT `Table 1 - Regional Bureau Activities in NCF`)
- A person's job-title clause plus their organization when only the title is asked.
  - Q: "What is the title of X?" → `<answer>President</answer>` (NOT `President, The Great Western Sugar Company`)
- Trailing periods, surrounding quote marks (`"..."` or `"..."`), em-dashes, or markdown such as `**bold**`, `*italic*`, backticks.
  - `<answer>May/June 1977</answer>` (NOT `May/June 1977.`)
  - `<answer>1.25</answer>` (NOT `**1.25**`)
  - `<answer>Reduce blending time where foaming is likely to occur.</answer>` is fine; surrounding `"..."` is not.
- Yes/No prose. For Yes/No questions emit exactly `<answer>Yes</answer>` or `<answer>No</answer>` — no clause after.

DO preserve the document's own formatting of the value:
- Keep thousand separators / decimal points exactly as printed: `5,979.25` not `5979.25` (and vice-versa if the doc has no comma).
- Keep currency symbols and units only when they are part of the value the question asks for (e.g. "what amount in dollars" → keep `$`); otherwise drop them.
- Match the casing/spacing of common company/brand names as printed in the document headline form (e.g. `Fairway`, not `FAIR WAY RENT-A-CAR`).
- For pure numeric answers, strip adjacent decorations that are not part of the number itself — list bullets, leading dashes/hyphens, dollar signs, percent signs (unless the question explicitly asks for a percent), table cell separators. `<answer>659</answer>` not `-659`.
- For typed (non-handwritten) documents, if the extracted span looks like a common English word with a single ambiguous letter (e.g. `Smokirs`), prefer the standard dictionary spelling (`Smokers`); OCR noise on typed text rarely produces real proper nouns.

Self-check before emitting: re-read your `<answer>` content. If you can delete a word, a punctuation mark, or a parenthetical and the answer is still complete and correct for the question asked, delete it.
