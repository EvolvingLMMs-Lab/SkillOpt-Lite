---
description: "Read alfworld rollout samples and improve workspace/skill.md (one round, no re-eval)"
agent: "agent"
tools: ['codebase', 'editFiles', 'runCommands']
---

You are running **one round** of SkillOpt improve on the alfworld skill.

## Inputs (paths are relative to this workspace, `copilot_example/alfworld/`)

- Skill file: `workspace/skill.md`
- Failed:     `workspace/.skillopt/samples/failed/*.md`
- Passed:     `workspace/.skillopt/samples/passed/*.md`

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
   - Decide your reading strategy based on what you see:
     - **Cluster by task type first.** Skim filenames + `## Input` lines
       to bucket episodes into the 6 ALFWorld task types (Pick & Place,
       Pick Two & Place, Examine in Light, Clean & Place, Heat & Place,
       Cool & Place). Patch the weakest cluster first.
     - **Trace economy.** ALFWorld traces are long (20–50 turns each, up
       to 8000 chars). Read `## Notes` (`fail_reason`) and the **last
       5–10 turns** of each trace first — that's usually where the agent
       gave up or repeated itself. Only expand the full trace when you
       can't explain the failure from the tail.
     - If `failed/` has ≤4 episodes, read all of them.
     - Once you have a hypothesis, read 1 `passed/` of the same task type
       to falsify it: does the current skill already handle this variant?
     - Stop reading when adding another sample wouldn't change your
       diagnosis.
   - **Reading budget** (smaller than livemath/searchqa because traces
     are huge; this is about reasoning depth, not coverage):
     | failed/ count | read this many failed | + passed for contrast |
     |---------------|-----------------------|-----------------------|
     | ≤ 4           | all                   | 1                     |
     | 4–10          | 4–6 across task types | 1–2                   |
     | 10–30         | 5–8 across task types | 2                     |
     | > 30          | 6–10 across task types| 2–3                   |
     If a single task type dominates (≥50% of failed), read 3–4 from it +
     1 from every other observed type. Hard ceiling: **~40KB total trace
     text** (traces are larger than QA samples).
   - In your Diagnosis section below you must report **how many you read,
     which task types, and which turn ranges** (e.g. "read 4/9 failed
     across Clean & Place / Heat & Place, focused on last 8 turns each").

3. **Diagnose** the most consistent weakness.
   - Cite each finding with sample ids (path) and the **turn number**
     where the failure pattern appears (so the reader can verify).
   - Quote the offending part of `skill.md` that should change.
   - Watch the known failure clusters in
     `.github/copilot-instructions.md` — especially **action-format
     violations** and **missing transform steps**.
   - If `hard=0` for an episode but `soft>0`, the agent made progress —
     the fix is usually about the last few turns, not the whole plan.

   **Patch discipline** (mirrors `skillopt/prompts/analyst_*.md`):
   - **Failure-first**: if `failed/` and `passed/` suggest conflicting
     edits, failure-driven fixes win. Don't undo a recurring failure to
     satisfy a single success.
   - **Common patterns only**: propose edits for patterns appearing in
     ≥2 failed episodes (or ≥2 passed). Single-episode edge cases → skip.
   - **Generalizable**: never hardcode task-specific values (specific
     object/receptacle ids like `apple 1`, `cabinet 3`). Edits must read
     like rules ("when multiple instances of X are visible, prefer the
     one not already on the target receptacle").
   - **Fill gaps, not duplicates**: don't restate something already in
     `skill.md`. If the rule exists but the agent ignored it, sharpen the
     wording (e.g. add a worked example) instead of adding a second copy.
   - **Success bias toward reinforcement**: prefer tightening an existing
     section over adding a new top-level header.

4. **Patch** `workspace/skill.md` with the **smallest effective** edit
   (≤4 edits — slightly larger than livemath/searchqa is OK because
   ALFWorld rewards are sparser, but full rewrites still regress). If you
   have more than 4 candidates, pick the ones with the highest support
   count across failed episodes. Use `editFiles` to apply directly — do
   **not** print a diff and stop.

5. **Sanity-check**: re-read `workspace/skill.md` after the edit and confirm
   the passed episodes you read are still consistent with the new wording
   (especially that you haven't broken the action-format examples).

## Output (in chat, after applying)

Use these exact section headers, in order:

### Diagnosis
- First bullet: **sampling report** — how many failed/passed you read,
  which task types covered, which turn ranges, and the cluster you chose
  to patch (with support count, e.g. "Heat & Place: 4/9 failed").
- 2–4 bullets on the most consistent weakness, each citing ≥1 sample id
  + turn number.

### Changes applied
- File: `workspace/skill.md`
- Snapshot: `workspace/.skillopt/history/${TS}__before.md`
- One-line bullets describing each edit.

### Expected impact
- Failure modes / task types this addresses.
- Regressions to watch for (especially action-format and other task types
  the skill mentions).

### Verify next
```bash
# gate-style: full val, same as /skillopt-loop's gate (~3–6 min on 128 workers)
bash run.sh --skill workspace/skill.md --split val --eval_limit 0 --limit 0
```
Tell the user to compare the new `hard=` (and `soft=`) line against the
previous val run under `workspace/.skillopt/_eval_run/`.

## Constraints

- Target model is **`gpt-5.4-nano`** (configured in `run.sh`). Don't change it.
- Do **not** run `run.sh` yourself in this prompt (eval is the user's call —
  use `/skillopt-loop` for closed-loop).
- Do **not** touch anything outside `workspace/`.
- Never edit `skills/initial.md` (it's the baseline).
- If you would rewrite >40% of the skill, **stop and ask** the user to
  confirm — that's a `lr=large` change and usually regresses on alfworld.
