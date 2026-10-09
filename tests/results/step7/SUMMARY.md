# Step 7: rate-limited CUBIC experiment

- Date: 2026-10-10 (Asia/Kolkata)
- Branch: `test/rli-implementation`
- Commit: `d436b16098bb749b7af2cedc696b743182314d33`
- Topology: four Linux network namespaces in a dumbbell layout
- Bottleneck: 20 Mbit/s with approximately 50 ms steady-state RTT
- Workloads: 20-second application-limited stream and 20 MB bulk transfer
- Repetitions: three matched baseline/RLI runs for each workload

## Results

| Run | Baseline max/final cwnd | RLI max/final cwnd | RLI average cwnd | RLI cap samples | Validation |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 15,360 bytes | 30,720 bytes | 30,520.1 bytes | 819 | Passed |
| 2 | 15,360 bytes | 30,720 bytes | 30,521.7 bytes | 819 | Passed |
| 3 | 15,360 bytes | 30,720 bytes | 30,520.4 bytes | 819 | Passed |

All baseline runs remained at the initial 15 KiB congestion window. All RLI
runs increased to the slow-start ceiling of 30 KiB (`2 * maxFS`) and stayed
within that limit. The RLI time-weighted average cwnd was about 98.7% higher
than baseline in every run.

Both modes sent the application-requested traffic at approximately 0.190
Mbit/s with zero retransmissions. Equal throughput is expected here because
the workload intentionally supplies data far below the 20 Mbit/s bottleneck;
the experiment measures permitted cwnd growth, not bulk-transfer speed.

## Bulk control results

| Run | Baseline throughput | RLI throughput | Baseline duration | RLI duration | Retransmissions | Validation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 17.650 Mbit/s | 17.810 Mbit/s | 9.506 s | 9.420 s | 0 / 0 | Passed |
| 2 | 17.773 Mbit/s | 17.805 Mbit/s | 9.440 s | 9.423 s | 0 / 0 | Passed |
| 3 | 17.840 Mbit/s | 17.831 Mbit/s | 9.404 s | 9.409 s | 0 / 0 | Passed |

The bulk results show no material throughput regression. The RLI cap was
active for only one or two qlog samples per run, as expected when the sender
normally keeps the congestion window utilized. Each RLI trace also recorded
congestion-window reductions and a corresponding `maxFS` reset.

Rate-limited plots, comparisons, and validation reports are in `plots/`,
`comparisons/`, and `validation/`. Bulk equivalents are in `bulk-plots/`,
`bulk-comparisons/`, and `bulk-validation/`. Raw qlogs and performance CSVs
remain under `experiments/results/` in the local workspace.
