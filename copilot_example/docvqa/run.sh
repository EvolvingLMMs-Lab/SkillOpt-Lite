#!/usr/bin/env bash
# copilot_example/docvqa/run.sh — end-to-end sample generator for the plugin.
#
# Prereqs: DocVQA data installed locally.
#   1. Split id manifest (this is the public artifact, JSON per split):
#        data/docvqa_id_split/{train,val,test}/items.json
#      Pull with: git checkout origin/main -- data/docvqa_id_split/
#   2. Materialized CSV rows + page images (NOT in this repo — gated on HF):
#        <split_dir>/{train,val,test}/*.csv     (one CSV per split)
#        data/docvqa_images/q<questionId>_d<docId>.png
#      The dataloader (skillopt/envs/docvqa/dataloader.py) reads the CSV;
#      the id manifest defines which rows belong to which split.
#   Override at runtime via --split_dir.
#
# 1. Runs DocVQA eval on `workspace/skill.md` (or --skill PATH) with the
#    target model (default gpt-5.5, medium reasoning).
# 2. Exports the resulting results.jsonl into a plugin-ready workspace.
#
# Usage: same flags as searchqa/run.sh + --split_dir.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../env.sh"

# ── Model short-name resolver ───────────────────────────────────────────────
# Maps dated TRAPI deployment names back to short aliases for workspace paths.
# E.g. gpt-5.5_2026-04-24 → gpt-5.5, Qwen/Qwen3.5-9B → qwen3.5-9b
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
        *)                      echo "${m}" ;;
    esac
}

# ── Defaults ────────────────────────────────────────────────────────────────
# WORKSPACE is auto-resolved after --target_model is known (see below).
# User can override via --workspace to use a custom path.
SKILL=""           # will be resolved to workspace skill or initial skill
WORKSPACE=""       # "" = auto-resolve to workspaces/<model>/
SPLIT="test"
LIMIT=20
EVAL_LIMIT=0        # 0 = all items in split; small number = fast smoke
TARGET_MODEL="gpt-5.5"
REASONING="medium"
WORKERS=16          # docvqa config default; bump cautiously (image payload heavy)
SEED=42             # controls which items are sampled when EVAL_LIMIT<full split
SPLIT_DIR="${PROJECT_ROOT}/data/docvqa_id_split"

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
        -h|--help)      sed -n '2,21p' "$0"; exit 0 ;;
        *)              echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Route AZURE_OPENAI_ENDPOINT based on the chosen target model.
select_endpoint_for_model "${TARGET_MODEL}"
# After routing, use the resolved (dated TRAPI) deployment name from now on.
TARGET_MODEL="${RESOLVED_TARGET_MODEL:-${TARGET_MODEL}}"

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

# ── Data presence check ─────────────────────────────────────────────────────
if [[ ! -d "${SPLIT_DIR}" ]]; then
    echo "ERROR: split dir not found: ${SPLIT_DIR}" >&2
    echo "       Override with --split_dir <path>, or pull the public id split:" >&2
    echo "         git checkout origin/main -- data/docvqa_id_split/" >&2
    exit 1
fi
if ! find "${SPLIT_DIR}/${SPLIT}" -maxdepth 1 -name '*.csv' -print -quit | grep -q .; then
    echo "ERROR: no *.csv found in ${SPLIT_DIR}/${SPLIT}" >&2
    echo "       The pulled id_split only contains items.json (questionId/docId/image_path)." >&2
    echo "       Materialize full CSV rows + page images from lmms-lab/DocVQA before evaluation," >&2
    echo "       or point --split_dir at an already-materialized split tree." >&2
    exit 1
fi

# Ensure workspace dirs exist (no-op if already created in bootstrap).
mkdir -p "${WORKSPACE}/.skillopt/_eval_run" "${WORKSPACE}/.skillopt/history" \
         "${WORKSPACE}/.skillopt/samples/failed" "${WORKSPACE}/.skillopt/samples/passed"
EVAL_OUT="${WORKSPACE}/.skillopt/_eval_run/$(date +%Y%m%d_%H%M%S)"

echo "============================================================"
echo "  DocVQA — eval + sample export"
echo "  Skill:      ${SKILL}"
echo "  Workspace:  ${WORKSPACE}"
echo "  Split:      ${SPLIT}  (eval_limit=${EVAL_LIMIT}, sample_limit=${LIMIT})"
echo "  Target:     ${TARGET_MODEL}  (reasoning=${REASONING})"
echo "  Workers:    ${WORKERS}"
echo "  Seed:       ${SEED}"
echo "  Split dir:  ${SPLIT_DIR}"
echo "  Eval out:   ${EVAL_OUT}"
echo "============================================================"

cd "${PROJECT_ROOT}"
# Forward the TRAPI-resolved endpoint/scope/api_version as CLI flags so they
# override the vanilla Azure OpenAI defaults baked into configs/_base_/default.yaml
# (which would otherwise force ad_scope=cognitiveservices.azure.com → TRAPI 401).
python scripts/eval_only.py \
    --config configs/docvqa/default.yaml \
    --skill "${SKILL}" \
    --split "${SPLIT}" \
    --target_model "${TARGET_MODEL}" \
    --reasoning_effort "${REASONING}" \
    --workers "${WORKERS}" \
    --seed "${SEED}" \
    --split_dir "${SPLIT_DIR}" \
    --test_env_num "${EVAL_LIMIT}" \
    --out_root "${EVAL_OUT}" \
    --azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --target_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --target_azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --target_azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --target_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --optimizer_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --optimizer_azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --optimizer_azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --optimizer_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}"

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
    --env docvqa \
    --limit "${LIMIT}"

# Optional human-facing completion hook (see env.sh `notify_done`).
SCORES="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(f\"hard={d.get('hard',0):.4f} soft={d.get('soft',0):.4f} n={d.get('n','?')}\")" "${EVAL_OUT}/eval_summary.json" 2>/dev/null || echo "scores unavailable")"
notify_done "docvqa ${SPLIT} ${SCORES} (skill=${SKILL##*/}, model=${TARGET_MODEL})"

echo ""
echo "Done. Workspace: ${WORKSPACE}"
echo ""
echo "Next steps:"
echo "  1. Open the env folder in VS Code:  code $(dirname ${WORKSPACE})"
echo "  2. In Copilot Chat (Agent mode) run:  /skillopt-loop rounds=3 batch=20"
echo "     — or —"
echo "  3. Re-run this script with --split test --skill ${WORKSPACE}/skill.md for a straight eval."
