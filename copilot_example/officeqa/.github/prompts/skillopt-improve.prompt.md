---
description: "Read officeqa rollout samples and improve workspace/skill.md (one round, no re-eval)"
agent: "agent"
tools: ['codebase', 'editFiles', 'runCommands']
---

You are running **one round** of SkillOpt improve on the officeqa skill.

## Inputs (paths are relative to this workspace, `copilot_example/officeqa/`)

- Skill file: `workspace/skill.md`
- Failed:    `workspace/.skillopt/samples/failed/*.md`
- Passed:    `workspace/.skillopt/samples/passed/*.md`
- Predictions root (for raw conversations / target prompts):
  `workspace/.skillopt/_eval_run/<latest_ts>/predictions/<task_id>/`
  - `conversation.json` — full ReAct trajectory (tool calls + reasoning)
  - `target_user_prompt.txt` — exact question + oracle-parsed pages
    the agent saw

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
     line to bucket failures into `easy` / `medium` / `hard`. Patch the
     dominant cluster first.
   - **Trace economy.** OfficeQA traces are short (typically 4–12 ReAct
     turns: a few `grep`/`read` calls then an `<answer>`). Read:
     1. The `## Input` (question + `_meta_` + `_sources_`) and
        `## Notes` (fail_reason) of each failed sample first.
     2. The `## Expected` vs `## Agent output` diff — is the agent off
        by a unit (`wrong-scale`), off by a row/period (`wrong-row`),
        or skipping the source entirely (`no-answer-tag`,
        `agent_failed`)?
     3. The **last 3–4 ReAct turns** of the trace — that's where the
        agent committed to the wrong cell or wrote the answer.
     4. For very short traces (≤ 2 turns), read the *whole* trace —
        the agent likely skipped the required `grep`+`read` discipline.
   - Once you have a hypothesis, read 1 `passed/` of the same
     `task_type` to falsify it: does the current skill already handle
     this variant?
   - Stop reading when adding another sample wouldn't change your
     diagnosis.
   - **Reading budget** (caps reasoning depth, not coverage; officeqa
     traces are small):
     | failed/ count | read this many failed | + passed for contrast |
     |---------------|-----------------------|-----------------------|
     | ≤ 4           | all                   | 1                     |
     | 4–10          | 4–6 across task types | 1–2                   |
     | 10–30         | 6–10 across task types| 2                     |
     | > 30          | 8–12 across task types| 2–3                   |
     If a single task type dominates (≥50% of failed), read 4–5 from
     it + 1 from every other observed type. Hard ceiling: **~30KB
     total trace text** (officeqa conversations are small; you can
     afford full traces, but don't expand every one of 30+ samples).
   - In your Diagnosis section below you must report **how many you
     read, which task types, which fail_reasons, and which turn
     ranges** (e.g. "read 6/15 failed across hard (4) + medium (2);
     focused on last 3 turns each; 4/6 are wrong-scale on yen tables").

3. **Diagnose** the most consistent weakness.
   - Cite each finding with sample ids (path) plus the **ReAct turn
     number** or **question text** where the failure pattern appears,
     so the reader can verify.
   - Quote the offending part of `skill.md` that should change.
   - Watch the known failure clusters in
     `.github/copilot-instructions.md` — especially **wrong-scale**
     (the dominant failure: unit/currency conversion forgotten),
     **wrong-row** (off-by-period match), and **skipped tool call**
     (very short trace, hallucinated answer).
   - If multiple failures share a single root cause (e.g. all
     wrong-scale on currencies with non-USD bracketed `[In ...]`
     headers), patch the root, not each symptom.

   **Patch discipline** (mirrors `skillopt/prompts/analyst_*.md`):
   - **Failure-first**: if `failed/` and `passed/` suggest conflicting
     edits, failure-driven fixes win. Don't undo a recurring failure
     to satisfy a single success.
   - **Common patterns only**: propose edits for patterns appearing
     in ≥2 failed tasks. Single-task edge cases → skip.
   - **Generalizable**: never hardcode task-specific values (specific
     company names, fiscal-year numbers, table IDs). Edits must read
     like rules ("when the header says `[In billions of <X>]`,
     multiply the raw cell value by 10^9 before normalising to the
     question's unit").
   - **Prefer worked code/grep snippets over prose.** A 4-line
     `grep → read → convert → write inside <answer>` example beats a
     paragraph of "remember to check units".
   - **Fill gaps, not duplicates**: don't restate something already in
     `skill.md`. If the rule exists but the agent ignored it,
     sharpen it (add a worked example or move it earlier in the file)
     instead of adding a second copy.

4. **Patch** `workspace/skill.md` with the **smallest effective** edit
   (≤4 edits — slightly larger budget than livemath/searchqa is OK
   because office QA skills benefit from concrete worked grep/convert
   snippets, but full rewrites still regress). If you have more than 4
   candidates, pick the ones with the highest support count across
   failed tasks. Use `editFiles` to apply directly — do **not** print
   a diff and stop.

5. **Sanity-check**: re-read `workspace/skill.md` after the edit and
   confirm the passed tasks you read are still consistent with the
   new wording (especially that you haven't broken the "minimum
   tool-call discipline" or "Final Answer Format (STRICT)" sections).

## Output (in chat, after applying)

Use these exact section headers, in order:

### Diagnosis
- First bullet: **sampling report** — how many failed/passed you read,
  which task_types covered, which fail_reasons dominated, and the
  cluster you chose to patch (with support count, e.g. "wrong-scale on
  hard tasks: 5/12 failed").
- 2–4 bullets on the most consistent weakness, each citing ≥1 sample
  id + ReAct turn number or the agent's exact wrong answer.

### Changes applied
- File: `workspace/skill.md`
- Snapshot: `workspace/.skillopt/history/${TS}__before.md`
- One-line bullets describing each edit.

### Expected impact
- Failure modes / task types this addresses.
- Regressions to watch for (especially: did you tighten the unit
  conversion rule in a way that breaks single-table easy questions
  where no conversion is needed?).

### Verify next
```bash
# gate-style: full val, same as /skillopt-loop's gate
bash run.sh --skill workspace/skill.md --split val --eval_limit 0 --limit 0
```
Tell the user to compare the new `hard=` line against the previous
val run under `workspace/.skillopt/_eval_run/`.

## Constraints

- Target model is whatever the user picked via `--target_model` (default
  `gpt-5.5`). Don't change it without an explicit request.
- Do **not** run `run.sh` yourself in this prompt (eval is the user's
  call — use `/skillopt-loop` for closed-loop).
- Do **not** touch anything outside `workspace/`.
- Never edit `skills/initial.md` (it's the baseline).
- The skill explicitly requires `grep`+`read` per numeric question and
  a strict `<answer>...</answer>` output format. Don't water either
  down — they are load-bearing.
- If you would rewrite >40% of the skill, **stop and ask** the user
  to confirm — that's a `lr=large` change and usually regresses.
