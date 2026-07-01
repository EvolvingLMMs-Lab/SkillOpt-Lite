---
description: "Closed-loop harness-opt on spreadsheetbench-local: edit harness Python code only (skill is denylist; route skill rewrites to /skillopt-loop) → smoke val=5 → full val gate, repeat for N rounds with git-tag rollback."
agent: "agent"
argument-hint: "rounds=2 batch=12"
tools: ['codebase', 'editFiles', 'runCommands']
---

Run **${input:rounds:2} rounds** of closed-loop harness-opt on
**spreadsheetbench-local** (`harness_example/spreadsheetbench/`). Treat
**only the harness Python code** as the optimisation target this
round; skill files (`skills/initial.md`,
`workspaces/<model>/skill.md`) are read-only context and live in the
**denylist** — skill rewrites are handled by the `/skillopt-loop`
slash command. The loop decides per round which code file(s) move the
score:

```
round 0 (bootstrap — full-coverage scan + design pass + user approval):
    git tag baseline        — capture starting harness state
    gate-val(full val=39)   — baseline val_hard_0 (number to beat)
    rollout-train(FULL=80)  — full failure coverage for the design pass
    inline recon            — mode (single|multi|react), tool inventory,
                              turn budget, exec_timeout, current skill.md
                              (skill is read-only context here)
    subagent(failure-scan)  — 1× Explore thorough → failure taxonomy
                              (reads ~50+ failed sample .md files → 4–8 clusters)
    design pass             — main agent, 5 lenses inline (tools(add/modify),
                              prompt-context, loop-policy, codegen-shape,
                              memory), A / E have explicit Y/N decisions;
                              skill-content clusters flagged for /skillopt-loop
    synthesize              — main agent picks plan around 3 explicit decisions:
                              (1) add memory? (2) add tool? (3) other code edits
    *** USER BRIEFING ***   — print brief + end turn; wait for user reply:
                              approve | approve with edits | skip <decision>
                              | redesign | abort.  NO patch yet.
    apply patch             — editFiles over {rollout, react_agent, codegen_agent,
                              executor, recalc_harness, adapter}.py
    diff guard              — allowlist check; auto-reject if any skill file moved
    git commit + tag round-0-best   (message cites the 3 approved decisions)
    debug batch(train=6)    — smoke-test the bootstrap; not a gate
    seed round-1 samples    — batch=${input:batch:12}, --seed 1; round 1's improve reads this

for r in 1..R:
    git tag round-${r}-before
    pick surface (inline)   — memory|tool|other-code chosen from
                              cluster_residuals + tried_surfaces (5-line block, no subagent)
    improve(surface)        — patch any allowlist code file
    diff guard              — auto-reject if denylist file touched (including any skill file)
    smoke-val(=5)           — catch import errors / crashes BEFORE the long gate
    gate-val(full val=39)   — accept_new_best | accept | reject | flat (dead band ±0.05; val is small)
    rollback on reject      — git reset --hard round-${r}-before
    rollout-train(batch)    — samples for next round (skipped on the last round)
    one-row progress        — includes surface= so the trajectory is scannable

final:
    git checkout best tag → harness_example/spreadsheetbench/ is the harness from best round
    test(full=281)          — held-out generalization (LONG: 20-60 min, run once)
```

**Target model**: `gpt-5.4-nano` (configured in `run.sh`; baseline is
expected to be very low — spreadsheetbench is hard for nano. Target
after harness-opt: any clearly positive Δ over baseline).

**Why a single loop over the harness Python code (no skill edits)?**
SpreadsheetBench has two agent shapes baked into the harness — codegen
(single / multi) and ReAct (legacy bash tool). The harness controls
code extraction, the executor sandbox, the workbook preview, the
turn budget, and the tool inventory. The skill text also steers
behavior inside whichever mode is active, but it's tuned by a separate
optimisation loop (`/skillopt-loop`) that compares apples-to-apples
across skill drafts. This prompt focuses purely on harness-shape
improvements (e.g. "agent emits non-Python prose around the code
block" → widen the extraction regex in `codegen_agent.py`).
Skill-content clusters ("agent writes to the wrong sheet because the
skill doesn't mention sheet preservation") are flagged in the design
pass as residuals and routed to `/skillopt-loop` instead of being
patched here.

## Critical invariants (the loop enforces these every round)

| Invariant | How it's enforced |
|-----------|-------------------|
| Only **allowlist** files edited | `git diff --name-only` ⊆ `{rollout.py, react_agent.py, codegen_agent.py, executor.py, recalc_harness.py, adapter.py}` |
| **Smoke val** must pass before full gate | smoke val=5 with `hard ≥ 0.0` and exit=0; otherwise rollback |
| **Reversible** rollback | `git reset --hard <tag>` (not `cp`) |
| **Skill is denylist** | diff guard rejects the round if `skills/initial.md` or `workspaces/<model>/skill.md` moves; route skill rewrites to `/skillopt-loop` |

**Allowlist** (editable): `rollout.py`, `react_agent.py`,
`codegen_agent.py`, `executor.py`, `recalc_harness.py`, `adapter.py`
**Denylist** (never edited): `evaluator.py`, `dataloader.py`,
`configs/`, `prompts/*.md`, `skills/initial.md`,
`workspaces/<model>/skill.md` (skill rewrites → `/skillopt-loop`)

**Split semantics**

| phase                          | split   | size                                   | purpose                                                  |
|--------------------------------|---------|----------------------------------------|----------------------------------------------------------|
| **round-0 bootstrap signal**   | `train` | **full (80)**                          | full-coverage failure scan → design pass proposals               |
| **round-0 debug batch**        | `train` | **6** (first slice, seed=0)            | smoke-test the bootstrap patch end-to-end                |
| per-round improve signal       | `train` | `batch=12`                             | failed episodes that drive each round's patch (round 1+) |
| smoke                          | `val`   | 5                                      | catches crashes / hard regressions                       |
| gate                           | `val`   | full (39)                              | accept/reject decision (held-out)                        |
| final report                   | `test`  | full (281)                             | held-out generalization, run once at end                 |

**⚠️ Cost note**: spreadsheetbench on gpt-5.4-nano is the most
expensive bench in this repo — each task has a 600 s exec timeout and
launches a real openpyxl Python sandbox per case. Estimates assume the
default 24 workers and `mode=multi`:
- Full val gate (39) ≈ **6–18 min** (depends on how many tasks hit the timeout)
- Full train rollout (80) ≈ **15–35 min**
- Smoke val=5 ≈ **2–6 min**
- Debug batch train=6 ≈ **2–8 min**
- Train rollout batch=12 ≈ **4–12 min**
- Subagent failure-scan (1 × Explore thorough on ~60+ files) ≈ **2–4 min**
- Design pass (main agent, 6 lenses inline + synthesis) ≈ **~0** wall
  (chat-only; folded into the same turn as the failure-scan write-up)
- User briefing & approval gate (step 0.7) — wall-clock = however long
  the user takes to reply; assistant compute = ~0 (turn ends immediately
  after printing the brief)
- Seed round-1 samples (step 0.11) ≈ train batch=12 ≈ **4–12 min**
- **Round-0 bootstrap total** (steps 0.1 → 0.11, excluding user reply
  wait) ≈ **30–80 min** of compute time
- Per-round total (no rollback, round 1+) ≈ 15–35 min; last round saves
  ~4–12 min (no train-regen). Full 2-round loop + final test (~20–60 min)
  ≈ **80–180 min** end-to-end

> **Heads up on `batch=` choice**: officeqa uses `batch=16` because train
> rollouts there cost ~1–2 min. Here we default to **`batch=12`** because
> each spreadsheet train rollout segment costs 4–12 min. Bump to `batch=16`
> only if your model has higher API throughput than the default cap.

## Round 0 — bootstrap improve (full-coverage scan → design pass → user approval → patch + debug batch)

> **Why round 0 is special.** Round 1+ runs on a small `batch=12` train
> slice (cheap, targeted). But the **first** patch needs full visibility
> of the failure distribution to decide *what kind of harness change to
> make at all* — adding a tool, reshaping the system prompt context,
> raising turn budget, fixing the codegen output extraction, etc. So
> round 0 rolls out the **entire** train split, has the main agent walk
> through a 5-lens design pass (with a single failure-scan subagent as
> a context reducer for the failed samples), then commits the proposal
> as a normal round (`harness-opt/spreadsheetbench/round-0-best`), with
> a small debug batch as the smoke check before the loop proper takes
> over.

### 0.1 Prereq check + git baseline
```bash
cd harness_example/spreadsheetbench

# Make sure the harness is git-tracked so we can tag/reset.
if git -C . status --short -- harness_example/spreadsheetbench/ | grep -q .; then
    git -C . add harness_example/spreadsheetbench/
    git -C . commit -m "harness-opt: baseline spreadsheetbench-local harness state"
fi

# Create the working branch (idempotent: switch if already exists).
if git -C . rev-parse --verify skillopt-harness/spreadsheetbench >/dev/null 2>&1; then
    git -C . checkout skillopt-harness/spreadsheetbench
else
    git -C . checkout -b skillopt-harness/spreadsheetbench
fi

# Tag the baseline (this is the rollback target if the whole bootstrap regresses).
git -C . tag -f harness-opt/spreadsheetbench/baseline
```

Remember the baseline tag (`harness-opt/spreadsheetbench/baseline`).
Skill `workspaces/gpt-5.4-nano/skill.md` and `skills/initial.md` are
in the **denylist** this round — they're read-only context for the
design pass; skill rewrites are handled by `/skillopt-loop`.

### 0.2 Baseline val (full) — the number to beat
```bash
rm -rf workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
bash run.sh --target_model gpt-5.4-nano --split val --eval_limit 0 --limit 0
```
Read `Results: hard=<X> soft=<Y>` → `val_hard_0`, `val_soft_0`.
This is the baseline every subsequent round must beat (or tie within
the dead band).

> **No-poll**: this is a full val on 39 tasks (≈6–18 min). After
> kicking it off, end your turn; resume on the
> `[Terminal … notification: command completed]` message.

### 0.3 Full train rollout — full failure coverage
Run the **entire** train split (80 items) so step 0.5's subagent gets
the complete failure distribution, not a sampled slice. The 0.6 design
pass then reasons from that full distribution — if you sample here,
you bias the bootstrap toward whatever 12 questions happened to land in
the slice.

```bash
rm -rf workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
bash run.sh --target_model gpt-5.4-nano --split train --eval_limit 0 --limit 0
```
Read `hard=<X>` → `train_hard_0`. Confirm
`.skillopt/samples/failed/` now contains ≈`80 * (1 − train_hard_0)`
`.md` files (the per-item rollout traces with `fail_reason`, the
generated code or tool calls, gold vs. predicted xlsx diff).

**~15–35 min, full-train.** Same no-poll discipline as 0.2.

### 0.4 Inline recon (no file write; just print to chat)
While the train rollout runs (or right after), use `list_dir` +
`read_file` to fill these blanks. The 0.6 design pass will reference
this recon directly, and the 0.5 failure-scan subagent gets a copy in
its prompt:

- **Active mode** (read `configs/spreadsheetbench-local/default.yaml`
  + its `_base_`): `env.mode` is one of `single` | `multi` | `react`.
  This determines whether codegen or ReAct is the agent contract.
- **Tool inventory** — mode-dependent:
  - codegen modes (`single`, `multi`): **no tools**. The agent emits
    Python and the harness `executor.run_generated_code` runs it.
    Read `codegen_agent.py` (`run_single` / `run_multi`) for the
    LLM-call shape and `executor.py` for the sandbox.
  - ReAct mode (`react`): read `react_agent.py` top — `BASH_TOOL_CHAT`,
    `WRITE_FILE_TOOL_CHAT`, and `recalc_harness.extra_tools_chat()` for
    the opt-in `recalc_xlsx` tool (gated by `SPREADSHEETBENCH_RECALC=1`).
- **Loop config**: `env.max_turns`, `env.exec_timeout`,
  `env.max_completion_tokens` from
  `configs/spreadsheetbench/default.yaml`; also the `max_turns=5` /
  `max_turns=30` defaults wired in `rollout.py` (`process_one_codegen`
  vs. `process_one`).
- **System prompt source**: `prompts/codegen_system.md` (codegen) or
  `prompts/react_system.md` (react), plus `prompts/critical_rules.md`
  baked into both. Read in full; these stay in the **denylist** this
  round, so the design pass can refer to them but not patch them. If
  you find the system prompt is the real bottleneck, flag it for the
  user instead of editing.
- **Current skill** (read-only context; **denylist**): read
  `workspaces/gpt-5.4-nano/skill.md` AND `skills/initial.md` to confirm
  they match and to ground every diagnosis in what the agent currently
  sees. The design pass below must NOT propose edits to either file —
  skill rewrites belong to `/skillopt-loop`.

Format as one chat block under heading `### Round-0 recon` and include
the absolute paths to all four areas so the 0.5 subagent and the 0.6
design pass can cite them.

### 0.5 Subagent failure-scan (Explore, thorough, single shot)
Fan out one `Explore` subagent that reads **every** file in
`workspaces/gpt-5.4-nano/.skillopt/samples/failed/`, clusters them by
failure mode, and reports a taxonomy. Run it with `thoroughness=thorough`.

Use `runSubagent` with `agentName="Explore"` and the following prompt
(substitute the real absolute paths):

> **Task**: Read **every** `.md` file under
> `./harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/failed/`.
> Each file contains one rollout trace (instruction, gold xlsx delta,
> generated code or tool-call transcript, `fail_reason`, evaluator
> mismatch details). Cluster the failures into 4–8 distinct buckets by
> *root cause* (not by surface task topic).
>
> For each cluster, return:
> - `cluster_id` (short slug like `wrote-wrong-sheet` or `formula-evaluation-needed`)
> - `count` (how many failed samples fall in it)
> - `exemplar_ids` (task ids of 2–3 representative failures)
> - `evidence` (one verbatim snippet per exemplar showing the failure —
>   prefer the failed code block, the eval-mismatch reason, or the
>   final ReAct turn)
> - `hypothesis` — one of: `tool-missing`, `tool-result-shape`,
>   `prompt-context` (the system prompt / preamble doesn't surface what
>   the agent needs), `turn-budget`, `error-format`, `loop-policy`,
>   `codegen-output-shape` (extraction fails on the LLM's wrapping
>   tokens), `executor-environment` (sandbox missing packages, wrong
>   cwd, etc.), `skill-content` (out of scope this round — the skill
>   text is denylist; flag for `/skillopt-loop`), `memory-needed`
>   (agent re-derives or re-fetches what it already had),
>   `system-prompt` (out of scope this round — flag).
> - `confidence` (low/med/high)
>
> Also report a **residual** bucket for anything that doesn't fit.
> Do NOT propose code changes; just describe the patterns. Read all
> failed samples (don't sample).
>
> Return as a single chat block under heading `### Round-0 failure taxonomy`.

Wait for this subagent's report inline (it's read-only, ~2–4 min). Pin
its output in chat memory as `TAXONOMY` — the 0.6 design pass consumes
it verbatim.

### 0.6 Design pass (main agent — 5 lenses, then synthesis)

> **No subagents here.** The main agent already holds the recon (0.4)
> and TAXONOMY (0.5) — that's the entire signal a designer needs.
> Parallel `Explore` subagents would re-read the same material in
> isolation, then dump 5 proposals back for the main agent to merge
> anyway; the merge is where the real judgement lives. So instead: the
> main agent writes one proposal per lens **inline**, then synthesizes.

Walk through the five lenses below **in order**, in a single chat block
under heading `### Round-0 design pass`. For each lens, output the
proposal template (filling Y/N decisions explicitly for A and E).
Keep each lens block tight — pseudo-diff sketches, not full code.

**Constraints (apply to all five lenses)**:
- Allowlist (only these files may be edited):
  - `harness_example/spreadsheetbench/rollout.py`
  - `harness_example/spreadsheetbench/react_agent.py`
  - `harness_example/spreadsheetbench/codegen_agent.py`
  - `harness_example/spreadsheetbench/executor.py`
  - `harness_example/spreadsheetbench/recalc_harness.py`
  - `harness_example/spreadsheetbench/adapter.py`
- Denylist (must NOT be edited): `evaluator.py`, `dataloader.py`,
  `configs/*`, `prompts/*.md`, `skills/initial.md`,
  `workspaces/<model>/skill.md` (skill edits belong to `/skillopt-loop`)

**Lens prompts** (use these as the section headers; each lens's body
follows the proposal template below):

| # | lens                          | the question to answer                                                                                                                                                                                                                                                                                                                                                                                                                                  |
|---|-------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A | **tools (add/modify)**        | **Decision (Y/N): should we ADD a new tool?** (`react` mode only — codegen has no tool surface.) If Y, exactly one tool: `name`, JSON-schema args, return shape, registration in `react_agent.py`'s `tools` list. Also: should `bash` / `write_file` / `recalc_xlsx`'s schema or return change? Cite cluster_ids. If mode is `multi`/`single` and the dominant clusters point at "agent needs to introspect the workbook", consider switching mode or upgrading the codegen preamble — but a real new tool means proposing a switch to react. Be opinionated. |
| B | **prompt context / preamble**| Which clusters are downstream of *what the user-turn preamble or workbook preview tells the agent*? Read `codegen_agent.py:_preview_workbook` and the user-message assembly. Propose changes to the preview format, sheet-listing, formula vs. value handling, column-letter hints. Bound: this lens does NOT add tools, memory, or touch skill (denylist). (System prompt content stays denylist; only the harness-side preamble around it is in scope.) |
| C | **loop policy**               | Which clusters are downstream of *turn budget / error recovery / when the loop stops*? Propose changes to `process_one_codegen` (`max_turns`, "run code then re-prompt on stderr" handling, force-final turn) or `process_one` (`max_turns=30`, ReAct stopping). Bound: this lens does NOT add tools, memory, or touch skill. |
| D | **codegen / executor shape** | Which clusters are downstream of *how the LLM's code is extracted or executed*? Propose changes to `codegen_agent.py`'s code-block extraction (regex, fenced-block handling, "no code block" recovery) and/or `executor.run_generated_code` (env preparation, timeout, error truncation, working dir, post-exec auto-recalc gating). Bound: this lens does NOT add new tools, only reshapes existing IO. |
| E | **memory & state**            | **Decision (Y/N): should we ADD memory?** Memory = *anything that survives past one tool turn or one episode* — multi-turn scratch of "what worked on the prior case", per-task workbook fingerprint to skip redundant preview, cross-episode cache of `(instruction-pattern → code template)`, etc. If Y: **where it lives**, **what it stores**, **read/write policy**, **eviction**. Cite cluster_ids. If N, say so with reasoning. |

> **Skill edits are not a lens here.** If a cluster's hypothesis is
> `skill-content` (e.g. "the skill doesn't mention sheet preservation"),
> do **not** propose a fix — list the cluster under the residuals at
> the end of the synthesis with the note "route to `/skillopt-loop`".
> The harness loop's job is to move the score while skill is held fixed.

**Per-lens proposal template** (use this for each of A–E):

```
#### Lens <A|B|C|D|E>: <lens name>
- Decision (A/E only): <Y | N> + one-sentence reasoning
- Clusters addressed: <cluster_id_1, cluster_id_2, ...>  (cite TAXONOMY)
- Files to touch (allowlist only): <list>
- Diff sketch (pseudocode or unified-diff fragments, ≤ 40 lines):
  ```
  <sketch>
  ```
- Expected impact: <which fail_reason patterns this should remove, expected Δ on val>
- Risks / side effects: <what could regress; which clusters this does NOT touch>
- Out-of-scope flags: <denylist concerns, system-prompt issues, skill-content clusters to route to /skillopt-loop, etc.>
```

**Synthesis** (immediately after the five lens blocks, same chat turn):

Print one block under heading `### Round-0 design synthesis`,
structured **explicitly around the three user-facing decisions**:

```
### Round-0 design synthesis

#### Decision 1 — Memory: <ADD | SKIP>
- Recommendation: <ADD | SKIP> because <reason, citing lens E>
- If ADD: <one-paragraph spec — where/what/RW policy/eviction>
- Clusters this fixes: <ids + their counts from TAXONOMY>
- Cost: <est. diff lines, files touched, runtime overhead>

#### Decision 2 — New tool: <ADD | SKIP>
- Recommendation: <ADD <name> | SKIP> because <reason, citing lens A>
- If ADD: <name, JSON-schema args, return shape, where it registers (react_agent.py only)>
- Clusters this fixes: <ids + their counts from TAXONOMY>
- Cost: <est. diff lines, files touched>

#### Decision 3 — Other code changes
- Adopted from B (prompt context): <bullet list or "none">
- Adopted from C (loop policy): <bullet list or "none">
- Adopted from D (codegen / executor shape): <bullet list or "none">
- Rejected / deferred to round 1+ (with reason): <list>

#### Conflict resolution
- <e.g. "B wanted to surface sheet-count + formula presence in the
  workbook preview, D wanted to widen the codegen extraction regex —
  adopted D first because it rescues whole rounds that today extract
  zero code; B kept as fallback for round 1+">

#### Skill-content residuals (route to /skillopt-loop)
- <list cluster_ids whose hypothesis is `skill-content` and that no
  lens can address from the harness side; "none" if there are none>

#### Cluster coverage check
- Top-3 clusters by count: <id (count), id (count), id (count)>
- Each addressed by which decision? <map>
- Residual (no decision touches): <ids + counts>  — leave for round 1+
```

There is no hard line cap on the unified plan; the diff guard in step
0.8 enforces allowlist/denylist, and the debug batch in step 0.9 catches
crashes. Larger plans are allowed if all five lenses point that way.

> **When to escalate back to subagents.** If the failure TAXONOMY has
> ≥ 8 clusters or the per-lens diff sketches are blowing past ~80 lines
> each, fall back to one `runSubagent Explore medium` *per lens* and
> have it return only its proposal block. Default is still inline.

### 0.7 User briefing & approval gate (HARD STOP — wait for user reply)

> **Do not apply any patch until the user explicitly approves.**

After printing the synthesis block in 0.6, also print this concise
brief to chat — and then **end your turn**. Do **not** call `editFiles`,
`git`, or any further tool in this turn.

```
=== Round-0 bootstrap brief (awaiting approval) ===

Baseline: val_hard_0 = <X>, val_soft_0 = <Y>   (gpt-5.4-nano, current harness)
Mode:     <single | multi | react>
Failures: <T> / 80 train items in <K> clusters
Top clusters: <id (count) — one-line gist>, <id (count) — one-line gist>, ...

Proposed bootstrap = three decisions:

  1. MEMORY:    <ADD | SKIP>           <if ADD: one-line spec; else one-line reason>
  2. NEW TOOL:  <ADD <name> | SKIP>    <if ADD: name + args + react-only note; else reason>
  3. OTHER:     <one-line summary of B/C/D edits adopted, or "none">

Files this will touch (allowlist only):
  <subset of {rollout, react_agent, codegen_agent, executor, recalc_harness, adapter}.py>
Estimated diff: ~<N> lines across <F> files.
Expected impact (best case): val_hard ≈ <X> → <X'> (Δ ≈ +<d>)
Clusters NOT addressed this round: <ids>  → carried to round 1+
Skill-content residuals (route to /skillopt-loop): <ids or "none">

Reply with one of:
  • "approve"                              — apply the plan as-is and continue to 0.8
  • "approve with edits: …"                — apply with the user's listed tweaks
  • "skip memory" / "skip tool" /
    "skip other"                          — drop one decision, keep the rest
  • "redesign: …"                          — rerun 0.6 with the user's redirection
  • "abort"                                — git reset --hard harness-opt/spreadsheetbench/baseline + stop
```

**End your turn here.** Wait for the user's reply. When the user
responds in the next turn:

- `approve`            → proceed to 0.8 with the synthesis plan unchanged.
- `approve with edits` → fold edits into the plan, restate the final
  three decisions in one sentence each as confirmation, then proceed.
- `skip <decision>`    → drop that decision from the plan, restate the
  remaining ones, then proceed.
- `redesign`           → jump back to 0.6 with the user's redirection
  appended to the shared preamble; do NOT re-run 0.3/0.5 (the train
  rollout and TAXONOMY are still valid).
- `abort`              → `git checkout -- harness_example/spreadsheetbench/`
  (rewind if anything was staged); print "round-0 aborted by user" and
  stop. Do not enter the per-round loop.

> Why a hard stop here, not at every per-round step? Round 0 is the
> only step that can introduce **architectural** changes (a new tool,
> a memory subsystem, a reshape of the codegen / ReAct loop). Round 1+
> improves are surgical edits and are gated by smoke + full val
> automatically. User approval is concentrated here so the bootstrap
> commit is auditable in one diff with one rationale.

### 0.8 Apply patch + diff guard + git isolation
**Precondition: user reply in 0.7 was `approve` / `approve with edits` /
`skip …`.** If you reached this step without a user approval in the
previous turn, stop and re-print the 0.7 brief.

Apply the (possibly user-edited) plan via `editFiles` (one or more
edits, one or more allowlist files). Skill files are denylist this
round — the diff guard below will reject the round if either
`skills/initial.md` or `workspaces/<model>/skill.md` moves. Then run
the diff guard:

```bash
cd .

DIFF_LINES=$(git diff --numstat -- harness_example/spreadsheetbench/ \
  | awk '{a+=$1; d+=$2} END {print a+d+0}')
DIFF_FILES=$(git diff --name-only -- harness_example/spreadsheetbench/ | sort)
ALLOWED_RE='^harness_example/spreadsheetbench/(rollout\.py|react_agent\.py|codegen_agent\.py|executor\.py|recalc_harness\.py|adapter\.py)$'
DENY_HIT=$(echo "$DIFF_FILES" | grep -E 'evaluator\.py|dataloader\.py|^configs/|prompts/.*\.md|skills/initial\.md|workspaces/[^/]+/skill\.md' || true)
ALLOW_VIOLATION=$(echo "$DIFF_FILES" | grep -v -E "$ALLOWED_RE" | grep -v '^$' || true)

echo "  DIFF_LINES=${DIFF_LINES}"
echo "  DIFF_FILES:"; echo "${DIFF_FILES}" | sed 's/^/    /'
echo "  ALLOW_VIOLATION:"; echo "${ALLOW_VIOLATION}" | sed 's/^/    /'
echo "  DENY_HIT:"; echo "${DENY_HIT}" | sed 's/^/    /'
```

If `ALLOW_VIOLATION` or `DENY_HIT` is non-empty, **rewind the working
tree** (don't commit), report which decision slipped through, and ask
the user before re-trying:
```bash
git -C . checkout -- harness_example/spreadsheetbench/
```

Otherwise commit + tag the bootstrap as `round-0-best`. The commit
message **must reference the three approved decisions**:
```bash
cd .
git add harness_example/spreadsheetbench/
git commit -m "harness-opt round-0 bootstrap (user-approved): mem=<add:spec|skip>, tool=<add:name|skip>, other=<one-line>"
git tag -f harness-opt/spreadsheetbench/round-0-best
```

### 0.9 Debug batch — verify the bootstrap patch doesn't crash
Use the **first 6** train items (seed=0, deterministic slice) as a smoke
test of the on-disk patched harness:

```bash
rm -rf harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
cd harness_example/spreadsheetbench
bash run.sh --target_model gpt-5.4-nano --split train --eval_limit 6 --limit 6 --seed 0
```
**~2–8 min.** Read `hard=<X>` → `debug_acc`.

**Triage** (do NOT roll back automatically — this is a *debug* loop, not
the per-round gate):
- **Exit non-zero / ImportError / agent crash** → the patch is broken.
  Print the traceback, read the patched files, decide whether to
  `editFiles` a fix in place (and re-run 0.9) or
  `git reset --hard harness-opt/spreadsheetbench/baseline` and ask the user.
- **Exit 0 but `debug_acc = 0`** → patch *runs* but every sample fails.
  Spot-check 2–3 `samples/failed/*.md` to confirm the patch is doing
  what the approved decisions intended (not some no-op). Continue if
  so; the full val gate at round 1 will give the real signal.
- **Exit 0, any `debug_acc ≥ 0`** → green. Continue. (Spreadsheet
  baseline on nano may legitimately be 0/6 on a slice this small.)

> Round-0 deliberately does **not** run a full val gate here — the
> validation belongs to round 1 (which immediately re-runs with the
> new harness, with smoke + full val). 0.9 is just "did we wire up
> live code".

### 0.10 Hand-off state for round 1+
At this point on disk:
- Branch: `skillopt-harness/spreadsheetbench`
- HEAD tag: `harness-opt/spreadsheetbench/round-0-best` (= the user-approved bootstrap patch)
- `harness-opt/spreadsheetbench/baseline` still points to the pre-bootstrap commit
- `val_hard_0` recorded from step 0.2 (still the number to beat)
- `samples/` currently contains the 6 debug-batch traces (about to be
  overwritten by 0.11)

Track for the loop (pin in chat memory; re-print at the top of each
round so the trajectory is visible):
- `current_acc = val_hard_0`, `current_soft = val_soft_0`
- `best_acc = val_hard_0`, `best_round = 0`,
  `best_tag = harness-opt/spreadsheetbench/round-0-best`  ← bootstrap is the
  starting "best"; round 1's gate will compare against `current_acc`
  (the original baseline), so a working bootstrap can win on its first
  evaluation.
- `noop_streak = 0`, `regression_streak = 0`
- `tried_surfaces = [(0, <list of approved decisions, e.g. "tool,other-code">)]`
  — lift the three decisions you applied in 0.8 (memory / tool /
  other-code) as the round-0 entry. Each subsequent round appends its
  own `(r, surface)`.
- `cluster_residuals` = the cluster_ids from TAXONOMY (step 0.5) that
  none of the three decisions in 0.6 synthesis addressed. This is the
  "shopping list" for round 1+. (Skill-content clusters listed under
  the synthesis's "Skill-content residuals" stay routed to
  `/skillopt-loop` and do NOT count as harness-residuals.)

### 0.11 Seed round-1's train samples (last step of round 0)

Round 1 step 2 reads `samples/failed/*.md` directly; the 6 debug-batch
traces are not a representative slice. Fire off a fresh `batch=12`
train rollout with `--seed 1` so round 1 has the same-size,
same-convention sample shape as r=2, r=3, … (and so its first improve
actually sees the *patched* harness's failures, not the bootstrap's
smoke-test).

```bash
rm -rf harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
cd harness_example/spreadsheetbench
bash run.sh --target_model gpt-5.4-nano --split train \
    --eval_limit ${input:batch:12} --limit ${input:batch:12} \
    --seed 1
```
**~4–12 min.** Scores incidental; don't gate on them. After this,
`samples/` is the input to round 1's improve.

## Per-round procedure (round `r` in `1..${input:rounds:2}`)

At the top of each round, **re-print one line** so the user can scan
the trajectory:
```
starting round ${r}  current=<current_acc>/<current_soft>  best=<best_acc>@r<best_round>  tried_surfaces=<list>  residuals=<top 3 cluster_ids>  streaks=reject<n>/flat<m>
```

### 1. Tag the round's "before" state
```bash
git -C . tag -f harness-opt/spreadsheetbench/round-${r}-before
```
(`-f` because re-running the loop may hit the same tag name.)

### 2. Pick this round's surface + improve

**2a. Surface pick** (inline, in chat under `### Round ${r} surface`; ~5
lines, no subagent — batch=12 samples is small enough to scan directly):

1. Read `workspaces/gpt-5.4-nano/.skillopt/samples/failed/*.md` headers
   (just `## Notes` / `fail_reason` of each — ~1 KB total) and tag each
   into either an existing `cluster_residuals` entry or a new cluster.
2. Pick the **target surface** for this round from {`memory`, `tool`,
   `other-code`}, with this priority:
   - **(a)** the surface paired with the dominant cluster in round-0's
     synthesis (if that cluster is still in residuals), or
   - **(b)** the least-tried surface in `tried_surfaces` if (a) is
     exhausted, or
   - **(c)** the surface the prior round flat/rejected on — **switch
     away** from it (don't bang the same surface twice after a no-op).
3. Print one line: `surface=<pick> reason=<one sentence citing 2 sample ids>`.

> **Skill is not a surface in this loop.** Skill files are denylist;
> if the dominant residual cluster's hypothesis is `skill-content`,
> note it in chat as "flag for `/skillopt-loop`" and pick the next
> surface in the priority list.

> **`tool` is `react`-mode-only.** If the active mode (from 0.4 recon)
> is `single` or `multi`, the surface pick must skip `tool` and pick
> from {`memory`, `other-code`} instead. If the dominant cluster
> genuinely needs a tool, flag it as "needs mode switch" and route to
> `other-code` (proposing the switch in adapter.py / config), not
> silently no-op.

**2b. Improve.** Follow [harnessopt-improve.prompt.md](./harnessopt-improve.prompt.md):
read the failed/passed samples + relevant harness slice, apply a
surgical patch across the allowlist (code files only) via `editFiles`.
**Pass `surface=<pick>` as a soft preference** in your invocation
context — improve may pivot if its own triage disagrees, but it
should say so explicitly. The diff guard below rejects skill-file
touches (those belong to `/skillopt-loop`). There is **no hard
line-count cap** — the diff size is reported in the round summary,
and the smoke + full val gates are the actual quality filter.

Append `(r, surface_actually_used)` to `tried_surfaces`.

### 3. Diff guard (hard gate — auto-reject if violated)

After improve finishes, **before** running any eval:

```bash
cd .

# Net line count (added + removed).
DIFF_LINES=$(git diff --numstat -- harness_example/spreadsheetbench/ \
  | awk '{a+=$1; d+=$2} END {print a+d+0}')

# Files touched.
DIFF_FILES=$(git diff --name-only -- harness_example/spreadsheetbench/ | sort)

# Allowlist: harness code files only (skill is denylist this round).
ALLOWED_RE='^harness_example/spreadsheetbench/(rollout\.py|react_agent\.py|codegen_agent\.py|executor\.py|recalc_harness\.py|adapter\.py)$'

# Denylist: harness internals + configs + rollout system prompts + skill files.
DENY_HIT=$(echo "$DIFF_FILES" | grep -E 'evaluator\.py|dataloader\.py|^configs/|prompts/.*\.md|skills/initial\.md|workspaces/[^/]+/skill\.md' || true)
ALLOW_VIOLATION=$(echo "$DIFF_FILES" | grep -v -E "$ALLOWED_RE" | grep -v '^$' || true)

echo "  DIFF_LINES=${DIFF_LINES}"
echo "  DIFF_FILES:"; echo "${DIFF_FILES}" | sed 's/^/    /'
echo "  ALLOW_VIOLATION:"; echo "${ALLOW_VIOLATION}" | sed 's/^/    /'
echo "  DENY_HIT:"; echo "${DENY_HIT}" | sed 's/^/    /'
```

Reject this round (jump to step 7 "rollback path") if **any** of:
- `ALLOW_VIOLATION` is non-empty
- `DENY_HIT` is non-empty (this includes any touch to `skills/initial.md`
  or `workspaces/<model>/skill.md` — those belong to `/skillopt-loop`)

(`DIFF_LINES` is recorded for the round summary but is **not** a reject
trigger — a large diff is allowed as long as it's confined to the
allowlist and survives smoke + full val.)

Reject path:
```bash
git -C . checkout -- harness_example/spreadsheetbench/
```
Then: `regression_streak += 1`, log `action=reject(diff-guard:<reason>)`,
**skip to step 7** (regenerate train samples + report row).

### 4. Smoke val=5 (catch crashes BEFORE the long gate)

```bash
rm -rf harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
cd harness_example/spreadsheetbench
bash run.sh --target_model gpt-5.4-nano --split val --eval_limit 5 --limit 5
```
**~2–6 min.** Read `hard=<X>` → `smoke_acc`.

Smoke-fail if:
- `run.sh` exited non-zero (ImportError, agent crash, schema mismatch), **or**
- `smoke_acc < 0.0` (impossible, but kept as a sentinel — the real
  catch is exit-code non-zero or a per-task-timeout flood; on the small
  smoke=5 slice, even 0 hard correct is acceptable).

On smoke fail → rollback this round:
```bash
git -C . reset --hard harness-opt/spreadsheetbench/round-${r}-before
```
Then: `regression_streak += 1`, log `action=reject(smoke:<reason>)`,
**skip to step 7**.

### 5. Full val gate
```bash
rm -rf harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
cd harness_example/spreadsheetbench
bash run.sh --target_model gpt-5.4-nano --split val --eval_limit 0 --limit 0
```
Capture `hard=<X>` → `cand_acc`, `soft=<Y>` → `cand_soft`. Compute
`Δ = cand_acc − current_acc`. **~6–18 min.** Val samples produced here
are throwaway; step 7 will overwrite them.

### 6. Gate decision (dead band ±0.05 — val is small, so be a bit looser than officeqa)

| condition                                              | action              | side effect |
|--------------------------------------------------------|---------------------|-------------|
| `Δ ≥ +0.05` and `cand_acc > best_acc`                  | **accept_new_best** | commit + tag `round-${r}-best`; update `best_*` |
| `Δ ≥ +0.05` (≤ best)                                   | **accept**          | commit (no `best` tag) |
| `Δ ≤ −0.05`                                            | **reject**          | `git reset --hard round-${r}-before` |
| `|Δ| < 0.05` AND `cand_soft − current_soft ≥ +0.05`    | **accept** (soft)   | commit (the harness moved partial credit) |
| `|Δ| < 0.05`                                           | **flat**            | `git reset --hard round-${r}-before` (don't pollute history with no-op) |

> The dead band is ±0.05 (vs officeqa's ±0.02) because val=39 means
> one task is worth ~0.026 — a 1-task swing is in the noise. Two tasks
> (Δ ≈ ±0.05) is roughly where signal starts to dominate.

Apply the gate:

```bash
# accept_new_best path:
cd .
git add harness_example/spreadsheetbench/
git commit -m "harness-opt round-${r}: <one-line edit summary> | val ${current_acc}→${cand_acc} (Δ=+${delta})"
git tag -f harness-opt/spreadsheetbench/round-${r}-best
# update best_acc=cand_acc, best_round=r, best_tag=harness-opt/spreadsheetbench/round-${r}-best
```

```bash
# accept path:
cd .
git add harness_example/spreadsheetbench/
git commit -m "harness-opt round-${r}: <summary> | val ${current_acc}→${cand_acc} (Δ=+${delta})"
# do NOT update best_*
```

```bash
# reject / flat path:
git -C . reset --hard harness-opt/spreadsheetbench/round-${r}-before
```

Update streak counters:
- `accept_new_best` / `accept` → both counters reset to 0
- `reject` → `regression_streak += 1`, `noop_streak = 0`
- `flat`   → `noop_streak += 1`, `regression_streak = 0`

Update `current_*`:
- `accept_new_best` / `accept` → both = candidate values
- `reject` / `flat` → both unchanged (we rolled back)

### 7. Regenerate next round's train samples (skip if this is the last round)

If `r == ${input:rounds:2}`, **skip this step** — there's no next round
and the final test ("After all rounds") uses `--split test`, not
`--split train`. Saves ~4–12 min on the last iteration (the biggest
single saving in the loop).

Otherwise, after the gate decision is applied (so the on-disk harness
is the accepted/rolled-back version), regenerate train samples for the
**next** round's improve. Use `--seed $((r+1))` so each round sees a
different slice:

```bash
rm -rf harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
cd harness_example/spreadsheetbench
bash run.sh --target_model gpt-5.4-nano --split train \
    --eval_limit ${input:batch:12} --limit ${input:batch:12} \
    --seed $((r+1))
```
**~4–12 min.** Scores incidental; we don't gate on them.

### 8. Stream a one-row progress update
```
r=<r>  surface=<pick>  diff=±<N>L/<F>f  smoke=<smoke_acc|skip>  val_hard=<cand_acc>  val_soft=<cand_soft>  Δ=<+/-Y>  action=<accept_new_best|accept|reject|flat|reject(diff)|reject(smoke)>  best=<best_acc@best_round>  edit=<short summary>
```

If `action ∈ {flat, reject}` AND the same surface was used in the prior
round, also print a one-line hint:
```
  hint: surface=<X> has flat/rejected twice in a row; next round will switch to <least-tried surface from {memory,tool,other-code} \ {X}>
```
(This is just guidance; step 2a of the next round still picks formally.)

## Stopping conditions (any one)

- `${input:rounds:2}` rounds completed.
- `regression_streak ≥ 3` (harness-opt is more fragile than skill-opt;
  3 rejects in a row signals you're out of ideas in scope).
- `noop_streak ≥ 3`.
- User cancels.

## After all rounds

### 1. Restore best
If the on-disk harness isn't already at `best_tag`:

```bash
cd .
git checkout ${best_tag} -- harness_example/spreadsheetbench/
```

### 2. Final test (held-out, one-shot)

> **Cost warning**: full test is 281 tasks at up to 600 s each. With 24
> workers this is typically **20–60 min** but can spike higher if many
> tasks time out. Confirm with the user before launching if they care
> about turnaround. The no-poll discipline applies.

```bash
rm -rf harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/failed/* \
       harness_example/spreadsheetbench/workspaces/gpt-5.4-nano/.skillopt/samples/passed/*
cd harness_example/spreadsheetbench
bash run.sh --target_model gpt-5.4-nano --split test --eval_limit 0 --limit 0
```
Capture `hard=<X>` → `test_acc`, `soft=<Y>` → `test_soft`.

## Final output

```
| round | surface       | diff       | smoke | val_hard | val_soft | Δ vs r-0 | action          | edit summary       | best? |
|-------|---------------|------------|-------|----------|----------|----------|-----------------|--------------------|-------|
| 0     | tool          | (bootstrap)| 0.20  | <X>      | <Y>      | —        | (baseline)      | (initial state)    |  *    |
| 1     | other-code    | +18/-4L/2f | 0.20  | 0.18     | 0.20     | +0.08    | accept_new_best | preview shows sheet list | * |
| 2     | memory        | +6/-2L/1f  | skip  | 0.18     | 0.21     | 0.00     | flat            | (rolled back)      |       |
...
```

(`*` marks the round whose harness is currently on disk.)

Then:

### Headline
- **Test hard**: `test_acc = <X>` &nbsp; **soft**: `test_soft = <Y>`
- Baseline: `val_hard_0 = <X> / val_soft_0 = <Y>`
- Best on val: `best_acc = <X> / @ round <r>` (tag `harness-opt/spreadsheetbench/round-<r>-best`)
- Test - val (held-out gap): `<+/-Y>`

### Best harness
- `best_acc = <best_acc>` at `best_round = <best_round>` (val)
- Git tag: `${best_tag}`
- `harness_example/spreadsheetbench/` is currently the best revision (restored if necessary).
- To inspect any round: `git show harness-opt/spreadsheetbench/round-<r>-best:harness_example/spreadsheetbench/rollout.py`
- To diff against baseline:
  `git diff harness-opt/spreadsheetbench/baseline harness-opt/spreadsheetbench/round-<r>-best -- harness_example/spreadsheetbench/`

### Open questions
- Harness areas the loop didn't touch (cite cluster_ids from
  `cluster_residuals` that are still uncovered after the final round).
- Surfaces in `tried_surfaces` that never produced an `accept` /
  `accept_new_best` — candidates to either retire or try harder with a
  bigger redesign next pass.
- Suggested next move (e.g. "patch the workbook preview to surface
  formula vs. value distinction next round before trying a new tool").

## Constraints

- Target model is **`gpt-5.4-nano`**. Don't change it.
- **Skill is denylist this round.** Skill files
  (`harness_example/spreadsheetbench/skills/initial.md` and
  `harness_example/spreadsheetbench/workspaces/<model>/skill.md`) are
  read-only context for the design pass and improve triage. The diff
  guard (step 3) rejects the round if either file moves. Skill edits
  belong to the `/skillopt-loop` slash command — flag skill-content
  clusters there.
- **Allowlist** (only editable):
  `harness_example/spreadsheetbench/{rollout.py, react_agent.py,
  codegen_agent.py, executor.py, recalc_harness.py, adapter.py}`.
- **Denylist** (never editable): `evaluator.py`, `dataloader.py`,
  `configs/`, `prompts/*.md`, `skills/initial.md`,
  `workspaces/<model>/skill.md`.
- **Every non-trivial harness code change MUST be wrapped behind an
  on/off toggle** so the loop can bisect which round's change actually
  moved the needle. Use an env var (`SPREADSHEETBENCH_<change_name>=1`
  read at module import time — follows the existing
  `SPREADSHEETBENCH_RECALC*` precedent) or a module-level boolean
  constant near the top of the affected file. Default ON when the
  round accepts; the prior code path must remain reachable when the
  flag is OFF. **Don't strip prior rounds' toggles** — they're the A/B
  handles for the final ablation. Tiny one-line tweaks (constant
  bumps, description string changes) are exempt.
- **Never delete** git tags under `harness-opt/spreadsheetbench/*` —
  they're the rollback handles.
- **No-poll discipline for long commands.** Full val gates take 6–18
  min, full test takes 20–60 min, full train rollouts take 15–35 min.
  After kicking off any
  `bash run.sh ... --split val --eval_limit 0` or `--split test` or
  `--split train --eval_limit 0`, do **not** call
  `get_terminal_output` / `ps` / `sleep` in the same turn. Instead:
  1. Send the command (sync mode is fine; it'll move to background and
     return a terminal id, or you can use async).
  2. Reply briefly in chat with the rough ETA.
  3. **End your turn** — do not call any further tools.
  The chat host auto-injects a `[Terminal <id> notification: command
  completed with exit code <N>]` message into the next turn with the
  full output. Pick up there. Polling within the same turn just burns
  the iteration budget without making the command finish faster.

  Smoke val=5 (~2–6 min) and train rollout batch=12 (~4–12 min) are
  borderline — wait inline only if the user explicitly asked for a
  fast end-to-end pass; otherwise apply no-poll for those too.

- **Auto-continue on terminal notification.** When a
  `[Terminal <id> notification: command completed ...]` message arrives,
  treat it as a resume signal, **not** as a stopping point. Parse
  `hard=<X> soft=<Y>` from the included output, then **immediately
  continue the loop** in the same turn:
  - Full val gate finished → step 6 (gate decision) + step 7 (next train
    rollout — **skipped on the last round**; otherwise fires another
    long-ish command — apply no-poll if it'll take ≥ 5 min) + step 8
    (one-row update). If rounds left, jump to step 1 of next round.
  - Test finished → produce the final output table + headline; loop done.
  Only end the turn when (a) you've just kicked off another long
  command (≥ 5 min), or (b) the loop has finished, or (c) `run.sh`
  failed (surface stderr and stop).
