# SearchQA Answering Skill

You receive a Jeopardy-style clue (or short question) followed by `[DOC]`-delimited
retrieved passages. Your job is to output a single, minimal answer.

## Output format (strict)

- End your response with exactly one tag: `<answer>FINAL ANSWER</answer>`.
- The text inside `<answer>` MUST be plain text only — no markdown (`**bold**`,
  `*italic*`, backticks), no emojis, no parentheses, no quotes, no trailing period.
- Do NOT put multiple `<answer>` tags. The grader takes the LAST one.
- Keep any reasoning above the tag short.

## Span minimality (the #1 rule)

The gold answer is almost always the **shortest noun phrase** that identifies
the entity. Strip everything that isn't strictly required.

- Drop trailing qualifiers: years, dates, states, countries, parties, roles.
  - "Happy Feet (2006)" → `Happy Feet`
  - "Louisville, Kentucky" → `Louisville`
  - "Barack H. Obama" / "President Barack Obama" → `Barack Obama`
- Drop parenthetical clarifications and acronym expansions.
  - "Boy Scouts of America (BSA)" → `Boy Scouts of America` (or `Boy Scouts` if
    the clue uses that wording)
  - "J. K. Rowling (Harry Potter)" → `J. K. Rowling`
- Drop honorifics, titles, middle initials unless the clue specifically asks
  for the full form.
- No leading "the/a/an" (normalization strips them, but cleaner is safer).
- One entity per answer unless the question explicitly asks for a list.

## Reading the clue

- Identify the **answer type** before scanning the docs: person, place, work,
  year, number, single word, etc. Output must match that type.
  - "In this city..." → output a city name only.
  - "this autumn month" → output a month name only.
  - "What year..." → output 4 digits only.
- Jeopardy clues are statements; the answer is the entity they describe.
  Don't answer with a definition, summary, or how-to — answer with the entity.
- If the clue quotes a work's title, the answer is usually the author, the
  character, or another work — read carefully which is being asked.

## Using the docs

- Prefer evidence from earlier `[DOC]` blocks when later docs disagree on a
  specific fact — earlier docs are more relevant on average.
- If the docs don't mention the entity but the clue is unambiguous, answer
  from common knowledge rather than refusing.
- Never quote a full sentence from a doc as the answer; extract the entity.

## Examples

Clue: "In 1933 she penned 'The Autobiography of Alice B. Toklas'"
`<answer>Gertrude Stein</answer>`

Clue: "When in this Scottish city, visit the Willow Tea Rooms..."
`<answer>Glasgow</answer>`

Clue: "...the USA's Constitution Day is observed in this autumn month"
`<answer>September</answer>`

