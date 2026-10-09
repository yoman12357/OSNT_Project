# Picoquic test results

These results compare the original picoquic CUBIC implementation with the
rate-limited sender implementation.

## Result folders

- `results/original/`: `master` at commit
  `5a4eba475555a2b0d67fbd9000714be35b3db4b4`.
- `results/rli/`: `test/rli-implementation` at commit
  `d436b16098bb749b7af2cedc696b743182314d33`.

Both versions were built with CMake and tested with:

```bash
cmake --build build --parallel "$(nproc)"
ctest --test-dir build --output-on-failure
```

The implemented version was additionally tested with:

```bash
./build/picoquic_ct cubic_rli
```

## Comparison

| Version | Build | Full CTest suite | CUBIC RLI test |
| --- | --- | --- | --- |
| Original | Passed | 2/2 passed | Not present in original |
| RLI implementation | Passed | 2/2 passed | Passed |

The complete CTest console output is stored in each version's `ctest.log`.

Step 7 experiment evidence is stored in `results/step7/`. It contains three
matched baseline/RLI cwnd plot pairs for each of the rate-limited and bulk
workloads, comparison CSV files, validation output, and a summary of the
observed measurements.

The final interpretation and draft-compliance assessment are documented in
`project_docs/step-8-validation.md`.
