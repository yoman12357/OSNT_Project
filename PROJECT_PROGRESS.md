# Rate-limited sender project progress

Steps 1–5 are complete in this fork. Steps 6, 7, and 8 remain.

## Completed

1. **Picoquic installed and verified** on native Linux. See
   `project_docs/step-1-installation-and-verification.md`.
2. **Congestion-control architecture and CUBIC implementation studied**
   and documented. See `project_docs/step-2-congestion-control-study.md`.
3. **Linux network-namespace dumbbell topology created and tested**. See
   `topology/` for the scripts and `topology/VERIFICATION.md`.
4. **Baseline CUBIC experiment and cwnd plot**. A 20 MB transfer over the
   20 Mbit/s / 50 ms topology with CUBIC was captured as qlog and plotted.
   See `project_docs/step-4-baseline-experiment.md` and
   `experiments/baseline/cubic_cwnd_baseline.png`.
5. **CUBIC changes required by the draft identified**. Analysis documented
   in `project_docs/step-2-congestion-control-study.md`, section
   "Mapping the IETF draft to picoquic".

## Remaining

6. Implement the rate-limited increase functionality in `picoquic/cubic.c`
   and validate against the regression suite.
7. Repeat the Step 4 experiment with the functionality enabled.
8. Compare and validate the cwnd graphs.

## Repository layout

    project_docs/
        step-1-installation-and-verification.md
        step-2-congestion-control-study.md
        step-4-baseline-experiment.md
    topology/
        setup.sh            create the four-namespace dumbbell
        check.sh            verify namespaces, routes, qdiscs, ping
        cleanup.sh          remove all four namespaces
        README.md           topology description and how to run
        VERIFICATION.md     recorded verification of Step 3
    experiments/
        baseline/
            cubic_cwnd_baseline.png        Step 4 plot
    plot_cwnd.py            qlog-to-cwnd-plot converter
    picoquic/
        cubic.c             unchanged CUBIC implementation (baseline)

## How to reproduce

See `project_docs/step-1-installation-and-verification.md` for the build
and `project_docs/step-4-baseline-experiment.md` for the experiment. The
`topology/README.md` file describes the network setup.
