#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# SkillOpt — officeqa training (target=gpt-5.4-nano, optimizer=gpt-5.5 by default)
#
# Thin wrapper over scripts/run_officeqa.sh that sets TARGET_MODEL=gpt-5.4-nano.
# Override OPTIMIZER_MODEL or SKILLOPT_TRAPI_LANE via env vars; pass extra
# flags through to train.py via "$@".
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export TARGET_MODEL="gpt-5.4-nano"
export OPTIMIZER_MODEL="${OPTIMIZER_MODEL:-gpt-5.5}"

exec bash "${SCRIPT_DIR}/run_officeqa.sh" "$@"
