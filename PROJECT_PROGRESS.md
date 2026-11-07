# Rate-limited sender project progress

All eight project steps have implementation and experimental evidence for the
documented scope. The final submission is indexed in `SUBMISSION.md`.
The selected CUBIC congestion-avoidance ceiling is explained in the report;
the project does not claim independent IETF conformance certification.

## Final verification — 7 November 2026

- Baseline: 562 picoquic and 105 picohttp subtests, zero failures.
- Implementation: 563 picoquic and 105 picohttp subtests, zero failures;
  separate `cubic_rli` execution passed.
- Main matrix: 12 single-flow experiments, three repeats per mode/workload.
- Full dumbbell: six two-flow experiments, 12 additional complete transfers.
- Main rate-limited average cwnd: +98.71%; throughput essentially unchanged.
- Main bulk throughput: +1.23% observed; competing-flow combined rate: -0.22%
  observed. Neither establishes a general performance gain or regression.
- Final report, LaTeX, plots, raw evidence archive, and checks: `results 1/`.

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
6. **CUBIC RLI implementation and regression testing completed**:
   - opt-in using `-G cubic -H rli=on`;
   - per-path `maxFS` accounting;
   - Slow Start and Congestion Avoidance caps;
   - reset/recovery and spurious-loss handling;
   - qlog metrics, plotting, and focused `cubic_rli` test;
   - full native-Linux CTest suite passed.

   See `project_docs/step-6-implementation.md` and `tests/results/rli/`.
7. **Matched baseline/RLI experiments**:
   - rate-limited and bulk workloads each run three times;
   - baseline stayed at 15 KiB cwnd;
   - RLI reached its 30 KiB cap in all runs;
   - all six mechanical RLI checks passed;
   - bulk throughput showed no material regression.

   See `tests/results/step7/`.
8. **RLI graph and behavior validation completed**:
   - every recorded cwnd increase stayed within its RLI limit;
   - rate-limited cwnd reached the expected `2 * maxFS` ceiling;
   - all six experiment traces passed mechanical validation;
   - bulk throughput and retransmission behavior showed no material
     regression;
   - the final conclusion is supported by the observed traces for the
     documented growth-limit interpretation and tested conditions.

   See `project_docs/step-8-validation.md`.

## Important files

```text
IMPLEMENTATION_PLAN.md
project_docs/
    step-1-installation-and-verification.md
    step-2-congestion-control-study.md
    step-4-baseline-experiment.md
    step-5-rli-design.md
    step-6-implementation.md
    step-8-validation.md
tests/results/step7/
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
