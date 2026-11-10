# Same-connection congestion-avoidance experiment

Each connection contains a 20 MiB bulk warm-up, a limited stream, and a 5 MiB burst.
The limited stream sends 400 frames of 1200 bytes at 20 frames per second.
The nominal offered rate is 192 kbit/s.
All phases use one connection and the same CUBIC controller state.

Access links: 1000 Mbit/s and 5 ms per direction. Core: 20 Mbit/s and 25 ms per direction.
Nominal base RTT: 70 ms. The analysis excludes 0.5 seconds at both ends of the limited phase.

## Checks and cap coverage

- Measurement and invariant checks: PASS.
- Cap exercised in every RLI limited interval: no.
- Overall coverage verdict: INCOMPLETE: no active cap in some CA-limited intervals.

The checker uses qlog congestion_state_updated events to verify CA state 2 before the limited phase.
It verifies that state 2 persists throughout the measured limited interior.
Stream IDs 0, 4, and 8 identify warm-up, limited traffic, and the burst.
Client-side byte-range accounting confirms complete delivery and the dependency order.
Duplicate or out-of-order frames cannot falsely complete a stream.

## Per-run measurements

| Mode | Run | CA at limited start | Limited cwnd change (bytes) | Active CA-cap samples | Burst completion (s) | Whole-connection retransmissions |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 2 | 0 | 0 | 2.281505 | 0 |
| rli | 1 | 2 | 0 | 0 | 2.281891 | 0 |
| rli | 2 | 2 | 0 | 0 | 2.281471 | 0 |
| baseline | 2 | 2 | 0 | 0 | 2.282106 | 0 |
| baseline | 3 | 2 | 0 | 0 | 2.281836 | 0 |
| rli | 3 | 2 | 0 | 0 | 2.282253 | 0 |

## Interpretation

The CA formula check validates the implemented conservative ceiling, maxFS plus the sender MTU.
It does not independently establish that this adaptation is the exact CUBIC limit required by the IETF draft.
A passing bound check without an active cap does not prove the cap constrained growth.
CUBIC may hold cwnd constant if its normal growth candidate does not exceed the existing window.
Different window heights can be inherited from warm-up; they do not demonstrate new growth during congestion avoidance.
A non-binding cap is a coverage limitation, not automatically an implementation failure.
An existing window above a newly lower ceiling is not forcibly reduced by this growth limiter.

Mean burst completion: baseline 2.281816 seconds; RLI 2.281872 seconds.
Observed time change: +0.002%. Negative means faster completion.
Three repetitions do not establish statistical significance or a general performance gain.

Burst completion uses the client's first request-packet timestamp and the timestamp of complete payload reception with FIN.
Both timestamps use the same clock. This interval includes request latency and delivery, not just server sending time.
The current final report and earlier 18-experiment campaign remain unchanged.

## Files

- plots/: full traces, limited-window zooms, paired comparisons, and the three-run overview where available.
- measurements.csv: numeric per-run measurements.
- summary.json: measurements, phase boundaries, state transitions, and validation errors.
- collection.json: commands, source revisions, binary hashes, topology, and run order.
- baseline/ and rli/: local compressed qlogs and per-run evidence; these raw directories are ignored by Git.
- The parent folder's raw-evidence.tar.gz preserves the compressed traces for distribution.
