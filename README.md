# SkillOptLite and HarnessOpt: Better and Faster Agent Self-evolution with One Line of Vibe

*Train your agent's skills and harness with a single line of vibe — automatic, looped improvements.*

[![arXiv](https://img.shields.io/badge/arXiv-coming%20soon-b31b1b)](#)
[![Poster](https://img.shields.io/badge/Poster-PDF-8a2be2)](images/icml2026_poster.pdf)
[![Report](https://img.shields.io/badge/Report-PDF-informational)](images/skillopt_lite.pdf)
[![HuggingFace Dataset](https://img.shields.io/badge/🤗%20Dataset-SkillOpt__Lite__Benchmarks-yellow)](https://huggingface.co/datasets/yshenaw/SkillOpt_Lite_Benchmarks)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<p align="center">
👉 <b><a href="https://evolvinglmms-lab.github.io/SkillOpt-Lite/">Project Page</a></b> 👈
</p>

<p align="center">
👉 <b><a href="images/wechat-group.jpg">WeChat Group</a></b> 👈
</p>

---

## TL;DR

**Open this repo folder inside your coding agent** (VS Code Copilot
Chat, Codex CLI, Claude Code, kimi-code, glm-code, deepseek-tui —
anything that reads `.github/prompts/*.prompt.md`), then **type the
commands below into that same coding-agent chat** — not a plain shell.
The coding agent handles environment setup for you (`pip install`,
auth, data download); you never leave the chat.

**1. Optimize a skill on a shipped benchmark** (edit `skill.md` only).
Open `copilot_example/livemath` (or `spreadsheetbench` / `alfworld` /
`docvqa` / `officeqa` / `searchqa`) with your coding agent, then type
at the chat prompt:

```
/skillopt-loop rounds=10 batch=40 target=gpt-5.4-nano
```

**2. Co-optimize skill + agent harness** (also edit the Python code).
Open `harness_example/spreadsheetbench` with your coding agent, then
type at the chat prompt:

```
/harnessopt-loop rounds=2 batch=40 target=gpt-5.4-nano skill=skill_best_nano.md
```

**3. Bring your own repo + data** — no shim to write; point the coding
agent at a reference env and let it scaffold. Sample vibe:

> Read `copilot_example/livemath/` as a reference (env code +
> `.github/prompts/skillopt-loop.prompt.md`). Build a new env at
> `copilot_example/myrepo/` that runs my eval:
> `python -m myrepo.eval --items X --skill Y --out results.jsonl`.
> My raw data is a single `data/all.jsonl` — split it **2:2:6**
> (train / val / test) with a fixed seed. Each result row has
> `{id, input, expected, predicted, success}`. Also copy and adapt
> the slash-command prompt files to my layout — `skillopt-loop.prompt.md`
> for skill-only, and `harnessopt-loop.prompt.md` (see
> `harness_example/spreadsheetbench/.github/prompts/`) if I want harness
> co-optimization; rewrite their split sizes, allow-listed editable files,
> and rollback tag prefix to match my directory. Smoke-test with
> `--eval_limit 5` and confirm `samples/failed/*.md` is non-empty.

Once it reports done, run flow #1 or #2 against the new folder.

In all three cases the coding agent drives the loop — rollouts, sample
inspection, `skill.md` patches, val-gated keep-or-revert, archive to
`workspace/.skillopt/history/`. You don't touch anything else. When it
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

## Setup (fallback — your coding agent normally handles this)

Skip this section unless you're running headless or want to prep the
environment before opening the coding agent. In the normal flow, the
first time you issue any TL;DR command your coding agent will `pip
install -r requirements.txt`, prompt you to fill in `.env` for whichever
auth mode fits (`az login` / OpenAI key / OpenAI-compatible endpoint),
`source ./env.sh`, and `python data/download.py` before starting the
loop.

Manual bootstrap:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && $EDITOR .env       # AZURE_OPENAI_ENDPOINT / OPENAI_API_KEY / ...
source ./env.sh
python data/download.py                     # ~a few hundred MB
```

Full auth walkthrough (Azure CLI / Azure key / OpenAI / OpenAI-compatible)
in [docs/authentication.md](docs/authentication.md).

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
