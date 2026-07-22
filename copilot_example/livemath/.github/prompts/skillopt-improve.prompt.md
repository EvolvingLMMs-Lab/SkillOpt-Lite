---
description: "Read livemath rollout samples and improve workspace/skill.md (one round, no re-eval)"
agent: "agent"
tools: ['codebase', 'editFiles', 'runCommands']
---

You are running **one round** of SkillOpt improve on the livemath skill.

## Inputs (paths are relative to this workspace, `copilot_example/livemath/`)

- Skill file: `workspace/skill.md`
- Failed:     `workspace/.skillopt/samples/failed/*.md`
- Passed:     `workspace/.skillopt/samples/passed/*.md`

If `workspace/skill.md` doesn't exist or the samples dirs are empty, **stop**
and tell the user to run
`bash run.sh --split train --eval_limit 20 --limit 20` first to populate
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
   - Decide your reading strategy based on what you see:
     - **Cluster first, sample second.** Skim filenames / first lines
       (cheap) to group failed samples by symptom (e.g. similar problem
       types, same wrong-answer pattern). Then sample 1-2 representatives
       per cluster, prioritising bigger clusters. **Goal is symptom
       coverage, not sample coverage** — reading 10/100 across all
       clusters is better than reading 30/100 from one cluster.
     - If `failed/` has ≤5 files, just read all of them.
     - Once you have a hypothesis, read 1-2 `passed/` samples to falsify
       it: does the current skill already handle this case correctly?
     - Stop reading when adding another sample wouldn't change your
       diagnosis.
   - **Reading budget** (scales with batch; this is about reasoning
     depth, not coverage):
     | failed/ count | read this many failed | + passed for contrast |
     |---------------|-----------------------|-----------------------|
     | ≤ 10          | all                   | 1–2                   |
     | 10–30         | 6–10 across clusters  | 1–2                   |
     | 30–100        | 10–15 across clusters | 2–3                   |
     | > 100         | 12–18 across clusters | 2–3                   |
     If a single cluster dominates (≥50% of failed), read 3–4 from it +
     1 from every minor cluster. Hard ceiling: ~25KB total sample text.
   - In your Diagnosis section below you must report **how many you read
     and why** (e.g. "read 4/12 failed across 2 clusters, 1 passed for
     contrast").

3. **Diagnose** the most consistent weakness.
   - Cite each finding with sample ids (path).
   - Quote the offending part of `skill.md` that should change.
   - Group findings into clusters yourself from what you observe in
     `samples/failed/`; do not rely on any pre-labelled taxonomy.

   **Patch discipline** (mirrors `skillopt/prompts/analyst_*.md`):
   - **Failure-first**: if `failed/` and `passed/` suggest conflicting
     edits, failure-driven fixes win. Don't undo a recurring failure to
     satisfy a single success.
   - **Common patterns only**: propose edits for patterns appearing in
     ≥2 failed (or ≥2 passed) samples. Single-sample edge cases → skip.
   - **Generalizable**: never hardcode task-specific values (problem
     numbers, exact strings from one task). Edits must read like rules.
   - **Fill gaps, not duplicates**: don't restate something already in
     `skill.md`. If the rule exists but the agent ignored it, sharpen the
     wording instead of adding a second copy.
   - **Success bias toward reinforcement**: prefer tightening an existing
     section over adding a new top-level header.

4. **Patch** `workspace/skill.md` with the **smallest** edit (≤4 edits,
   prefer additions over rewrites). If you have more than 4 candidates,
   pick the ones with the highest support count. Use `editFiles` to apply
   directly — do **not** print a diff and stop.

5. **Sanity-check**: re-read `workspace/skill.md` after the edit and confirm
   the passed samples you read are still consistent with the new wording.

## Output (in chat, after applying)

Use these exact section headers, in order:

### Diagnosis
- First bullet: **sampling report** — how many failed/passed you read,
  out of how many available, and the criterion you used (recency,
  cluster, exhaustive).
- 2–4 bullets on the most consistent weakness, each citing ≥1 sample id.

### Changes applied
- File: `workspace/skill.md`
- Snapshot: `workspace/.skillopt/history/${TS}__before.md`
- One-line bullets describing each edit.

### Expected impact
- Failure modes this addresses.
- Regressions to watch for (especially answer-format).

### Verify next
```bash
# gate-style: full val, same as /skillopt-loop's gate
bash run.sh --skill workspace/skill.md --split val --eval_limit 0 --limit 0
```
Tell the user to compare the new `hard=` line against the previous val run
under `workspace/.skillopt/_eval_run/`.

## Constraints

- Do **not** run `run.sh` yourself in this prompt (eval is the user's call —
  use `/skillopt-loop` for closed-loop).
- Do **not** touch anything outside `workspace/`.
- Never edit `skills/initial.md` (it's the baseline).
