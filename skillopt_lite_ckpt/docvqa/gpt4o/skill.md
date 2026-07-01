# DocVQA Skill

## Visual Evidence Discipline
- Read the document carefully before answering.
- Prefer the smallest exact text span that answers the question.
- When several nearby strings look similar, choose the one whose surrounding labels or layout best match the question.

## Exact Answer Discipline
- Copy names, numbers, and dates exactly from the document whenever possible.
- Prefer direct extraction over paraphrase.
- Before finalizing, compare the answer against nearby alternatives and keep the best-supported exact span.

## Output Format — STRICT
The content inside `<answer>...</answer>` must be the **minimal bare span**, nothing else. The grader is character-level (normalized Levenshtein) — every extra word, label, qualifier, or punctuation mark hurts.

Inside `<answer>`, NEVER include:
- Sentence wrappers or restatements of the question.
  - Q: "Where were sample webs produced?" → `<answer>University of Maine</answer>` (NOT `Sample webs were produced at the University of Maine.`)
  - Q: "...for how many stalk positions?" → `<answer>three</answer>` (NOT `Three stalk positions`)
- Qualifiers, units, counts, or category nouns the document shows next to the value.
  - `<answer>561</answer>` (NOT `561 males`)
  - `<answer>three</answer>` (NOT `three stalk positions`)
- Field labels when the question asks for the value.
  - Q: "What is the diagram no.?" → `<answer>1</answer>` (NOT `Diagram 1`)
- A person's organization clause when only the title is asked.
  - Q: "What is the title of X?" → `<answer>President</answer>` (NOT `President, The Great Western Sugar Company`)
- A brand's descriptor / location suffix when only the name is asked.
  - Q: "Which is the rent-a-car advertised?" → `<answer>Fairway</answer>` (NOT `Fairway Rent-A-Car System of Hawaii`)
- Trailing periods, surrounding quote marks, em-dashes, or markdown (`**bold**`, `*italic*`, backticks).
  - `<answer>where foaming is likely to occur</answer>` (NOT `Where foaming is likely to occur.`)
- Yes/No prose. For Yes/No questions emit exactly `<answer>Yes</answer>` or `<answer>No</answer>` — no clause after.

Self-check before emitting: re-read your `<answer>` content. If you can delete a word, a label, a unit suffix, or a punctuation mark and the answer still directly and completely answers the question, delete it.
