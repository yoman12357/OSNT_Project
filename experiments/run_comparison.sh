#!/usr/bin/env bash
set -euo pipefail

# Run one reproducible CUBIC experiment in the existing netns topology.
# Usage: sudo ./experiments/run_comparison.sh baseline|rli [rate-limited|bulk]

MODE=${1:-}
WORKLOAD=${2:-rate-limited}
PYTHON_BIN=${PYTHON_BIN:-python3}

if [[ ${EUID} -ne 0 ]]; then
    echo "Run as root: sudo $0 baseline|rli [rate-limited|bulk]" >&2
    exit 1
fi

if [[ ${MODE} != baseline && ${MODE} != rli ]]; then
    echo "Mode must be 'baseline' or 'rli'." >&2
    exit 1
fi

if [[ ${WORKLOAD} != rate-limited && ${WORKLOAD} != bulk ]]; then
    echo "Workload must be 'rate-limited' or 'bulk'." >&2
    exit 1
fi

for command_name in ip git sha256sum; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        echo "Required command not found: ${command_name}" >&2
        exit 1
    fi
done
if ! "${PYTHON_BIN}" --version >/dev/null 2>&1; then
    echo "Python interpreter is not executable: ${PYTHON_BIN}" >&2
    exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
BUILD_DIR=${BUILD_DIR:-"${REPO_ROOT}/build"}
DEMO="${BUILD_DIR}/picoquicdemo"
RLI_OPTION=rli=off
if [[ ${MODE} == rli ]]; then
    RLI_OPTION=rli=on
fi

for required in "${DEMO}" "${REPO_ROOT}/certs/cert.pem" \
    "${REPO_ROOT}/certs/key.pem" "${REPO_ROOT}/certs/test-ca.crt"; do
    if [[ ! -e ${required} ]]; then
        echo "Required file not found: ${required}" >&2
        exit 1
    fi
done

for namespace in rls-client rls-r1 rls-r2 rls-server; do
    if ! ip netns list | awk '{print $1}' | grep -Fxq "${namespace}"; then
        echo "Topology is not active. Run: sudo ${REPO_ROOT}/topology/setup.sh" >&2
        exit 1
    fi
done

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RESULT_DIR="${REPO_ROOT}/experiments/results/${MODE}/${WORKLOAD}/${RUN_ID}"
mkdir -p "${RESULT_DIR}"

SERVER_LOG="${RESULT_DIR}/server.stdout.log"
CLIENT_LOG="${RESULT_DIR}/client.stdout.log"
SERVER_PERF="${RESULT_DIR}/server-performance.csv"
CLIENT_PERF="${RESULT_DIR}/client-performance.csv"

server_pid=
stop_server() {
    if [[ -n ${server_pid} ]] && kill -0 "${server_pid}" 2>/dev/null; then
        kill "${server_pid}" 2>/dev/null || true
        wait "${server_pid}" 2>/dev/null || true
    fi
}
trap stop_server EXIT INT TERM

ip netns exec rls-server "${DEMO}" -1 -p 4443 \
    -c "${REPO_ROOT}/certs/cert.pem" \
    -k "${REPO_ROOT}/certs/key.pem" \
    -w "${REPO_ROOT}" -G cubic -H "${RLI_OPTION}" \
    -q "${RESULT_DIR}" -L -F "${SERVER_PERF}" \
    >"${SERVER_LOG}" 2>&1 &
server_pid=$!
sleep 1

if [[ ${WORKLOAD} == rate-limited ]]; then
    # 20 frames/s * 1200 bytes for 400 frames: about 192 kbit/s for 20 s.
    # The server is intentionally well below the 20 Mbit/s bottleneck.
    PERF_SCENARIO='=rli:s20:n400:1200:G20:I1200;'
    ip netns exec rls-client "${DEMO}" -D -a perf \
        -G cubic -H "${RLI_OPTION}" \
        -t "${REPO_ROOT}/certs/test-ca.crt" -n test.example.com \
        -q "${RESULT_DIR}" -L -F "${CLIENT_PERF}" \
        10.10.2.2 4443 "${PERF_SCENARIO}" \
        >"${CLIENT_LOG}" 2>&1
else
    BULK_FILE="${REPO_ROOT}/file_20M.bin"
    if [[ ! -f ${BULK_FILE} ]]; then
        dd if=/dev/urandom of="${BULK_FILE}" bs=1M count=20 status=none
    fi
    ip netns exec rls-client "${DEMO}" -D \
        -G cubic -H "${RLI_OPTION}" \
        -t "${REPO_ROOT}/certs/test-ca.crt" -n test.example.com \
        -q "${RESULT_DIR}" -L -F "${CLIENT_PERF}" \
        10.10.2.2 4443 /file_20M.bin \
        >"${CLIENT_LOG}" 2>&1
fi

wait "${server_pid}"
server_pid=

SERVER_QLOG=$(find "${RESULT_DIR}" -maxdepth 1 -type f -name '*.server.qlog' -print -quit)
if [[ -z ${SERVER_QLOG} ]]; then
    echo "No sender qlog was produced; inspect ${SERVER_LOG}." >&2
    exit 1
fi

"${PYTHON_BIN}" "${REPO_ROOT}/plot_cwnd.py" "${SERVER_QLOG}" \
    "${RESULT_DIR}/cubic-${MODE}-${WORKLOAD}.png"

if [[ ${MODE} == rli ]]; then
    VALIDATION_ARGS=(check "${SERVER_QLOG}")
    if [[ ${WORKLOAD} == rate-limited ]]; then
        # A rate-limited comparison is only meaningful if the implementation
        # was exercised strongly enough for at least one cap to be observed.
        VALIDATION_ARGS+=(--require-cap)
    fi
    "${PYTHON_BIN}" "${REPO_ROOT}/experiments/validate_rli.py" \
        "${VALIDATION_ARGS[@]}" | tee "${RESULT_DIR}/validation.txt"
fi

GIT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD)
GIT_DIFF_HASH=$(git -C "${REPO_ROOT}" diff --binary | git hash-object --stdin)
if [[ -n $(git -C "${REPO_ROOT}" status --porcelain=v1) ]]; then
    GIT_TREE_STATE=dirty
else
    GIT_TREE_STATE=clean
fi
git -C "${REPO_ROOT}" status --porcelain=v1 >"${RESULT_DIR}/git-status.txt"

{
    echo "git_commit=${GIT_COMMIT}"
    echo "git_tree_state=${GIT_TREE_STATE}"
    echo "tracked_diff_hash=${GIT_DIFF_HASH}"
    echo "mode=${MODE}"
    echo "rli_option=${RLI_OPTION}"
    echo "workload=${WORKLOAD}"
    echo "utc_run_id=${RUN_ID}"
    echo "kernel=$(uname -srmo)"
    echo "demo=${DEMO}"
    echo "demo_sha256=$(sha256sum "${DEMO}" | awk '{print $1}')"
    echo "python=${PYTHON_BIN}"
    echo "invocation=$0 ${MODE} ${WORKLOAD}"
} >"${RESULT_DIR}/metadata.txt"

find "${RESULT_DIR}" -maxdepth 1 -type f ! -name manifest.sha256 \
    -print0 | sort -z | xargs -0 sha256sum >"${RESULT_DIR}/manifest.sha256"

echo "Experiment completed: ${RESULT_DIR}"
