# SkillOpt officeqa — Copilot context

You are working in the **officeqa** env of SkillOpt. The workspace root
opened in this VS Code window is `copilot_example/officeqa/`.

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

- `workspaces/<model>/skill.md` — **the skill being optimized** for that model
- `workspaces/<model>/.skillopt/samples/failed/*.md` — failed tasks
- `workspaces/<model>/.skillopt/samples/passed/*.md` — successful tasks
- `workspaces/<model>/.skillopt/history/` — snapshots of `skill.md` before edits
- `workspaces/<model>/.skillopt/_eval_run/<ts>/results.jsonl` — eval output
- `workspaces/<model>/.skillopt/_eval_run/<ts>/predictions/<task_id>/conversation.json` —
  full ReAct trajectory
- `skills/initial.md` — **shared baseline skill** (copied to each model's
  `workspace/skill.md` on first run; read-only reference thereafter)
- `run.sh` — runs eval; auto-selects workspace based on `--target_model`

## Task summary

- **Document-grounded numeric QA**: each task gives a natural-language
  question (e.g. *"As of the end of fiscal year 2003, what was the total
  amount of unrecognized actuarial losses (in millions of yen) for the
  Japanese yen pension plan?"*) plus a small set of source documents (PDF
  pages extracted to `.txt` under `data/officeqa_docs_official/`). The
  agent runs in a **ReAct** loop: `grep` the docs to locate the right
  table row, `read` to pull the column header band + value, convert
  units, and emit a single number inside `<answer>...</answer>`.
- A task has **exactly one** ground-truth numeric (or short-string)
  answer. Scoring is **exact match after light normalisation**
  (strip `$`, `%`, commas; tolerate trailing zeros) — so getting the
  scale wrong (millions vs billions, percent vs ratio) is the most
  common way to lose 1.0 → 0.0.
- **Target model** (default): `gpt-5.5`, reasoning `medium`. The
  `select_endpoint_for_model` helper in `../env.sh` lets you swap to
  `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, or `qwen3.5-9b` without
  touching this folder. See **Switching target models** below.
- **Per-task budget**: up to `max_tool_turns=24` ReAct turns,
  `max_completion_tokens=16384`. There is no per-task hard wall-clock
  timeout (TRAPI rate-limits are the practical cap).
- **Scoring** (`eval_only.py`):
  - `hard` = exact-match correctness (1 or 0). This is the only
    metric `/skillopt-loop`'s gate compares.
  - `soft` = same as `hard` for officeqa (no partial credit). When
    `soft != hard` it's a normalisation edge case (e.g. `1,234.0`
    vs `1234`) — fix is on the scorer, not the skill.

## Sample file format

Each `.md` under `samples/{failed,passed}/`:

```markdown
---
id: UID0042
status: failed | passed
score: 0.0 | 1.0
timestamp: <iso>
env: officeqa
tags: [easy | medium | hard, <fail_reason snippet>]
---
## Input
(natural-language question)
_meta_: task_type=<easy|medium|hard>, n_sources=<N>, oracle_chars=<N>
_sources_: doc1.txt, doc2.txt (+K more)

## Expected
(the gold short answer — usually a single number or short string)

## Agent output
(the agent's final `<answer>...</answer>` payload)

## Trace
<details><summary>Full trajectory</summary>
the conversation.json contents (ReAct turns)
</details>

## Notes
fail_reason: wrong-value | wrong-scale | wrong-row | exec-failed | no-answer-tag | agent-error
```

The trace is loaded from
`_eval_run/<ts>/predictions/<task_id>/conversation.json` and truncated at
8000 chars. Use `## Notes` (`fail_reason`) and the **last 3–6 ReAct turns**
to triage; expand only if you need to see what the agent originally
grepped for.

## Switching target models

Each example supports the full TRAPI deployment matrix via the
`--target_model` flag (see `../env.sh::select_endpoint_for_model`):

| Alias            | TRAPI deployment              | Lane          | When to use                                                |
|------------------|-------------------------------|---------------|------------------------------------------------------------|
| `gpt-5.4-nano`   | `gpt-5.4-nano_2026-03-17`     | `msra/shared` | Fastest/cheapest smoke runs. Hard baseline ≈ 0.05–0.10.    |
| `gpt-5.4-mini`   | `gpt-5.4-mini_2026-03-17`     | `msra/shared` | Mid-tier. Hard baseline ≈ 0.10–0.15.                       |
| `gpt-5.4`        | `gpt-5.4_2026-03-05`          | `msra/shared` | Full 5.4. Hard baseline ≈ 0.16.                            |
| `gpt-5.5`        | `gpt-5.5_2026-04-24`          | `msra/shared` | **Default.** Hard baseline ≈ 0.48; best skill ≈ 0.74.      |
| `qwen3.5-9b`     | `Qwen/Qwen3.5-9B`             | `msra/shared` | OSS comparison. Tool-use weaker; expect a bigger gap.      |

Examples:

```bash
# Quick smoke on the cheapest model
bash run.sh --target_model gpt-5.4-nano --eval_limit 8 --limit 8

# Full val on Qwen for a cross-family comparison
bash run.sh --target_model qwen3.5-9b --split val --eval_limit 0 --limit 0

# Default (gpt-5.5)
bash run.sh --split val --eval_limit 0 --limit 0
```

`select_endpoint_for_model` exports `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_AD_SCOPE`, and `TARGET_DEPLOYMENT`
automatically — you don't need to set them by hand. If you want a non-default
TRAPI lane (e.g. `gcr/shared`), set `SKILLOPT_TRAPI_LANE=gcr/shared` before
calling `run.sh`. **Note**: as of 2026-06 only `msra/shared` works for the
full matrix — `gcr/shared` blocks `gpt-5.4`/`gpt-5.5`, and Qwen only ships
on `msra/shared`.

**Skills are model-specific.** A `skill.md` tuned for `gpt-5.5` (the
seeded `workspace/skill.md` here, hard=0.74) does **not** transfer to
`gpt-5.4` — cross-model evaluation showed it actually scored slightly
*worse* than `gpt-5.4`'s own baseline. Re-run `/skillopt-loop` per target
model if you care about that model's headline number.

## Editing principles for `workspace/skill.md`

1. **Unit / scale guidance is the highest leverage knob.** The dominant
   failure mode is the agent extracting the right cell but reporting it
   in the wrong unit (millions vs billions, raw vs percent, native
   currency vs USD). A 3-line "always re-read the `[In ...]` scale note
   before computing" block usually moves several tasks at once.
2. **Cluster by `task_type`.** Failures fall into:
   - `easy` — single table, single row; failures here mean the skill's
     basic table-reading rules need sharpening.
   - `medium` — multi-row arithmetic (sum / diff across years).
   - `hard` — multi-table / multi-currency / cross-section conversion.
   Patch the dominant cluster first; `easy` fixes rarely help `hard`.
3. **Concrete > abstract.** Replace prose like *"check units"* with a
   worked snippet showing
   `grep -n "FCP-II-1" docs/<id>.txt → read header band → multiply ×1_000_000_000`.
   The model imitates the worked examples in `skill.md` much more
   reliably than declarative rules.
4. **Force the tool-use prefix.** The skill explicitly requires at
   least one `grep` and one `read` per numeric question — keep that
   contract loud at the top of the file. The biggest single-turn failure
   is the agent guessing from the oracle-parsed-pages excerpt without
   re-reading the source.
5. **Cite samples by id** (e.g. `samples/failed/UID0042.md`) plus the
   ReAct turn number where the failure pattern appears, so the diff is
   auditable.
6. **Snapshot before edit.** Always
   `cp workspace/skill.md workspace/.skillopt/history/<ts>__before.md`
   before mutating — the only undo path.
7. **Don't touch `skills/initial.md`.** It's the baseline used for
   round-0 comparison.

## Known failure clusters on officeqa

- **Wrong scale (`wrong-scale`)** — agent reads `123` from a table whose
  header says `[In billions of yen]` and answers `123` (millions) or
  `123,000,000` (raw). Fix: always re-read the bracketed scale note
  *and* convert before computing.
- **Wrong row (`wrong-row`)** — agent matches a similar but
  off-by-one-period row ("end of FY2003" vs "as of Mar 2003"). Fix:
  insist on exact date / period match and re-read neighbouring rows.
- **Wrong column** — multi-column tables with a `(1)(2)(3)(4)` index
  header row plus a label row; agent picks the wrong column. Fix:
  worked example showing the two-header pattern and how to map
  question wording → column index.
- **Skipped tool call (`no-answer-tag`, agent_ok=false)** — agent
  answers directly from the oracle-parsed-pages excerpt without
  running `grep`/`read`. Symptom: very short trace (≤ 2 turns) and a
  hallucinated number. Fix: reinforce the "minimum tool-call
  discipline" block at the top of `skill.md`.
- **Currency-conversion direction** — `<currency> per USD` vs `USD per
  <currency>` confusion. Fix: worked example for each direction.
- **Format violations (`no-answer-tag`)** — agent emits prose around
  the answer, or includes a `%` / `$` / `million` suffix that the
  scorer rejects. Fix: keep the "Final Answer Format (STRICT)" block
  unambiguous and at the *end* of the skill so it's the last thing the
  agent reads before answering.

## Running eval (terminal commands you may issue)

Quick smoke (8 tasks, ~2–4 min on gpt-5.5):
```bash
bash run.sh --eval_limit 8 --limit 8
```

Standard check (24 tasks, ~5–10 min — matches the default sample budget):
```bash
bash run.sh --eval_limit 24 --limit 24
```

Full val (whatever `data/officeqa_split/val/items.csv` contains — what
`/skillopt-loop`'s gate uses):
```bash
bash run.sh --split val --eval_limit 0 --limit 0
```

Full test (only run at end / for final report):
```bash
bash run.sh --split test --eval_limit 0 --limit 0
```

Each run prints `Results: hard=<X> soft=<Y>` — `hard` is what the gate
compares on. For officeqa `soft == hard` in normal cases; a gap means
the scorer normalised differently for those samples (rare, ignore unless
chasing the last point or two).

## Expected scores on the seeded skill

The `workspace/skill.md` shipped with this example is the best skill
produced by a 4-epoch SkillOpt run on `gpt-5.5` (msra/shared,
2026-06-11). Reproducing the headline:

| target model     | initial.md hard | workspace/skill.md hard |
|------------------|-----------------|--------------------------|
| `gpt-5.5`        | 0.4767          | **0.7384** (+26.2 pp)    |
| `gpt-5.4`        | 0.1628          | 0.1570 (no transfer)     |
| `gpt-5.4-mini`   | ~0.00 (smoke)   | ~0.21 (smoke, 24 items)  |
| `gpt-5.4-nano`   | low             | re-run /skillopt-loop    |
| `qwen3.5-9b`     | TBD             | re-run /skillopt-loop    |

The takeaway: **skills are model-specific**. Use the seeded skill as a
strong baseline only for `gpt-5.5`; for any other target run
`/skillopt-loop` against that target from `skills/initial.md`.
