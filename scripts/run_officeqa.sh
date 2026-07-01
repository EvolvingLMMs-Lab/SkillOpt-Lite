#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# SkillOpt — OfficeQA training launch script (TRAPI edition)
#
# One-key per-model launchers live alongside this file:
#   scripts/run_officeqa_gpt-5.4.sh
#   scripts/run_officeqa_gpt-5.4-mini.sh
#   scripts/run_officeqa_gpt-5.4-nano.sh
#   scripts/run_officeqa_gpt-5.5.sh
#   scripts/run_officeqa_gpt-4o.sh
#
# Prerequisites:
#   data/officeqa_split/{train,val,test}/items.csv
#   data/officeqa_docs_official/    (override with OFFICEQA_DOCS_DIR)
#   OFFICEQA_CUSTOM_SEARCH_AUTH     (only if env.search_mode != offline)
#
# Usage:
#   bash scripts/run_officeqa.sh                              # defaults (gpt-5.5)
#   bash scripts/run_officeqa.sh --target_model gpt-5.4-nano
#   TARGET_MODEL=gpt-5.4 bash scripts/run_officeqa.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

# shellcheck source=trapi_env.sh
source "${SCRIPT_DIR}/trapi_env.sh"

TARGET_MODEL_ALIAS="${TARGET_MODEL:-gpt-5.5}"
OPTIMIZER_MODEL_ALIAS="${OPTIMIZER_MODEL:-gpt-5.5}"
PASSTHROUGH=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target_model)    TARGET_MODEL_ALIAS="$2"; shift 2 ;;
        --optimizer_model) OPTIMIZER_MODEL_ALIAS="$2"; shift 2 ;;
        *)                 PASSTHROUGH+=("$1"); shift ;;
    esac
done

apply_trapi_env "${TARGET_MODEL_ALIAS}" "${OPTIMIZER_MODEL_ALIAS}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_ROOT="${PROJECT_ROOT}/outputs/skillopt_officeqa_${TARGET_MODEL_ALIAS}_${TIMESTAMP}"

echo "============================================================"
echo "  SkillOpt — OfficeQA Training (TRAPI)"
echo "============================================================"
echo "  Optimizer:  ${OPTIMIZER_MODEL_ALIAS} → ${RESOLVED_OPTIMIZER_MODEL}"
echo "  Target:     ${TARGET_MODEL_ALIAS} → ${RESOLVED_TARGET_MODEL}"
echo "  Lane:       ${RESOLVED_TRAPI_LANE}"
echo "  Out root:   ${OUT_ROOT}"
echo "============================================================"

python scripts/train.py \
    --config configs/officeqa/default.yaml \
    --optimizer_model "${RESOLVED_OPTIMIZER_MODEL}" \
    --target_model "${RESOLVED_TARGET_MODEL}" \
    --azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --optimizer_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --optimizer_azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --optimizer_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --optimizer_azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --target_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --target_azure_openai_api_version "${AZURE_OPENAI_API_VERSION}" \
    --target_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --target_azure_openai_auth_mode "${AZURE_OPENAI_AUTH_MODE}" \
    --out_root "${OUT_ROOT}" \
    "${PASSTHROUGH[@]}"

echo ""
echo "Done! Results saved to: ${OUT_ROOT}"
