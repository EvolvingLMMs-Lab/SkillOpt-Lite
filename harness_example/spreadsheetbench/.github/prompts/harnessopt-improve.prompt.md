---
description: "One round of harness-opt on spreadsheetbench-local: read samples + harness, diagnose the weakness, apply small surgical patch to the allowlist (harness Python code only; skill is denylist)"
agent: "agent"
tools: ['codebase', 'editFiles', 'runCommands']
---

You are running **one round** of harness-opt on the spreadsheetbench-local
env. The optimisation target is the **harness Python code only**
(codegen extraction, executor sandbox, tool design, loop policy, turn
budget). Skill files (`skills/initial.md` and
`workspaces/<model>/skill.md`) are **denylist** this round — they're
read-only context to ground your diagnosis. If a failure cluster's
hypothesis is `skill-content`, **do not patch the skill** — flag it
in chat for `/skillopt-loop` and patch a different surface.

**Surface preference (from `/harnessopt-loop` step 2a).** The loop may
hand you a soft `surface=<memory|tool|other-code>` hint based on which
cluster/surface is least-explored. Honour it by default. If your
own inline triage in step 4 strongly disagrees (e.g. the dominant
pattern in this batch points at a different surface), you may pivot —
but **say so explicitly** under the `Diagnosis` section and cite the
sample ids that justify the pivot.

> **`tool` surface only applies in `react` mode.** If
> `env.mode` (from `configs/spreadsheetbench-local/default.yaml`) is
> `single` or `multi`, the harness has no tool registry to extend.
> A `surface=tool` hint in codegen mode means the loop wants you to
> consider proposing a mode switch (an `adapter.py` / config edit that
> flips to `react`) — call that out under Diagnosis instead of trying
> to register a tool nowhere is listening for.

## Inputs (paths are relative to this workspace, `harness_example/spreadsheetbench/`)

**Read-only signals**
- Failed: `workspaces/gpt-5.4-nano/.skillopt/samples/failed/*.md`
- Passed: `workspaces/gpt-5.4-nano/.skillopt/samples/passed/*.md`

**Editable allowlist** (the only files you may modify this round)
- `rollout.py` — top-level batch driver, mode dispatch
  (`process_one_codegen` vs `process_one`), per-task lifecycle
  (timeout, exec wiring, eval call), `fail_reason` strings.
- `react_agent.py` — ReAct loop (tool-call handling, system prompt
  assembly, stopping criteria); tool schemas (`BASH_TOOL_CHAT`,
  `WRITE_FILE_TOOL_CHAT`).
- `codegen_agent.py` — codegen single/multi loop (LLM call, code-block
  extraction, workbook preview helpers, multi-turn refine).
- `executor.py` — sandbox that runs the generated code against the
  input xlsx (env preparation, timeout, stderr capture).
- `recalc_harness.py` — opt-in `recalc_xlsx` tool + auto-recalc post
  step (only active when `SPREADSHEETBENCH_RECALC*=1`).
- `adapter.py` — env adapter glue; rarely the culprit but in scope.

**Denylist** (never edit; touching these is grounds for reject by
`/harnessopt-loop`)
- `skills/initial.md` and `workspaces/gpt-5.4-nano/skill.md` — skill
  files are read-only context this round; skill rewrites belong to
  `/skillopt-loop`. If a cluster's hypothesis is `skill-content`,
  flag it for `/skillopt-loop` and patch a different surface here.
- `evaluator.py` — editing the scorer is **cheating**.
- `dataloader.py` — editing input space is **cheating**.
- `prompts/*.md` (`codegen_system.md`, `react_system.md`,
  `critical_rules.md`, `analyst_*.md`) — system / reflect prompts are
  out of scope this round (denylist).
- `configs/spreadsheetbench*/` — knobs are not the patch surface.

If the samples dirs are empty or `workspaces/gpt-5.4-nano/skill.md` is
missing, **stop** and tell the user to run
`bash run.sh --target_model gpt-5.4-nano --split train --eval_limit 12 --limit 12 --seed 1`
first (or use `/harnessopt-loop` which handles setup).

## Procedure

### 1. Read the current skill once (in full) — read-only context
Read `workspaces/gpt-5.4-nano/skill.md` end-to-end. It's **denylist**
this round, but it's still constraint context: harness changes
shouldn't fight rules the skill already states, and if you spot a
pattern that's clearly a skill-text problem (e.g. the executor strips
a needed env var, or the codegen extractor drops the agent's correct
fenced block) you'll flag it for `/skillopt-loop` rather than try to
fix it in code.

### 2. List + budget samples (tail-first)
1. List `workspaces/gpt-5.4-nano/.skillopt/samples/{failed,passed}/`
   for counts.
2. Read each failed sample's `## Notes` (`fail_reason`) header first to
   cluster. Common fail_reason values in spreadsheetbench:
   - `agent-error: <Type>: <msg>` — LLM call or schema error
   - `no-solution-py-for-other-cases` — first case passed but extracted
     code didn't generalize to extra cases
   - `exec-error: <tail>` — `executor.run_generated_code` raised /
     subprocess returned non-zero
   - `output-not-found` — the agent's code ran but didn't produce the
     expected output xlsx at the expected path
   - `eval-mismatch: <reason>` — output exists but values don't match
     golden (the most common signal-bearing bucket)
   - `task-timeout-{N}s` — per-task wall budget exceeded
   - `empty-code-block` (codegen) — extractor found no fenced code
   - `llm-call-failed: <Type>: <msg>` — API error
   - `unexpected: <Type>: <msg>` — anything else
3. Then read the **last 1–2 code blocks** or **last 3–6 ReAct turns**
   of each chosen failed sample. Spreadsheet traces can be long when
   the code is long — focus on the final code attempt + the eval-mismatch
   reason, not the whole transcript.
4. Read 1–2 `passed/` of the **same fail_reason cluster** for
   falsification (a `passed` whose code looks structurally similar to
   a failed one is a strong attribution clue).

**Reading budget** (spreadsheet traces are 2–10× heavier than officeqa):

| failed count | read this many failed | + passed |
|--------------|-----------------------|----------|
| ≤ 4          | all                   | 1        |
| 5 – 15       | 4 – 6 across clusters | 1 – 2    |
| > 15         | 5 – 8 across clusters | 2        |

Hard ceiling: **~40 KB total trace text**. Stop reading when adding
another sample wouldn't change your diagnosis.

### 3. Read the harness code (in this order, only what you need)
1. **Confirm the active mode** from `configs/spreadsheetbench-local/default.yaml`
   (and its `_base_`). The dispatcher in `rollout.py` (`run_spreadsheet_batch`)
   routes to codegen vs ReAct based on this.
2. **Codegen modes (`single`, `multi`)** — the common case:
   - `codegen_agent.py`: `run_single` / `run_multi`, `_extract_code`,
     `_build_system`, `_build_user`, `_preview_workbook`. The
     extraction regex and preview format are the most common
     codegen-side bugs.
   - `executor.py`: `run_generated_code` (env, cwd, timeout, error
     truncation).
   - `rollout.py:process_one_codegen` for per-task lifecycle.
3. **ReAct mode (`react`)**:
   - `react_agent.py`: `run_react`, `BASH_TOOL_CHAT`,
     `WRITE_FILE_TOOL_CHAT`, system-prompt assembly.
   - `recalc_harness.py` if `SPREADSHEETBENCH_RECALC=1` is set (check
     `run.sh` flags).
   - `rollout.py:process_one` for the per-task lifecycle.
4. `adapter.py` only if you suspect input formatting / output
   extraction / mode dispatch.

Don't read the whole codebase. Read just enough to ground each
diagnosis finding in a specific line range.

### 4. Diagnose — **classify each pattern**

For every recurring failure pattern (≥2 supporting samples), tag it
with the cheapest fix surface:

- **skill-content** — the skill text is missing a rule, contradictory,
  or doesn't tell the agent something it needs to know (e.g. "preserve
  other sheets when saving", "use the file's existing engine to keep
  formulas alive"). **Out of scope this round.** Flag for
  `/skillopt-loop` with a one-line summary + ≥ 2 failed sample IDs
  and pick a different surface to patch here. Do **not** edit
  `skill.md` — it's denylist.
- **harness-issue** — one of:
  - **codegen extraction** (regex misses ` ```python` vs ` ``` ` vs
    inline blocks; or accepts non-code chatter as code),
  - **workbook preview** (sheets/columns/formula info the agent needs
    isn't surfaced in `_preview_workbook`),
  - **executor sandbox** (`run_generated_code` missing a package on
    PYTHONPATH; cwd inside / outside the task dir; stderr truncated
    before the useful line; timeout too tight),
  - **loop policy** (codegen `max_turns=5` too small for the eval-mismatch
    retry pattern; ReAct stopping fires before the agent saves the
    output; no signal when budget is about to expire),
  - **tool inventory** (react-only — a tool the agent clearly wishes
    it had),
  - **tool result format unhelpful** (react-only — `bash` truncates
    output mid-line, agent retries blindly),
  - **arg validation / dispatch** (`run_tool` mishandles an argument
    type, `process_one_codegen` swallows a real error as
    `unexpected:…`).

For each pattern, cite:
- ≥2 sample ids + the turn / code-block number where the pattern
  appears
- 1 quote of the offending file (harness code line range, **or** the
  skill paragraph the agent is mis-applying — quoted as context only,
  not as a patch target, **or** the executor stderr tail)
- The fix surface you'll target and why it's cheaper than the
  alternative (e.g. "widening the codegen extraction regex catches
  every `output-not-found` from fenced-block edge cases; raising the
  executor timeout would be a strictly larger change")

### 5. Patch discipline (harness-specific)

**Hard rules** (enforced by `/harnessopt-loop` after you finish):

- **Only allowlist files** in `git diff --name-only`. Any denylist file
  in the diff — including `skills/initial.md` or
  `workspaces/<model>/skill.md` — auto-rejects the round.

(Diff size is **not** capped — the smoke val and full val gates are the
real quality filter. The round summary will report `diff=±N/Kf` so
large patches are visible.)

**Patch-shape preferences** (smallest effective change first):

1. For codegen: widen the extraction regex / add fallback for
   non-fenced output before adding a new prompt scaffold.
2. For the executor: surface the real stderr (raise the truncation cap
   from 4 KB → 8 KB, or move the truncation marker so the final line
   survives) before adding wholesale env changes.
3. For the preview: extend `_preview_workbook` to surface one missing
   field (sheet count, header row, formula presence) before rewriting
   the whole preview shape.
4. Adjust `max_turns` / `exec_timeout` config-side knobs aside — but
   if a loop-level constant in `rollout.py` / `codegen_agent.py` is
   wrong, patch it with conservative headroom (≤ +5 turns,
   ≤ 1.5× timeout); don't double it.
5. Tighten an existing tool's error / empty-result message (so the
   agent knows what went wrong) before adding a new tool.

**Required pattern — on/off toggle on every non-trivial code change**:

- Every change to `rollout.py` / `react_agent.py` / `codegen_agent.py` /
  `executor.py` / `recalc_harness.py` / `adapter.py` that changes
  runtime behavior (new code-extraction fallback, new preview field,
  new sandbox env var, new tool, new loop branch) **must be reachable
  via an on/off toggle**. Follow the existing `SPREADSHEETBENCH_RECALC*`
  precedent — read an env var at module import time:
  ```python
  _SPREADSHEETBENCH_PREVIEW_FORMULAS = os.environ.get(
      "SPREADSHEETBENCH_PREVIEW_FORMULAS", "1") == "1"
  ```
  or a module-level boolean constant near the top of the file. Default
  ON when the round accepts; the prior behavior must remain reachable
  when the flag is OFF (so the final report can A/B which round's
  change actually moved the score).
- **Don't strip prior rounds' toggles.** They're the bisection handles
  the loop needs. Pile them up; future cleanup is cheap, lost ablation
  signal is not.
- Exempt: pure refactors with no behavior change, constant bumps
  (`max_turns: 5 → 7`), tool docstring / description tweaks.
  Anything that adds a new code path or changes return shape needs the
  toggle.

**Forbidden patches** (auto-reject):

- Hardcoding answers, golden xlsx lookups, or task-specific shortcuts
  in `rollout.py` / `executor.py` / agent files. This is cheating
  against the eval.
- Modifying `evaluator.py` to be more lenient. This is cheating.
- Pre-running the golden code as a fallback. Cheating.
- Adding a non-trivial code change **without** an on/off toggle (see
  the "Required pattern" block above). The loop needs the toggle to
  bisect which round moved the score.
- Editing `skills/initial.md` or `workspaces/<model>/skill.md` — skill
  files are denylist this round; route skill rewrites to
  `/skillopt-loop`.
- Editing anything else in the denylist (`evaluator.py`, `dataloader.py`,
  `configs/`, `prompts/`).

### 6. Apply via `editFiles`, then self-verify

After applying:

```bash
cd harness_example/spreadsheetbench
git diff --stat .
git diff --numstat . | awk '{a+=$1; d+=$2} END {print "net="a+d}'
git diff --name-only . | sort
```

Confirm in chat:
- Net diff lines (informational — no cap; just report for the round
  summary).
- Every file in `--name-only` is in the allowlist
  (`rollout.py | react_agent.py | codegen_agent.py | executor.py |
  recalc_harness.py | adapter.py`).
- No skill file appears in the diff (`skills/initial.md` and
  `workspaces/<model>/skill.md` are denylist this round).

### 7. Smoke import check (cheap, catches the obvious)

```bash
cd .
python3 -c "
from harness_example.spreadsheetbench.adapter import SpreadsheetBenchAdapter
from harness_example.spreadsheetbench import (
    rollout, react_agent, codegen_agent, executor, recalc_harness,
    evaluator, dataloader,
)
print('ok adapter:', SpreadsheetBenchAdapter.__name__)
print('ok react tools:', [t['function']['name'] for t in [react_agent.BASH_TOOL_CHAT, react_agent.WRITE_FILE_TOOL_CHAT]])
"
```

If this raises (`ImportError`, `SyntaxError`, `AttributeError` on
`BASH_TOOL_CHAT`), **revert your patch** with
`git checkout -- harness_example/spreadsheetbench/` and stop. A broken
import wastes the full val gate and burns 6–18 min.

## Output (in chat, after applying)

Use these exact section headers, in order:

### Diagnosis
- First bullet: **sampling report** — failed/passed read, fail_reason
  clusters covered, turn / code-block ranges, files inspected (with
  line ranges).
- 2–4 bullets on the pattern(s) you chose to patch, each citing ≥2
  sample ids + turn or code-block numbers + 1 file quote (harness
  code; skill quotes only as context, never as patch target).
- For each pattern: which fix surface (harness code: codegen /
  executor / preview / loop / tool) and why.

### Patterns deferred to a later round
- 0–3 bullets listing patterns you saw but didn't patch (e.g. needs
  more samples, conflicts with this round's edit, requires a larger
  redesign). Cite sample ids so a future round can pick them up.

### Changes applied
- For each edited file: 1 line per edit with line range and a 1-line
  rationale.
- Net diff: `<N>` lines across `<K>` files in allowlist.
- Self-verify output (paste the `git diff --stat .` line).

### Expected impact
- Failure modes addressed (which fail_reason clusters; cite sample ids).
- Predicted Δ vs current val (rough range, e.g. "+0.05 to +0.10").
- Regressions to watch for (which passed sample types might break).

### Verify next
```bash
# Smoke val=5 first, then full val. /harnessopt-loop will do this.
bash run.sh --target_model gpt-5.4-nano --split val --eval_limit 5 --limit 5
```
Tell the user to compare new `hard=` against current best (look under
`workspaces/gpt-5.4-nano/.skillopt/_eval_run/`).

## Constraints

- Target model is **`gpt-5.4-nano`**. Don't change it.
- **Skill is denylist this round.** `skills/initial.md` and
  `workspaces/<model>/skill.md` are read-only context; skill rewrites
  belong to the `/skillopt-loop` slash command. The harness-opt loop's
  diff guard rejects the round if either file moves.
- **Allowlist** (only editable): `rollout.py`, `react_agent.py`,
  `codegen_agent.py`, `executor.py`, `recalc_harness.py`, `adapter.py`.
- **Denylist** (never editable): `evaluator.py`, `dataloader.py`,
  `configs/`, `prompts/*.md`, `skills/initial.md`,
  `workspaces/<model>/skill.md`.
- Do **not** run `run.sh` from this prompt — that's `/harnessopt-loop`'s
  job. This prompt is one local "improve" step, no eval.
- If your best patch would touch the denylist, or would add a
  non-trivial code change without an on/off toggle: **stop and ask
  the user** to relax the constraint explicitly. Don't silently work
  around it.
- Never delete files under `workspaces/<model>/.skillopt/history/` or
  git tags under `harness-opt/spreadsheetbench/*`.
