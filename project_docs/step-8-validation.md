# Step 8: validation of rate-limited CUBIC

This document preserves the October experiment assessment. The final
7 November 2026 report, repeated source-revision comparison, full dumbbell
tests, and qualification of the CUBIC congestion-avoidance interpretation are
in `results 1/`; see `SUBMISSION.md` for the submission index. Small numerical
differences between experiment dates are measured run variation.

## Conclusion

The rate-limited sender implementation behaves as expected for the tested
conditions. The rate-limited cwnd graphs follow the rules in
[`draft-ietf-ccwg-ratelimited-increase-11`](https://datatracker.ietf.org/doc/html/draft-ietf-ccwg-ratelimited-increase-11),
and the bulk control experiments show no material throughput regression.

## Test environment

- Branch: `test/rli-implementation`
- Implementation commit: `d436b16098bb749b7af2cedc696b743182314d33`
- Date: 2026-10-10 (Asia/Kolkata)
- Topology: four Linux network namespaces in a dumbbell layout
- Bottleneck: 20 Mbit/s, approximately 50 ms steady-state RTT
- Rate-limited workload: approximately 192 kbit/s for 20 seconds
- Bulk workload: 20 MB continuous transfer
- Repetitions: three matched baseline/RLI runs per workload

## Draft requirement validation

| Draft requirement | Implementation/evidence | Result |
| --- | --- | --- |
| Initialize `maxFS` to `initcwnd` | Focused `cubic_rli` unit test checks initialization at 15,360 bytes | Passed |
| Update `maxFS = max(maxFS, FlightSize)` | Send/dequeue accounting plus qlog validation ensures `maxFS` never falls below observed FlightSize | Passed |
| Reset `maxFS` after any cwnd reduction | Focused loss/ECN/timeout tests pass; every bulk trace observed post-reduction reset behavior | Passed |
| Cap every cwnd increase at `limit(maxFS)` | All six qlog traces were checked sample-by-sample; no increase exceeded its recorded limit | Passed |
| Slow Start limit is `2 * maxFS` | All rate-limited runs stopped at 30,720 bytes for `maxFS = 15,360` bytes | Passed |
| Congestion Avoidance limit is `maxFS + SMSS` | Focused test passes and bulk qlogs contain no limit violation | Passed |

## Rate-limited graph validation

| Run | Baseline max/final cwnd | RLI max/final cwnd | RLI average cwnd | Validator |
| --- | ---: | ---: | ---: | --- |
| 1 | 15,360 bytes | 30,720 bytes | 30,520.1 bytes | Passed |
| 2 | 15,360 bytes | 30,720 bytes | 30,521.7 bytes | Passed |
| 3 | 15,360 bytes | 30,720 bytes | 30,520.4 bytes | Passed |

The original behavior kept cwnd fixed at its initial 15 KiB because the
application did not fill the window. With RLI enabled, cwnd increased to
30 KiB and then remained at the required `2 * maxFS` Slow Start limit. The
time-weighted average cwnd increased by approximately 98.7% without unlimited
growth. This is the expected improvement in congestion-window behavior.

Both modes delivered approximately 0.190 Mbit/s because the application
intentionally supplied data far below the network capacity. RLI is not
expected to increase throughput when no additional application data exists.

## Fully utilized sender control

| Run | Baseline throughput | RLI throughput | Baseline duration | RLI duration | Retransmissions |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 17.650 Mbit/s | 17.810 Mbit/s | 9.506 s | 9.420 s | 0 / 0 |
| 2 | 17.773 Mbit/s | 17.805 Mbit/s | 9.440 s | 9.423 s | 0 / 0 |
| 3 | 17.840 Mbit/s | 17.831 Mbit/s | 9.404 s | 9.409 s | 0 / 0 |

Mean throughput was 17.754 Mbit/s for baseline and 17.816 Mbit/s with RLI, a
0.35% difference. This is too small to treat as a meaningful performance
change in three local runs. There were zero retransmissions in both modes.
The RLI cap was active for only about 0.10% to 0.12% of each bulk trace,
confirming that it rarely intervened when the sender was continuously
backlogged.

## Final assessment

Step 8 passes for the tested topology and workloads:

1. RLI permits bounded cwnd growth when the application is rate-limited.
2. The observed ceiling exactly matches the draft's Slow Start rule.
3. No observed cwnd increase exceeded its applicable RLI limit.
4. Congestion responses rebuild `maxFS` after a reset.
5. Normal bulk behavior has no material throughput or loss regression.

The conclusion is limited to the tested 20 Mbit/s, approximately 50 ms RTT
topology, three repetitions per workload, and this picoquic revision. It does
not claim a universal throughput improvement across all networks.

## Evidence

- Summary: `tests/results/step7/SUMMARY.md`
- Rate-limited graphs: `tests/results/step7/plots/`
- Rate-limited comparisons: `tests/results/step7/comparisons/`
- Rate-limited validation: `tests/results/step7/validation/`
- Bulk graphs: `tests/results/step7/bulk-plots/`
- Bulk comparisons: `tests/results/step7/bulk-comparisons/`
- Bulk validation: `tests/results/step7/bulk-validation/`
- Raw local qlogs and performance logs: `experiments/results/`
