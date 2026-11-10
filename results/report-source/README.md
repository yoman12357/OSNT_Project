# Editable final report

`main.tex`, `sections/`, and `images/` are the source and assets for
`../Final report.pdf`. Measured tables and plots use the retained Ubuntu Linux
campaign in `../measurements.csv`, `../summary.json`, and `../dumbbell/`.
`diagrams/` contains editable Mermaid diagram sources.

From the repository root, run `python3 results/build_final_report.py` with
pdfLaTeX and pypdf installed. It compiles twice, checks the PDF, and publishes
`results/Final report.pdf`. Compiler intermediates stay in the ignored `build/`
subdirectory. `data/` retains the original measurement/provenance snapshot.

## Historical and current validation

The retained campaign passed the validator from evaluated revision 60323926.
Its matching parser and validator are included in `results/evaluated-tools/`
and used by the retained analysis helpers. The newer local validator adds
stricter reset requirements. Rechecking all twelve archived RLI traces with
that validator passes three and flags nine without observable reset evidence.
`results/current-validator-checks.json` records every error. The raw traces
and measured values are unchanged. Folder consolidation does not resolve
these additional validation findings or certify the current local C source.
