#!/usr/bin/env bash
set -euo pipefail
export MPLBACKEND=Agg
# Run inside unshare --user --map-root-user --net --mount.
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
OUT="${REPO}/results 1"
cd "${REPO}"
test -f "${OUT}/environment.json"
test -x "${REPO}/.local-deps/report-baseline/build/picoquicdemo"
test -x "${REPO}/build/picoquicdemo"
if [[ -d "${OUT}/runs" ]]; then
    mkdir -p "${OUT}/archive"
    archive_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    mv -- "${OUT}/runs" "${OUT}/archive/runs-${archive_id}"
fi
mount --make-rprivate /
mount -t tmpfs tmpfs /run
mkdir -p /run/netns
trap 'bash topology/cleanup.sh' EXIT
bash topology/setup.sh | tee "${OUT}/topology-setup.log"
bash topology/check.sh | tee "${OUT}/topology-check.log"
ip netns list >"${OUT}/topology-namespaces.log"
for workload in rate-limited bulk; do
    for repetition in 1 2 3; do
        # Alternate ordering across repetitions to reduce order bias.
        if [[ ${repetition} == 2 ]]; then modes=(rli baseline); else modes=(baseline rli); fi
        for mode in "${modes[@]}"; do
            echo "START ${workload} ${mode} repetition ${repetition}"
            build="${REPO}/build"
            if [[ ${mode} == baseline ]]; then build="${REPO}/.local-deps/report-baseline/build"; fi
            destination="${OUT}/runs/${workload}/${mode}/run-${repetition}"
            mkdir -p "${destination}"
            env PYTHON_BIN="${REPO}/.venv/bin/python" BUILD_DIR="${build}" \
                bash experiments/run_comparison.sh "${mode}" "${workload}" \
                | tee "${destination}/runner.log"
            result=$(sed -n 's/^Experiment completed: //p' "${destination}/runner.log" | tail -1)
            test -n "${result}"
            cp -a "${result}/." "${destination}/"
            # The inherited runner's git_commit reports the orchestrator's HEAD.
            # Record the actual source revision of each tested binary separately.
            if [[ ${mode} == baseline ]]; then source_commit=5a4eba475555a2b0d67fbd9000714be35b3db4b4;
            else source_commit=$(git rev-parse HEAD); fi
            printf 'tested_source_commit=%s\noriginal_result_directory=%s\n' \
                "${source_commit}" "${result}" >"${destination}/provenance.txt"
            echo "END ${workload} ${mode} repetition ${repetition}"
        done
    done
done
echo 'PASS: 12 fresh experiments finished'
