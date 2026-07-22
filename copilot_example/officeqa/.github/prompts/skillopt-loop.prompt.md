---
description: "Closed-loop officeqa SkillOpt: rollout(batch) → improve → gate, repeat for N rounds with auto-rollback and best tracking"
agent: "agent"
argument-hint: "rounds=3 batch=40"
tools: ['codebase', 'editFiles', 'runCommands']
---

Run **${input:rounds:3} rounds** of closed-loop SkillOpt on officeqa
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

**Target model**: default `gpt-5.5` (configured in `run.sh`). To run
the loop against another model in the matrix, pass `--target_model`
through to every `run.sh` invocation below. Supported aliases:
`gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `qwen3.5-9b`.
**Pick one model and stick with it for the whole loop** — mixing
target models invalidates the gate (the skill is being tuned for the
model that produced the samples).

**Split semantics**

| phase           | split   | size              | purpose                                  |
|-----------------|---------|-------------------|------------------------------------------|
| improve signal  | `train` | `batch` items     | failed tasks that drive the rewrite      |
| gate            | `val`   | full              | accept/reject decision (held-out)        |
| final report    | `test`  | full              | held-out generalization, run once at end |

Official splits: `data/officeqa_split/{train,val,test}/items.csv` over
the `officeqa_docs_official` bundle. Train ≈ 100–200 items, val ≈
30–80, test ≈ 100+ — confirm by `wc -l data/officeqa_split/*/items.csv`
once. Val is a real held-out set — don't read or train on val items,
only gate on them.

Official `batch_size=40` (from `configs/officeqa/default.yaml`). The
improve step won't read all 40 traces — its reading budget table caps
at ~8–12 across clusters with a 30KB ceiling — but rolling out 40
tasks per round gives proper cluster signal across the three
task_types (`easy`, `medium`, `hard`) and whatever fail-reason buckets
the harness emits.

**⚠️ Cost note**: officeqa tasks involve up to 24 ReAct turns with
~16k completion tokens per task. On `gpt-5.5` with **16 workers**
(default in `run.sh`):
- Full val ≈ **3–8 min** per gate (depends on val size).
- Train rollout (40 tasks) ≈ **3–6 min** per round.
- Per-round total ≈ 7–15 min; full 3-round loop + final test
  ≈ **30–60 min**.

On `gpt-5.4-nano` cut both numbers roughly in half. On `qwen3.5-9b`
expect 1.5–2× longer per turn (slower TPM).

## Setup (round 0 = baseline)

Establish baseline `val_acc_0` AND seed the `best` slot AND produce
the first batch of samples for round 1's improve.

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

3. **Seed round-1 samples from a train batch** (use `--seed 1` so round
   1 sees a different `batch` tasks than round 2 etc.):
   ```bash
   rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
   bash run.sh --split train --eval_limit ${input:batch:40} --limit ${input:batch:40} --seed 1
   ```
   (We do not gate on this; it only exists to populate `samples/` for
   the next improve. ~3–6 min for 40 tasks on 16 workers.)

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
Follow [skillopt-improve.prompt.md](./skillopt-improve.prompt.md):
explore `workspace/.skillopt/samples/{failed,passed}/`, diagnose, apply
smallest patch via `editFiles`. These samples were produced by the
previous round's **train rollout** — they reflect the current skill's
weaknesses on training tasks. For `agent_failed` / `no-answer-tag`
samples, also look at
`workspace/.skillopt/_eval_run/<latest>/predictions/<task_id>/conversation.json`
in full (those traces are short — the agent gave up early).

### 3. Gate: evaluate the patched skill on full val
```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split val --eval_limit 0 --limit 0
```
Capture `hard=<X>` → `cand_acc`, `soft=<Y>` → `cand_soft`. Compute
`Δ = cand_acc − current_acc`. (Val samples produced here are
throwaway; step 5 will overwrite them.) **~3–8 min on 16 workers.**

### 4. Gate decision

Same logic as `skillopt/evaluation/gate.py` (`evaluate_gate`):

| condition                              | action              | side effect |
|----------------------------------------|---------------------|-------------|
| `cand_acc > best_acc`                  | **accept_new_best** | keep skill; snapshot as `__best.md`; update `best_*` |
| `cand_acc > current_acc` (but ≤ best)  | **accept**          | keep skill; do **not** update `best_*` |
| `cand_acc ≤ current_acc`               | **reject**          | rollback skill from `__before.md`; do **not** update `best_*` |

Dead band for noise (val is small — typically 30–80 tasks — so
per-task granularity is coarse):

- `Δ ≥ +0.02` → treat as improvement (accept / accept_new_best as above)
- `Δ ≤ −0.02` → reject (rollback)
- `|Δ| < 0.02` → **flat**: keep skill but do **not** update
  `current_acc` or `best_*`; increment `noop_streak`. (Soft tracks
  hard exactly for officeqa, so no soft-only acceptance carve-out.)

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
accepted/rejected/rolled-back version), regenerate train samples for
the **next** round's improve. Run this **even on reject** so samples
match the on-disk skill, not the rejected candidate. **Use
`--seed $((r+1))`** so each round's improve sees a different slice of
train tasks:

```bash
rm -rf workspace/.skillopt/samples/failed/* workspace/.skillopt/samples/passed/*
bash run.sh --skill workspace/skill.md --split train \
    --eval_limit ${input:batch:40} --limit ${input:batch:40} \
    --seed $((r+1))
```

(This rollout's scores are incidental — we don't gate on them. ~3–6
min for 40 tasks on 16 workers.)

Also snapshot the round's final on-disk skill for audit (regardless
of gate action):

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
Capture `hard=<X>` → `test_acc`, `soft=<Y>` → `test_soft`. These are
the headline generalization numbers. **~5–15 min on 16 workers**
(test is typically the biggest split).

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
- **Test hard**: `test_acc = <X>` &nbsp; **soft**: `test_soft = <Y>`
- For comparison: baseline `val_acc_0 = <X>`, best
  `val_acc = <X>` at round `<r>`.
- **Reference**: prior gpt-5.5 run on msra/shared achieved
  `test_acc ≈ 0.74` (+26 pp over baseline 0.48).

### Best skill
- `best_acc = <best_acc>` at `best_round = <best_round>` (val)
- Snapshot: `<best_snapshot>`
- `workspace/skill.md` is currently the best revision (restored if necessary).
- To inspect any other round: diff against
  `workspace/.skillopt/history/round<r>__<ts>__before.md`.

### Open questions
- Unaddressed task-type clusters (cite `easy` / `medium` / `hard` and
  which fail_reasons still dominate, with task ids from the latest
  train rollout).
- Train→val gap, val→test gap if notable.
- Cross-model question: if you ran this against anything other than
  `gpt-5.5`, note whether your final skill resembles the shipped
  `workspace/skill.md` (it shouldn't — skills are model-specific).
- Suggested next move (e.g. "add a worked yen→USD conversion snippet
  for the hard cluster").

## Constraints

- **Target model is locked for the whole loop.** Whichever
  `--target_model` you pick for round 0, pass it to every `run.sh`
  in this prompt. The gate / improve / final-test must all use the
  same model.
- **Never delete** files under `workspace/.skillopt/history/`.
- **No-poll discipline for long commands.** officeqa gates / final-test
  take 3–15 min each. After kicking off any `bash run.sh ... --split
  val` or `--split test` (or any rollout >2 min), do **not** call
  `get_terminal_output` / `ps` / `sleep` in the same turn. Instead:
  1. Send the command (sync mode is fine; it'll time out and return a
     terminal id, or you can use async).
  2. Reply briefly in chat with the rough ETA (e.g. "gate val in
     flight, ~3–8 min, waiting for notification").
  3. **End your turn** — do not call any further tools.
  The chat host auto-injects a `[Terminal <id> notification: command
  completed with exit code <N>]` message into the next turn with the
  full output. Pick up there. Polling within the same turn just burns
  the iteration budget without making the command finish faster.
- **Auto-continue on terminal notification.** When a
  `[Terminal <id> notification: command completed ...]` message
  arrives, treat it as a resume signal, **not** as a stopping point.
  Parse `hard=<X> soft=<Y>` from the included output, then
  **immediately continue the loop procedure** in the same turn:
  - Gate (val) finished → do gate decision + next train rollout
    (which will fire another long command and end the turn again) +
    one-row update.
  - Train rollout finished → advance `r += 1` and start the next
    round (snapshot + improve, then fire the next gate command).
  - Final test finished → produce final table + headline; done.
  Only end the turn when (a) you've just kicked off another long
  command, (b) the loop has finished and you've reported results, or
  (c) `run.sh` failed. A successful notification is **never** itself
  a reason to stop.
- **Gate uses `--split val --eval_limit 0` (full val)** — that is
  intentional and matches SkillOpt's main flow. Do not shrink it to
  save cost without the user explicitly asking. If you're prototyping
  and want faster cycles, set `--eval_limit 20` *and tell the user
  you're deviating from the standard gate*.
- **Train rollouts use `--eval_limit ${input:batch:40}`** — these are
  just for samples, not for gating; never bump to full split inside
  the loop.
- **Test (`--split test --eval_limit 0` = full test) runs exactly
  once, after the loop.** Never peek at test mid-loop.
- If `run.sh` fails (Azure auth, missing data dirs, network, etc.):
  **stop the loop**, surface stderr, do not retry. Especially: if
  the splits / docs root are missing, the user needs to install
  `data/officeqa_split` and `data/officeqa_docs_official` (or pass
  `--split_dir` / `--data_root`) before re-running. The officeqa
  dataset is gated on HuggingFace; license must be accepted manually.
