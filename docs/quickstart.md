# Quickstart

The one-command path from a fresh clone to a running benchmark.

## 1. Install

```bash
git clone <this-repo>.git && cd <this-repo>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.10+ required.

## 2. Configure LLM auth

Pick one of three modes and populate `.env`:

```bash
cp .env.example .env
$EDITOR .env
```

Then `source ./env.sh` to export vars and sanity-check the mode. See
[authentication.md](authentication.md) for the mode cheat-sheet.

## 3. Download benchmark splits

```bash
python data/download.py                       # all six benchmarks
# or scope to one:
python data/download.py --config livemath
```

For **SearchQA / DocVQA / ALFWorld** you'll also need the underlying corpus
per each benchmark's official source — `download.py` prints instructions.
See [data.md](data.md).

## 4. Smoke-run one benchmark

`livemath` is the fastest sanity check (single-turn multiple-choice, ~30 s
for 5 items):

```bash
bash copilot_example/livemath/run.sh --eval_limit 5 --limit 5
```

This will:

1. Source `copilot_example/env.sh` → top-level `env.sh` → your mode
2. Run `scripts/eval_only.py` on 5 test items
3. Copy `copilot_example/livemath/skills/initial.md` → `workspace/skill.md`
4. Call `make_samples.py` on the produced `results.jsonl` → exports 5
   markdown samples to `workspace/.skillopt/samples/{failed,passed}/`

Success line:

```
[env.sh] mode=azure_cli
[env.sh] endpoint=https://…
…
Wrote: failed=N passed=M
```

## 5. Full run on any benchmark

Drop the limits:

```bash
bash copilot_example/livemath/run.sh                 # ~88 items, several minutes
bash copilot_example/searchqa/run.sh                 # ~1400 items
bash copilot_example/alfworld/run.sh                 # ~134 items, long
bash copilot_example/docvqa/run.sh
bash copilot_example/officeqa/run.sh
bash copilot_example/spreadsheetbench/run.sh        # ~281 items
```

Flags common to every `run.sh`:

| flag | meaning | default |
|---|---|---|
| `--skill PATH`     | starting skill (absolute path)                | env's `skills/initial.md` |
| `--split NAME`     | `train` \| `val` \| `test`                    | `test` |
| `--eval_limit N`   | items sent to the LLM (`0` = full split)      | `0` (varies per env) |
| `--limit M`        | samples exported to `workspace/.skillopt/`    | `20` |
| `--target_model X` | model / deployment name                       | per env README |

## 6. Reproduce paper numbers

```bash
python scripts/eval_only.py \
    --config configs/searchqa/default.yaml \
    --skill skillopt_ckpt/searchqa/gpt5.5_skill.md \
    --split test \
    --target_model gpt-5.5
```

Swap `searchqa`/`gpt5.5_skill.md` for any of the other five benchmarks.

## What next

- Iterate a skill with the **VS Code plugin** — see the top-level `copilot_example/README.md` for the F5 workflow.
- Try a different model — swap `--target_model` and the matching config.
- Optimize your own skill — the training loop ships in a separate release,
  [`harness_example/`](../harness_example/README.md) (coming soon).
