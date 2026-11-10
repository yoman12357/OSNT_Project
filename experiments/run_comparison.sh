#!/usr/bin/env bash
set -euo pipefail
# Compatibility entry point for the completed paired workflow.
if [[ $# -ne 0 ]]; then
    echo 'The single-mode interface has been replaced by the paired campaign.' >&2
    echo 'Run: PYTHON_BIN=<venv-python> bash experiments/run_all.sh' >&2
    echo 'See experiments/README.md for options and retained-results protection.' >&2
    exit 2
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec bash "${SCRIPT_DIR}/run_all.sh"
