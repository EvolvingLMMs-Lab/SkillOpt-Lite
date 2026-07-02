# livemath/

Reference implementation for **LiveMathematicianBench**: theorem-grounded
multiple-choice math QA, lifted from `skillopt/envs/livemathematicianbench/`
for plugin debugging.

## Task

- **Input:** a research-level math question with 4–5 lettered choices (A–E).
  Choice E is often a "none of the above" / meta-option that requires extra
  care.
- **Agent:** one LLM call. System prompt = `prompts/rollout_system.md` filled
  with the current skill; user prompt = question + formatted choices.
- **Output:** the chosen letter wrapped in `<answer>X</answer>` — the evaluator
  regex requires this exact format.
- **Scoring:** `hard` = 1 if `predicted_label == correct_label` else 0.

## Files

| File | Purpose |
|---|---|
| `rollout.py` | `_build_system(skill)`, `_format_choices(...)`, batch runner |
| `evaluator.py` | `extract_answer(text)` regex + label compare |
| `adapter.py` | dataset row → rollout input |
| `dataloader.py` | load problem set + splits |
| `reflect.py` | old per-sample error analysis (kept for reference) |
| `prompts/rollout_system.md` | agent system prompt template |
| `prompts/analyst_error.md`, `analyst_success.md` | old reflect prompts |
| `skills/initial.md` | baseline skill — weaker than HITL outputs, good for diff demo |

## Why this is the sharpest starter env

LiveMath has a clean experimental ladder: baseline `skills/initial.md`
scores ~0.41 on test; a few `/skillopt-loop` rounds land in the 0.52–0.54
range. That makes it a great smoke test for whether the loop is doing its
job — you should see improvement within 2–3 rounds.

## Generating samples for the loop

Every time `run.sh` finishes, `make_samples.py` is called automatically to
expand the run's `results.jsonl` into per-item files under
`workspaces/<model>/.skillopt/samples/{failed,passed}/`. If you want to
refresh samples from an old run manually:

```bash
python copilot_example/make_samples.py \
    --results /path/to/livemath_run/test_eval/results.jsonl \
    --workspace copilot_example/livemath/workspaces/gpt-5.5 \
    --env livemath --limit 20
```

The exporter:
- preserves `task_type` (e.g. `Universal`, `Specific`) as a tag
- preserves `fail_reason` (e.g. `MCQ=0: predicted 'D' but expected 'C'`) in `## Notes`
- writes `<answer>X</answer>` style output as `## Agent output` so the loop's
  patch attempts can target the answer-extraction failure mode directly

## Run the /skillopt-loop

**Open the `copilot_example/livemath/` folder in your coding agent** (VS Code
Copilot Chat / Codex CLI / Claude Code / kimi-code / glm-code /
deepseek-tui — any host that reads local `.github/prompts/*.prompt.md`),
then **type this at the coding-agent chat prompt** (not a shell terminal):

In `copilot_example/livemath`, type:

```
/skillopt-loop rounds=2 batch=40 target=gpt-5.4-nano
```

That's the whole loop — your coding agent handles env setup (pip
install, `source ../env.sh`, data download) and then runs `run.sh`,
inspects samples, patches `skill.md`, val-gates, and archives, all on
its own. No manual bootstrap needed.

## Failure mode to watch for

The `<answer>X</answer>` regex is **strict** — if the loop's improved skill
encourages "Answer: X" or "The answer is X.", the evaluator will return 0
even when the model picked the right letter. When reviewing patches, make
sure the final-answer format is preserved.
