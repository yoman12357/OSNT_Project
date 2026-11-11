# Final report: Rate-Limited Sender functionality in picoquic

Project #16 · Linux verification: 7 November 2026

Team members: Aryan Bokolia, Affan Arshad, Soumyadeep Raj, Kevin Shiju George,
and Aryan Sanjay palimkar.

Open [Final report.pdf](Final%20report.pdf) for the final report. Download
[Final report LaTeX.zip](Final%20report%20LaTeX.zip) for its matching Overleaf
source. The topology figure includes the updated 1000 Mbit/s access links
with 5 ms one-way delay. The report identifies the earlier setup used for
the saved comparison measurements.

## Is the output correct?

The recorded builds, full registered regression suites, and RLI trace checks
pass for the tested conditions. The PDF is compiled on Linux, checked for all
five cover names, complete text, embedded figures, undefined references, and
overflow, then rendered for visual review. Final results are recorded in
pdf-checks.json and verification.json. Minor underfull-spacing warnings do not
mean missing content or compilation failure.

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

- Final report.pdf and Final report LaTeX.zip: final PDF and matching source.
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
python3 "results 1/package_evidence.py" --unpack
cd "results 1"
sha256sum --check --quiet SHA256SUMS
```

## Reproduction on the current Linux workspace

```bash
cd /home/aryy_02/Desktop/OSNT_Project
python3 "results 1/run_tests.py"

# Main matrix; old run copies are archived automatically.
unshare --user --map-root-user --net --mount \
  bash "results 1/run_experiments.sh"
.venv/bin/python "results 1/analyze_results.py"

# Competing-flow matrix. Refuses to overwrite existing dumbbell runs.
# Preserve/relocate dumbbell/baseline and dumbbell/rli before repeating.
unshare --user --map-root-user --net --mount sh -c \
  'mount --make-rprivate /; mount -t tmpfs tmpfs /run; mkdir -p /run/netns; exec .venv/bin/python "results 1/run_dumbbell.py"'
.venv/bin/python "results 1/analyze_dumbbell.py"

python3 "results 1/build_report.py"
.venv/bin/python "results 1/make_contact_sheets.py"

# Only after actually reviewing the rendered pages:
python3 "results 1/finalize.py" --visual-reviewed
xdg-open "results 1/report.pdf"
```

The existing workspace has local OpenSSL headers, picotls, a Python venv with
matplotlib/Pillow, and Tectonic. A fresh machine needs CMake, Ninja, GCC/G++,
OpenSSL development files, Python venv support, iproute2, ping, Poppler tools,
and a LaTeX compiler. Install experiments/requirements.txt in .venv.
Adapt the test helper's local dependency paths when using system headers.
Unprivileged user namespaces must be enabled for the unshare workflow.

With TeX Live, run pdflatex report.tex twice from this folder instead of
Tectonic. The report's figures and generated inputs are included.

## Housekeeping and attribution

Toolchains, .venv, build products, PDF previews, and unpacked raw logs are
ignored by Git. The report, source, figures, compressed raw evidence, and test
summaries are included. Generated build qlogs are compressed losslessly;
source files and submission evidence are preserved.

The report credits picoquic, the IETF specifications, and the build, measurement,
and reporting tools. Commit and push remain with the repository owner. Do not
force-push or run git clean -fdx.
