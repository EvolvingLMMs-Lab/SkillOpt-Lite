# SkillOptLite and HarnessOpt: Better and Faster Agent Self-evolution with One Line of Vibe

*Train your agent's skills and harness with a single line of vibe — automatic, looped improvements.*

[![arXiv](https://img.shields.io/badge/arXiv-coming%20soon-b31b1b)](#)
[![Poster](https://img.shields.io/badge/Poster-PDF-8a2be2)](images/icml2026_poster.pdf)
[![Report](https://img.shields.io/badge/Report-PDF-informational)](images/skillopt_lite.pdf)
[![HuggingFace Dataset](https://img.shields.io/badge/🤗%20Dataset-SkillOpt__Lite__Benchmarks-yellow)](https://huggingface.co/datasets/yshenaw/SkillOpt_Lite_Benchmarks)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<p align="center">
  <a href="images/wechat-group.jpg"><img src="images/wechat-group.jpg" alt="WeChat Group QR" width="220"/></a>
  <br/>
  <sub>Scan to join the WeChat community</sub>
</p>

---

## TL;DR

Do the one-time setup (`pip install -r requirements.txt`, fill in `.env`,
`source ./env.sh`, `python data/download.py` — see [Setup](#setup-one-time)
below). Then open the env folder **inside your coding agent** (VS Code
Copilot Chat, Codex CLI, Claude Code, kimi-code, glm-code, deepseek-tui —
anything that reads `.github/prompts/*.prompt.md`) and type one line at the
chat prompt:

```
cd copilot_example/livemath        # or spreadsheetbench / alfworld / ...
/skillopt-loop rounds=10 batch=40
```

That's it. The coding agent itself drives the loop — rollouts, sample
inspection, `skill.md` patches, val-gated keep-or-revert, archive to
`workspace/.skillopt/history/` — you don't touch anything else. When it
stops improving, `workspace/skill.md` is the artifact you ship.

**Two slash commands, one loop:**

| Command             | Cwd it expects                              | What the coding agent is allowed to edit                   |
| ------------------- | ------------------------------------------- | ---------------------------------------------------------- |
| `/skillopt-loop`    | inside `copilot_example/<env>/`             | just `skill.md`                                            |
| `/harnessopt-loop`  | inside `harness_example/<env>/`             | `skill.md` **and** the agent code (`rollout.py`, `react_agent.py`, `codegen_agent.py`, `executor.py`, `adapter.py`) |

Both are just prompt files at `<env>/.github/prompts/*.prompt.md` — read
them to tune the loop policy (round count, gate discipline, dead-band,
roll-back tag names).

## Pipeline

<p align="center">
  <img src="images/Pipeline.png" alt="SkillOptLite / HarnessOpt pipeline" width="820"/>
</p>

## Performance

<p align="center">
  <img src="images/Performance.png" alt="SkillOptLite vs SkillOpt across 6 benchmarks" width="900"/>
</p>

A few concrete headlines from the release ckpts:

| Setup                                    | Score |
| ---------------------------------------- | ----- |
| SpreadsheetBench, GPT-5.4-nano + HarnessOpt (`skill_best_nano.md`) | **0.7758** |
| SpreadsheetBench, GPT-5.5 baseline harness + full SkillOpt          | 0.7620 |
| LiveMath, GPT-5.5 + SkillOptLite         | **+8.8** pts over SkillOpt |
| LiveMath, GPT-5.4-nano + SkillOptLite    | **+25.4** pts over SkillOpt |
| ALFWorld, GPT-5.4-nano + SkillOptLite    | **81.3** (+9.5 over SkillOpt) |
| Spreadsheet, avg + SkillOptLite          | **+12.6** pts over SkillOpt |

All numbers come from the ckpts in this repo — reproduce them with
`scripts/eval_only.py` (see [Direct eval](#run-harnessopt-loop-skill--harness-code) below).

---

## What's in this repo

```
copilot_example/                  ← 6 benchmarks, run.sh + /skillopt-loop each
├── searchqa/    livemath/    alfworld/
├── docvqa/      officeqa/    spreadsheetbench/
├── env.sh                        thin auth delegator
└── make_samples.py               results.jsonl → per-item .md for the loop

harness_example/                  ← full harness training loop
└── spreadsheetbench/             baseline code + starting skills + /harnessopt-loop

skillopt_lite_ckpt/               ← baked skills produced by /skillopt-loop
└── <env>/<model>/skill.md        (per env × per target model)

harnessopt_ckpt/                  ← end-state of /harnessopt-loop
└── spreadsheetbench/             optimized code + best_skill_*.md snapshot

skillopt_ckpt/                    ← paper GPT-5.5 reference skills
└── <env>/gpt5.5_skill.md

skillopt/  scripts/  configs/     ← runtime the run.sh scripts call into
data/                             ← download.py + local split cache
docs/                             ← quickstart, auth, data
env.sh  .env.example              ← 3-mode auth bootstrap
```

Datasets are hosted on 🤗 [`yshenaw/SkillOpt_Lite_Benchmarks`](https://huggingface.co/datasets/yshenaw/SkillOpt_Lite_Benchmarks).

---

## Setup (one-time)

Assumed: Python 3.10+, any coding agent that supports slash-command
prompt files (VS Code Copilot Chat, Codex CLI, Claude Code, ...), and
either `az login` on Azure OpenAI, an OpenAI API key, or any
OpenAI-compatible endpoint (vLLM / ollama / together / ...).

```bash
# 1) Deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Auth (pick ONE mode — see docs/authentication.md)
cp .env.example .env
$EDITOR .env                       # AZURE_OPENAI_ENDPOINT / OPENAI_API_KEY / ...
source ./env.sh

# 3) Splits (~a few hundred MB, ALFWorld games + DocVQA images included)
python data/download.py
```

Smoke test any benchmark from the shell (no chat needed):

```bash
bash copilot_example/livemath/run.sh --eval_limit 5 --limit 5
```

---

## Run `/skillopt-loop` (skill-only optimization)

Inside your coding agent (agent / tool-use mode), type:

```
cd copilot_example/spreadsheetbench
/skillopt-loop rounds=10 batch=40
```

That's the whole "one line of vibe". The coding agent itself, per round,
runs `run.sh` on a `batch`-item slice of `train`, inspects the resulting
`.skillopt/samples/*.md` files, patches `workspace/skill.md`, re-runs
`run.sh --split val` as the accept/reject gate, and archives every attempt
into `workspace/.skillopt/history/`. When it finishes, the best skill
lives at `workspace/skill.md`:

```bash
bash run.sh --split test --skill $(pwd)/workspace/skill.md
```

The slash-command prompt lives at
`copilot_example/<env>/.github/prompts/skillopt-loop.prompt.md` — read it
if you want to tweak the loop policy (round count, gate discipline,
dead-band, roll-back tag names).

Baked outputs from previous runs are already in
[`skillopt_lite_ckpt/`](skillopt_lite_ckpt/) (per env × per target model),
so you can skip the loop and go straight to eval:

```bash
python scripts/eval_only.py \
    --config configs/spreadsheetbench/default.yaml \
    --skill skillopt_lite_ckpt/spreadsheetbench/gpt5.5/skill.md \
    --split test \
    --split_dir data/spreadsheetbench_split \
    --target_model gpt-5.5
```

---

## Run `/harnessopt-loop` (skill + harness code)

Same idea, but the loop is also allowed to edit the Python files under
`harness_example/<env>/`. Currently shipped: **SpreadsheetBench**.

Inside your coding agent:

```
cd harness_example/spreadsheetbench
/harnessopt-loop rounds=2 batch=12
```

Per round the coding agent `git tag`s a rollback point, runs full training
coverage, clusters failures into a taxonomy, proposes a plan that touches
an allow-listed subset of
`{rollout, react_agent, codegen_agent, executor, adapter}.py` and/or
`skill.md`, **pauses for user approval**, applies the patch, re-runs val,
and either keeps it or `git reset`s back to the tag. When done, the
optimized bundle lives in your working tree; a matching frozen snapshot
is in
[`harnessopt_ckpt/spreadsheetbench/`](harnessopt_ckpt/spreadsheetbench/)
(both code and `best_skill_*.md`).

Direct eval from a frozen snapshot:

```bash
python scripts/eval_only.py \
    --config configs/spreadsheetbench/default.yaml \
    --skill harnessopt_ckpt/spreadsheetbench/best_skill_5.5.md \
    --split test \
    --split_dir data/spreadsheetbench_split \
    --target_model gpt-5.5
```

Or replay the whole run with the exact snapshotted harness:

```bash
cd harnessopt_ckpt/spreadsheetbench
bash run.sh --model gpt-5.4-nano --skill skill_best_nano.md
```

---

## Auth modes at a glance

| Mode              | When                                             | Vars                                                     |
| ----------------- | ------------------------------------------------ | -------------------------------------------------------- |
| `azure_cli` (default) | Azure OpenAI + `az login`                    | `AZURE_OPENAI_ENDPOINT`                                  |
| `azure_key`       | Azure OpenAI + resource key                      | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`          |
| `openai`          | Official OpenAI or any OpenAI-compatible server  | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`             |

Set `SKILLOPT_AUTH_MODE` in `.env`. Full walkthrough in
[docs/authentication.md](docs/authentication.md).

---

## Adding a new benchmark or model

- **New benchmark for `/skillopt-loop`:** drop a folder into
  `copilot_example/<env>/` with `dataloader.py`, `rollout.py`,
  `skills/initial.md`, and a `run.sh` wired to
  `scripts/eval_only.py --config configs/<env>/default.yaml`. Copy an
  existing `.github/prompts/skillopt-loop.prompt.md` next to it and edit
  the split sizes.
- **New benchmark for `/harnessopt-loop`:** mirror the same layout under
  `harness_example/<env>/`, register `<env>-local` in
  `scripts/eval_only.py` and `scripts/train.py`, and add a
  `configs/<env>-local/default.yaml` that inherits from the base config.
- **New target model:** add the deployment name + backend routing in
  `configs/_base_/default.yaml` and pass `--target_model <name>` to
  `run.sh`. If the model needs a fresh backend (chat / exec) plug it in
  under `skillopt/model/`.

---

## Roadmap / TODO

- [ ] **Agent-agnostic loop runner.** A drop-in script that wraps `/skillopt-loop`
  around *any* existing agent codebase (not just the `copilot_example/` and
  `harness_example/` layouts). Bring your own `rollout(item) → trace, score`
  and a `skill.md` entry point, get the same round-based
  train → patch → val-gate → rollback loop. (Coming soon.)
- [ ] **Codex CLI plugin.** Port the `/skillopt-loop` and `/harnessopt-loop`
  slash-commands to OpenAI Codex CLI so the same loop works outside VS Code.
- [ ] **Claude Code plugin.** Same, for Anthropic Claude Code — package the
  prompts as a slash-command extension.

Contributions welcome — open an issue at
[EvolvingLMMs-Lab/SkillOpt-Lite](https://github.com/EvolvingLMMs-Lab/SkillOpt-Lite/issues)
if you want to help land any of the above.

---

## Cite

```bibtex
@article{shen2026skilloptlite,
  title  = {SkillOpt-Lite: Better and Faster Agent Self-evolution with One Line of Vibe},
  author = {Shen, Yifei and Li, Bo and Zhang, Xinjie},
  year   = {2026},
  note   = {arXiv link coming soon}
}
```

---

## Contact

- WeChat community: [scan the QR above](images/wechat-group.jpg)
- Correspondence: `yshenaw@connect.ust.hk`
- Issues / PRs: welcome at [EvolvingLMMs-Lab/SkillOpt-Lite](https://github.com/EvolvingLMMs-Lab/SkillOpt-Lite)

## Acknowledgements

Built on top of [**SkillOpt**](https://github.com/microsoft/SkillOpt) — the
text-space optimizer that trains reusable natural-language skills for frozen
LLM agents through trajectory-driven edits, validation-gated updates, and
deployable `best_skill.md` artifacts. `SkillOpt-Lite` is the minimal
coding-agent-driven variant of that loop; `HarnessOpt` extends the same
loop to also edit the agent code. Huge thanks to the SkillOpt authors and
contributors for the original design and open-source release.

Released under the [MIT License](LICENSE).
