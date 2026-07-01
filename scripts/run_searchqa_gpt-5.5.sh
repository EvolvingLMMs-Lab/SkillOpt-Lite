#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# SkillOpt — searchqa training (target=gpt-5.5, optimizer=gpt-5.5 by default)
#
# Thin wrapper over scripts/run_searchqa.sh that sets TARGET_MODEL=gpt-5.5.
# Override OPTIMIZER_MODEL or SKILLOPT_TRAPI_LANE via env vars; pass extra
# flags through to train.py via "$@".
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export TARGET_MODEL="gpt-5.5"
export OPTIMIZER_MODEL="${OPTIMIZER_MODEL:-gpt-5.5}"

exec bash "${SCRIPT_DIR}/run_searchqa.sh" "$@"
