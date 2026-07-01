#!/usr/bin/env bash
# copilot_example/env.sh — thin delegator to the top-level env.sh.
#
# Historical layout had all the Azure config here; the public release moves
# the real config to the repo root so it can be shared with any future
# example directory. This shim keeps every run.sh unchanged:
#
#     source "$(dirname "$0")/../env.sh"

_COPILOT_EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$(dirname "${_COPILOT_EXAMPLE_DIR}")"

# shellcheck disable=SC1091
source "${_PROJECT_ROOT}/env.sh"
