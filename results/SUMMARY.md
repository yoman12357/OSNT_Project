# Fresh experiment summary

All numbers below come from this folder's new runs, not the older Step 7 evidence.

| Workload | Mean baseline throughput | Mean RLI throughput | Change | Mean cwnd change |
|---|---:|---:|---:|---:|
| rate-limited | 0.190179 Mbit/s | 0.190186 Mbit/s | +0.003% | +98.708% |
| bulk | 17.731656 Mbit/s | 17.949780 Mbit/s | +1.230% | +9.865% |

RLI passed all six trace validations; the rate-limited runs require an observed active cap, and the bulk runs require a visible cwnd reduction with maxFS reset.

A larger permitted cwnd is a behavioral improvement for this workload, not proof of faster data delivery. Three local repeats do not establish statistical significance or general network performance.

Exact per-run values are in measurements.csv; raw traces and performance logs are under runs/. Both source revisions passed all registered CTest suites.
