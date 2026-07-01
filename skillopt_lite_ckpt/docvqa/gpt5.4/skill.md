# DocVQA Skill

## Visual Evidence Discipline
- Read the document carefully before answering.
- Prefer the smallest exact text span that answers the question.
- When several nearby strings look similar, choose the one whose surrounding labels or layout best match the question.

## Exact Answer Discipline
- Copy names, numbers, and dates exactly from the document whenever possible.
- Prefer direct extraction over paraphrase.
- Before finalizing, compare the answer against nearby alternatives and keep the best-supported exact span.

## Minimal-Span Output
Put the final answer inside `<answer>...</answer>`. Strip whatever the question already implies — leave only the value:
- Drop leading prepositions/articles ("at the …", "on …", "in …") — `<answer>University of Maine</answer>`, not `at the University of Maine`.
- For a brand/company name, give the brand only when the question asks for the brand. Drop trailing descriptors like "Rent-A-Car System of Hawaii", ", Inc.", legal form, location — `<answer>Fairway</answer>`, not `Fairway Rent-A-Car System of Hawaii`.
- For a person's title, drop the organization clause — `<answer>President</answer>`, not `President, The Great Western Sugar Company`.
- Drop a unit/symbol the question already names: when the question says "What %…", emit the bare number — `<answer>39</answer>`, not `39%`. Same for "$" when the question says "amount in dollars".

Keep the document's exact text when it IS the answer — including its own quote marks, casing of brand/headline forms, thousand separators, decimals, and punctuation that the printed value contains.
