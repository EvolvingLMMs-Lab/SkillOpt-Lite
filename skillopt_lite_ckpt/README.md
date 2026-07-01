# skillopt_lite_ckpt/

Per-benchmark × per-model **optimized skills** used by
`copilot_example/<env>/run.sh` as its `--skill` default and displayed in each
env's README as a reference baseline.

These are lighter-weight than the paper's canonical
[`skillopt_ckpt/`](../skillopt_ckpt/) skills (fewer optimization epochs, no
`SLOW_UPDATE` tail) — they exist so you have a ready-to-plug artifact for
each of the 5 model families we tested, not just GPT-5.5.

## Layout

```
skillopt_lite_ckpt/
├── searchqa/
│   ├── gpt4o/skill.md
│   ├── gpt5.4/skill.md
│   ├── gpt5.4-mini/skill.md
│   ├── gpt5.4-nano/skill.md
│   └── gpt5.5/skill.md
├── livemath/       (same 5 models)
├── docvqa/         (same 5 models)
├── officeqa/       (gpt-5.4, gpt-5.4-mini, gpt-5.5)
├── spreadsheetbench/ (same 5 models)
└── alfworld/       (gpt-4o, gpt-5.4-mini, gpt-5.4-nano)
```

(Model coverage per env reflects what was optimized in the release train
run; missing cells default to the env's `skills/initial.md`.)

## How to use

Point `run.sh --skill` at any of these files:

```bash
bash copilot_example/livemath/run.sh \
    --skill skillopt_lite_ckpt/livemath/gpt5.4-mini/skill.md \
    --target_model gpt-5.4-mini \
    --eval_limit 20
```

Or `scripts/eval_only.py` directly if you want to evaluate the skill without
producing plugin samples:

```bash
python scripts/eval_only.py \
    --config configs/livemathematicianbench/default.yaml \
    --skill skillopt_lite_ckpt/livemath/gpt5.4-mini/skill.md \
    --split test \
    --target_model gpt-5.4-mini
```

## When to prefer `skillopt_ckpt/` instead

If you specifically want to reproduce the numbers in the SkillOpt paper's
main table, use [`skillopt_ckpt/<env>/gpt5.5_skill.md`](../skillopt_ckpt/) —
those went through the full paper training loop and include the
`SLOW_UPDATE` section.
