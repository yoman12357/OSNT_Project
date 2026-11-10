# Editable final report

`main.tex`, `sections/`, and `images/` are the source and assets for
`../Final report.pdf`. Measured tables and plots use the retained Ubuntu Linux
campaign in `../measurements.csv`, `../summary.json`, and `../dumbbell/`.
The current campaign ran on 10 November 2026 with 1000 Mbit/s, 5 ms access
links and a 20 Mbit/s, 25 ms core link in both directions. Base RTT is about 70 ms.
`diagrams/` contains editable Mermaid diagram sources.

From the repository root, run `.venv/bin/python results/build_final_report.py`
with pdfLaTeX or Tectonic and pypdf installed. It compiles twice, checks the PDF, and publishes
`results/Final report.pdf`. Compiler intermediates stay in the ignored `build/`
subdirectory. `data/` retains the current measurement/provenance snapshot.

## Historical and current validation

The new campaign uses the current parser and validator, not the frozen
historical tools in `results/evaluated-tools/`. All twelve fresh RLI traces
must pass, including observable reset checks. `campaign-checks.json` records
build, topology, source, and connection checks. `current-validator-checks.json`
contains per-trace counters and errors. The previous distribution is backed
up under `results/archive/` and is not mixed into the new measurements.
