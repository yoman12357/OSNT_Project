# Same-connection congestion-avoidance test

Run date: 10 November 2026.

The additional test uses one connection for three dependent streams:

1. Transfer 20 MiB to reach congestion avoidance.
2. Send 1200-byte frames at 20 frames per second for about 20 seconds.
3. Request a 5 MiB burst without restarting the connection.

The matched campaign contains three baseline and three RLI connections.
An earlier RLI-only pilot is retained separately and excluded from the three-run averages.

## Result

All six matched connections entered congestion avoidance before the limited phase.
All 18 streams completed, with zero whole-connection retransmissions.
The state, delivery, and observed-invariant checks passed.

However, cwnd stayed constant during every measured limited interval.
No RLI cap became active during those intervals.
The coverage verdict is therefore **INCOMPLETE for active CA-cap exercise**.
This is not a failed transfer or an observed cap violation.
It does not fully close the live CA-cap validation gap.

Mean burst completion was 2.281816 seconds for baseline and 2.281872 seconds for RLI.
These near-identical times do not support a burst-speed improvement claim.
Different low-phase window heights were inherited from warm-up, not measured CA growth.

The analysis checks the implemented conservative CA ceiling.
It does not independently establish exact CUBIC conformance to the IETF draft.
The earlier campaign, its graphs, and `results/Final report.pdf` remain unchanged.

## Open the results

- [Matched campaign summary](campaign/SUMMARY.md)
- [Overview graph](campaign/plots/overview.png)
- [Paired comparison, run 1](campaign/plots/comparison-1.png)
- [Paired comparison, run 2](campaign/plots/comparison-2.png)
- [Paired comparison, run 3](campaign/plots/comparison-3.png)
- [Numeric measurements](campaign/measurements.csv)
- [Detailed checks and phase boundaries](campaign/summary.json)
- [Commands, source revisions, and executable hashes](campaign/collection.json)
- [Pilot summary](pilot-20mib/SUMMARY.md)
- [Analysis-tool tests](tool-tests.log): 17 tests passed.

Individual full traces and limited-window zooms are in `campaign/plots/`.
Zoom panels use different Y scales and are labelled accordingly.
Paired comparison panels use a shared scale and show changes from each interval's first sample.

## Evidence and integrity

`raw-evidence.tar.gz` contains losslessly compressed client and server qlogs,
performance CSVs, stdout logs, per-run commands, and per-run analysis.
`archive-checks.json` records byte-for-byte archive checks.
Local raw directories are ignored by Git; the archive is included for distribution.

Restore traces after cloning:

```bash
.venv/bin/python results/ca-rate-limited/package_evidence.py --unpack
```

The restore command refuses to overwrite different existing evidence.
Runtime C/C++ code and the evaluated binaries were not changed for this test.

## Repeat the test

Use a new output folder. The collector refuses to overwrite an existing campaign.
Run these commands from the repository root:

```bash
unshare --user --map-root-user --net --mount sh -c \
  'mount --make-rprivate /; mount -t tmpfs tmpfs /run; mkdir -p /run/netns; exec .venv/bin/python experiments/run_ca_rate_limited.py --output results/ca-rate-limited/repeat-new --mode both --repetitions 3'
.venv/bin/python experiments/analyze_ca_rate_limited.py results/ca-rate-limited/repeat-new
.venv/bin/python -m unittest experiments.test_ca_rate_limited experiments.test_results -v
```

Add `--require-ca-cap` to the analysis command to require an active cap in every RLI limited interval.
For this recorded campaign, that stricter command exits with status 1 because the cap was not exercised.
It still saves all measurements and graphs.

Phase boundaries come from stream requests and payload completion in qlog.
Congestion-state events confirm CA state 2.
The measured low-rate interior excludes 0.5 seconds at each boundary.
Burst completion uses two client-side timestamps: first request packet and full payload receipt with FIN.
Byte-range accounting handles duplicates and out-of-order arrivals.
