# Final report: Rate-Limited Sender functionality in picoquic

Project #16. Linux verification: 7 November 2026

Team members: Aryan Bokolia, Affan Arshad, Soumyadeep Raj, Kevin Shiju George,
and Aryan Sanjay palimkar.

Open [Final report.pdf](Final%20report.pdf) for the final report. The matching editable source is [report-source/main.tex](report-source/main.tex).
The earlier `report.tex` and `report1.tex` editions and their inputs are retained separately.

## Is the output correct?

The recorded builds, full registered regression suites, and RLI trace checks
pass for the tested conditions. The final experiment environment is Ubuntu 26.04 LTS
with Linux kernel 7.0.0-38-generic, recorded in `environment.json`.
Historical report checks are retained in `pdf-checks.json`, `report1-checks.json`,
and `verification.json`; they describe earlier editions. The current final PDF
is checked separately in `final-report-checks.json`. Its editable source and
all included figures are retained under `report-source/`.

The report documents the conservative additive congestion-avoidance ceiling,
its relationship to Sections 3 and 4.5 of draft revision 11, and the limits of
the evaluation. This is an evaluated implementation, not independent standards
certification or a universal speedup claim.

## Source and test evidence

| Version | Evaluated source |
|---|---|
| Unchanged pre-RLI baseline | 5a4eba475555a2b0d67fbd9000714be35b3db4b4 |
| CUBIC implementation | 60323926df8ef75c440f959789ac4d043071879d |

The revisions were built separately with the same compiler, picotls source,
OpenSSL libraries, and build settings. No runtime C/C++ implementation files
were changed during final report preparation. Additional topology scripts
provide the full two-pair dumbbell. environment.json records binary hashes.

The inherited main experiment runner records the orchestrator's Git HEAD even
when it uses the separate baseline binary. Use each run's provenance.txt for
the actual source revision and demo_sha256 for executable identity.
Supplementary dumbbell metadata records the actual source and binary directly.

| Check | Baseline | Implementation |
|---|---:|---:|
| Build | Passed | Passed |
| CTest suites | 2/2 passed | 2/2 passed |
| picoquic internal subtests | 562, zero failures | 563, zero failures |
| picohttp internal subtests | 105, zero failures | 105, zero failures |
| Separate cubic_rli test | Not present | Passed |
| Single-flow experiments | 6 completed | 6 completed |
| Two-flow experiments | 3 completed | 3 completed |

The CTest entries use the repository's -n -r configuration. Full default
regression suites do not include every optional stress/fuzz configuration or
external network environment. Multiple focused assertions belong to one
registered cubic_rli test.

## Measured findings

There are 18 experiments and 24 complete QUIC connections: 12 main single-flow
runs, plus six supplementary runs with two simultaneous connections each.

| Main metric | Baseline mean | RLI mean | Interpretation |
|---|---:|---:|---|
| Limited-sender final cwnd | 15 KiB | 30 KiB | Bounded growth |
| Limited-sender average cwnd | 15.000 KiB | 29.806 KiB | +98.71% permitted window |
| Limited-sender throughput | 0.190179 Mbit/s | 0.190186 Mbit/s | Essentially unchanged |
| Bulk throughput | 17.731656 Mbit/s | 17.949780 Mbit/s | +1.23% observed |

The limited application supplies 480,000 bytes. A larger window cannot create
additional data. maxFS starts at 15 KiB; the largest observed flight is 3,426
bytes. The 30 KiB ceiling is twice the initialized maxFS, not 30 KiB sent at once.

The full dumbbell has two client/server pairs sharing the 20 Mbit/s link.
Combined wall-time throughput averaged approximately 18.665 Mbit/s for baseline
and 18.625 Mbit/s for RLI (-0.22%). Jain fairness and all per-run figures are in
dumbbell/measurements.csv and dumbbell/aggregate.json. Three repeats support
descriptive comparisons, not statistically proven general gains/regressions.

All main runs have zero retransmissions. The competing-flow runs do have
retransmissions; the report distinguishes the two experiment sets.
All 12 RLI connections pass observed-invariant checks. Low-rate main cases
require an active cap; main bulk cases additionally require a visible reduction
and history reset. Competing-flow transfers check bytes at sender and receiver.

The report analysis includes the logger's initial zero cap-flag interval in
whole-trace cap fractions. This corrects a conditional statistic in the generic
helper without changing cwnd/throughput measurements. Comparison logs explain
the adjustment and retain the raw tool output.

## Submission files

- Final report.pdf: final submission.
- report-source/: matching final-report source, diagrams, images, and measured tables.
- final-report-checks.json: current PDF checks.
- bundle-checks.json and check_bundle.py: current bundle inventory and integrity checks.
- report.tex, team.json, and generated-*.tex: inputs for the earlier edition.
- plots/: 12 main graphs, one overview, and six competing-flow graphs.
- raw-evidence.tar.gz: lossless archive of all raw experiment runs.
- tests/: build, CTest, focused-test logs, and detailed records.
- measurements.csv, summary.json, SUMMARY.md: main measurements.
- dumbbell/: supplementary tables, aggregates, checks, and topology logs.
- comparisons/, validation/: main pair comparisons and RLI checks.
- implementation.patch, changed-files.txt: evaluated implementation diff.
- environment.json, pdf-checks.json, verification.json: verification evidence.
- SHA256SUMS: portable checksums for distributable files.

Raw directories remain available locally but are ignored by Git; their complete
contents are delivered in raw-evidence.tar.gz. The archive is checked
byte-for-byte before the final manifest is created. Restore logs after cloning:

```bash
cd /path/to/OSNT_Project
python3 "results/package_evidence.py" --unpack
cd "results"
sha256sum --check --quiet SHA256SUMS
```

## Reproduction on Linux

See [../experiments/README.md](../experiments/README.md) for Ubuntu dependencies,
separate baseline/RLI builds, both topology commands, and safe fresh-run output.
The final measured source revisions remain those listed above; the current
working-tree runtime edits have not been rerun as part of this folder cleanup.

Check the bundle and rebuild the final report from the repository root:

```bash
python3 results/check_bundle.py
.venv/bin/python results/build_final_report.py
xdg-open 'results/Final report.pdf'
```

The main reproduction helper uses the matching `run_single_comparison.sh` in
this folder. `topology/setup_dumbbell.sh` and `topology/check_dumbbell.sh`
provide the supplementary two-pair topology. Existing measurements must be
preserved before invoking collectors or analyses that regenerate outputs.
`run_tests.py` uses the Linux system OpenSSL development package by default,
with optional locally unpacked headers when available.

The original manifest is retained as `SHA256SUMS.original`. `SHA256SUMS`
checks the consolidated bundle, including updated paths and report sources.
The original raw archive and recorded measurement values remain unchanged.
Historical JSON may contain original folder names in captured commands or
source hashes; those are provenance records rather than current instructions.

## Housekeeping and attribution

Toolchains, .venv, build products, PDF previews, and unpacked raw logs are
ignored by Git. The report, source, figures, compressed raw evidence, and test
summaries are included. Generated build qlogs are compressed losslessly;
source files and submission evidence are preserved.

The report credits picoquic, the IETF specifications, and the build, measurement,
and reporting tools. Commit and push remain with the repository owner. Do not
force-push or run git clean -fdx.

## Historical and current validation

The retained campaign passed the validator from evaluated revision 60323926.
Its matching parser and validator are included in `results/evaluated-tools/`
and used by the retained analysis helpers. The newer local validator adds
stricter reset requirements. Rechecking all twelve archived RLI traces with
that validator passes three and flags nine without observable reset evidence.
`results/current-validator-checks.json` records every error. The raw traces
and measured values are unchanged. Folder consolidation does not resolve
these additional validation findings or certify the current local C source.
