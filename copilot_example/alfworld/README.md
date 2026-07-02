# alfworld/

Reference implementation for **ALFWorld**: a multi-turn embodied-agent
benchmark (text-based household tasks). Lifted from `skillopt/envs/alfworld/`
for plugin debugging.

## Task

- **Input:** a high-level goal like *"put a clean mug in the cabinet"* plus the
  initial scene observation.
- **Agent:** multi-turn loop. Each turn:
  - system prompt = `prompts/rollout_with_history.md` (or `_no_history.md` /
    `_with_memory.md`) filled with the current skill;
  - user message = current observation + admissible actions;
  - LLM emits an action string; environment returns next observation.
  - Episode ends on success / failure / max steps.
- **Scoring:** binary `success` (task goal achieved) + `n_turns`.

## Files

| File | Purpose |
|---|---|
| `rollout.py` | `build_alfworld_env()`, `run_alfworld_batch()`, `TASKS` list |
| `adapter.py` | task instance → rollout input shape |
| `dataloader.py` | load ALFWorld task splits |
| `reflect.py` | old per-episode error analysis (kept for reference) |
| `prompts/rollout_with_history.md` | default agent prompt (sees full action history) |
| `prompts/rollout_with_memory.md` | variant: summarized memory instead of full history |
| `prompts/rollout_no_history.md` | variant: no history (state-only) |
| `prompts/analyst_error.md`, `analyst_success.md` | old reflect prompts |
| `skills/initial.md` | baseline skill |
| `vendor/` | vendored SkillRL ALFWorld env wrapper |

## Why ALFWorld is the hard case

Unlike SearchQA / livemath (single LLM call → one short answer), ALFWorld
**trajectories are long** — typically 20–50 turns per episode, each with a
multi-line observation. A naive dump of one failed episode can be 5–10k
characters.

The exporter handles this by:
1. wrapping the trajectory in `<details><summary>` so Copilot sees a
   collapsed view by default, only expanding when asked;
2. truncating at 8000 chars with a `[truncated N chars]` marker.

You should still pick a small `--limit` (5–10 episodes) when generating
samples for ALFWorld, otherwise the loop's context gets noisy.

## Generating samples for the plugin

```bash
python copilot_example/make_samples.py \
    --results /path/to/alf_run/test_eval/results.jsonl \
    --workspace copilot_example/alfworld/workspace \
    --env alfworld --limit 8
```

The exporter recognizes ALFWorld-specific fields:
- `task` / `goal` / `instruction` → `## Input`
- `success` → status (passed/failed)
- `trajectory` / `trace` / `turns` / `messages` → `## Trace` (collapsed)

## Run the /skillopt-loop

**Open the `copilot_example/alfworld/` folder in your coding agent** (VS Code
Copilot Chat / Codex CLI / Claude Code / kimi-code / glm-code /
deepseek-tui — any host that reads local `.github/prompts/*.prompt.md`),
then **type this at the coding-agent chat prompt** (not a shell terminal):

In `copilot_example/alfworld`, type:

```
/skillopt-loop rounds=2 batch=8 target=gpt-5.4-nano
```

That's the whole loop — your coding agent handles env setup (pip
install, `source ../env.sh`, data download) and then runs `run.sh`,
inspects samples, patches `skill.md`, val-gates, and archives, all on
its own. No manual bootstrap needed.

Manual sample refresh (already have results.jsonl):

```bash
WS=copilot_example/alfworld/workspaces/gpt-5.4-nano
mkdir -p "$WS"
cp copilot_example/alfworld/skills/initial.md "$WS/skill.md"
python copilot_example/make_samples.py \
    --results /path/to/alf_run/test_eval/results.jsonl \
    --workspace "$WS" --env alfworld --limit 8
```

## Notes when reviewing patches

- ALFWorld rewards are sparse — a single failed episode can be very noisy
  signal. Prefer `batch >= 6` so the loop sees patterns across episodes.
- Many "failures" are actually planning issues (wrong tool used too early),
  not skill issues. When the loop suggests rewriting the skill but the trace
  shows a search bug, the right fix may be in `vendor/` or `rollout.py`
  — not in `skill.md`. Consider `/harnessopt-loop` instead if you want the
  loop to also touch the agent code.
