# Rate-Limited Increase implementation and verification

This project implements optional RLI for picoquic CUBIC using
`draft-ietf-ccwg-ratelimited-increase-11`. The completed Ubuntu Linux campaign
and its limitations are documented in [results/README.md](results/README.md).

## State and accounting

Each `picoquic_path_t` holds the enable flag, maximum observed FlightSize,
last calculated growth limit, cap flag, and reset counter. CUBIC initializes
maxFS to PICOQUIC_CWIN_INITIAL. The sender updates it after enqueue/dequeue
FlightSize accounting. An actual congestion response starts a new observation
interval by resetting maxFS. Algorithm reinitialization restores the initial
state. A spurious-loss correction retains only post-reduction observations.

## Growth limits

CUBIC first calculates its growth candidate. With `-G cubic -H rli=on`,
Slow Start growth is bounded by `2 * maxFS`; Congestion Avoidance uses
`maxFS + send_mtu`. Arithmetic saturates instead of wrapping. The growth
helper preserves an already permitted window and clips an oversized
Reno-friendly estimate. Real congestion responses retain their reductions.
DCUBIC and RLI-off instances keep the existing behavior.

The additive CA expression is the project's conservative interpretation of
Sections 3 and 4.5. The draft's general algorithm-dependent limit definition
still merits independent review before broader conformance claims.

## Source map

| File | Responsibility |
|---|---|
| picoquic/picoquic_internal.h | Per-path RLI state |
| picoquic/sender.c | Peak-flight accounting |
| picoquic/cubic.c | Options, growth limits, recovery, reset, and cleanup |
| picoquic/logwriter.c | Binary congestion metrics |
| loglib/qlog.c and loglib/qlog_fns.c | Converted and direct qlog metrics |
| picoquictest/congestion_test.c | Focused cubic_rli checks |
| plot_cwnd.py | Qlog parsing and plots |
| experiments/validate_rli.py | Checks of observed trace invariants |
| topology/ | Single-flow and competing-flow Linux namespaces |
| results/ | Final report, editable source, archived runs, and Linux reproduction helpers |

## Retained validation

The baseline revision is 5a4eba475555a2b0d67fbd9000714be35b3db4b4.
The evaluated RLI revision is 60323926df8ef75c440f959789ac4d043071879d.
The recorded Linux environment is Ubuntu 26.04 LTS with kernel 7.0.0-38-generic.
Both revisions were built separately and passed their registered CTest suites.
The retained campaign contains twelve main runs and six two-flow experiments.
The source revisions, binary hashes, commands, and test exit codes are retained.

These results belong to the recorded revisions. The current local source edits
must be built and tested separately before attributing fresh runtime results
to them. Preserve the saved evidence when collecting another campaign.

## Repeat the work

Follow [experiments/README.md](experiments/README.md) to install Linux tools,
restore raw evidence, inspect checksums, and reproduce the report. Use a fresh
output location for a new campaign. Keep three repetitions for each workload
and mode, and retain every individual plot and provenance record.

Compare throughput, RTT, retransmissions, FlightSize, maxFS, and the cap.
An application-limited flow does not gain data supply when its window grows.
Snapshot checks cannot recover every individual send/dequeue operation.
Controlled loss, receiver limits, multipath, additional workloads, and longer
campaigns remain useful extensions.
