---
description: "Closed-loop livemath SkillOpt: rollout(batch) → improve → gate, repeat for N rounds with auto-rollback and best tracking"
agent: "agent"
argument-hint: "rounds=3 batch=20"
tools: ['codebase', 'editFiles', 'runCommands']
---

Run **${input:rounds:3} rounds** of closed-loop SkillOpt on livemath with a
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

**Target model**: `gpt-5.5` (configured in `run.sh`).

**Split semantics**

| phase           | split   | size           | purpose                                  |
|-----------------|---------|----------------|------------------------------------------|
| improve signal  | `train` | `batch` items  | failure samples that drive the rewrite   |
| gate            | `val`   | full (35)      | accept/reject decision                   |
| final report    | `test`  | full (106)     | held-out generalization, run once at end |

Official split: `data/ablation_splits/livemathematicianbench/2-2-6_seed42`
(train=36 / val=35 / test=106; same as `configs/livemathematicianbench/
default.yaml`). val is a *real* held-out set here — don't read or train on
val items, only gate on them.

Cost note: gate-val on 18 items per round with `gpt-5.5` is cheap (~1–2
min); the final test (124 items) runs exactly once at the end (~7–14 min).

## Setup (round 0 = baseline)

Establish baseline `val_acc_0` AND seed the `best` slot AND produce the first
batch of samples for round 1's improve.

1. **Gate baseline on full val**:
   ```bash
   rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
   bash run.sh --split val --eval_limit 0 --limit 0
   ```
   Read the printed `Results: hard=<X>` line as `val_acc_0`.

2. **Snapshot baseline as initial best**:
   ```bash
   TS0=$(date +%Y%m%d_%H%M%S)
   cp workspace/skill.md workspace/.skillopt/history/round0__${TS0}__best.md
   ```

3. **Seed round-1 samples from a train batch** (use `--seed 1` so round 1
   sees a different 20 items than round 2 etc. — `run.sh` forwards seed to
   `eval_only.py` which subsamples via `random.Random(seed).sample`):
   ```bash
   rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
   bash run.sh --split train --eval_limit ${input:batch:20} --limit ${input:batch:20} --seed 1
   ```
   (We do not gate on this; it only exists to populate `samples/` for the
   next improve.)

4. Track:
   - `current_acc = val_acc_0`
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
Capture `hard=<X>` → `cand_acc`. Compute `Δ = cand_acc − current_acc`.
(Val samples produced here are throwaway; step 5 will overwrite them.)

### 4. Gate decision

Same logic as `skillopt/evaluation/gate.py` (`evaluate_gate`):

| condition                              | action              | side effect |
|----------------------------------------|---------------------|-------------|
| `cand_acc > best_acc`                  | **accept_new_best** | keep skill; snapshot as `__best.md`; update `best_*` |
| `cand_acc > current_acc` (but ≤ best)  | **accept**          | keep skill; do **not** update `best_*` |
| `cand_acc ≤ current_acc`               | **reject**          | rollback skill from `__before.md`; do **not** update `best_*` |

Dead band for noise (val is full so this is mostly belt-and-suspenders):

- `Δ ≥ +0.01` → treat as improvement (accept / accept_new_best as above)
- `Δ ≤ −0.01` → reject (rollback)
- `|Δ| < 0.01` → **flat**: keep skill but do **not** update `current_acc` or
  `best_*`; increment `noop_streak`

Apply the gate:

```bash
# Reject path:
cp workspace/.skillopt/history/round${r}__${TS}__before.md workspace/skill.md
```

```bash
# accept_new_best path (only when cand_acc > best_acc AND Δ ≥ +0.01):
cp workspace/skill.md workspace/.skillopt/history/round${r}__${TS}__best.md
# then update best_acc=cand_acc, best_round=r, best_snapshot=<that path>
```

Update `current_acc`:
- accept_new_best / accept → `current_acc = cand_acc`
- reject → `current_acc` unchanged (skill rolled back)
- flat   → `current_acc` unchanged (noise)

Update streak counters:
- reject → `regression_streak += 1`, `noop_streak = 0`
- flat   → `noop_streak += 1`, `regression_streak = 0`
- accept(_new_best) → both reset to 0

### 5. Produce next round's train samples (always run)
After the gate decision is applied (so `skill.md` on disk is the
accepted/rejected/rolled-back version), regenerate train samples for the
**next** round's improve. Run this **even on reject** so samples match the
on-disk skill, not the rejected candidate. **Use `--seed $((r+1))`** so each
round's improve sees a different slice of train items (not the same 20
over and over):

```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split train \
    --eval_limit ${input:batch:20} --limit ${input:batch:20} \
    --seed $((r+1))
```

(This rollout's hard score is just incidental — we don't gate on it.)

Also snapshot the round's final on-disk skill for audit (regardless of
gate action):

```bash
cp workspace/skill.md workspace/.skillopt/history/round${r}__${TS}__after.md
```

### 6. Stream a one-row progress update
```
r=<r>  val=<cand_acc>  Δ=<+/-Y>  action=<accept_new_best|accept|reject|flat>  best=<best_acc@best_round>  edit=<short summary>
```

## Stopping conditions (any one)

- `${input:rounds:3}` rounds completed.
- `regression_streak ≥ 5` OR `noop_streak ≥ 5`.
- `best_acc ≥ 0.5455` (stale HITL ceiling measured on gpt-5.4 medium; re-baseline once gpt-5.5 baseline is known).
- User cancels.

## After all rounds

### 1. Restore best
If the on-disk skill is not the best (last action was `accept` whose
`current_acc < best_acc`, or `flat`/`reject` after a peak):

```bash
cp <best_snapshot> workspace/skill.md
```

### 2. Final test (held-out, one-shot)
```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split test --eval_limit 0 --limit 0
```
Capture `hard=<X>` → `test_acc`. This is the headline generalization number.

## Final output

```
| round | val_acc  | Δ vs round-0 | action            | edit summary       | best? |
|-------|----------|---------------|-------------------|--------------------|-------|
| 0     | <X>      | —             | (baseline)        | (initial.md)       |  *    |
| 1     | ...      | ...           | accept_new_best   | ...                |       |
| 2     | ...      | ...           | reject (rolled)   | ...                |       |
...
```

(`*` marks the round whose skill is currently on disk as `workspace/skill.md`.)

Then:

### Headline
- **Test accuracy** (full held-out): `test_acc = <X>`
- For comparison: baseline `val_acc_0 = <X>`, best `val_acc = <X>` at round `<r>`.

### Best skill
- `best_acc = <best_acc>` at `best_round = <best_round>` (val)
- Snapshot: `<best_snapshot>`
- `workspace/skill.md` is currently the best revision (restored if necessary).
- To inspect any other round: diff against
  `workspace/.skillopt/history/round<r>__<ts>__before.md`.

### Open questions
- Unaddressed failure clusters (cite sample ids from the latest train rollout).
- Train→val gap, val→test gap if notable.
- Suggested next move (e.g. "bump to `lr=large` for a structural rewrite").

## Constraints

- Target model is `gpt-5.5`. Don't change it without the user explicitly asking.
- **Never delete** files under `workspace/.skillopt/history/`.
- **No-poll discipline for long commands.** Per-round gate is 1–2 min on
  livemath, but final test (124 items) is ~7–14 min. For any
  `bash run.sh` call you expect to take >2 min, do **not** call
  `get_terminal_output` / `ps` / `sleep` in the same turn. Send the
  command, reply briefly with ETA, **end your turn**. The chat host
  auto-injects a `[Terminal <id> notification: command completed]`
  message next turn. Polling burns the iteration budget without
  making the command finish faster.
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
- **Gate uses `--split val --eval_limit 0` (full val = 18)** — that is
  intentional and matches SkillOpt's main flow. Do not shrink it to save
  cost without the user explicitly asking.
- **Train rollouts use `--eval_limit ${input:batch:20}`** — these are just for
  samples, not for gating; never bump to full split inside the loop.
- **Test (`--split test --eval_limit 0`) runs exactly once, after the loop.**
  Never peek at test mid-loop.
- If `run.sh` fails (Azure auth, network, etc.): **stop the loop**, surface
  stderr, do not retry.
- Cap each round at 1 patch attempt — no inner retry loop on a single round.
