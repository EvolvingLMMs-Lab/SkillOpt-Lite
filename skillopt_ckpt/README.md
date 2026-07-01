# skillopt_ckpt/ — paper reference skills (GPT-5.5)

Paper Table 1 GPT-5.5 optimized skills, one per benchmark. Plug into
`scripts/eval_only.py` to reproduce the reported numbers without re-running
the training loop.

## What's here

| Benchmark              | Skill artifact                                | Matching config                                     |
|------------------------|-----------------------------------------------|-----------------------------------------------------|
| SearchQA               | `skillopt_ckpt/searchqa/gpt5.5_skill.md`      | `configs/searchqa/default.yaml`                     |
| ALFWorld               | `skillopt_ckpt/alfworld/gpt5.5_skill.md`      | `configs/alfworld/default.yaml`                     |
| DocVQA                 | `skillopt_ckpt/docvqa/gpt5.5_skill.md`        | `configs/docvqa/default.yaml`                       |
| LiveMathematicianBench | `skillopt_ckpt/livemath/gpt5.5_skill.md`      | `configs/livemathematicianbench/default.yaml`       |
| OfficeQA               | `skillopt_ckpt/officeqa/gpt5.5_skill.md`      | `configs/officeqa/default.yaml`                     |
| SpreadsheetBench       | `skillopt_ckpt/spreadsheetbench/gpt5.5_skill.md` | `configs/spreadsheetbench/default.yaml`          |

Each file is plain Markdown (~2k–13k chars). It contains a protected
`SLOW_UPDATE` section at the end that holds epoch-wise longitudinal
guidance — that's expected, not a formatting issue.

For the multi-model harness-optimized SpreadsheetBench skills
(`best_skill_5.4.md`, `best_skill_5.5.md`, `best_skill_mini.md`,
`skill_best_nano.md`, `best_skill_5.4_harness.md`), see
[`../harnessopt_ckpt/spreadsheetbench/`](../harnessopt_ckpt/spreadsheetbench/).

## How to evaluate

```bash
python scripts/eval_only.py \
    --config configs/searchqa/default.yaml \
    --skill skillopt_ckpt/searchqa/gpt5.5_skill.md \
    --split test \
    --split_dir data/searchqa \
    --target_model gpt-5.5
```

Substitute the benchmark, config, skill path, and `--split_dir` to evaluate
any of the other five. Splits are hydrated by `python data/download.py`
from HuggingFace.

## Difference vs `skillopt_lite_ckpt/`

- `skillopt_ckpt/`      = paper GPT-5.5 skills only, full training loop
- `skillopt_lite_ckpt/` = shorter loop, 5 model families (gpt-4o through gpt-5.5)
