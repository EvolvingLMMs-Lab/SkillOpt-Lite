#!/usr/bin/env bash
# copilot_example/alfworld/run.sh — end-to-end sample generator for the plugin.
#
# Prereqs: ALFWorld data installed (see ../alfworld/README.md or run_alfworld.sh).
#
# 1. Runs ALFWorld eval on `initial.md` (or --skill PATH) with gpt-5.4-nano
#    as the target model.
# 2. Exports the resulting results.jsonl into a plugin-ready workspace.
#
# Usage: same flags as livemath/run.sh. Smaller --limit recommended (5–10)
# because ALFWorld trajectories are long.

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
SPLIT="test"
LIMIT=8
EVAL_LIMIT=10       # 0 = all; ALFWorld episodes are slow, keep small
TARGET_MODEL="gpt-5.4-nano"
REASONING="medium"
SEED=42             # controls which items are sampled when EVAL_LIMIT<full split
WORKERS=128         # env worker count (overrides config workers=8)
MAX_API_WORKERS=128 # concurrent in-flight Azure OpenAI calls
SPLIT_DIR="${PROJECT_ROOT}/data/alfworld_split_200_140_134_seed42"
export ALFWORLD_DATA="${ALFWORLD_DATA:-${HOME}/.cache/alfworld}"

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
        --seed)            SEED="$2"; shift 2 ;;
        --workers)         WORKERS="$2"; shift 2 ;;
        --max_api_workers) MAX_API_WORKERS="$2"; shift 2 ;;
        --split_dir)       SPLIT_DIR="$2"; shift 2 ;;
        -h|--help)      sed -n '2,14p' "$0"; exit 0 ;;
        *)              echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

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

# ── ALFWorld data check ─────────────────────────────────────────────────────
if [[ ! -d "${ALFWORLD_DATA}/json_2.1.1" ]]; then
    echo "ERROR: ALFWorld data not found at ${ALFWORLD_DATA}/json_2.1.1" >&2
    echo "       pip install 'alfworld[full]' && alfworld-download" >&2
    echo "       Or set ALFWORLD_DATA to the directory containing json_2.1.1/" >&2
    exit 1
fi

# Ensure workspace dirs exist (no-op if already created in bootstrap).
mkdir -p "${WORKSPACE}/.skillopt/_eval_run" "${WORKSPACE}/.skillopt/history" \
         "${WORKSPACE}/.skillopt/samples/failed" "${WORKSPACE}/.skillopt/samples/passed"
EVAL_OUT="${WORKSPACE}/.skillopt/_eval_run/$(date +%Y%m%d_%H%M%S)"

echo "============================================================"
echo "  ALFWorld — eval + sample export"
echo "  Skill:        ${SKILL}"
echo "  Workspace:    ${WORKSPACE}"
echo "  Split:        ${SPLIT}  (limit=${LIMIT})"
echo "  Target:       ${TARGET_MODEL}  (reasoning=${REASONING})"
echo "  Seed:         ${SEED}"
echo "  Workers:      env=${WORKERS}  api=${MAX_API_WORKERS}"
echo "  Split dir:    ${SPLIT_DIR}"
echo "  ALFWorld data:${ALFWORLD_DATA}"
echo "  Eval out:     ${EVAL_OUT}"
echo "============================================================"

cd "${PROJECT_ROOT}"
python scripts/eval_only.py \
    --config configs/alfworld/default.yaml \
    --skill "${SKILL}" \
    --split "${SPLIT}" \
    --target_model "${TARGET_MODEL}" \
    --reasoning_effort "${REASONING}" \
    --seed "${SEED}" \
    --split_dir "${SPLIT_DIR}" \
    --test_env_num "${EVAL_LIMIT}" \
    --workers "${WORKERS}" \
    --max_api_workers "${MAX_API_WORKERS}" \
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
    --env alfworld \
    --limit "${LIMIT}"

# Optional human-facing completion hook (sentinel file + bell + desktop notify).
SCORES="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(f\"hard={d.get('hard',0):.4f} soft={d.get('soft',0):.4f} n={d.get('n','?')}\")" "${EVAL_OUT}/eval_summary.json" 2>/dev/null || echo "scores unavailable")"
notify_done "alfworld ${SPLIT} ${SCORES} (skill=${SKILL##*/})"

echo ""
echo "Done. Workspace: ${WORKSPACE}"
echo ""
echo "Next steps:"
echo "  1. Open the env folder in VS Code:  code $(dirname ${WORKSPACE})"
echo "  2. In Copilot Chat (Agent mode) run:  /skillopt-loop rounds=3 batch=20"
echo "     — or —"
echo "  3. Re-run this script with --split test --skill ${WORKSPACE}/skill.md for a straight eval."
