# Rate-limited sender project progress

The final retained campaign was executed on Ubuntu 26.04 LTS, Linux kernel
7.0.0-38-generic. See [results/README.md](results/README.md) for the report,
measurements, test logs, environment record, and reproducible commands.

| Step | Recorded completion evidence |
|---|---|
| 1. Installation and build | Separate baseline and RLI builds; results/tests/status.json |
| 2. Congestion-control study | IMPLEMENTATION_PLAN.md; report-source/sections/04-implementation.tex |
| 3. Linux topology | Four-namespace single-flow path and six-namespace two-flow dumbbell; topology checks retained |
| 4. Original baseline | Pre-RLI revision 5a4eba47; three runs for each main workload |
| 5. RLI design | Per-path maximum-flight tracking; Slow Start and additive CA limits |
| 6. Implementation and testing | Both registered CTest suites and the focused cubic_rli test passed in the retained campaign |
| 7. RLI experiments | Six main RLI runs and three two-flow RLI experiments |
| 8. Validation and comparison | 18 experiments, 24 completed connections; main and supplementary RLI checks passed |

## Final evidence layout

```text
results/
  Final report.pdf
  README.md
  report-source/           # Editable source and assets for the final PDF
  environment.json        # Recorded Linux environment and source/binary identities
  measurements.csv
  summary.json
  plots/                  # 12 main plots, overview, and 6 two-flow plots
  tests/                  # Build and regression evidence
  comparisons/
  validation/
  dumbbell/               # Two-flow measurements and checks
  raw-evidence.tar.gz     # 240 raw files, including 48 qlogs
  SHA256SUMS
```

The raw archive restores the main runs and the two-flow run directories.
The consolidated bundle supersedes the earlier results layout. Historical
verification JSON and source identifiers describe the runs when collected.
The existing local runtime edits are separate from the evaluated revision
60323926; this repository cleanup does not establish a new C regression run.

## Interpretation and limits

RLI increased the limited-sender window from 15 KiB to 30 KiB. Its fixed
application supply kept throughput essentially unchanged. The reported bulk
and competing-flow measurements describe three repetitions of the tested
conditions. They do not establish a universal speedup or full IETF conformance.
The implementation uses the conservative maxFS + send_mtu CA ceiling.

Reproduction instructions are in [experiments/README.md](experiments/README.md).
