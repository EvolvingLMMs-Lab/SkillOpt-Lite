# Question Answering Skill

Given a question and `[DOC]`-delimited retrieved passages, output one final answer wrapped in `<answer>...</answer>` on the last line. Keep all reasoning short.

## Output format

- Wrap the final answer in a single `<answer>...</answer>` tag on the last line. Do not emit multiple `<answer>` tags.
- Inside the tag, write the **shortest span** that fully and exactly answers the question — no leading article, no trailing qualifier, no enclosing quotes.
- Use plain ASCII characters. Replace curly quotes/apostrophes with straight ones: `’` → `'`, `“ ”` → `"`.

## Pick the minimal answer span

The grader uses SQuAD-style exact match after lowercasing, stripping punctuation, dropping `a|an|the`, and collapsing whitespace. So extra honorifics, regnal numerals, role prefixes, organization suffixes, and trailing category nouns will all cause EM=0 even when the core entity is right.

Prefer the shortest noun phrase that uniquely answers the question:

- If the question asks for a person's name and the doc says "King Philip II of Spain", answer just **Philip** (or **Philip II** only if the question explicitly asks "which Philip" / mentions other Philips).
- For modern / well-known cultural figures (authors, scientists, politicians, performers), default to the **standard full name** — typically "First Last" — not the surname alone. E.g. **Margaret Thatcher** not "Thatcher"; **Edgar Allan Poe** not "Poe"; **Christopher Paolini** not "Paolini". Use surname alone only for one-name historical figures (Shakespeare, Voltaire) or when the question itself uses only the surname.
- If the question asks for an organization that the doc calls "the Boy Scouts of America" but is colloquially "the Boy Scouts", answer **Boy Scouts** unless the question asks for the full legal name.
- If the question asks for a property (e.g. "what charge does an electron carry?"), answer the bare property word — **negative** — not the full phrase "negative electric charge".
- If the question asks for a verb or action (e.g. "what do you do to support a motion?"), answer the bare verb — **second** — not the whole idiom "second the motion".
- **Number** — default to singular when the question asks for a generic noun ("this **type** of plant", "these grants are called", "name a facility"): answer **a subsidy** not "subsidies", **rehab facility** not "rehab centers". Use plural only when the question explicitly mentions a count ("these two ships") or asks for a collective.
- Drop the category noun when the question already names it: for "what river…" answer "Mississippi" not "Mississippi River"; for "what year…" output just the year. **Exception**: when the entity's canonical name includes the category word (e.g. "Pacific Ocean", "World War II", "New York City"), keep it. **Counter-exception**: if the question itself uses a generic category noun to refer to the answer (e.g. "this cabinet **dept.**", "this **agency**", "this **organization**"), include that category noun in the answer (e.g. "Agriculture department", not just "Agriculture").

## Match the answer type to the question

Read the question stem first and lock the answer type before scanning the docs:

- **who / which person / name the author / who wrote** → a person's name. Do not return a work, role, or organization.
- **what work / which book / name the novel / what film** → a title. Do not return the author or a subtitle/tagline.
- **when / in what year / which century** → a date or year. Do not return an event name.
- **where / in what city / which country** → a place. Do not return a person or a date.
- **what event / which war / which battle** → a named event. Do not return a year.
- **how many / what number** → a numeral.

If the most prominent span in the passages is the wrong **type** for the question, keep scanning — the right-type answer is usually in the same passage, often one clause earlier or later.

**Jeopardy-style clues without an interrogative.** Many questions are statements like `A "savage journey" titled "Fear & Loathing in Las Vegas"` — no explicit who/what/when. Treat these as `who/what is being described?` and identify the asked-for type from the clue structure: a clue that quotes a work or subtitle is almost always asking for the **author / creator / performer**, not the work itself or another fragment of the title. A clue that describes an event or location is asking for the event/place name, not its date.

## Prefer earlier `[DOC]` passages on conflicts

Passages are ordered by retrieval relevance. When two passages give different answers, prefer the one in the earliest `[DOC]` block unless a later passage clearly disambiguates.

## Multi-item answers: preserve canonical / question order

If the question asks for several items ("these two ships", "the three sisters", "name both founders"), list them in the order they appear in the question or the order the passages introduce them — that is almost always the historically canonical order. Use `&` or `and` between items. Example: for Columbus' two ships commanded by the Pinzon brothers, answer **Nina & Pinta** (the order the docs list them), not "Pinta and Nina".

## Final reminder

Last line of your response must be `<answer>SHORTEST_EXACT_SPAN</answer>` — nothing after it.
