# Rate-Limited Sender Implementation Plan

## Goal

Complete project Steps 4-8 by measuring picoquic's current CUBIC behavior,
implementing Rate-Limited Increase (RLI), repeating the same experiment, and
validating the result against the IETF draft.

This plan targets `draft-ietf-ccwg-ratelimited-increase-11`. Before merging the
implementation, recheck the datatracker in case the draft has changed.

## Current status

- Steps 1-5 are complete: setup, congestion-control study, netns topology,
  baseline experiment/plot, and the RLI design.
- Step 6 has an opt-in first implementation and focused test. The modified C
  sources compile, but the full suite must still pass on native Linux.
- Steps 7-8 have not been run. The repeatable comparison runner and RLI-aware
  plotter are ready for those Linux experiments.

## Required behavior from the draft

For each congestion-control instance/path:

1. Initialize `maxFS` to `initcwnd` when congestion control starts.
2. Whenever FlightSize changes, update:

   ```text
   maxFS = max(maxFS, FlightSize)
   ```

3. Reset `maxFS` to zero whenever `cwnd` is reduced for any reason.
4. Whenever `cwnd` increases, cap it at `limit(maxFS)`.
5. Use saturating/checked arithmetic so calculating the limit cannot overflow.

`limit(maxFS)` means the maximum permitted cwnd after processing the ACKs for
one successfully transmitted flight of size `maxFS`. Draft version 11 gives
the phase limits used here: `2 * maxFS` in Slow Start and `maxFS + SMSS` in
Congestion Avoidance. CUBIC still calculates its own candidate window before
that phase-specific limit is applied.

## Proposed repository layout

Create the following files while completing the work:

```text
experiments/
  README.md
  requirements.txt
  run_baseline.sh
  run_rli.sh
  convert_logs.sh
  plot_cwnd.py
  validate_results.py
  scenarios/
    bulk.conf
    rate_limited.conf
  results/
    baseline/          # CSV summaries and plots
    rli/               # CSV summaries and plots
project_docs/
  step-4-baseline-experiment.md
  step-5-rli-design.md
  step-6-implementation.md
  step-7-rli-experiment.md
  step-8-validation.md
```

Do not commit large raw binary logs. Keep compact CSV results, plots, scenario
configuration, commands, software versions, and enough metadata to reproduce
each run.

## Phase 0: Prepare a clean development branch

Run on native Linux from the repository root:

```bash
git switch -c feature/rate-limited-cubic

cmake -S . -B build -G Ninja \
  -DPICOQUIC_FETCH_PTLS=Y \
  -DWITH_OPENSSL=ON \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel "$(nproc)"
ctest --test-dir build --output-on-failure
```

Record the Git commit, kernel version, compiler version, CMake version, and
test result. Do not begin source changes unless the original suite passes.

## Phase 1: Complete Step 4 -- baseline CUBIC experiment

### 1. Freeze two workloads

Use exactly the same workloads before and after implementation:

- **Bulk control:** enough continuously available data to keep CUBIC
  cwnd-limited. This checks that ordinary CUBIC behavior is not accidentally
  changed.
- **Rate-limited workload:** repeated, fixed-size application bursts separated
  by fixed idle intervals, or a fixed-rate quicperf media stream below the
  bottleneck capacity. This is the main comparison workload.

Store all workload parameters in `experiments/scenarios/`. Record transfer
size, burst size, pause/rate, duration, repetitions, MTU, bottleneck rate,
delay, queue size, and selected congestion algorithm.

### 2. Start the topology

```bash
cd topology
sudo ./setup.sh
sudo ./check.sh
cd ..
```

The expected path is:

```text
rls-client -> rls-r1 == 20 Mbit/s, ~50 ms RTT == rls-r2 -> rls-server
```

### 3. Run picoquic through the namespaces

Use `picoquicdemo -h` and `doc/quicperf.md` to freeze the exact command in
`run_baseline.sh`. A starting command structure is:

```bash
# Terminal 1: server
sudo ip netns exec rls-server \
  ./build/picoquicdemo -1 -p 4443 \
  -c certs/cert.pem -k certs/key.pem \
  -G cubic -b experiments/results/baseline/server-bin

# Terminal 2: client
sudo ip netns exec rls-client \
  ./build/picoquicdemo -D -G cubic \
  -t certs/test-ca.crt -n test.example.com \
  -b experiments/results/baseline/client-bin \
  10.10.2.2 4443 '<frozen quicperf scenario>'
```

Use absolute repository paths in the final scripts so that execution does not
depend on the caller's directory. Check the actual CLI with `-h`; the command
above is a template, not the final experiment contract.

### 4. Convert and plot logs

Binary congestion logs can be converted using `picolog`:

```bash
./build/picolog -f csv -o experiments/results/baseline/csv <binlog-file>
```

`plot_cwnd.py` should produce at least:

- cwnd versus elapsed time;
- bytes in transit versus elapsed time;
- cwnd and bytes in transit on the same time axis; and
- markers or shaded regions for rate-limited periods.

Run each workload at least three times. Keep individual plots plus an aligned
summary plot; do not silently average away different loss events.

### Step 4 completion criteria

- One command reproducibly creates the topology and runs each workload.
- Baseline CSV logs and cwnd plots exist.
- The exact commands and environment are documented.
- The topology is cleaned with `sudo topology/cleanup.sh` even after failure.

## Phase 2: Complete Step 5 -- finalize the design

Write `project_docs/step-5-rli-design.md` before editing C code. Review these
decisions:

### State placement

Preferred design: maintain `max_flight_size` per `picoquic_path_t`, because
`bytes_in_transit` and congestion control are already per path and the send
path observes the real peak FlightSize.

Candidate files:

- `picoquic/picoquic_internal.h`: add per-path RLI state.
- `picoquic/sender.c`: update maxFS immediately after increasing
  `bytes_in_transit` in `picoquic_queue_for_retransmit()`.
- `picoquic/cubic.c`: initialize, reset, calculate the CUBIC limit, and cap
  growth.

Keep maxFS update/reset operations behind small helpers instead of scattering
raw assignments. Document whether generic state belongs on the path or in the
CUBIC-private state and why.

### CUBIC limit definition -- mandatory design gate

Derive `limit(maxFS)` for picoquic CUBIC from the draft's generic definition
and RFC 9438's per-ACK behavior. Specify how these values are handled without
mutating live state merely to calculate a limit:

- CUBIC epoch time and `K`;
- `W_max` and `W_last_max`;
- Reno-friendly `W_reno`;
- ACKed-byte accounting and SMSS/send MTU; and
- transition from slow start to congestion avoidance inside the hypothetical
  one-flight increase.

Review this derivation with the project mentor or draft authors before coding.
Add numeric examples to the design document. In slow start, verify the draft's
example where an initial 10-packet flight grows cwnd to 20 packets and a later
4-packet flight cannot grow it beyond 20.

### A/B switch

Use CUBIC's existing congestion-control option string (`picoquicdemo -H`) to
support an explicit experimental option such as `rli=on` and `rli=off`.
Initially preserve the old behavior when off. Decide during review whether RLI
should become the default after validation.

### Step 5 completion criteria

- Every draft MUST is mapped to a function and state field.
- Every cwnd-reduction path in `cubic.c` is listed.
- The CUBIC limit derivation has numeric tests and mentor review.
- Logging, option behavior, overflow handling, and multipath behavior are
  specified.

## Phase 3: Complete Step 6 -- implement RLI for CUBIC

Implement in small reviewable commits.

### Commit A: state and accounting

- Add per-path maxFS state and helpers.
- Initialize it to `PICOQUIC_CWIN_INITIAL` when CUBIC starts/resets.
- Update it after `path_x->bytes_in_transit += length` in `sender.c`.
- Keep state independent for every path.

### Commit B: reset and cap

- Reset maxFS after every actual cwnd reduction: loss, ECN, timeout, persistent
  congestion, reset/restart, and any CUBIC-specific reduction branch.
- Replace the current all-or-nothing sender-limited growth gate in slow start
  and congestion avoidance with candidate growth followed by the reviewed
  `limit(maxFS)` cap when RLI is enabled.
- Keep `W_reno`, epoch time, and other internal CUBIC state consistent with the
  capped cwnd so there is no jump after an idle/rate-limited interval.
- Preserve current behavior with `rli=off`.

### Commit C: observability

- Log maxFS and whether the cap was applied.
- Prefer an explicit logging field. If the binary log format changes, update
  `loglib/csv.c`, `loglib/memory_log.c`, converters, and affected reference
  tests together.
- Include maxFS and the calculated limit in experiment CSV output.

### Commit D: tests

Add focused tests to `picoquictest/app_limited.c` or create
`picoquictest/ratelimited_test.c` and register it in `CMakeLists.txt` and the
test runner.

Required cases:

1. maxFS initializes to initcwnd.
2. maxFS captures the peak flight, including a peak between ACKs.
3. Slow-start growth obeys its cap.
4. Congestion-avoidance growth obeys the reviewed CUBIC limit.
5. maxFS resets after loss, ECN, timeout, and other cwnd reductions.
6. A fully utilized sender behaves like ordinary CUBIC.
7. Repeated small bursts never cause unbounded cwnd growth.
8. Multiple paths keep independent maxFS values.
9. Limit arithmetic is overflow-safe.
10. `rli=off` preserves the previous behavior.

Run after every commit:

```bash
cmake --build build --parallel "$(nproc)"
ctest --test-dir build --output-on-failure
```

Also run the focused test directly while developing, then the full suite before
committing.

### Step 6 completion criteria

- All focused and existing tests pass.
- No sanitizer or Valgrind errors occur in the new tests.
- Code comments connect non-obvious behavior to the draft requirements.
- The implementation works independently per path.

## Phase 4: Complete Step 7 -- repeat the experiment

Use the same topology, workloads, durations, log settings, and number of runs
from Step 4. Change only the RLI option:

```text
Baseline: -G cubic -H rli=off
RLI:      -G cubic -H rli=on
```

`run_rli.sh` should write to a separate `results/rli/` directory and refuse to
overwrite baseline data. Generate the same plot set, adding maxFS and
`limit(maxFS)` to the RLI graph.

### Step 7 completion criteria

- At least three successful RLI runs exist for each workload.
- Plots use the same units, axes, workload, and topology as the baseline.
- Raw-data provenance records the exact Git commit and command.

## Phase 5: Complete Step 8 -- validate the result

`validate_results.py` should check machine-readable invariants rather than only
relying on visual inspection:

- Every RLI cwnd increase respects the recorded `limit(maxFS)`.
- maxFS never decreases except when a cwnd reduction resets it.
- The first post-reduction FlightSize correctly rebuilds maxFS from zero.
- Rate-limited periods may show controlled growth but never unbounded growth.
- Fully utilized bulk CUBIC remains functionally equivalent within normal run
  variation.
- No unexpected regression occurs in transfer completion, loss, RTT, or
  throughput.

The final comparison should show:

1. Baseline CUBIC's conservative behavior during rate-limited periods.
2. RLI CUBIC's permitted but capped growth.
3. maxFS and the limit explaining every capped section of the graph.
4. Correct reset and recovery after a congestion event.

Write the results, plots, anomalies, and limitations in
`project_docs/step-8-validation.md`.

### Step 8 completion criteria

- Automated validation passes for every retained RLI run.
- Baseline and RLI plots are directly comparable.
- All eight project steps have reproducible documentation.
- The full picoquic test suite passes at the final commit.

## Recommended execution order

```text
Baseline experiment
        -> CUBIC-specific design review
        -> maxFS accounting
        -> cap/reset implementation
        -> focused tests
        -> full regression suite
        -> identical RLI experiment
        -> automated and visual validation
        -> final report
```

Do not implement first and invent the baseline afterward. Freeze the workload
and collect Step 4 data before changing CUBIC so the final comparison remains
credible.
