# Project #16: Rate-Limited Sender functionality in picoquic

Team: Aryan Bokolia, Affan Arshad, Soumyadeep Raj, Kevin Shiju George,
and Aryan Sanjay palimkar.

## Submission

- [Final PDF report](results%201/report.pdf)
- [Editable LaTeX](results%201/report.tex)
- [Verification and reproduction guide](results%201/README.md)
- [Main measured results](results%201/SUMMARY.md)
- [Two-flow dumbbell results](results%201/dumbbell/measurements.csv)
- [Complete compressed experiment evidence](results%201/raw-evidence.tar.gz)

The implementation adds opt-in RLI to CUBIC (`-G cubic -H rli=on`). The
unchanged baseline and implementation passed all registered CTest suites.
There are 12 single-flow experiments and six supplementary two-flow dumbbell
experiments. The report distinguishes controlled cwnd growth from measured
throughput and describes the selected congestion-avoidance ceiling.

## Build and demo

On Linux with CMake, Ninja, a C/C++ compiler, and OpenSSL development files:

```bash
cmake -S . -B build -G Ninja -DPICOQUIC_FETCH_PTLS=Y \
  -DWITH_OPENSSL=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel 4
ctest --test-dir build --output-on-failure
./build/picoquic_ct cubic_rli
```

For the full two-pair topology:

```bash
sudo bash topology/setup_dumbbell.sh
sudo bash topology/check_dumbbell.sh
sudo bash topology/cleanup.sh
```

To restore the packaged raw logs after cloning:

```bash
python3 "results 1/package_evidence.py" --unpack
```

See [results 1/README.md](results%201/README.md) for the experiment matrix and
local toolchain details. This fork retains the upstream picoquic implementation
and attribution; the project contribution and its limits are described in the
report.
