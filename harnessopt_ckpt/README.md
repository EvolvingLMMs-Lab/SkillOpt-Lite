# harnessopt_ckpt/ — full snapshot of the optimized harness run

Verbatim end-state of the SkillOpt_Lite harness training loop, preserved so
you can reproduce or study the exact code + skill combination that produced
the reported numbers.

Where [`../harness_example/`](../harness_example/) is the **clean starting
point** (baseline env code + starting skills copied from `copilot_example`
ckpt), `harnessopt_ckpt/` is the **optimized end-state** — same layout, but
with every file exactly as it existed when the loop finished:

- `codegen_agent.py` retains the harness-added feature gates
  (`SPREADSHEETBENCH_HARNESS_NANO`, `_self_introspect`,
  `SPREADSHEETBENCH_TIMEOUT_FALLBACK`) that were tuned during the run.
- `rollout.py`, `react_agent.py`, `adapter.py`, `executor.py` reflect any
  loop-side edits.
- `best_skill_*.md` are the optimized outputs of the loop, one per target
  model.

## What ships now

| Benchmark        | Snapshot                                                       |
| ---------------- | -------------------------------------------------------------- |
| SpreadsheetBench | [`spreadsheetbench/`](spreadsheetbench/) — code + 5 skill files |

Skill files in `spreadsheetbench/`:

| File                              | Target model                     |
| --------------------------------- | -------------------------------- |
| `best_skill_5.5.md`               | gpt-5.5                          |
| `best_skill_5.4.md`               | gpt-5.4                          |
| `best_skill_5.4_harness.md`       | gpt-5.4 (with harness feature-gate variant) |
| `best_skill_mini.md`              | gpt-5.4-mini                     |
| `skill_best_nano.md`              | gpt-5.4-nano                     |

## How to reproduce a run

Direct evaluation with just the skill (uses the stock env in `skillopt/envs/`):

```bash
python scripts/eval_only.py \
    --config configs/spreadsheetbench/default.yaml \
    --skill harnessopt_ckpt/spreadsheetbench/best_skill_5.5.md \
    --split test \
    --split_dir data/spreadsheetbench_split \
    --target_model gpt-5.5
```

Full loop replay against the snapshot code (edits stay isolated to the
snapshot dir):

```bash
cd harnessopt_ckpt/spreadsheetbench
bash run.sh --model gpt-5.4-nano --skill skill_best_nano.md
```

See the `.github/prompts/` inside each snapshot for the exact GitHub Copilot
prompts used by the loop.

## Difference from `../skillopt_ckpt/`

- [`skillopt_ckpt/`](../skillopt_ckpt/)      = paper GPT-5.5 reference skills
  only (one file per benchmark), no code snapshot.
- `harnessopt_ckpt/` (this dir) = per-benchmark full code + multi-model skill
  snapshot from the harness_example training loop.
