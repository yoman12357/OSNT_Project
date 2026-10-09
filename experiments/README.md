# CUBIC experiment workflow

The comparison runner uses the four-namespace topology from `topology/` and
stores every run in a unique directory under `experiments/results/`.

Build picoquic, start the topology, and verify it:

```bash
cmake -S . -B build -G Ninja -DPICOQUIC_FETCH_PTLS=Y \
  -DWITH_OPENSSL=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel "$(nproc)"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r experiments/requirements.txt
sudo topology/setup.sh
sudo topology/check.sh
```

Run matched baseline and RLI experiments:

```bash
sudo env PYTHON_BIN="$PWD/.venv/bin/python" \
  bash experiments/run_comparison.sh baseline rate-limited
sudo env PYTHON_BIN="$PWD/.venv/bin/python" \
  bash experiments/run_comparison.sh rli rate-limited

# Regression/control workload: continuously backlogged sender
sudo env PYTHON_BIN="$PWD/.venv/bin/python" \
  bash experiments/run_comparison.sh baseline bulk
sudo env PYTHON_BIN="$PWD/.venv/bin/python" \
  bash experiments/run_comparison.sh rli bulk
```

The rate-limited workload is a 20-second quicperf media stream at about
192 kbit/s over a 20 Mbit/s bottleneck. This makes the server application
limited without changing the network capacity. The bulk workload checks that
RLI does not materially alter fully utilized CUBIC.

Each run contains raw qlogs, stdout, performance CSV files, metadata, Git
working-tree status, file hashes, and a PNG showing `cwnd`, bytes in flight,
and (when enabled) `maxFS`, the RLI limit, and cap-active samples. RLI runs
also contain `validation.txt`. Raw results are ignored by Git but are not
deleted by the runner.

Check an RLI sender log mechanically:

```bash
python3 experiments/validate_rli.py \
  check experiments/results/rli/rate-limited/<run-id>/*.server.qlog \
  --require-cap
```

Do not require a reset for the loss-free workloads above. For a separate
experiment that deliberately causes a cwnd reduction, add
`--expect-reduction`; that mode requires both an observed cwnd reduction and
an associated fall in `maxFS`.

Compare matched baseline and RLI measurements without assuming either is
automatically better:

```bash
python3 experiments/validate_rli.py compare \
  experiments/results/baseline/rate-limited/<run-id>/*.server.qlog \
  experiments/results/rli/rate-limited/<run-id>/*.server.qlog \
  --workload rate-limited --output rate-limited-comparison.csv

python3 experiments/validate_rli.py compare \
  experiments/results/baseline/bulk/<run-id>/*.server.qlog \
  experiments/results/rli/bulk/<run-id>/*.server.qlog \
  --workload bulk --output bulk-comparison.csv
```

The comparison reports duration, minimum/maximum/final/time-weighted cwnd,
FlightSize, application-limited fraction, and RLI cap fraction. Interpret the
performance CSV alongside these congestion-control measurements.

Run each mode/workload combination at least three times. When finished:

```bash
sudo topology/cleanup.sh
```
