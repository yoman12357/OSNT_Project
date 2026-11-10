#!/usr/bin/env bash
set -euo pipefail

# Run on Linux as root, or in a root-mapped user namespace.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
WORK_ROOT=${WORK_ROOT:-/home/aryan/projects}
RLI_ROOT=${RLI_ROOT:-"${WORK_ROOT}/osnt-rli"}
ORIGINAL_ROOT=${ORIGINAL_ROOT:-"${WORK_ROOT}/osnt-original"}
RESULTS_ROOT=${RESULTS_ROOT:-"${REPO_ROOT}/experiments/results/paired-campaign"}
PYTHON_BIN=${PYTHON_BIN:-python3}
REPETITIONS=${REPETITIONS:-3}
TOPOLOGY=dumbbell_access1000mbps_5ms_core20mbps_25ms

if [[ ${EUID} -ne 0 ]]; then
    echo "Run inside Linux as root; see experiments/README.md." >&2
    exit 1
fi
"${PYTHON_BIN}" -c 'import matplotlib' || {
    echo "Use a Python environment with experiments/requirements.txt installed." >&2
    exit 1
}
mkdir -p "${WORK_ROOT}"
for checkout in "${RLI_ROOT}" "${ORIGINAL_ROOT}"; do
    if [[ ! -d ${checkout}/.git ]]; then
        git -c safe.directory="${REPO_ROOT}" -c safe.directory="${REPO_ROOT}/.git" \
            clone --no-hardlinks "${REPO_ROOT}" "${checkout}"
    fi
done
if [[ -n $(git -C "${ORIGINAL_ROOT}" diff --name-only HEAD) ]]; then
    echo "Original checkout has source changes; refusing to overwrite them." >&2
    exit 1
fi
git -C "${ORIGINAL_ROOT}" checkout --detach 5a4eba47

# Copy the caller's tracked source edits as well as the committed source.
# Build outputs remain on the Linux filesystem for reliable permissions/I/O.
git -c safe.directory="${REPO_ROOT}" -C "${REPO_ROOT}" ls-files -z |
    while IFS= read -r -d '' relative; do
        if [[ -f ${REPO_ROOT}/${relative} && ${relative} != results/* ]]; then
            mkdir -p "${RLI_ROOT}/$(dirname -- "${relative}")"
            cp "${REPO_ROOT}/${relative}" "${RLI_ROOT}/${relative}"
        fi
    done
# Normalize shell-script line endings before execution.
"${PYTHON_BIN}" - "${RLI_ROOT}/topology" <<'PY'
from pathlib import Path
import sys
for path in Path(sys.argv[1]).glob('*.sh'):
    path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
PY

for mode in original rli_implemented; do
    source_root=${ORIGINAL_ROOT}
    [[ ${mode} == rli_implemented ]] && source_root=${RLI_ROOT}
    folder="${RESULTS_ROOT}/${mode}/${TOPOLOGY}"
    mkdir -p "${folder}/logs" "${folder}/results" "${folder}/graphs"
    cmake -S "${source_root}" -B "${source_root}/build" -G Ninja \
        -DPICOQUIC_FETCH_PTLS=ON -DWITH_OPENSSL=ON \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo >"${folder}/logs/configure.log" 2>&1
    cmake --build "${source_root}/build" --parallel 4 >"${folder}/logs/build.log" 2>&1
    ctest --test-dir "${source_root}/build" --output-on-failure \
        --output-junit "${folder}/results/regression-tests.xml" \
        >"${folder}/logs/regression-tests.log" 2>&1
    cp "${source_root}/build/Testing/Temporary/LastTest.log" "${folder}/logs/regression-details.log"
done
"${RLI_ROOT}/build/picoquic_ct" -S "${RLI_ROOT}" cubic_rli \
    >"${RESULTS_ROOT}/rli_implemented/${TOPOLOGY}/logs/cubic-rli-test.log" 2>&1
cd "${REPO_ROOT}"
"${PYTHON_BIN}" -m unittest discover -s experiments -p 'test_*.py' -v \
    >"${RESULTS_ROOT}/rli_implemented/${TOPOLOGY}/logs/result-tool-tests.log" 2>&1
cmake -S "${RLI_ROOT}" -B "${RLI_ROOT}/build-sanitize" -G Ninja \
    -DPICOQUIC_FETCH_PTLS=ON -DWITH_OPENSSL=ON \
    -DFETCHCONTENT_SOURCE_DIR_PICOTLS="${RLI_ROOT}/build/_deps/picotls-src" \
    -DENABLE_ASAN=ON -DENABLE_UBSAN=ON -DCMAKE_BUILD_TYPE=Debug \
    >"${RESULTS_ROOT}/rli_implemented/${TOPOLOGY}/logs/sanitizer-configure.log" 2>&1
cmake --build "${RLI_ROOT}/build-sanitize" --target picoquic_ct --parallel 4 \
    >"${RESULTS_ROOT}/rli_implemented/${TOPOLOGY}/logs/sanitizer-build.log" 2>&1
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
    "${RLI_ROOT}/build-sanitize/picoquic_ct" -S "${RLI_ROOT}" cubic_rli \
    >"${RESULTS_ROOT}/rli_implemented/${TOPOLOGY}/logs/sanitizer-cubic-rli-test.log" 2>&1
git -C "${RLI_ROOT}" diff HEAD --binary | gzip -n \
    >"${RESULTS_ROOT}/rli_implemented/${TOPOLOGY}/results/source-changes.patch.gz"
"${PYTHON_BIN}" "${SCRIPT_DIR}/collect_results.py" \
    --original-root "${ORIGINAL_ROOT}" --rli-root "${RLI_ROOT}" \
    --output "${RESULTS_ROOT}" --repetitions "${REPETITIONS}"
"${PYTHON_BIN}" "${SCRIPT_DIR}/report_results.py" --output "${RESULTS_ROOT}"
