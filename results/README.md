# Rate-limited CUBIC: current results

Project #16. Fresh Linux campaign: 10 November 2026.

Open [Final report.pdf](Final%20report.pdf). Its matching source is
[report-source/main.tex](report-source/main.tex).

## Network configuration

Both outer access links use **1000 Mbit/s and 5 ms per direction**.
The shared core uses **20 Mbit/s and 25 ms per direction**.
Every shaped interface has a 1000-packet queue limit.
The nominal base RTT is 2 * (5 + 25 + 5) = **70 ms**.
Topology logs include connectivity tests and each interface's actual qdisc.

The single-flow topology uses four namespaces. The competing-flow topology
uses six namespaces, with identical settings on both pairs' access links.

## Builds and tests

Baseline source: `5a4eba475555a2b0d67fbd9000714be35b3db4b4`.

RLI source: `80c9186fd466c105cd11c5b6d5ac95ee95911db0`.

Both versions were rebuilt separately. Both passed their two registered CTest
suites. Baseline ran 562 picoquic and 105 picohttp subtests; RLI ran 563 and 105.
The separate `cubic_rli` test and nine Python result-tool tests also passed.
These are registered regression suites, not every optional stress or fuzz test.

The campaign contains twelve single-flow experiments and six two-flow
experiments: **24 completed connections**. Each workload/mode has three repeats.
All twelve RLI sender traces pass the current validator, including reset checks.
Limited runs require an active cap; main RLI bulk runs also require a reduction
and an observable history reset. These checks do not certify every protocol state.

## Measured results

| Workload | Baseline throughput | RLI throughput | Observed change |
|---|---:|---:|---:|
| rate-limited | 0.189391 Mbit/s | 0.189369 Mbit/s | -0.012% |
| bulk | 17.096857 Mbit/s | 17.602599 Mbit/s | +2.958% |
| Two competing flows, combined wall rate | 18.595626 Mbit/s | 18.580062 Mbit/s | -0.084% |

Fixed-rate final cwnd is 15 KiB for baseline and 30 KiB for RLI.
The application still supplies only 480,000 bytes at about 192 kbit/s.
The initialized 15 KiB maxFS permits a bounded 30 KiB slow-start window.
A larger window is not a doubling of throughput.

Three repeats support descriptive comparisons, not general or statistically
proven performance gains. Do not attribute differences from the previous
campaign solely to access-link shaping: the RLI source revision also changed.
Source identifiers and executable hashes distinguish the campaigns.

## Graphs and evidence

- `plots/rate-limited-{baseline,rli}-{1,2,3}.png`: six fixed-rate graphs.
- `plots/bulk-{baseline,rli}-{1,2,3}.png`: six bulk graphs.
- `plots/overview.png`: three-run means and sample standard deviations.
- `plots/dumbbell/{baseline,rli}-{1,2,3}.png`: six competing-flow graphs.
- `raw-evidence.tar.gz`: lossless qlogs and performance logs for this campaign.
- `measurements.csv`, `summary.json`, `SUMMARY.md`: main measurements.
- `dumbbell/`: competing-flow measurements and validation.
- `tests/`: fresh build, regression, focused-test, and Python-tool logs.
- `campaign-checks.json`: source, binary, topology, and campaign audit.
- `current-validator-checks.json`: current per-trace invariant checks.
- `final-report-checks.json`: checks for the regenerated final PDF.
- `SHA256SUMS`: current portable distribution checksums.

The earlier distribution and topology are backed up under `archive/`.
The exact backup path and digest are recorded in `campaign-checks.json`.
The backup is ignored by Git and remains local. Historical report editions,
their checks, `SHA256SUMS.original`, and `evaluated-tools/` are retained for
reference. Only `Final report.pdf` and `report-source/` describe this campaign.

## Reproduce

Preserve the current evidence before another run. Main collection archives
existing `runs/`; competing-flow collection refuses to overwrite its raw runs.
Use the Linux dependencies and namespace commands in `../experiments/README.md`.

```bash
.venv/bin/python results/run_tests.py
unshare --user --map-root-user --net --mount bash results/run_experiments.sh
.venv/bin/python results/analyze_results.py
unshare --user --map-root-user --net --mount sh -c \
  'mount --make-rprivate /; mount -t tmpfs tmpfs /run; mkdir -p /run/netns; exec .venv/bin/python results/run_dumbbell.py'
.venv/bin/python results/analyze_dumbbell.py
.venv/bin/python results/refresh_campaign.py --previous-archive <path-to-backup.tar.gz>
.venv/bin/python results/build_final_report.py
.venv/bin/python results/refresh_campaign.py --finalize
.venv/bin/python results/check_bundle.py
```

To restore raw traces after cloning, run `results/package_evidence.py --unpack`.
It refuses to overwrite differing local evidence. To check distribution hashes,
run `sha256sum --check --quiet SHA256SUMS` inside this directory.

No runtime C/C++ source was edited for this campaign. The report documents the
selected congestion-avoidance interpretation and the limits of the evaluation.
Commit and push remain with the repository owner.

## Additional same-connection CA test

The later [three-phase experiment](ca-rate-limited/README.md) is saved separately.
It adds three baseline and three RLI connections, plus an excluded pilot.
All matched transfers and observed checks pass, but no cap activates in the limited CA intervals.
Its cap-coverage verdict is incomplete. The final PDF above does not include this additional test.
