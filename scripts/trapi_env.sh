# ──────────────────────────────────────────────────────────────────────────────
# Shared TRAPI helper for scripts/run_*.sh
#
# Exposes:
#   resolve_trapi_deployment <model>       → echoes the dated deployment name
#   apply_trapi_env <target_model> [optimizer_model]
#       → exports AZURE_OPENAI_* + TARGET_* + OPTIMIZER_* env vars pointing at
#         TRAPI, picks a TRAPI lane appropriate for the chosen model, and sets
#         RESOLVED_TARGET_MODEL / RESOLVED_OPTIMIZER_MODEL.
#
# Endpoint lanes (verified 2026-06-22):
#   msra/shared    — ALL models OK including gpt-5.4, gpt-5.5, Qwen/Qwen3.5-9B
#   gcr/shared     — gpt-5.5 currently OK; gpt-5.4 family historically 403/503
#
# Default lane is msra/shared (covers every model). Override per shell via
#   SKILLOPT_TRAPI_LANE=gcr/shared bash scripts/run_officeqa_gpt-5.5.sh
# ──────────────────────────────────────────────────────────────────────────────

# Translate a friendly model alias to its dated TRAPI deployment name. Pass
# through if the input already looks like a dated name.
resolve_trapi_deployment() {
    local model="$1"
    case "${model}" in
        gpt-5.4-nano|gpt-5.4-nano_*)     echo "gpt-5.4-nano_2026-03-17" ;;
        gpt-5.4-mini|gpt-5.4-mini_*)     echo "gpt-5.4-mini_2026-03-17" ;;
        gpt-5.4|gpt-5.4_*)               echo "gpt-5.4_2026-03-05" ;;
        gpt-5.5|gpt-5.5_*)               echo "gpt-5.5_2026-04-24" ;;
        qwen3.5-9b|qwen3.5-9B|Qwen3.5-9B|Qwen/Qwen3.5-9B)
                                         echo "Qwen/Qwen3.5-9B" ;;
        gpt-5-nano|gpt-5-nano_*)         echo "gpt-5-nano_2025-08-07" ;;
        gpt-5-mini|gpt-5-mini_*)         echo "gpt-5-mini_2025-08-07" ;;
        gpt-5|gpt-5_*)                   echo "gpt-5_2025-08-07" ;;
        gpt-4o|gpt-4o_*)                 echo "gpt-4o_2024-11-20" ;;
        gpt-4o-mini|gpt-4o-mini_*)       echo "gpt-4o-mini_2024-07-18" ;;
        *)                               echo "${model}" ;;
    esac
}

# Choose a TRAPI lane for a model. Qwen lives only on msra/shared; everything
# else uses ${SKILLOPT_TRAPI_LANE:-msra/shared}.
_trapi_lane_for_model() {
    local model="$1"
    case "${model}" in
        qwen3.5-9b|qwen3.5-9B|Qwen3.5-9B|Qwen/Qwen3.5-9B)
            echo "msra/shared" ;;
        *)
            echo "${SKILLOPT_TRAPI_LANE:-msra/shared}" ;;
    esac
}

# Set up all the env vars scripts/train.py expects. Idempotent — safe to call
# multiple times in a row.
apply_trapi_env() {
    local target_model="${1:?apply_trapi_env: missing target_model}"
    local optimizer_model="${2:-${target_model}}"

    local target_dep optimizer_dep lane
    target_dep="$(resolve_trapi_deployment "${target_model}")"
    optimizer_dep="$(resolve_trapi_deployment "${optimizer_model}")"
    lane="$(_trapi_lane_for_model "${target_model}")"

    local endpoint="https://trapi.research.microsoft.com/${lane}"

    # Shared (used by gate / one-off eval calls)
    export AZURE_OPENAI_ENDPOINT="${endpoint}"
    export AZURE_OPENAI_AD_SCOPE="api://trapi/.default"
    export AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-10-21}"
    export AZURE_OPENAI_AUTH_MODE="${AZURE_OPENAI_AUTH_MODE:-azure_cli}"
    unset AZURE_OPENAI_API_KEY  # TRAPI is token-based

    # Target lane
    export TARGET_AZURE_OPENAI_ENDPOINT="${endpoint}"
    export TARGET_AZURE_OPENAI_AD_SCOPE="api://trapi/.default"
    export TARGET_AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION}"
    export TARGET_AZURE_OPENAI_AUTH_MODE="${AZURE_OPENAI_AUTH_MODE}"

    # Optimizer lane
    export OPTIMIZER_AZURE_OPENAI_ENDPOINT="${endpoint}"
    export OPTIMIZER_AZURE_OPENAI_AD_SCOPE="api://trapi/.default"
    export OPTIMIZER_AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION}"
    export OPTIMIZER_AZURE_OPENAI_AUTH_MODE="${AZURE_OPENAI_AUTH_MODE}"

    # Resolved names so the run script can forward --target_model / --optimizer_model
    export RESOLVED_TARGET_MODEL="${target_dep}"
    export RESOLVED_OPTIMIZER_MODEL="${optimizer_dep}"
    export RESOLVED_TRAPI_LANE="${lane}"

    # Convenience env vars some backends read directly
    export TARGET_DEPLOYMENT="${target_dep}"
    export OPTIMIZER_DEPLOYMENT="${optimizer_dep}"

    echo "[trapi_env] lane=${lane}"
    echo "[trapi_env]   target    : ${target_model} → ${target_dep}"
    echo "[trapi_env]   optimizer : ${optimizer_model} → ${optimizer_dep}"
    echo "[trapi_env]   endpoint  : ${endpoint}"
}
