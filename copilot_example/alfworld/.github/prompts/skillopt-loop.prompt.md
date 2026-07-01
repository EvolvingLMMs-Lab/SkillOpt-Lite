---
description: "Closed-loop alfworld SkillOpt: rollout(batch) → improve → gate, repeat for N rounds with auto-rollback and best tracking"
agent: "agent"
argument-hint: "rounds=3 batch=40"
tools: ['codebase', 'editFiles', 'runCommands']
---

Run **${input:rounds:3} rounds** of closed-loop SkillOpt on alfworld with a
proper train/val/test split (mirrors `scripts/train.py`):

```
for r in 1..R:
    improve(samples from prev round's train rollout)   — patch skill.md
    gate-val(full val)                                 — evaluate patched skill → val_acc
    decide: accept_new_best | accept | reject | flat   — rollback on reject
    rollout-train(batch)                               — produce samples for next round
final:
    test(full)                                         — one-shot generalization report
```

**Target model**: `gpt-5.4-nano` (configured in `run.sh`).

**Split semantics**

| phase           | split   | size           | purpose                                  |
|-----------------|---------|----------------|------------------------------------------|
| improve signal  | `train` | `batch` items  | failed episodes that drive the rewrite   |
| gate            | `val`   | full (140)     | accept/reject decision (held-out)        |
| final report    | `test`  | full (134)     | held-out generalization, run once at end |

Official split: `data/alfworld_split_200_140_134_seed42`
(train=200 / val=140 / test=134). val is a *real* held-out set here — don't
read or train on val items, only gate on them.

Official `batch_size=40` (from `configs/_base_/default.yaml`, alfworld
doesn't override). The improve step won't read all 40 traces — its reading
budget table caps at ~10–15 across clusters with a 40KB ceiling — but
rolling out 40 episodes per round gives proper cluster signal across the
6 ALFWorld task types (Pick&Place, Pick Two&Place, Examine in Light,
Clean&Place, Heat&Place, Cool&Place). With `batch=8` you usually get 1–2
episodes per type, which is below the "common pattern ≥2 samples"
threshold the improve prompt uses.

**⚠️ Cost note**: alfworld episodes are long (20–50 turns each). On
`gpt-5.4-nano` with **128 workers** (default in `run.sh`):
- Full val/test (140 / 134 ep) ≈ **3–6 min** per gate / final test
- Train rollout (40 ep) ≈ **2–4 min** per round (likely 1 wave of 40)
- Per-round total ≈ 5–10 min; full 3-round loop + final test ≈ **20–40 min**

If the nano deployment's TPM is throttling, lower with
`--workers 32 --max_api_workers 32` (still 4× the old default of 8).

## Setup (round 0 = baseline)

Establish baseline `val_acc_0` (hard=success-rate, soft=goal-condition-rate)
AND seed the `best` slot AND produce the first batch of samples for
round 1's improve.

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
   sees a different `batch` episodes than round 2 etc. — `run.sh` forwards
   seed to `eval_only.py` which subsamples via
   `random.Random(seed).sample`):
   ```bash
   rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
   bash run.sh --split train --eval_limit ${input:batch:40} --limit ${input:batch:40} --seed 1
   ```
   (We do not gate on this; it only exists to populate `samples/` for the
   next improve. ~2–4 min for 40 ep on 128 workers.)

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
**train rollout** — they reflect the current skill's weaknesses on training
items.

### 3. Gate: evaluate the patched skill on full val
```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split val --eval_limit 0 --limit 0
```
Capture `hard=<X>` → `cand_acc`, `soft=<Y>` → `cand_soft`. Compute
`Δ = cand_acc − current_acc`. (Val samples produced here are throwaway;
step 5 will overwrite them.) **~3–6 min on 128 workers.**

### 4. Gate decision

Same logic as `skillopt/evaluation/gate.py` (`evaluate_gate`):

| condition                              | action              | side effect |
|----------------------------------------|---------------------|-------------|
| `cand_acc > best_acc`                  | **accept_new_best** | keep skill; snapshot as `__best.md`; update `best_*` |
| `cand_acc > current_acc` (but ≤ best)  | **accept**          | keep skill; do **not** update `best_*` |
| `cand_acc ≤ current_acc`               | **reject**          | rollback skill from `__before.md`; do **not** update `best_*` |

Dead band for noise (val=140 episodes, so success-rate granularity is
≈0.007; the band is wider than that to absorb stochasticity):

- `Δ ≥ +0.02` → treat as improvement (accept / accept_new_best as above)
- `Δ ≤ −0.02` → reject (rollback)
- `|Δ| < 0.02` → **flat**: keep skill but do **not** update `current_acc` or
  `best_*`; increment `noop_streak`. **EXCEPTION**: if
  `cand_soft − current_soft ≥ +0.03` (goal-condition rate moved
  meaningfully even though full-task success didn't), still treat as
  improvement (accept) — the skill is satisfying more sub-goals and may
  cross the success threshold next round.

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
round's improve sees a different slice of train episodes:

```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split train \
    --eval_limit ${input:batch:40} --limit ${input:batch:40} \
    --seed $((r+1))
```

(This rollout's scores are incidental — we don't gate on them. ~2–4 min
for 40 ep on 128 workers.)

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
headline generalization numbers. **~3–6 min on 128 workers.**

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
- **Test hard (success-rate)**: `test_acc = <X>` &nbsp; **soft (goal-condition)**: `test_soft = <Y>`
- For comparison: baseline `val_acc_0 = <X> / val_soft_0 = <Y>`,
  best `val_acc = <X> / val_soft = <Y>` at round `<r>`.

### Best skill
- `best_acc = <best_acc>` at `best_round = <best_round>` (val)
- Snapshot: `<best_snapshot>`
- `workspace/skill.md` is currently the best revision (restored if necessary).
- To inspect any other round: diff against
  `workspace/.skillopt/history/round<r>__<ts>__before.md`.

### Open questions
- Unaddressed task-type clusters (cite which of the 6 ALFWorld task types
  still fail and at what rate, with sample ids from the latest train
  rollout).
- soft vs hard gap: if `soft − hard` is large and growing, the skill is
  satisfying more sub-conditions but missing final completion. Worth
  pushing on end-game / `put` step instructions.
- Train→val gap, val→test gap if notable.
- Suggested next move (e.g. "patch action-format examples for Clean & Place").

## Constraints

- Target model is `gpt-5.4-nano`. Don't change it without the user explicitly asking.
- **Never delete** files under `workspace/.skillopt/history/`.
- **No-poll discipline for long commands.** alfworld gates / final-test
  take 3–6 min each. After kicking off any `bash run.sh ... --split val`
  or `--split test` (or any rollout >2 min), do **not** call
  `get_terminal_output` / `ps` / `sleep` in the same turn. Instead:
  1. Send the command (sync mode is fine; it'll time out and return a
     terminal id, or you can use async).
  2. Reply briefly in chat with the rough ETA (e.g. "gate val=140 in
     flight, ~3–6 min, waiting for notification").
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
  - If the completed command was a **gate (val)**: do step 4 (gate
    decision), step 5 (next train rollout — fires another long command
    and ends turn again), and step 6 (one-row update).
  - If the completed command was a **train rollout**: advance `r += 1`
    and start the next round's step 1 (snapshot) + step 2 (improve).
    The improve step runs locally (no long bash), so don't end the turn
    after improve; flow straight into the next gate command.
  - If the completed command was the **final test**: produce the final
    output table and headline; loop is done.
  Only end the turn when (a) you've just kicked off another long
  command, or (b) the loop has finished and you've reported results, or
  (c) `run.sh` failed (surface stderr and stop). Receiving a successful
  notification is **never** itself a reason to stop.
- **Gate uses `--split val --eval_limit 0` (full val = 140)** — that is
  intentional and matches SkillOpt's main flow. Do not shrink it to save
  cost without the user explicitly asking. If you're prototyping and want
  faster cycles, set `--eval_limit 40` *and tell the user you're deviating
  from the standard gate*.
- **Train rollouts use `--eval_limit ${input:batch:40}`** — these are just
  for samples, not for gating; never bump to full split inside the loop.
- **Test (`--split test --eval_limit 0` = full 134) runs exactly once,
  after the loop.** Never peek at test mid-loop.
- If `run.sh` fails (Azure auth, ALFWORLD_DATA missing, network, etc.):
  **stop the loop**, surface stderr, do not retry.
