# Fresh experiment summary

Access links: 1000 Mbit/s and 5 ms per direction. Core: 20 Mbit/s and 25 ms per direction. Nominal base RTT: 70 ms.

All numbers below come from this folder's new runs. The previous campaign is backed up under archive/.

| Workload | Mean baseline throughput | Mean RLI throughput | Change | Mean cwnd change |
|---|---:|---:|---:|---:|
| rate-limited | 0.189391 Mbit/s | 0.189369 Mbit/s | -0.012% | +98.896% |
| bulk | 17.096857 Mbit/s | 17.602599 Mbit/s | +2.958% | -43.144% |

RLI passed all six trace validations; the rate-limited runs require an observed active cap, and the bulk runs require a visible cwnd reduction with maxFS reset.

A larger permitted cwnd is a behavioral improvement for this workload, not proof of faster data delivery. Three local repeats do not establish statistical significance or general network performance.

Exact per-run values are in measurements.csv; raw traces and performance logs are under runs/. Both source revisions passed all registered CTest suites.
