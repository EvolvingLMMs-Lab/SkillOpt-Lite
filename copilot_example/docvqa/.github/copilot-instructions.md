# SkillOpt searchqa — Copilot context

You are working in the **searchqa** env of SkillOpt. The workspace root opened
in this VS Code window is `copilot_example/searchqa/`.

## Model-specific workspaces

Workspaces are **isolated by target model** to prevent runs from clobbering
each other. When you run `bash run.sh --target_model <M>`, the script
auto-creates `workspaces/<model>/` (e.g. `workspaces/gpt-5.5/`,
`workspaces/gpt-5.4-nano/`). Each workspace has its own `skill.md`,
`.skillopt/samples/`, and `.skillopt/history/`.

For backward compatibility, `run.sh` also maintains a `workspace` symlink
pointing to the **most-recently-used** model's workspace, so existing
prompts and commands that reference `workspace/skill.md` keep working
against whichever model was last run.

## Files you care about

- `workspace/skill.md` → `workspaces/<current_model>/skill.md` — **the skill being optimized** (read & rewrite this)
- `workspace/.skillopt/samples/failed/*.md` — failed rollouts (read these)
- `workspace/.skillopt/samples/passed/*.md` — successful rollouts (read a few for contrast)
- `workspace/.skillopt/history/` — snapshots of `skill.md` before each edit
- `workspace/.skillopt/_eval_run/<ts>/results.jsonl` — raw eval output (one rollout per line)
- `skills/initial.md` — baseline skill (read-only reference; don't edit)
- `run.sh` — re-runs eval against the current `workspace/skill.md` (auto-selects workspace by `--target_model`)
- `evaluator.py` — scoring logic; useful when diagnosing format failures

## Task summary

- **Single-turn QA**: question + `[DOC]`-delimited retrieved passages
  (truncated to ~6k chars) → one LLM call → `<answer>...</answer>`.
- **Target model**: `gpt-5.4`, reasoning `medium`.
- **Scoring** (`evaluator.py`):
  - `hard` = SQuAD-style **Exact Match** (normalized: lowercase, strip
    punctuation, drop `a|an|the`, collapse whitespace).
  - `soft` = SQuAD-style **token F1** (max across gold answers).
  - Answer is extracted from `<answer>...</answer>` (case-insensitive); falls
    back to the last non-empty line.

## Sample file format

Each `.md` under `samples/{failed,passed}/`:

```markdown
---
id: <searchqa_id>
status: failed | passed
score: 0.0 | 1.0 | ...   # hard EM
timestamp: <iso>
tags: [optional]
---
## Input
(question + [DOC] context blob)
## Expected
(gold answers — may be a list of equivalent strings)
## Agent output
(what the model produced; should contain <answer>...</answer>)
## Notes
fail_reason: EM=0: predicted 'Barack H. Obama' but expected 'Barack Obama'
```

## Editing principles for `workspace/skill.md`

1. **Conservative wins.** Small targeted edits beat rewrites — same lesson as
   livemath. Default to ≤3 edits per round.
2. **Output-format strictness matters.** The grader extracts the **last**
   `<answer>` tag (case-insensitive). Any wording that nudges the model
   toward "The answer is X." outside an `<answer>` tag still works because of
   the fallback — but adding *multiple* `<answer>` tags will be picked from
   the last, which is a common failure mode.
3. **Normalization is generous, but not infinite.** EM strips punctuation,
   articles, and case. So `the Eiffel Tower` == `Eiffel Tower` == `eiffel
   tower`. But it does **not** strip honorifics, middle names, parenthetical
   clarifications, or alternate spellings — that's where most F1>0 but EM=0
   failures come from.
4. **Cite samples by id** when proposing changes (e.g.
   `samples/failed/<id>.md`), so the diff is auditable.
5. **Snapshot before edit.** Always `cp workspace/skill.md
   workspace/.skillopt/history/<ts>__before.md` before mutating — only undo path.
6. **Don't touch `skills/initial.md`.** It's the baseline for comparison.

## Known failure clusters on searchqa

- **Span over-extension** — model returns "Barack H. Obama" or "President
  Barack Obama" when gold is "Barack Obama" (EM=0 but F1≈0.67). The skill
  should instruct to extract the **minimal** noun phrase.
- **Multi-span answers** — questions with comma-separated gold answers
  (e.g. "List three…") that the model collapses or reorders.
- **Long-context distraction** — answer is in the first `[DOC]` but the model
  pulls a wrong number/name from a later doc. The skill can hint to prefer
  earlier docs when conflicting.
- **`<answer>` tag missing** — model outputs reasoning then "Final: X." with
  no tag. Falls back to last line, but if there's a trailing period or other
  punctuation in a way that breaks the answer, EM=0.
- **Extra articles/punctuation** — usually normalized away; if you see EM=0
  with what looks like a clean answer, double-check `evaluator.py` rules.

## Running eval (terminal commands you may issue)

Quick smoke (5 items, ~30s):
```bash
bash run.sh --eval_limit 5 --limit 5
```

Standard check (20 items, ~1–2 min on gpt-5.4):
```bash
bash run.sh --eval_limit 20 --limit 20
```

Full test split:
```bash
bash run.sh --eval_limit 0 --limit 20
```

Each run prints `Results: hard=<EM> soft=<F1> (n=N)` — `hard` is the metric
the gate compares on. Track both: if `hard` is flat but `soft` improved, the
skill is producing closer-but-not-exact answers (often a span-extraction
issue) — usually a productive direction to keep pushing.
