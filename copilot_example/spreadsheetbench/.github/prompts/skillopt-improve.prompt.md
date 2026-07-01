---
description: "Read spreadsheetbench rollout samples and improve workspace/skill.md (one round, no re-eval)"
agent: "agent"
tools: ['codebase', 'editFiles', 'runCommands']
---

You are running **one round** of SkillOpt improve on the spreadsheetbench
skill.

## Inputs (paths are relative to this workspace, `copilot_example/spreadsheetbench/`)

- Skill file: `workspace/skill.md`
- Failed:    `workspace/.skillopt/samples/failed/*.md`
- Passed:    `workspace/.skillopt/samples/passed/*.md`
- Predictions root (for raw conversations / scripts):
  `workspace/.skillopt/_eval_run/<latest_ts>/predictions/<task_id>/`
  - `conversation.json` — full ReAct trajectory
  - `solution.py` — the last script the agent generated
  - `target_user_prompt.txt` — exact instruction the agent saw

If `workspace/skill.md` doesn't exist or the samples dirs are empty, **stop**
and tell the user to run
`bash run.sh --split train --eval_limit 40 --limit 40` first to populate
samples (or use `/skillopt-loop` which handles the full setup).

## Procedure

1. **Snapshot** the current skill (run once, remember `TS`):
   ```bash
   TS=$(date +%Y%m%d_%H%M%S)
   cp workspace/skill.md workspace/.skillopt/history/${TS}__before.md
   ```

2. **Explore the samples** (use your file tools — `list_dir`, `read_file`):
   - Always read `workspace/skill.md` in full.
   - List `workspace/.skillopt/samples/failed/` and
     `workspace/.skillopt/samples/passed/` to see counts and filenames first.
   - **Cluster by `task_type` first.** Skim sample frontmatter `tags:`
     line to bucket failures into `cell_level` / `sheet_level` / `other`.
     Patch the dominant cluster first.
   - **Trace economy.** Spreadsheet ReAct traces are long but have a
     predictable shape: explore → write `solution.py` → execute → maybe
     fix-and-retry. Read:
     1. The `## Input` (instruction) and `## Notes` (fail_reason) of each
        failed sample first.
     2. The **last 3–6 ReAct turns** of the trace — that's where the
        agent gave up or wrote the broken script.
     3. For `phase=exec` failures, read
        `_eval_run/<latest>/predictions/<id>/solution.py` directly — the
        bug is almost always in there, not in the chat.
     4. For `phase=agent` failures (hit max_turns without producing a
        passing script), read the conversation tail to see what the
        agent kept getting stuck on (usually inspecting the wrong sheet
        or the wrong cells).
   - Once you have a hypothesis, read 1 `passed/` of the same task type
     to falsify it: does the current skill already handle this variant?
   - Stop reading when adding another sample wouldn't change your
     diagnosis.
   - **Reading budget** (caps reasoning depth, not coverage; xlsx traces
     are larger than QA samples):
     | failed/ count | read this many failed | + passed for contrast |
     |---------------|-----------------------|-----------------------|
     | ≤ 4           | all                   | 1                     |
     | 4–10          | 4–6 across task types | 1–2                   |
     | 10–30         | 5–8 across task types | 2                     |
     | > 30          | 6–10 across task types| 2–3                   |
     If a single task type dominates (≥50% of failed), read 3–4 from it +
     1 from every other observed type. Hard ceiling: **~40KB total trace
     text** (don't expand every conversation.json — sample them).
   - In your Diagnosis section below you must report **how many you read,
     which task types, which fail_reasons, and which turn ranges /
     `solution.py` files** (e.g. "read 5/12 failed across cell_level
     (3) + sheet_level (2); inspected solution.py for 2 exec-fail
     samples; focused on last 4 ReAct turns each").

3. **Diagnose** the most consistent weakness.
   - Cite each finding with sample ids (path) plus the **ReAct turn
     number** or **specific line in `solution.py`** where the failure
     pattern appears, so the reader can verify.
   - Quote the offending part of `skill.md` that should change.
   - Watch the known failure clusters in
     `.github/copilot-instructions.md` — especially **`pandas.to_excel`
     formula loss**, **A1 vs (row, col) confusion**, and **hardcoded
     ranges** (the `n_pass < n_cases` smell).
   - If `hard=0` for a task but `soft>0`, the agent solved some cases
     but not all — fix is about generality (avoid hardcoding case-1's
     row count), not about correctness from scratch.

   **Patch discipline** (mirrors `skillopt/prompts/analyst_*.md`):
   - **Failure-first**: if `failed/` and `passed/` suggest conflicting
     edits, failure-driven fixes win. Don't undo a recurring failure to
     satisfy a single success.
   - **Common patterns only**: propose edits for patterns appearing in
     ≥2 failed tasks. Single-task edge cases → skip.
   - **Generalizable**: never hardcode task-specific values (specific
     sheet names, column letters, row counts). Edits must read like
     rules ("when the instruction names a sheet, use
     `wb[sheet_name]`; only fall back to `wb.active` when no sheet is
     named").
   - **Prefer code snippets over prose.** A 6-line example
     (`load → modify → save`) beats a paragraph of "remember to preserve
     formatting".
   - **Fill gaps, not duplicates**: don't restate something already in
     `skill.md`. If the rule exists but the agent ignored it, sharpen it
     (e.g. add a worked example or move it earlier in the file) instead
     of adding a second copy.

4. **Patch** `workspace/skill.md` with the **smallest effective** edit
   (≤4 edits — slightly larger budget than livemath/searchqa is OK
   because xlsx skills benefit from concrete code snippets, but full
   rewrites still regress). If you have more than 4 candidates, pick
   the ones with the highest support count across failed tasks. Use
   `editFiles` to apply directly — do **not** print a diff and stop.

5. **Sanity-check**: re-read `workspace/skill.md` after the edit and
   confirm the passed tasks you read are still consistent with the new
   wording (especially that you haven't broken the openpyxl /
   pandas-write-back guidance).

## Output (in chat, after applying)

Use these exact section headers, in order:

### Diagnosis
- First bullet: **sampling report** — how many failed/passed you read,
  which task_types covered, which fail_reasons dominated, and the
  cluster you chose to patch (with support count, e.g. "cell_level
  pandas-clobber: 4/9 failed").
- 2–4 bullets on the most consistent weakness, each citing ≥1 sample id
  + ReAct turn number or `solution.py` line.

### Changes applied
- File: `workspace/skill.md`
- Snapshot: `workspace/.skillopt/history/${TS}__before.md`
- One-line bullets describing each edit.

### Expected impact
- Failure modes / task types this addresses.
- Regressions to watch for (especially: did you tighten library guidance
  in a way that hurts a different task type?).

### Verify next
```bash
# gate-style: full val, same as /skillopt-loop's gate
bash run.sh --skill workspace/skill.md --split val --eval_limit 0 --limit 0
```
Tell the user to compare the new `hard=` (and `soft=`) line against the
previous val run under `workspace/.skillopt/_eval_run/`.

## Constraints

- Target model is **`gpt-5.5`** (configured in `run.sh`). Don't change it.
- Do **not** run `run.sh` yourself in this prompt (eval is the user's call —
  use `/skillopt-loop` for closed-loop).
- Do **not** touch anything outside `workspace/`.
- Never edit `skills/initial.md` (it's the baseline).
- The skill explicitly forbids libraries other than `openpyxl` / `pandas`.
  Don't introduce examples using anything else.
- If you would rewrite >40% of the skill, **stop and ask** the user to
  confirm — that's a `lr=large` change and usually regresses.
