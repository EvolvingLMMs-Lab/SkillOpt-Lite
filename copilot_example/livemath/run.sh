#!/usr/bin/env bash
# copilot_example/livemath/run.sh — end-to-end sample generator for the plugin.
#
# Prereqs: Fetch LiveMathematicianBench data first by running
#   cd $PROJECT_ROOT && python scripts/fetch_livemath_bench.py
# That creates data/live_math_bench/ and data/livemath_split/.
#
# This script:
# 1. Runs LiveMathematicianBench eval on `initial.md` (or --skill PATH) with
#    gpt-5.4-nano as the target model.
# 2. Exports the resulting results.jsonl into a plugin-ready workspace under
#    .skillopt/samples/{failed,passed}/.
#
# Usage:
#   bash run.sh                          # smoke: 5-task val subset
#   bash run.sh --eval_limit 20 --limit 20  # larger run
#   bash run.sh --skill myskill.md --split test --eval_limit 0 --limit 20
#
# Key flags:
#   --skill PATH       Skill file to inject into the system prompt.
#   --workspace PATH   Where to store .skillopt/samples/* — can be reused
#                      by the VS Code extension.
#   --split            train | val | test (default: val).
#   --eval_limit N     Number of problems to evaluate (0 = all).
#   --limit N          How many failed/passed samples to export to workspace.
#   --target_model     The TRAPI deployment model name (default: gpt-5.4-nano).
#   --reasoning        Reasoning effort: none | low | medium | high (default: medium).
#   --workers N        Concurrent worker count (default: 128).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../env.sh"

# ── Model short-name resolver ───────────────────────────────────────────────
# Maps dated TRAPI deployment names back to short aliases for workspace paths.
# E.g. gpt-5.5_2026-04-24 → gpt-5.5, Qwen/Qwen3.5-9B → qwen3.5-9b,
#     Qwen/Qwen3.5-27B → qwen3.5-27b
model_short_name() {
    local m="$1"
    case "${m}" in
        gpt-5.5*|gpt-5.5_*)     echo "gpt-5.5" ;;
        gpt-5.4-nano*|gpt-5.4-nano_*) echo "gpt-5.4-nano" ;;
        gpt-5.4-mini*|gpt-5.4-mini_*) echo "gpt-5.4-mini" ;;
        gpt-5.4*|gpt-5.4_*)     echo "gpt-5.4" ;;
        gpt-5-nano*|gpt-5-nano_*) echo "gpt-5-nano" ;;
        gpt-5-mini*|gpt-5-mini_*) echo "gpt-5-mini" ;;
        gpt-5*|gpt-5_*)         echo "gpt-5" ;;
        gpt-4o-mini*|gpt-4o-mini_*) echo "gpt-4o-mini" ;;
        gpt-4o*|gpt-4o_*)       echo "gpt-4o" ;;
        Qwen/Qwen3.5-9B|qwen3.5-9b|qwen3.5-9B) echo "qwen3.5-9b" ;;
        Qwen/Qwen3.5-27B|qwen3.5-27b|qwen3.5-27B) echo "qwen3.5-27b" ;;
        *)                      echo "${m}" ;;
    esac
}

# ── Defaults ────────────────────────────────────────────────────────────────
# WORKSPACE is auto-resolved after --target_model is known (see below).
# User can override via --workspace to use a custom path.
SKILL=""           # will be resolved to workspace skill or initial skill
WORKSPACE=""       # "" = auto-resolve to workspaces/<model>/
SPLIT="val"
LIMIT=5
EVAL_LIMIT=5        # 0 = all; non-zero = quick smoke test
TARGET_MODEL="gpt-5.4-nano"
REASONING="medium"
WORKERS=128         # concurrent API workers
SEED=42             # controls which items are sampled when EVAL_LIMIT<full split
SPLIT_DIR="${PROJECT_ROOT}/data/ablation_splits/livemathematicianbench/2-2-6_seed42"
ENABLE_TOOLS=0      # 0 = off (default). 1 = expose sympy tool to the agent
ENABLE_ROUTER=0     # 0 = off (default). 1 = enable per-question skill router
ROUTER_CONFIG=""    # path to router.json; auto-resolves to ${WORKSPACE}/router.json if unset & router enabled
USE_BEST=0          # 0 = off (default). 1 = before eval, promote latest *best.md from .skillopt/history to skill.md

# ── Parse args ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skill)        SKILL="$2"; shift 2 ;;
        --workspace)    WORKSPACE="$2"; shift 2 ;;
        --split)        SPLIT="$2"; shift 2 ;;
        --limit)        LIMIT="$2"; shift 2 ;;
        --eval_limit)   EVAL_LIMIT="$2"; shift 2 ;;
        --target_model) TARGET_MODEL="$2"; shift 2 ;;
        --reasoning)    REASONING="$2"; shift 2 ;;
        --workers)      WORKERS="$2"; shift 2 ;;
        --seed)         SEED="$2"; shift 2 ;;
        --split_dir)    SPLIT_DIR="$2"; shift 2 ;;
        --enable_tools)   ENABLE_TOOLS=1; shift 1 ;;
        --enable_router)  ENABLE_ROUTER=1; shift 1 ;;
        --router_config)  ROUTER_CONFIG="$2"; shift 2 ;;
        --use_best)       USE_BEST=1; shift 1 ;;
        -h|--help)      sed -n '2,28p' "$0"; exit 0 ;;
        *)              echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Pin the TRAPI lane to msra/shared (only lane that serves the full model
# matrix; gcr/shared is capacity-limited, redmond/interactive is down).
export SKILLOPT_TRAPI_LANE="${SKILLOPT_TRAPI_LANE:-msra/shared}"

# Route AZURE_OPENAI_ENDPOINT based on the chosen target model.
select_endpoint_for_model "${TARGET_MODEL}"
# After routing, use the resolved (dated TRAPI) deployment name from now on.
TARGET_MODEL="${RESOLVED_TARGET_MODEL:-${TARGET_MODEL}}"
# Cap WORKERS/MAX_API_WORKERS for throttled deployments (see env.sh).
apply_model_workers_cap

# ── Auto-resolve workspace per model ────────────────────────────────────────
# Workspaces are isolated by model so runs don't clobber each other.
# Structure: workspaces/<model_short>/{skill.md, .skillopt/}
MODEL_SHORT="$(model_short_name "${TARGET_MODEL}")"
if [[ -z "${WORKSPACE}" ]]; then
    WORKSPACE="${SCRIPT_DIR}/workspaces/${MODEL_SHORT}"
fi
if [[ -z "${SKILL}" ]]; then
    SKILL="${WORKSPACE}/skill.md"
fi

# Bootstrap workspace if it doesn't exist: create dirs + copy initial skill.
if [[ ! -d "${WORKSPACE}" ]]; then
    echo "[run.sh] Creating new workspace for model=${MODEL_SHORT}: ${WORKSPACE}"
    mkdir -p "${WORKSPACE}/.skillopt/history" \
             "${WORKSPACE}/.skillopt/samples/failed" \
             "${WORKSPACE}/.skillopt/samples/passed" \
             "${WORKSPACE}/.skillopt/_eval_run"
    if [[ -f "${SCRIPT_DIR}/skills/initial.md" ]]; then
        cp "${SCRIPT_DIR}/skills/initial.md" "${WORKSPACE}/skill.md"
        echo "[run.sh] Seeded skill.md from skills/initial.md"
    else
        echo "[run.sh] WARNING: skills/initial.md not found; workspace has no skill.md"
    fi
fi

# Create/update symlink `workspace` → current model's workspace for convenience.
WORKSPACE_LINK="${SCRIPT_DIR}/workspace"
if [[ -L "${WORKSPACE_LINK}" ]]; then
    rm "${WORKSPACE_LINK}"
fi
if [[ ! -e "${WORKSPACE_LINK}" ]]; then
    ln -s "workspaces/${MODEL_SHORT}" "${WORKSPACE_LINK}"
    echo "[run.sh] Symlinked workspace → workspaces/${MODEL_SHORT}"
fi

# ── LiveMath data check ─────────────────────────────────────────────────────
if [[ ! -d "${SPLIT_DIR}" ]]; then
    echo "ERROR: LiveMathematicianBench split data not found at ${SPLIT_DIR}" >&2
    echo "       cd \$PROJECT_ROOT && python scripts/fetch_livemath_bench.py" >&2
    exit 1
fi

# Ensure workspace dirs exist (no-op if already created in bootstrap).
mkdir -p "${WORKSPACE}/.skillopt/_eval_run" "${WORKSPACE}/.skillopt/history" \
         "${WORKSPACE}/.skillopt/samples/failed" "${WORKSPACE}/.skillopt/samples/passed"
EVAL_OUT="${WORKSPACE}/.skillopt/_eval_run/$(date +%Y%m%d_%H%M%S)"

# ── Optional: promote latest best snapshot to on-disk skill ────────────────
if [[ "${USE_BEST}" == "1" ]]; then
    HIST_DIR="${WORKSPACE}/.skillopt/history"
    if [[ -d "${HIST_DIR}" ]]; then
        # Pick chronologically latest *best.md (mtime order)
        LATEST_BEST="$(ls -t "${HIST_DIR}"/*best.md 2>/dev/null | head -n1 || true)"
        if [[ -n "${LATEST_BEST}" && -f "${LATEST_BEST}" ]]; then
            CUR_MD5="$(md5sum "${SKILL}" 2>/dev/null | awk '{print $1}')"
            BEST_MD5="$(md5sum "${LATEST_BEST}" | awk '{print $1}')"
            if [[ "${CUR_MD5}" != "${BEST_MD5}" ]]; then
                BACKUP="${HIST_DIR}/$(date +%Y%m%d_%H%M%S)__pre_use_best__before.md"
                cp "${SKILL}" "${BACKUP}"
                cp "${LATEST_BEST}" "${SKILL}"
                echo "[run.sh] --use_best: promoted $(basename "${LATEST_BEST}") → skill.md (backup: $(basename "${BACKUP}"))"
            else
                echo "[run.sh] --use_best: on-disk skill.md already matches latest best ($(basename "${LATEST_BEST}"))"
            fi
        else
            echo "[run.sh] --use_best: no *best.md snapshot in ${HIST_DIR}; skipping"
        fi
    else
        echo "[run.sh] --use_best: history dir not found; skipping"
    fi
fi

echo "============================================================"
echo "  LiveMathematicianBench — eval + sample export"
echo "  Skill:      ${SKILL}"
echo "  Workspace:  ${WORKSPACE}"
echo "  Split:      ${SPLIT}  (limit=${LIMIT})"
echo "  Target:     ${TARGET_MODEL}  (reasoning=${REASONING})"
echo "  Workers:    ${WORKERS}"
echo "  Seed:       ${SEED}"
echo "  Split dir:  ${SPLIT_DIR}"
echo "  Eval out:   ${EVAL_OUT}"
echo "============================================================"

# ── Optional harness extensions (default OFF) ──────────────────────────────
if [[ "${ENABLE_TOOLS}" == "1" ]]; then
    export SKILLOPT_LIVEMATH_TOOLS=1
    echo "[run.sh] harness: sympy tool loop ENABLED"
fi
if [[ "${ENABLE_ROUTER}" == "1" ]]; then
    export SKILLOPT_LIVEMATH_ROUTER=1
    if [[ -z "${ROUTER_CONFIG}" ]]; then
        ROUTER_CONFIG="${WORKSPACE}/router.json"
    fi
    if [[ ! -f "${ROUTER_CONFIG}" ]]; then
        echo "[run.sh] WARNING: --enable_router set but ${ROUTER_CONFIG} not found; router will be a no-op" >&2
    fi
    export SKILLOPT_LIVEMATH_ROUTER_CONFIG="${ROUTER_CONFIG}"
    echo "[run.sh] harness: skill router ENABLED (config=${ROUTER_CONFIG})"
fi

cd "${PROJECT_ROOT}"
python scripts/eval_only.py \
    --config configs/livemathematicianbench/default.yaml \
    --skill "${SKILL}" \
    --split "${SPLIT}" \
    --target_model "${TARGET_MODEL}" \
    --reasoning_effort "${REASONING}" \
    --workers "${WORKERS}" \
    --seed "${SEED}" \
    --split_dir "${SPLIT_DIR}" \
    --test_env_num "${EVAL_LIMIT}" \
    --azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --target_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --target_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --optimizer_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --optimizer_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --out_root "${EVAL_OUT}"

RESULTS_JSONL="$(find "${EVAL_OUT}" -name results.jsonl -type f | head -1)"
if [[ -z "${RESULTS_JSONL}" ]]; then
    echo "ERROR: no results.jsonl produced under ${EVAL_OUT}" >&2
    exit 3
fi
echo "Found results: ${RESULTS_JSONL}"

# Mirror the skill into the workspace so the plugin sees the exact text the
# eval used. Skip when the source already *is* the workspace skill.
if [[ "$(readlink -f "${SKILL}")" != "$(readlink -f "${WORKSPACE}/skill.md")" ]]; then
    cp "${SKILL}" "${WORKSPACE}/skill.md"
fi

python "${COPILOT_EXAMPLE_DIR}/make_samples.py" \
    --results "${RESULTS_JSONL}" \
    --workspace "${WORKSPACE}" \
    --env livemath \
    --limit "${LIMIT}"

# Optional human-facing completion hook (sentinel file + bell + desktop notify).
SCORES="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(f\"hard={d.get('hard',0):.4f} soft={d.get('soft',0):.4f} n={d.get('n','?')}\")" "${EVAL_OUT}/eval_summary.json" 2>/dev/null || echo "scores unavailable")"
notify_done "livemath ${SPLIT} ${SCORES} (skill=${SKILL##*/})"

echo ""
echo "Done. Workspace: ${WORKSPACE}"
echo ""
echo "Next steps:"
echo "  1. Open the env folder in VS Code:  code $(dirname ${WORKSPACE})"
echo "  2. In Copilot Chat (Agent mode) run:  /skillopt-loop rounds=3 batch=20"
echo "     — or —"
echo "  3. Re-run this script with --split test --skill ${WORKSPACE}/skill.md for a straight eval."
