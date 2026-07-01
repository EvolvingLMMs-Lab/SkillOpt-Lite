---
description: "Closed-loop spreadsheetbench SkillOpt: rollout(batch) → improve → gate, repeat for N rounds with auto-rollback and best tracking"
agent: "agent"
argument-hint: "rounds=3 batch=40"
tools: ['codebase', 'editFiles', 'runCommands']
---

Run **${input:rounds:3} rounds** of closed-loop SkillOpt on spreadsheetbench
with a proper train/val/test split (mirrors `scripts/train.py`):

```
for r in 1..R:
    improve(samples from prev round's train rollout)   — patch skill.md
    gate-val(full val)                                 — evaluate patched skill → val_acc
    decide: accept_new_best | accept | reject | flat   — rollback on reject
    rollout-train(batch)                               — produce samples for next round
final:
    test(full)                                         — one-shot generalization report
```

**Target model**: `gpt-5.5` (configured in `run.sh`).

**Split semantics**

| phase           | split   | size              | purpose                                  |
|-----------------|---------|-------------------|------------------------------------------|
| improve signal  | `train` | `batch` items     | failed tasks that drive the rewrite      |
| gate            | `val`   | full              | accept/reject decision (held-out)        |
| final report    | `test`  | full              | held-out generalization, run once at end |

Official splits: `data/spreadsheetbench_split` over the
`spreadsheetbench_verified_400` bundle (~400 tasks total; `train` is
typically 80, val/test fill the rest — confirm by `wc` on the JSONs once).
Val is a *real* held-out set — don't read or train on val items, only gate
on them.

Official `batch_size=40` (from `configs/spreadsheetbench/default.yaml`).
The improve step won't read all 40 traces — its reading budget table caps
at ~10–15 across clusters with a 40KB ceiling — but rolling out 40 tasks
per round gives proper cluster signal across the 3 task types
(`cell_level`, `sheet_level`, `other`) and the various fail-reason
buckets (pandas-clobber, A1-confusion, hardcoded-ranges, exec-fail,
timeout).

**⚠️ Cost note**: spreadsheet tasks involve up to 30 ReAct turns + a 600 s
exec timeout per task. On `gpt-5.5` with **32 workers** (default in
`run.sh`):
- Full val ≈ **5–15 min** per gate (depends on val size / how many tasks
  hit timeout).
- Train rollout (40 tasks) ≈ **5–10 min** per round.
- Per-round total ≈ 10–25 min; full 3-round loop + final test
  ≈ **45–90 min**.

If the gpt-5.5 deployment's TPM is throttling, lower with
`--workers 16 --max_api_workers 16`.

## Setup (round 0 = baseline)

Establish baseline `val_acc_0` (hard=all-cases-pass-rate,
soft=case-pass-rate) AND seed the `best` slot AND produce the first batch
of samples for round 1's improve.

1. **Gate baseline on full val**:
   ```bash
   rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
   bash run.sh --split val --eval_limit 0 --limit 0
   ```
   Read `Results: hard=<X> soft=<Y>` → `val_acc_0`, `val_soft_0`.

2. **Snapshot baseline as initial best**:
   ```bash
   TS0=$(date +%Y%m%d_%H%M%S)
   cp workspace/skill.md workspace/.skillopt/history/round0__${TS0}__best.md
   ```

3. **Seed round-1 samples from a train batch** (use `--seed 1` so round 1
   sees a different `batch` tasks than round 2 etc.):
   ```bash
   rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
   bash run.sh --split train --eval_limit ${input:batch:40} --limit ${input:batch:40} --seed 1
   ```
   (We do not gate on this; it only exists to populate `samples/` for the
   next improve. ~5–10 min for 40 tasks on 32 workers.)

4. Track:
   - `current_acc = val_acc_0`, `current_soft = val_soft_0`
   - `best_acc = val_acc_0`, `best_round = 0`,
     `best_snapshot = workspace/.skillopt/history/round0__${TS0}__best.md`
   - `noop_streak = 0`, `regression_streak = 0`

## Per-round procedure (round `r` in `1..${input:rounds:3}`)

### 1. Snapshot the candidate's starting point
```bash
TS=$(date +%Y%m%d_%H%M%S)
cp workspace/skill.md workspace/.skillopt/history/round${r}__${TS}__before.md
```

### 2. Improve (reflect on the LATEST train batch's samples)
Follow [skillopt-improve.prompt.md](./skillopt-improve.prompt.md): explore
`workspace/.skillopt/samples/{failed,passed}/`, diagnose, apply smallest
patch via `editFiles`. These samples were produced by the previous round's
**train rollout** — they reflect the current skill's weaknesses on
training tasks. For exec failures, also look at
`workspace/.skillopt/_eval_run/<latest>/predictions/<task_id>/solution.py`.

### 3. Gate: evaluate the patched skill on full val
```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split val --eval_limit 0 --limit 0
```
Capture `hard=<X>` → `cand_acc`, `soft=<Y>` → `cand_soft`. Compute
`Δ = cand_acc − current_acc`. (Val samples produced here are throwaway;
step 5 will overwrite them.) **~5–15 min on 32 workers.**

### 4. Gate decision

Same logic as `skillopt/evaluation/gate.py` (`evaluate_gate`):

| condition                              | action              | side effect |
|----------------------------------------|---------------------|-------------|
| `cand_acc > best_acc`                  | **accept_new_best** | keep skill; snapshot as `__best.md`; update `best_*` |
| `cand_acc > current_acc` (but ≤ best)  | **accept**          | keep skill; do **not** update `best_*` |
| `cand_acc ≤ current_acc`               | **reject**          | rollback skill from `__before.md`; do **not** update `best_*` |

Dead band for noise (val is small — likely <80 tasks — so per-task
granularity is coarse; use a wider band):

- `Δ ≥ +0.02` → treat as improvement (accept / accept_new_best as above)
- `Δ ≤ −0.02` → reject (rollback)
- `|Δ| < 0.02` → **flat**: keep skill but do **not** update `current_acc` or
  `best_*`; increment `noop_streak`. **EXCEPTION**: if
  `cand_soft − current_soft ≥ +0.05` (case-pass rate moved meaningfully
  even though all-cases-pass didn't), still treat as improvement (accept) —
  the skill is solving more cases per task and may cross the all-pass
  threshold next round. (Wider soft threshold than alfworld because xlsx
  tasks have several cases each, so soft can move a lot without hard
  moving at all.)

Apply the gate:

```bash
# Reject path:
cp workspace/.skillopt/history/round${r}__${TS}__before.md workspace/skill.md
```

```bash
# accept_new_best path (only when cand_acc > best_acc AND Δ ≥ +0.02):
cp workspace/skill.md workspace/.skillopt/history/round${r}__${TS}__best.md
# then update best_acc=cand_acc, best_round=r, best_snapshot=<that path>
```

Update `current_acc` and `current_soft`:
- accept_new_best / accept → both = candidate values
- reject → both unchanged (skill rolled back)
- flat → both unchanged (noise)

Update streak counters:
- reject → `regression_streak += 1`, `noop_streak = 0`
- flat   → `noop_streak += 1`, `regression_streak = 0`
- accept(_new_best) → both reset to 0

### 5. Produce next round's train samples (always run)
After the gate decision is applied (so `skill.md` on disk is the
accepted/rejected/rolled-back version), regenerate train samples for the
**next** round's improve. Run this **even on reject** so samples match the
on-disk skill, not the rejected candidate. **Use `--seed $((r+1))`** so each
round's improve sees a different slice of train tasks:

```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split train \
    --eval_limit ${input:batch:40} --limit ${input:batch:40} \
    --seed $((r+1))
```

(This rollout's scores are incidental — we don't gate on them. ~5–10 min
for 40 tasks on 32 workers.)

Also snapshot the round's final on-disk skill for audit (regardless of
gate action):

```bash
cp workspace/skill.md workspace/.skillopt/history/round${r}__${TS}__after.md
```

### 6. Stream a one-row progress update
```
r=<r>  val_hard=<cand_acc>  val_soft=<cand_soft>  Δ=<+/-Y>  action=<accept_new_best|accept|reject|flat>  best=<best_acc@best_round>  edit=<short summary>
```

## Stopping conditions (any one)

- `${input:rounds:3}` rounds completed.
- `regression_streak ≥ 5` OR `noop_streak ≥ 5`.
- User cancels.

## After all rounds

### 1. Restore best
If the on-disk skill is not the best:

```bash
cp <best_snapshot> workspace/skill.md
```

### 2. Final test (held-out, one-shot)
```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split test --eval_limit 0 --limit 0
```
Capture `hard=<X>` → `test_acc`, `soft=<Y>` → `test_soft`. These are the
headline generalization numbers. **~10–25 min on 32 workers** (test is
typically the biggest split).

## Final output

```
| round | val_hard | val_soft | Δ vs round-0 | action            | edit summary       | best? |
|-------|----------|----------|---------------|-------------------|--------------------|-------|
| 0     | <X>      | <Y>      | —             | (baseline)        | (initial.md)       |  *    |
| 1     | ...      | ...      | ...           | accept_new_best   | ...                |       |
| 2     | ...      | ...      | ...           | reject (rolled)   | ...                |       |
...
```

(`*` marks the round whose skill is currently on disk as `workspace/skill.md`.)

Then:

### Headline
- **Test hard (all cases pass)**: `test_acc = <X>` &nbsp; **soft (case pass rate)**: `test_soft = <Y>`
- For comparison: baseline `val_acc_0 = <X> / val_soft_0 = <Y>`,
  best `val_acc = <X> / val_soft = <Y>` at round `<r>`.

### Best skill
- `best_acc = <best_acc>` at `best_round = <best_round>` (val)
- Snapshot: `<best_snapshot>`
- `workspace/skill.md` is currently the best revision (restored if necessary).
- To inspect any other round: diff against
  `workspace/.skillopt/history/round<r>__<ts>__before.md`.

### Open questions
- Unaddressed task-type clusters (cite `cell_level` / `sheet_level` /
  `other` and which fail_reasons still dominate, with task ids from the
  latest train rollout).
- soft vs hard gap: if `soft − hard` is large and growing, the skill is
  solving most cases but missing on generality (hardcoded values, missed
  edge cases). Worth pushing on "don't hardcode case-1 row counts".
- Train→val gap, val→test gap if notable.
- Suggested next move (e.g. "patch openpyxl-vs-pandas write-back guidance
  for sheet_level cluster").

## Constraints

- Target model is `gpt-5.5`. Don't change it without the user explicitly asking.
- **Never delete** files under `workspace/.skillopt/history/`.
- **No-poll discipline for long commands.** spreadsheet gates / final-test
  take 5–25 min each. After kicking off any `bash run.sh ... --split val`
  or `--split test` (or any rollout >2 min), do **not** call
  `get_terminal_output` / `ps` / `sleep` in the same turn. Instead:
  1. Send the command (sync mode is fine; it'll time out and return a
     terminal id, or you can use async).
  2. Reply briefly in chat with the rough ETA (e.g. "gate val in
     flight, ~5–15 min, waiting for notification").
  3. **End your turn** — do not call any further tools.
  The chat host auto-injects a `[Terminal <id> notification: command
  completed with exit code <N>]` message into the next turn with the full
  output. Pick up there. Polling within the same turn just burns the
  iteration budget without making the command finish faster.
- **Auto-continue on terminal notification.** When a
  `[Terminal <id> notification: command completed ...]` message arrives,
  treat it as a resume signal, **not** as a stopping point. Parse
  `hard=<X> soft=<Y>` from the included output, then **immediately
  continue the loop procedure** in the same turn:
  - Gate (val) finished → do gate decision + next train rollout (which
    will fire another long command and end the turn again) + one-row
    update.
  - Train rollout finished → advance `r += 1` and start the next round
    (snapshot + improve, then fire the next gate command).
  - Final test finished → produce final table + headline; done.
  Only end the turn when (a) you've just kicked off another long
  command, (b) the loop has finished and you've reported results, or
  (c) `run.sh` failed. A successful notification is **never** itself a
  reason to stop.
- **Gate uses `--split val --eval_limit 0` (full val)** — that is
  intentional and matches SkillOpt's main flow. Do not shrink it to save
  cost without the user explicitly asking. If you're prototyping and want
  faster cycles, set `--eval_limit 20` *and tell the user you're deviating
  from the standard gate*.
- **Train rollouts use `--eval_limit ${input:batch:40}`** — these are just
  for samples, not for gating; never bump to full split inside the loop.
- **Test (`--split test --eval_limit 0` = full test) runs exactly once,
  after the loop.** Never peek at test mid-loop.
- If `run.sh` fails (Azure auth, missing data dirs, network, etc.):
  **stop the loop**, surface stderr, do not retry. Especially: if the
  splits / data root are missing, the user needs to install
  `data/spreadsheetbench_split` and `data/spreadsheetbench_verified_400`
  (or pass `--split_dir` / `--data_root`) before re-running.
