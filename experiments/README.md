# Linux build, test, and experiment workflow

The retained final campaign is in [../results/README.md](../results/README.md).
Its environment record identifies Ubuntu 26.04 LTS and Linux kernel
7.0.0-38-generic. It includes twelve single-flow runs, six two-flow experiments,
the final report, and the complete compressed raw evidence.

## Linux dependencies

From the repository root on Ubuntu:

```bash
sudo apt update
sudo apt install build-essential cmake ninja-build git libssl-dev \
  python3-venv iproute2 iputils-ping texlive-latex-extra \
  texlive-fonts-recommended poppler-utils
python3 -m venv .venv
.venv/bin/python -m pip install -r experiments/requirements.txt pypdf
```

## Verify the retained bundle

```bash
.venv/bin/python results/check_bundle.py
.venv/bin/python results/package_evidence.py --unpack
cd results
sha256sum --check --quiet SHA256SUMS
cd ..
```

The archive restores `results/runs/`, `results/dumbbell/baseline/`, and
`results/dumbbell/rli/`. Saved metadata and source hashes are historical
records of the evaluated revisions. `check_bundle.py` inspects the current
bundle without building or rerunning network transfers.

## Rebuild the final report

```bash
.venv/bin/python results/build_final_report.py
xdg-open 'results/Final report.pdf'
```

The editable source is `results/report-source/main.tex`, with its sections,
diagrams, and images beside it. The older `report.tex` and `report1.tex`
editions remain available separately. Their original check records describe
those editions; `final-report-checks.json` describes the current final PDF.

## Reproduce the recorded campaign

The baseline revision is `5a4eba475555a2b0d67fbd9000714be35b3db4b4`.
The evaluated RLI revision is `60323926df8ef75c440f959789ac4d043071879d`.
Use separate Linux checkouts/builds of those revisions to reproduce their
behavior. Tests of a newer local revision are a new campaign.

Configure the RLI checkout before invoking the retained test helper:

```bash
cmake -S . -B build -G Ninja -DPICOQUIC_FETCH_PTLS=Y \
  -DWITH_OPENSSL=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel 4
.venv/bin/python results/run_tests.py
```

`run_tests.py` builds the exact baseline separately and tests both versions.
It uses system OpenSSL development packages; optional locally unpacked headers
are supported when present. Preserve the supplied evidence before running any
script that regenerates tests, measurements, or plots.

Run main network experiments in an isolated root-mapped Linux user namespace:

```bash
unshare --user --map-root-user --net --mount \
  bash results/run_experiments.sh
.venv/bin/python results/analyze_results.py
```

The main helper uses `results/run_single_comparison.sh`, the interface retained
for this campaign. It supplies a 20-second stream at 192 kbit/s or downloads
20 MiB, using three repetitions per mode over the 20 Mbit/s, 50 ms path.
Existing main runs are moved to `results/archive/` before another collection.

For the six-namespace competing-flow topology:

```bash
unshare --user --map-root-user --net --mount sh -c \
  'mount --make-rprivate /; mount -t tmpfs tmpfs /run; mkdir -p /run/netns; exec .venv/bin/python results/run_dumbbell.py'
.venv/bin/python results/analyze_dumbbell.py
```

Preserve or relocate existing `results/dumbbell/baseline` and
`results/dumbbell/rli` first. The script refuses to overwrite those runs.
The topology helpers include both endpoint pairs and clean up all six namespaces.
Unprivileged user namespaces must be enabled for the `unshare` workflow.

## Current working-tree campaign

`experiments/run_all.sh` is a separate paired collector for the current local
source. It builds both checkouts, runs regression and focused tests, and
collects the same main workloads. Run it as root on Linux, or inside a suitable
root-mapped user namespace. Its default output is
`experiments/results/paired-campaign/`, preserving the final submission bundle.
`WORK_ROOT`, `ORIGINAL_ROOT`, `RLI_ROOT`, `RESULTS_ROOT`, `PYTHON_BIN`, and
`REPETITIONS` can be set explicitly. Use fresh output for different builds.

## Individual trace checks

```bash
python3 experiments/validate_rli.py check <sender.qlog.gz> --require-cap
python3 experiments/validate_rli.py check <bulk-sender.qlog.gz> --expect-reduction
python3 plot_cwnd.py <sender.qlog.gz> output.png
python3 -m unittest discover -s experiments -p 'test_*.py' -v
```

The checker evaluates observed growth, cap, and reset information. Snapshot
data cannot reconstruct every send/dequeue. Compare cwnd with throughput,
RTT, retransmissions, and application supply. Three repetitions describe the
tested conditions; they do not establish a universal speedup.
