# SkillOpt alfworld — Copilot context

You are working in the **alfworld** env of SkillOpt. The workspace root opened
in this VS Code window is `copilot_example/alfworld/`.

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
- `workspace/.skillopt/samples/failed/*.md` — failed episodes (read these)
- `workspace/.skillopt/samples/passed/*.md` — successful episodes (read a few for contrast)
- `workspace/.skillopt/history/` — snapshots of `skill.md` before each edit
- `workspace/.skillopt/_eval_run/<ts>/results.jsonl` — raw eval output (one episode per line)
- `skills/initial.md` — baseline skill (read-only reference; don't edit)
- `run.sh` — re-runs eval against the current `workspace/skill.md` (auto-selects workspace by `--target_model`)
- `prompts/rollout_with_history.md` — system prompt template filled with the skill
- `rollout.py` — multi-turn loop runner; useful for understanding trace structure

## Task summary

- **Multi-turn embodied agent**: a high-level natural-language goal like
  *"put a clean mug in the cabinet"* over a text-based household environment.
- Each episode = 20–50 turns. Each turn: system prompt (filled with current
  skill) + current observation + admissible actions → LLM emits one action
  string → environment returns next observation. Ends on success / failure /
  max steps (50).
- **Target model**: `gpt-5.4-nano`, reasoning `medium`.
- **Scoring** (`eval_only.py`):
  - `hard` = **task success rate** (1 if `won`, else 0).
  - `soft` = **goal-condition success rate** (partial credit for satisfying
    sub-conditions even when the full task didn't complete).
  - Both are averaged across episodes.

## Sample file format

Each `.md` under `samples/{failed,passed}/`:

```markdown
---
id: <episode_id>
status: failed | passed
score: 0.0 | 1.0
timestamp: <iso>
---
## Input
(task goal + initial scene observation)
## Expected
(success criteria, e.g. "clean(mug) ∧ in(mug, cabinet)")
## Trace
<details>
<summary>Trajectory (N turns, may be truncated)</summary>
turn-by-turn observations + actions
</details>
## Notes
fail_reason: timed_out | wrong_object | unparseable_action | ...
```

Traces are wrapped in `<details>` and truncated at 8000 chars by the
exporter. Use the `<summary>` line + `## Notes` to triage before expanding.

## Editing principles for `workspace/skill.md`

1. **Bigger edits than livemath/searchqa.** ALFWorld rewards are sparse;
   small wording tweaks rarely move the needle. Default to 2–4 substantive
   edits per round (still less than a full rewrite).
2. **Cluster by task type first.** Skim filenames + `## Input` to group
   failures by the 6 ALFWorld task types: Pick & Place, Pick Two & Place,
   Examine in Light, Clean & Place, Heat & Place, Cool & Place. Patch the
   weakest task type first — a +20% on one task type often beats a +2%
   smear across all six.
3. **Action format is strict.** The environment parses actions like
   `go to fridge 1`, `take apple 1 from countertop 1`, `clean mug 1 with
   sinkbasin 1`. Any wording change in `skill.md` that nudges the model
   toward "I will pick up the apple" instead of `take apple 1 from …`
   tanks success on every episode.
4. **Cite samples by id** (e.g. `samples/failed/<id>.md`) when proposing
   changes, so the diff is auditable.
5. **Snapshot before edit.** Always `cp workspace/skill.md
   workspace/.skillopt/history/<ts>__before.md` before mutating — only undo
   path.
6. **Don't touch `skills/initial.md`.** It's the baseline for comparison.

## Running eval (terminal commands you may issue)

Quick smoke (3 episodes, ~2–4 min — depends on episode length):
```bash
bash run.sh --eval_limit 3 --limit 3
```

Standard check (10 episodes, ~5–10 min):
```bash
bash run.sh --eval_limit 10 --limit 10
```

Full val (140 episodes — what `/skillopt-loop`'s gate uses, ~20–40 min on
`gpt-5.4-nano` with 8 workers):
```bash
bash run.sh --split val --eval_limit 0 --limit 0
```

Full test (134 episodes — only run at end / for final report):
```bash
bash run.sh --split test --eval_limit 0 --limit 0
```

Each run prints `Results: hard=<success> soft=<gc_success> (n=N)` —
`hard` is the metric the gate compares on. `soft` often moves first
(agent gets partial credit) before `hard` follows; track both.
