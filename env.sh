#!/usr/bin/env bash
# env.sh — SkillOpt_Lite environment bootstrap (public release)
#
# Source this once per shell before running anything under copilot_example/:
#     source ./env.sh
#
# Selects one of three LLM authentication modes via SKILLOPT_AUTH_MODE:
#
#   azure_cli   Azure OpenAI + AAD via `az login`     (no api key needed)
#   azure_key   Azure OpenAI + api key                (AZURE_OPENAI_API_KEY)
#   openai      Official OpenAI (or any OpenAI-       (OPENAI_API_KEY,
#               compatible endpoint, e.g. together,    optional OPENAI_BASE_URL)
#               vLLM, ollama)
#
# The mode is read from ${SKILLOPT_AUTH_MODE:-azure_cli}. You can also drop a
# .env file next to this script — it will be auto-sourced if present.
#
# ── Repo root ───────────────────────────────────────────────────────────────
_SKILLOPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PROJECT_ROOT="${_SKILLOPT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

# Auto-load .env if present (never committed; see .env.example for keys).
if [[ -f "${_SKILLOPT_ROOT}/.env" ]]; then
    # shellcheck disable=SC1090
    set -a; source "${_SKILLOPT_ROOT}/.env"; set +a
fi

_MODE="${SKILLOPT_AUTH_MODE:-azure_cli}"

# ── Mode dispatch ───────────────────────────────────────────────────────────
case "${_MODE}" in

    azure_cli)
        : "${AZURE_OPENAI_ENDPOINT:?Set AZURE_OPENAI_ENDPOINT, e.g. https://<resource>.openai.azure.com/}"
        export AZURE_OPENAI_ENDPOINT
        export AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-12-01-preview}"
        export AZURE_OPENAI_AUTH_MODE="azure_cli"
        export AZURE_OPENAI_AD_SCOPE="${AZURE_OPENAI_AD_SCOPE:-https://cognitiveservices.azure.com/.default}"
        unset AZURE_OPENAI_API_KEY OPENAI_API_KEY OPENAI_BASE_URL

        if ! command -v az >/dev/null 2>&1; then
            echo "[env.sh] ERROR: azure_cli mode requires the 'az' CLI on PATH." >&2
            echo "         Install: https://learn.microsoft.com/cli/azure/install-azure-cli" >&2
            return 1 2>/dev/null || exit 1
        fi
        if ! az account show >/dev/null 2>&1; then
            echo "[env.sh] WARNING: 'az login' has not been run in this profile." >&2
            echo "         Run: az login   (or set AZURE_CONFIG_DIR to a profile that has)." >&2
        fi
        ;;

    azure_key)
        : "${AZURE_OPENAI_ENDPOINT:?Set AZURE_OPENAI_ENDPOINT, e.g. https://<resource>.openai.azure.com/}"
        : "${AZURE_OPENAI_API_KEY:?Set AZURE_OPENAI_API_KEY (Azure OpenAI resource key)}"
        export AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY
        export AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-12-01-preview}"
        export AZURE_OPENAI_AUTH_MODE="api_key"
        unset OPENAI_API_KEY OPENAI_BASE_URL
        ;;

    openai)
        : "${OPENAI_API_KEY:?Set OPENAI_API_KEY (from https://platform.openai.com/api-keys)}"
        # Backend uses OpenAI SDK with base_url + api_key when auth_mode = openai_compatible.
        export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
        export AZURE_OPENAI_ENDPOINT="${OPENAI_BASE_URL}"   # SkillOpt_Lite reads this var for the endpoint
        export AZURE_OPENAI_API_KEY="${OPENAI_API_KEY}"
        export AZURE_OPENAI_API_VERSION="openai-compat"
        export AZURE_OPENAI_AUTH_MODE="openai_compatible"
        ;;

    *)
        echo "[env.sh] ERROR: unknown SKILLOPT_AUTH_MODE='${_MODE}'." >&2
        echo "         Valid modes: azure_cli | azure_key | openai" >&2
        return 1 2>/dev/null || exit 1
        ;;
esac

# ── Model → deployment mapping ──────────────────────────────────────────────
# When you call `scripts/eval_only.py --target_model X`, SkillOpt_Lite uses X
# verbatim as the deployment/model name. For Azure, this must match the
# deployment name you created in the Azure portal (e.g. "gpt-4o" or
# "gpt-4o-mini"). For OpenAI, it must be a valid model id (e.g. "gpt-4o",
# "gpt-4o-mini", "o3-mini").
#
# The old TRAPI-specific mapping in the internal env.sh has been removed;
# users can define their own alias here or override per-command.

select_endpoint_for_model() {
    # No-op in the public release; kept for run.sh compatibility.
    # (Internal deployments used this to swap TRAPI lanes.)
    :
}

# ── Completion notification (best-effort) ───────────────────────────────────
notify_done() {
    local msg="${1:-skillopt run done}"
    local sentinel="${SKILLOPT_DONE_FILE:-/tmp/skillopt_done}"
    printf '[%s] %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "${msg}" >> "${sentinel}" 2>/dev/null || true
    printf '\a'
    if [[ "${SKILLOPT_DESKTOP_NOTIFY:-0}" == "1" ]] \
       && command -v notify-send >/dev/null 2>&1; then
        notify-send "SkillOpt_Lite run done" "${msg}" 2>/dev/null || true
    fi
}

echo "[env.sh] mode=${_MODE}"
echo "[env.sh] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[env.sh] endpoint=${AZURE_OPENAI_ENDPOINT}"
