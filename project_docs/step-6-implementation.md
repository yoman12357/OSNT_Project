# Step 6: CUBIC Rate-Limited Increase implementation

## Status

The first implementation is on branch `feature/rate-limited-cubic`. The
changed translation units compile with GCC/MinGW. Full picoquic linkage and
test execution still need to be performed on the project's native Linux
environment before this step can be marked complete.

## What was implemented

- Per-path RLI state: enable flag, `maxFS`, current cwnd limit, and a flag that
  records whether the last increase was capped.
- FlightSize accounting at both picoquic locations that change
  `bytes_in_transit`, so transient peaks and the first post-reduction sample
  are retained.
- Initialization to `PICOQUIC_CWIN_INITIAL` and reset after all reductions
  routed through `cubic_enter_recovery()`.
- Slow-start growth for a rate-limited sender, capped at `2 * maxFS`.
- Congestion-avoidance growth capped at `maxFS + send_mtu`.
- Saturating cap arithmetic.
- Spurious-loss recovery restores CUBIC's window/epoch state but retains only
  post-reduction `maxFS` observations, because draft version 11 requires a
  reset whenever cwnd is reduced for any reason.
- An opt-in A/B switch through `-H rli=on`; normal CUBIC and DCUBIC keep their
  prior behavior otherwise.
- qlog fields `rli_max_flight_size`, `rli_cwnd_limit`, and `rli_capped`.
- A plotter that overlays cwnd, bytes in flight, `maxFS`, and the RLI limit.
- A focused `cubic_rli` regression test covering Slow Start, both CUBIC CA
  growth regions, live packet accounting, repeated bursts, loss, ECN,
  timeout, spurious recovery, epoch exclusion, and opt-out behavior.

## Files changed

| File | Purpose |
|---|---|
| `picoquic/picoquic_internal.h` | Per-path state and accounting helper declaration |
| `picoquic/sender.c` | Update `maxFS` whenever FlightSize changes |
| `picoquic/cubic.c` | Option, reset, cap, recovery, and spurious-loss logic |
| `picoquic/logwriter.c` | Append RLI values to binary congestion log records |
| `loglib/qlog.c` | Convert optional RLI binary fields into qlog |
| `loglib/qlog_fns.c` | Emit RLI fields from direct qlog logging |
| `picoquictest/congestion_test.c` | Focused implementation checks |
| `picoquictest/picoquictest.h` | Test declaration |
| `picoquic_t/picoquic_t.c` | Command-line test registration |
| `UnitTest1/unittest1.cpp` | Visual Studio test registration |
| `plot_cwnd.py` | Baseline/RLI qlog plotting |
| `experiments/run_comparison.sh` | Repeatable baseline/RLI netns runs |
| `experiments/validate_rli.py` | Machine-check recorded RLI cwnd increases |

## Build and focused test on Linux

```bash
cmake -S . -B build -G Ninja \
  -DPICOQUIC_FETCH_PTLS=Y \
  -DWITH_OPENSSL=ON \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel "$(nproc)"

./build/picoquic_ct cubic_rli
ctest --test-dir build --output-on-failure
```

## Experiment command

After the build and tests pass:

```bash
sudo topology/setup.sh
sudo topology/check.sh

sudo env PYTHON_BIN="$PWD/.venv/bin/python" bash experiments/run_comparison.sh baseline rate-limited
sudo env PYTHON_BIN="$PWD/.venv/bin/python" bash experiments/run_comparison.sh rli rate-limited
sudo env PYTHON_BIN="$PWD/.venv/bin/python" bash experiments/run_comparison.sh baseline bulk
sudo env PYTHON_BIN="$PWD/.venv/bin/python" bash experiments/run_comparison.sh rli bulk

sudo topology/cleanup.sh
```

Repeat all four commands at least three times. Step 7 is complete only after
the actual Linux qlogs and plots are saved; no result is claimed from the
Windows source-compilation check.
