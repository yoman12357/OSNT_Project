# Recorded campaign analysis tools

These two files are retained verbatim from evaluated revision
60323926df8ef75c440f959789ac4d043071879d. They reproduce the archived campaign's
parser and observed-invariant checks. The current repository tools under
experiments/ enforce additional reset checks. They flagged nine traces in the
previous campaign without observable reset evidence. That distribution is
backed up under ../archive/. A historical PASS does not imply those newer
checks passed.

The fresh 10 November campaign uses the current root-level parser and validator.
Its twelve RLI traces pass the current checks. See ../current-validator-checks.json.
The frozen tools here are historical references, not the active campaign tools.
