# Question Answering Skill

## Output format (strict)

- End your reply with the answer wrapped in `<answer>...</answer>` tags
  on its own final line. Nothing should follow the closing tag.
- Inside the tags put **only the minimal noun phrase** that names the
  entity — no explanation, no rationale, no apposition.
- Use plain ASCII characters only: straight quotes `"` and `'` (never
  smart quotes `“ ” ‘ ’` or em-dash `—`).
- Do not prepend "The answer is", "Answer:", a colon, etc. Just the phrase.

## Span minimality

Strip everything that the grader will treat as extra:

- **No parenthetical clarifications**: write `Happy Feet`, not
  `Happy Feet (2006)`; `nibble`, not `A nibble (4 bits)`.
- **No trailing region/qualifier**: write `Louisville`, not
  `Louisville, Kentucky`; `Glasgow`, not `Glasgow, Scotland`.
- **No regnal numbers, honorifics, or middle names** unless the question
  explicitly asks for the full title: write `Philip`, not
  `Philip II of Macedon`; `Obama` / `Barack Obama`, not
  `President Barack H. Obama`. **Exception**: keep royal titles like
  `Prince`, `Princess`, `King`, `Queen` when the figure is normally
  cited with the title — write `Prince Harry`, not `Harry`;
  `Queen Elizabeth`, not `Elizabeth`.
- **No quoting of the answer**: write `For Whom the Bell Tolls`, not
  `"For Whom the Bell Tolls"`.
- **Drop generic-noun suffixes** when the proper name alone identifies
  the referent: write `Colorado` (not `Colorado River`), `Roanoke` (not
  `Roanoke Colony`), `Mississippi` (not `Mississippi River`), `Everest`
  (not `Mount Everest`) — unless the generic word is part of the
  canonical name (`Dead Sea`, `Suez Canal`).
- **Drop trailing modifiers**: write `negative` (not `negative electric
  charge`), `second` (not `second the motion`), `wave` (not `wave
  nature`). If the clue says "this kind of <X>", `<X>` is the topic,
  not part of the answer.
- **One answer, not a sentence**: never produce a full sentence like
  `X is Y because…`. If the clue can be paraphrased "the answer is ___",
  fill in just the blank.
- **Match grammatical number to the clue**: when the clue uses "these
  <X>" / "stop making these" / "two of these", answer **plural**
  (`cars`, `pixels`, `tanks`); when the clue uses "this <X>" / "one of
  these", answer **singular** (`car`, `pixel`, `tank`).

## Reading the clue (Jeopardy-style)

- Many clues are Jeopardy-style: a declarative description; the answer is
  the entity it describes. Pronouns like "this", "these", "he", "she"
  refer to the target — identify what the target is first.
  - `"Take a nibble if you want 4 of these binary digits"` → "these" =
    the units that make up a nibble → answer is `bit`, not `nibble`.
  - `"This 2006 film…"` → the film title, not a description of it.
- If the clue says "the longest river", "this city", "this organization",
  the answer is just the proper name — no leading article like "the"
  unless it is part of a proper title.
- When the clue *names a specific work* (book title, film name, song
  name) in quotes/italics **as the subject of the description**, the
  answer is almost always the **author / creator / performer**, never
  the title again. Example: `"A 'savage journey' titled 'Fear & Loathing
  in Las Vegas'"` → `Hunter S. Thompson`; `"A trilogy set in
  Alagaesia"` (no title given) → name the trilogy or its author per what
  the clue asks. Use the full canonical name (`Edgar Allan Poe`, not
  `Poe`) when the author is normally cited by first+last.
- If the clue specifies *which* part of a name is wanted (e.g. "his
  middle name is X", "her surname", "his nickname"), return only the
  matching part. `"this TV dad … middle name is Jay"` → `Homer` (not
  `Homer Simpson`).
- **Surname only for famous painters, explorers, and pre-20th-century
  figures who are canonically referred to by surname**: write `Gauguin`
  (not `Paul Gauguin`), `Audubon` (not `John James Audubon`), `Custer`
  (not `George Armstrong Custer`), `Webster` (not `Noah Webster`),
  `Marquette` (not `Jacques Marquette`), `Zapata` (not `Emiliano
  Zapata`), `Disraeli` (not `Benjamin Disraeli`), `Ashcroft` (not
  `John Ashcroft`).
  Exceptions where the full name is canonical: `Margaret Thatcher`,
  `William Shakespeare`, `Edgar Allan Poe`, `Prince Harry`.

## When you are not confident

- Prefer the **shortest plausible span** drawn from the `[DOC]` context.
- Earlier `[DOC]` blocks are usually more relevant; if a later doc
  contradicts an earlier one, trust the earlier doc unless the later one
  directly answers the question.
- If multiple gold-equivalent forms exist (e.g. `Barack Obama` vs
  `Obama`), prefer the form that appears verbatim in the context.
