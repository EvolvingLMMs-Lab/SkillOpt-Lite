#!/usr/bin/env bash
# Eval the paper-provided gpt-5.5 livemath skill on the full test split,
# routed through the TRAPI gcr/shared lane.
#
# Skill:     ckpt/livemath/gpt5.5_skill.md
# Target:    gpt-5.5  (TRAPI dep gpt-5.5_2026-04-24, gcr/shared)
# Split:     valid_unseen (test) of data/ablation_splits/livemathematicianbench/2-2-6_seed42
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

# shellcheck disable=SC1091
source "${PROJECT_ROOT}/official_example/env.sh"

export SKILLOPT_TRAPI_LANE="${SKILLOPT_TRAPI_LANE:-gcr/shared}"
select_endpoint_for_model gpt-5.5
TARGET_DEP="${RESOLVED_TARGET_MODEL}"
OPT_DEP="$(resolve_trapi_dep gpt-5.5)"

TS="$(date +%Y%m%d_%H%M%S)"
OUT_ROOT="${OUT_ROOT:-${PROJECT_ROOT}/outputs/eval_livemath_ckpt_gpt5.5_gcr_${TS}}"
mkdir -p "${OUT_ROOT}"

echo "============================================================"
echo "  livemath eval — paper skill (ckpt/livemath/gpt5.5_skill.md)"
echo "  Target:     ${TARGET_DEP}  (reasoning=medium)"
echo "  Lane:       ${SKILLOPT_TRAPI_LANE}"
echo "  Endpoint:   ${AZURE_OPENAI_ENDPOINT}"
echo "  Split:      valid_unseen (test) — full"
echo "  Out:        ${OUT_ROOT}"
echo "============================================================"

python scripts/eval_only.py \
    --config configs/livemathematicianbench/default.yaml \
    --skill ckpt/livemath/gpt5.5_skill.md \
    --split valid_unseen \
    --split_dir data/ablation_splits/livemathematicianbench/2-2-6_seed42 \
    --target_model "${TARGET_DEP}" \
    --optimizer_model "${OPT_DEP}" \
    --reasoning_effort medium \
    --workers 64 \
    --max_api_workers 64 \
    --seed 42 \
    --azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --target_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --target_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --optimizer_azure_openai_endpoint "${AZURE_OPENAI_ENDPOINT}" \
    --optimizer_azure_openai_ad_scope "${AZURE_OPENAI_AD_SCOPE}" \
    --out_root "${OUT_ROOT}"

echo ""
echo "============================================================"
if [[ -f "${OUT_ROOT}/eval_summary.json" ]]; then
    python3 -c "import json,sys;d=json.load(open('${OUT_ROOT}/eval_summary.json'));print(f\"hard={d['hard']:.4f} soft={d['soft']:.4f} n={d['n_items']}\")"
fi
echo "  out_root: ${OUT_ROOT}"
echo "============================================================"
