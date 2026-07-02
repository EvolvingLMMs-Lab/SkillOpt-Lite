# docvqa/

Reference implementation for **DocVQA**: single-turn document-image question
answering. Lifted from `skillopt/envs/docvqa/` for the standalone /skillopt-loop runner.

## Task

- **Input:** a natural-language question + one page image of a UCSF Industry
  Documents PDF (PNG, attached as a data URI / image_url for chat backends, or
  copied into the Codex workspace for exec backends).
- **Agent:** one LLM call. System prompt = `prompts/rollout_system.md` filled
  in with the current skill; user prompt = question + the page image.
- **Output:** answer wrapped in `<answer>...</answer>`.
- **Scoring:** see `evaluator.py` — strict + lenient EM vs. the list of gold
  answers (DocVQA ships multiple acceptable surface forms per question).

## Files

| File | Purpose |
|---|---|
| `rollout.py`   | `process_one(item, skill) -> result` (chat backend or codex-exec) |
| `evaluator.py` | strict/lenient EM against gold answers |
| `adapter.py`   | dataset row → rollout input shape |
| `dataloader.py`| reads a CSV per split from `<split_dir>/{train,val,test}/*.csv` |
| `prompts/rollout_system.md` | agent system prompt template (`{skill_section}` placeholder) |
| `prompts/analyst_*.md`      | legacy reflect prompts (kept for reference, not used by the plugin) |
| `skills/initial.md`         | baseline skill — starting point for the plugin demo |

## Split

This env uses the public **id split** at `data/docvqa_id_split/`:

```
data/docvqa_id_split/
├── split_manifest.json   (manifest_type=id_split, source=lmms-lab/DocVQA)
├── train/items.json      (107 items)
├── val/items.json        ( 53 items)
└── test/items.json       (374 items)
```

Each row carries `questionId`, `docId`, `image_path`, `ucsf_document_id`,
`ucsf_document_page_no`, and `topic`. **It is an id manifest, not the full
payload** — there is no `question` text and no PNG bytes in the manifest.

### Materializing the full split

The dataloader (`dataloader.py`) expects a CSV per split:

```
<split_dir>/{train,val,test}/*.csv
```

with at minimum: `questionId`, `docId`, `question`, `answer` (list-stringified),
`image_path`, optionally `topic` / `ucsf_document_*`. Image files referenced by
`image_path` must exist on disk (default location: `data/docvqa_images/`).

Use the bundled helper to fill both in-place from `lmms-lab/DocVQA`
(HF rev `539088ef…`, config `DocVQA`, split `validation`, filtered to the
manifest's question IDs):

```bash
# Smoke (3 val rows, downloads ≤2 parquet shards)
python scripts/materialize_docvqa_split.py --splits val --limit 3

# Full materialization (107 + 53 + 374 = 534 rows; downloads all 6 val shards)
python scripts/materialize_docvqa_split.py
```

Outputs `data/docvqa_id_split/{train,val,test}/items.csv` and PNG pages at
`data/docvqa_images/q<questionId>_d<docId>.png`. Idempotent: existing images
are skipped unless `--overwrite_images` is passed. Once done, `run.sh` will
proceed past the data-presence guard.

## Generating samples for the plugin

If you already have a DocVQA `results.jsonl`:

```bash
python copilot_example/make_samples.py \
    --results /path/to/docvqa_run/test_eval/results.jsonl \
    --workspace copilot_example/docvqa/workspace \
    --env docvqa --limit 20
```

The exporter handles DocVQA-specific quirks:
- `question` + `task_type` + `image_paths` are summarized in `## Input`
- `gold_answer` (list of acceptable surface forms) flattened to `a | b | c`
  in `## Expected`
- `predicted_answer` / `response` → `## Agent output`
- `fail_reason` is preserved in `## Notes`

## Run the /skillopt-loop

**Open the `copilot_example/docvqa/` folder in your coding agent** (VS Code
Copilot Chat / Codex CLI / Claude Code / kimi-code / glm-code /
deepseek-tui — any host that reads local `.github/prompts/*.prompt.md`),
then **type this at the coding-agent chat prompt** (not a shell terminal):

In `copilot_example/docvqa`, type:

```
/skillopt-loop rounds=2 batch=40 target=gpt-5.4-nano
```

That's the whole loop — your coding agent handles env setup (pip
install, `source ../env.sh`, data download) and then runs `run.sh`,
inspects samples, patches `skill.md`, val-gates, and archives, all on
its own. No manual bootstrap needed.

Manual sample refresh (already have results.jsonl):

```bash
WS=copilot_example/docvqa/workspaces/gpt-5.5
mkdir -p "$WS"
cp copilot_example/docvqa/skills/initial.md "$WS/skill.md"
python copilot_example/make_samples.py \
    --results /path/to/docvqa_run/test_eval/results.jsonl \
    --workspace "$WS" --env docvqa --limit 20
```

`run.sh` flags (same set as `searchqa/run.sh`):

| flag | default |
|---|---|
| `--skill PATH`       | `<workspace>/skill.md` (seeded from `skills/initial.md` on first run) |
| `--workspace DIR`    | `workspaces/<model_short>/` |
| `--split NAME`       | `test` |
| `--eval_limit N`     | `0` (= full split) |
| `--limit N`          | `20` (samples exported) |
| `--target_model`     | `gpt-5.5` |
| `--reasoning`        | `medium` |
| `--workers`          | `16` |
| `--seed`             | `42` |
| `--split_dir DIR`    | `data/docvqa_id_split` |
