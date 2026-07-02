# harness_example/ — in-shell training loop

Standalone counterpart to [`copilot_example/`](../copilot_example/). Where the
copilot flow prepares samples for a coding-agent slash command to iterate on,
`harness_example/` runs the full skill-optimization loop entirely in a shell
(rollouts → reflect → skill patch → eval) with every env's runtime editable
in place.

## What ships now

| Benchmark        | Runner                                              | Starting skills                                    |
| ---------------- | --------------------------------------------------- | -------------------------------------------------- |
| SpreadsheetBench | [`spreadsheetbench/run.sh`](spreadsheetbench/run.sh) | `best_skill_5.4.md`, `best_skill_5.5.md`, `best_skill_mini.md`, `skill_best_nano.md` |

Other benchmarks (ALFWorld, DocVQA, LiveMath, OfficeQA, SearchQA) follow the
same layout in the internal monorepo and will land here in a future cut. For
those benchmarks today, use the paper-reference skills under
[`../skillopt_ckpt/`](../skillopt_ckpt/) with `scripts/eval_only.py`.

## Layout

```
harness_example/
└── spreadsheetbench/
    ├── run.sh                    # one-command training runner
    ├── adapter.py                # env adapter (dataset ↔ SkillOpt harness)
    ├── rollout.py                # batch rollout orchestration
    ├── react_agent.py            # tool-using ReAct agent (Chat/Responses)
    ├── codegen_agent.py          # code-generation agent (baseline behavior)
    ├── executor.py               # sandboxed Python exec
    ├── evaluator.py              # openpyxl grader
    ├── dataloader.py             # split loader
    ├── skills/initial.md         # starting skill run.sh seeds into workspace
    ├── prompts/                  # system-prompt fragments
    ├── best_skill_5.4.md         # per-model starting skills
    ├── best_skill_5.5.md         #   (copies of copilot_example/ckpt/*/skill.md,
    ├── best_skill_mini.md        #    renamed to the harness naming convention)
    ├── skill_best_nano.md
    └── .github/                  # optional GitHub Copilot prompts for the loop
```

The `.py` files under `spreadsheetbench/` mirror
`skillopt/envs/spreadsheetbench/` in the runtime package, with all
`from skillopt.envs.spreadsheetbench.*` imports rewritten as relative imports
so you can hack on them without touching the installed package.

## Running

**Open `harness_example/spreadsheetbench/` in your coding agent** (VS
Code Copilot Chat / Codex CLI / Claude Code / kimi-code / glm-code /
deepseek-tui — any host that reads local `.github/prompts/*.prompt.md`),
then **type this at the coding-agent chat prompt** (not a shell terminal):

In `harness_example/spreadsheetbench`, type:

```
/harnessopt-loop rounds=2 batch=40 target=gpt-5.4-nano skill=skills/initial.md
```

The coding agent handles env setup for you (pip install, `source
../env.sh`, data download) and then drives the full loop: rollout → smoke
val → improve → full val gate → keep or `git reset` to the round tag,
repeated for N rounds.

If you'd rather run the harness once outside the loop:

```bash
cd release_pkg/harness_example/spreadsheetbench
bash run.sh --model gpt-5.5 --skill skills/initial.md
```

Consult [`run.sh`](spreadsheetbench/run.sh) for the full flag surface
(model selection, effort tier, workspace path, eval-only mode).

## Optimized outputs (what this loop produced)

The full harness-optimized end-state of the loop — the modified
`codegen_agent.py` / `rollout.py` / etc. **plus** the produced
`best_skill_*.md` files — lives verbatim in
[`../harnessopt_ckpt/spreadsheetbench/`](../harnessopt_ckpt/spreadsheetbench/).

If you only want the optimized skill markdown (no code) for direct evaluation
with `scripts/eval_only.py`, grab any `best_skill_*.md` from that same
directory — it evaluates against the stock env in `skillopt/envs/`.
