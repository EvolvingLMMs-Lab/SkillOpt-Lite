# searchqa/

Reference implementation for **SearchQA**: single-turn open-domain question
answering grounded in retrieved passages. Lifted from `skillopt/envs/searchqa/`
for plugin debugging.

## Task

- **Input:** a natural-language question + a `[DOC]`-delimited context blob of
  retrieved passages (truncated to ~6k chars).
- **Agent:** one LLM call. System prompt = `prompts/rollout_system.md` filled in
  with the current skill; user prompt = question + context.
- **Output:** answer wrapped in `<answer>...</answer>`.
- **Scoring:** see `evaluator.py` — string/normalized match against gold.

## Files

| File | Purpose |
|---|---|
| `rollout.py` | `process_one(item, skill) -> result`; `run_batch(items, skill)` parallel runner |
| `evaluator.py` | `evaluate(predicted, gold) -> {hard, soft, fail_reason}` |
| `adapter.py` | dataset row → rollout input shape |
| `dataloader.py` | load splits from `data/searchqa_id_split/` |
| `reflect.py` | per-sample error analysis (old SkillOpt reflect, kept for reference) |
| `prompts/rollout_system.md` | agent system prompt template (`{skill_section}` placeholder) |
| `prompts/analyst_error.md`, `analyst_success.md` | old reflect prompts |
| `skills/initial.md` | baseline skill — good starting point for plugin demo |

## Generating samples for the loop

Every time `run.sh` finishes, `make_samples.py` is called automatically to
expand the run's `results.jsonl` into per-item files under
`workspaces/<model>/.skillopt/samples/{failed,passed}/`. Manual refresh:

```bash
python copilot_example/make_samples.py \
    --results /path/to/searchqa_run/test_eval/results.jsonl \
    --workspace copilot_example/searchqa/workspaces/gpt-5.5 \
    --env searchqa --limit 20
```

The exporter handles SearchQA-specific quirks:
- `question` + `context` are concatenated into the `## Input` section
- `predicted_text` / `correct_text` map to `## Agent output` / `## Expected`
- `fail_reason` is preserved in `## Notes`

## Run the /skillopt-loop

```bash
code copilot_example/searchqa
# in Copilot Chat (Agent mode):
# /skillopt-loop rounds=3 batch=20
```

One-shot eval only (no chat):

```bash
bash copilot_example/searchqa/run.sh --eval_limit 5 --limit 5
# → copilot_example/searchqa/workspaces/<model>/{skill.md, .skillopt/samples/}
```

## Notes (vs the old reflect.py)

The `/skillopt-loop` does **not** use `reflect.py` / `analyst_*.md`.
Reflect, aggregate, and rewrite are all collapsed into a single Copilot
coding-agent call that reads the failed sample files directly. Those files
are kept here only as reference for what the old multi-step pipeline did.
