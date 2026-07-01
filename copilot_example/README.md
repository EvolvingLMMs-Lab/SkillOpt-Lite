# copilot_example/

**Six benchmarks, each set up so a single `/skillopt-loop` slash command in
GitHub Copilot Chat can iteratively improve `skill.md` for that env.**

```
copilot_example/
├── README.md                ← you are here
├── env.sh                   ← thin auth delegator (sources ../env.sh)
├── make_samples.py          ← results.jsonl → per-item .md (used by the loop)
├── collect_round_metrics.py ← aggregate history/*.json across a loop run
│
├── searchqa/         ← env code + run.sh + skills/ + .github/prompts/
├── livemath/         ← env code + run.sh + skills/ + .github/prompts/
├── docvqa/           ← env code + run.sh + skills/ + .github/prompts/
├── officeqa/         ← env code + run.sh + skills/ + .github/prompts/
├── alfworld/         ← env code + run.sh + skills/ + .github/prompts/
└── spreadsheetbench/ ← run.sh + skills/ + .github/prompts/
                       (env python lives in ../skillopt/envs/spreadsheetbench/)
```

Each env ships two artifacts that matter to end users:

1. `run.sh` — one-command evaluator that calls `scripts/eval_only.py`, writes
   `results.jsonl`, and then invokes `make_samples.py` to expand successes /
   failures into per-item markdown under `workspace/.skillopt/samples/`.
2. `.github/prompts/skillopt-loop.prompt.md` — the VS Code chat slash command
   that drives the closed-loop: run rollouts → inspect samples → patch
   `skill.md` → gate on val → keep or roll back → repeat.

## Run the loop

1. Open the env folder as the VS Code workspace root:
   ```bash
   code copilot_example/livemath
   ```
2. In the Copilot Chat panel, set the mode to **Agent**, then type:
   ```
   /skillopt-loop rounds=3 batch=20
   ```
3. The loop will, per round:
   - call `run.sh --split train --eval_limit batch` (~20 items),
   - inspect `.skillopt/samples/failed/*.md`,
   - propose a `skill.md` patch,
   - re-run `run.sh --split val` as the accept/reject gate,
   - archive every attempt under `workspace/.skillopt/history/`.
4. When it stops improving, the best `skill.md` is at
   `workspace/skill.md`. Evaluate it on test:
   ```bash
   bash run.sh --split test --skill "$(pwd)/workspace/skill.md"
   ```

Argument hints: `/skillopt-loop rounds=<N> batch=<M>`. See each env's
`.github/prompts/skillopt-loop.prompt.md` to change gate discipline, dead-band,
or rollback tag names.

## Run just `run.sh` (no chat, one-shot eval)

```bash
# smoke: 5 items, exports 5 sample .md files
bash copilot_example/livemath/run.sh --eval_limit 5 --limit 5
```

Two flags people confuse:

| flag             | meaning                                              |
| ---------------- | ---------------------------------------------------- |
| `--eval_limit N` | how many split items to actually run through the LLM |
| `--limit M`      | how many sample MDs to export to the workspace       |

Common flags (identical across envs):

| flag              | default                                                   |
| ----------------- | --------------------------------------------------------- |
| `--skill PATH`    | `<workspace>/skill.md` (seeded from `skills/initial.md`)  |
| `--workspace DIR` | `workspaces/<model_short>/` (per-model isolated)          |
| `--split NAME`    | `test`                                                    |
| `--target_model`  | env-specific default (see env's README)                   |
| `--reasoning`     | `medium`                                                  |
| `--split_dir DIR` | env-specific default (from `data/download.py`)            |

## Env quick picks

| env                | best for                                | notes                             |
| ------------------ | --------------------------------------- | --------------------------------- |
| **livemath** ⭐    | cleanest signal, shortest samples       | recommended starting env          |
| `searchqa`         | single-turn open-domain QA              | medium sample length              |
| `docvqa`           | document-image QA                       | requires image cache in `data/`   |
| `officeqa`         | long-doc QA with tool use               | uses `tool_runtime.py`            |
| `spreadsheetbench` | Excel-formula generation                | env code in `skillopt/envs/`      |
| `alfworld`         | long multi-turn embodied trajectories   | hardest — try last                |

## Skip the loop, use a pre-optimized skill

Each env has its baked skills under `../skillopt_lite_ckpt/<env>/<model>/`:

```bash
python scripts/eval_only.py \
    --config configs/livemathematicianbench/default.yaml \
    --skill skillopt_lite_ckpt/livemath/gpt5.4-mini/skill.md \
    --split test \
    --target_model gpt-5.4-mini
```

For paper-canonical GPT-5.5 skills use `../skillopt_ckpt/<env>/gpt5.5_skill.md`
instead. For SpreadsheetBench with the fully-optimized harness (edits code +
skill), use `../harnessopt_ckpt/spreadsheetbench/best_skill_*.md`.

## Adding a new benchmark

1. Copy an existing env folder: `cp -r copilot_example/searchqa copilot_example/<yourenv>`.
2. Replace `dataloader.py`, `adapter.py`, `evaluator.py`, `rollout.py`, and
   the prompts in `prompts/` with your task's logic.
3. Drop a starting `skills/initial.md`.
4. Update `run.sh`'s `--config` and `--split_dir` defaults.
5. Copy `.github/prompts/skillopt-loop.prompt.md` from a sibling env and
   adjust the split sizes referenced inside.

Config lives in `configs/<yourenv>/default.yaml` (see the base at
`configs/_base_/default.yaml`).
