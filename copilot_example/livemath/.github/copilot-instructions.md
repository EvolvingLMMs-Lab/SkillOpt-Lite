# SkillOpt livemath — Copilot context

You are working in the **livemath** env of SkillOpt. The workspace root opened
in this VS Code window is `copilot_example/livemath/`.

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

## Sample file format

Each `.md` under `samples/{failed,passed}/`:

```markdown
---
id: <livemath_id>           # e.g. 202512:20
status: failed | passed
score: 0.0 | 1.0 | 0.25 | ...
timestamp: <iso>
tags: [optional]
---
## Input
(the math problem; often MCQ)
## Expected
(reference answer, e.g. <answer>C</answer>)
## Agent output
(what the model produced)
## Notes
fail_reason: MCQ=0: predicted 'D' but expected 'C'
```

## Editing principles for `workspace/skill.md`

1. **Conservative wins.** The HITL ceiling (0.5455 on gpt-5.4 medium; stale
   for gpt-5.5 until re-baselined) came from a handful of small targeted
   edits — full rewrites consistently regressed. Default to ≤3 edits per round.
2. **Format strictness matters.** livemath grades on `<answer>X</answer>`
   regex. Any wording change that nudges the model toward "Answer: X" or
   "The answer is X." tanks accuracy even when the letter is correct.
3. **Cite samples by id** when proposing changes (e.g.
   `samples/failed/202512_20.md`), so the diff is auditable.
4. **Snapshot before edit.** Always `cp workspace/skill.md
   workspace/.skillopt/history/<ts>__before.md` before mutating; this is the
   only undo path.
5. **Don't touch `skills/initial.md`.** It's the baseline for comparison.

## Known failure clusters on livemath

- **Meta-option E / "none of the above"** — model picks E too eagerly when
  unsure. Watch for samples tagged `Universal` with `predicted 'E'`.
- **Symbolic vs numeric answers** — model sometimes outputs the simplified
  expression instead of the requested letter.
- **Answer-extraction** — correct reasoning but malformed `<answer>` tag.

## Running eval (terminal commands you may issue)

Quick smoke (5 items, ~30s):
```bash
bash run.sh --eval_limit 5 --limit 5
```

Standard check (20 items, ~2 min):
```bash
bash run.sh --eval_limit 20 --limit 20
```

Full val (18 items, ~1–2 min on gpt-5.5 — what `/skillopt-loop`'s gate uses):
```bash
bash run.sh --split val --eval_limit 0 --limit 20
```

Full test (default `--split test`, 124 items, ~7–14 min — only run at end / for final report):
```bash
bash run.sh --eval_limit 0 --limit 20
```

Each run prints `Results: hard=<X> soft=<Y> (n=N)` — that's the metric to
track across rounds.
