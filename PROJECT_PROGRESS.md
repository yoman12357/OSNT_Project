# Rate-limited sender project progress

The first three project steps are complete in this fork.

## Completed

1. Picoquic was cloned, configured, compiled, and verified on native Linux.
2. Picoquic's congestion-control architecture and CUBIC implementation were
   studied and documented.
3. A reproducible Linux network-namespace dumbbell topology was created and
   tested.

## Repository additions

- `project_docs/step-1-installation-and-verification.md`
- `project_docs/step-2-congestion-control-study.md`
- `topology/setup.sh`
- `topology/check.sh`
- `topology/cleanup.sh`
- `topology/README.md`
- `topology/VERIFICATION.md`

## Remaining project steps

4. Run baseline CUBIC experiments and plot the congestion window.
5. Finalize the CUBIC changes required by the rate-limited increase draft.
6. Implement the functionality and tests.
7. Repeat the experiment with the functionality enabled.
8. Compare and validate the congestion-window graphs.
