#!/usr/bin/env bash
# copilot_example/officeqa/run.sh — end-to-end sample generator for the plugin.
#
# Prereqs: OfficeQA data installed locally (manual; gated on HF):
#   1. Splits dir (CSV per split, with uid/question/ground_truth/source_files):
#        data/officeqa_split/{train,val,test}/items.csv
#   2. Document bundle (referenced by each row's source_files):
#        data/officeqa_docs_official/{jsons,transformed,...}/
#   Override at runtime via --split_dir / --data_root, or via OFFICEQA_DOCS_DIR.
#
# 1. Runs OfficeQA eval on `workspace/skill.md` (or --skill PATH) with the
#    target model (default gpt-5.5, medium reasoning).
# 2. Exports the resulting results.jsonl into a plugin-ready workspace.
#
# Search tool: defaults to offline (env.search_mode=offline) so this script
# works without OFFICEQA_CUSTOM_SEARCH_AUTH. The skill explicitly drives the
# agent through local-doc grep/read tools — the public web search hurts more
# than it helps on table-extraction questions. Pass --search_mode online to
# enable the duckduckgo gateway (requires OFFICEQA_CUSTOM_SEARCH_AUTH).
#
# Usage: same flags as spreadsheetbench/run.sh + --split_dir, --data_root,
# --search_mode.

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
LIMIT=24           # samples to export to .skillopt/samples/ (0 = all from eval)
EVAL_LIMIT=24      # tasks to actually eval; 0 = full split
TARGET_MODEL="gpt-5.5"
REASONING="medium"
SEED=42
WORKERS=16         # config default is 4; bump for parallel rollout
MAX_API_WORKERS=16 # concurrent in-flight TRAPI calls
SPLIT_DIR="${PROJECT_ROOT}/data/officeqa_split"
DATA_ROOT="${PROJECT_ROOT}/data/officeqa_docs_official"
SEARCH_MODE="offline"   # offline | online

# ── Parse args ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skill)           SKILL="$2"; shift 2 ;;
        --workspace)       WORKSPACE="$2"; shift 2 ;;
        --split)           SPLIT="$2"; shift 2 ;;
        --limit)           LIMIT="$2"; shift 2 ;;
        --eval_limit)      EVAL_LIMIT="$2"; shift 2 ;;
        --target_model)    TARGET_MODEL="$2"; shift 2 ;;
        --reasoning)       REASONING="$2"; shift 2 ;;
        --seed)            SEED="$2"; shift 2 ;;
        --workers)         WORKERS="$2"; shift 2 ;;
        --max_api_workers) MAX_API_WORKERS="$2"; shift 2 ;;
        --split_dir)       SPLIT_DIR="$2"; shift 2 ;;
        --data_root)       DATA_ROOT="$2"; shift 2 ;;
        --search_mode)     SEARCH_MODE="$2"; shift 2 ;;
        -h|--help)         sed -n '2,21p' "$0"; exit 0 ;;
        *)                 echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Route AZURE_OPENAI_ENDPOINT based on the chosen target model.
# After routing, use the resolved (dated TRAPI) deployment name from here on.
select_endpoint_for_model "${TARGET_MODEL}"
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
# This allows prompts and manual commands to use `workspace/skill.md` without
# specifying the model each time.
WORKSPACE_LINK="${SCRIPT_DIR}/workspace"
if [[ -L "${WORKSPACE_LINK}" ]]; then
    rm "${WORKSPACE_LINK}"
fi
if [[ ! -e "${WORKSPACE_LINK}" ]]; then
    ln -s "workspaces/${MODEL_SHORT}" "${WORKSPACE_LINK}"
    echo "[run.sh] Symlinked workspace → workspaces/${MODEL_SHORT}"
fi

# ── Data presence check ─────────────────────────────────────────────────────
if [[ ! -d "${SPLIT_DIR}" ]]; then
    echo "ERROR: split dir not found: ${SPLIT_DIR}" >&2
    echo "       Override with --split_dir <path>, or install splits there." >&2
    echo "       (databricks/officeqa is gated on HuggingFace — accept the" >&2
    echo "        license and download items.csv per split manually.)" >&2
    exit 1
fi
if [[ ! -d "${DATA_ROOT}" ]]; then
    echo "ERROR: officeqa docs root not found: ${DATA_ROOT}" >&2
    echo "       Override with --data_root <path> or OFFICEQA_DOCS_DIR." >&2
    exit 1
fi

if [[ "${SEARCH_MODE}" != "offline" && -z "${OFFICEQA_CUSTOM_SEARCH_AUTH:-}" ]]; then
    echo "WARNING: --search_mode=${SEARCH_MODE} but OFFICEQA_CUSTOM_SEARCH_AUTH is unset." >&2
    echo "         External search calls will fail. Falling back to offline." >&2
    SEARCH_MODE="offline"
fi

# Ensure workspace dirs exist (no-op if already created in bootstrap).
mkdir -p "${WORKSPACE}/.skillopt/_eval_run" "${WORKSPACE}/.skillopt/history" \
         "${WORKSPACE}/.skillopt/samples/failed" "${WORKSPACE}/.skillopt/samples/passed"
EVAL_OUT="${WORKSPACE}/.skillopt/_eval_run/$(date +%Y%m%d_%H%M%S)"

echo "============================================================"
echo "  OfficeQA — eval + sample export"
echo "  Model:        ${MODEL_SHORT}  (deployment=${TARGET_MODEL})"
echo "  Workspace:    ${WORKSPACE}"
echo "  Skill:        ${SKILL}"
echo "  Split:        ${SPLIT}  (eval_limit=${EVAL_LIMIT}, sample_limit=${LIMIT})"
echo "  Reasoning:    ${REASONING}"
echo "  Search mode:  ${SEARCH_MODE}"
echo "  Seed:         ${SEED}"
echo "  Workers:      env=${WORKERS}  api=${MAX_API_WORKERS}"
echo "  Split dir:    ${SPLIT_DIR}"
echo "  Data root:    ${DATA_ROOT}"
echo "  Eval out:     ${EVAL_OUT}"
echo "============================================================"

cd "${PROJECT_ROOT}"
python scripts/eval_only.py \
    --config configs/officeqa/default.yaml \
    --skill "${SKILL}" \
    --split "${SPLIT}" \
    --target_model "${TARGET_MODEL}" \
    --reasoning_effort "${REASONING}" \
    --seed "${SEED}" \
    --split_dir "${SPLIT_DIR}" \
    --data_root "${DATA_ROOT}" \
    --test_env_num "${EVAL_LIMIT}" \
    --workers "${WORKERS}" \
    --max_api_workers "${MAX_API_WORKERS}" \
    --out_root "${EVAL_OUT}" \
    --cfg-options "env.search_mode=${SEARCH_MODE}" ${MAX_COMPLETION_TOKENS:+"env.max_completion_tokens=${MAX_COMPLETION_TOKENS}"} \
    --azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --target_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --target_azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --target_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --target_azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --optimizer_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --optimizer_azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --optimizer_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --optimizer_azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}"

RESULTS_JSONL="$(find "${EVAL_OUT}" -name results.jsonl -type f | head -1)"
if [[ -z "${RESULTS_JSONL}" ]]; then
    echo "ERROR: no results.jsonl produced under ${EVAL_OUT}" >&2
    exit 3
fi
echo "Found results: ${RESULTS_JSONL}"

# Mirror the skill into the workspace so the plugin sees the exact text the
# eval used. Skip when --skill already IS the workspace skill.
if [[ "$(readlink -f "${SKILL}")" != "$(readlink -f "${WORKSPACE}/skill.md")" ]]; then
    cp "${SKILL}" "${WORKSPACE}/skill.md"
fi

python "${COPILOT_EXAMPLE_DIR}/make_samples.py" \
    --results "${RESULTS_JSONL}" \
    --workspace "${WORKSPACE}" \
    --env officeqa \
    --limit "${LIMIT}"

# Optional human-facing completion hook (see env.sh `notify_done`).
SCORES="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(f\"hard={d.get('hard',0):.4f} soft={d.get('soft',0):.4f} n={d.get('n','?')}\")" "${EVAL_OUT}/eval_summary.json" 2>/dev/null || echo "scores unavailable")"
notify_done "officeqa ${SPLIT} ${SCORES} (skill=${SKILL##*/}, model=${TARGET_MODEL})"

echo ""
echo "Done. Open ${WORKSPACE} in VS Code, then:"
echo "  Ctrl+Shift+P  →  Chat: Run Prompt  →  /skillopt-improve   (single round)"
echo "  Ctrl+Shift+P  →  Chat: Run Prompt  →  /skillopt-loop      (closed loop)"
