# Rate-limited sender project progress

Steps 1-5 are complete. Step 6 is implemented locally and awaiting the full
native-Linux regression run. Steps 7-8 require new experiment data.

## Completed

1. **Picoquic installed and verified** on native Linux. See
   `project_docs/step-1-installation-and-verification.md`.
2. **Congestion-control architecture and CUBIC studied**. See
   `project_docs/step-2-congestion-control-study.md`.
3. **Linux netns dumbbell topology created and tested**. See `topology/`.
4. **Baseline bulk CUBIC experiment and cwnd plot captured**. See
   `project_docs/step-4-baseline-experiment.md` and
   `experiments/baseline/cubic_cwnd_baseline.png`.
5. **RLI changes mapped to picoquic**. See
   `project_docs/step-5-rli-design.md`.

## In progress

6. **CUBIC RLI implementation**:
   - opt-in using `-G cubic -H rli=on`;
   - per-path `maxFS` accounting;
   - Slow Start and Congestion Avoidance caps;
   - reset/recovery and spurious-loss handling;
   - qlog metrics, plotting, and focused `cubic_rli` test.

   The changed C files compile. Native-Linux focused and full-suite execution
   remains before Step 6 is complete. See
   `project_docs/step-6-implementation.md`.

## Remaining

7. Run matched baseline/RLI experiments three times for the rate-limited and
   bulk workloads using `experiments/run_comparison.sh`.
8. Validate every cwnd increase against the recorded RLI limit and compare
   throughput/loss behavior with the baseline.

## Important files

```text
IMPLEMENTATION_PLAN.md
project_docs/
    step-1-installation-and-verification.md
    step-2-congestion-control-study.md
    step-4-baseline-experiment.md
    step-5-rli-design.md
    step-6-implementation.md
topology/
    setup.sh
    check.sh
    cleanup.sh
experiments/
    README.md
    run_comparison.sh
    baseline/cubic_cwnd_baseline.png
plot_cwnd.py
picoquic/cubic.c
picoquic/sender.c
picoquictest/congestion_test.c
```
