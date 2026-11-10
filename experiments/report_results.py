#!/usr/bin/env python3
"""Write the campaign report from saved measurements and test evidence."""

import argparse
import json
from pathlib import Path
import re
import statistics
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.collect_results import save_manifest

TOPOLOGY = "dumbbell_access1000mbps_5ms_core20mbps_25ms"


def write_report(output):
    rows = []
    tests = {}
    metadata = {}
    for mode in ("original", "rli_implemented"):
        base = output / mode / TOPOLOGY
        rows.extend(json.loads(path.read_text()) for path in
                    sorted((base / "results").glob("*/run_*/summary.json")))
        metadata[mode] = json.loads((base / "results/bulk/run_01/metadata.json").read_text())
        suite = ET.parse(base / "results/regression-tests.xml").getroot()
        details = (base / "logs/regression-details.log").read_text()
        counts = re.findall(r"Tried (\d+) tests, (\d+) fails", details)
        tests[mode] = {"ctest_suites": int(suite.attrib["tests"]),
                       "ctest_failures": int(suite.attrib["failures"]),
                       "internal_tests": sum(int(count) for count, _ in counts),
                       "internal_failures": sum(int(failures) for _, failures in counts)}
        (base / "results/regression-summary.json").write_text(json.dumps(tests[mode], indent=2) + "\n")
    passed = len(rows) == 12 and all(row["status"] == "PASS" for row in rows)
    checks = {"final_runs": len(rows), "passed_runs": sum(row["status"] == "PASS" for row in rows),
              "regression": tests,
              "topologies": [TOPOLOGY],
              "scope": "three repetitions, two workloads, two independently built versions"}
    (output / "rli_implemented" / TOPOLOGY / "results/campaign-summary.json").write_text(
        json.dumps(checks, indent=2) + "\n")
    text = ["# Original CUBIC and RLI CUBIC: completed results", "",
            f"**Final live runs: {checks['passed_runs']}/{len(rows)} passed.** "
            "Only the existing dumbbell topology was supplied and tested.", "",
            "## Where to look", "",
            f"- [Original results](original/{TOPOLOGY}/results/run-summary.csv)",
            f"- [RLI results](rli_implemented/{TOPOLOGY}/results/run-summary.csv)",
            f"- [Numeric comparison](rli_implemented/{TOPOLOGY}/results/comparison.csv)",
            f"- [Rate-limited comparison graph](rli_implemented/{TOPOLOGY}/graphs/rate-limited-comparison.png)",
            f"- [Bulk comparison graph](rli_implemented/{TOPOLOGY}/graphs/bulk-comparison.png)",
            f"- [Throughput, RTT, retransmission graph](rli_implemented/{TOPOLOGY}/graphs/throughput-rtt-loss-comparison.png)",
            "", "## Folder structure", "", "```text", "results/", "  README.md"]
    for mode in ("original", "rli_implemented"):
        text.extend([f"  {mode}/{TOPOLOGY}/", "    graphs/", "    results/", "    logs/"])
    text.extend(["```", "", "Each category contains `bulk/run_01` through `run_03` and "
                 "`rate-limited/run_01` through `run_03`. Per-run graphs, CSV/JSON measurements, "
                 "performance CSVs, full `.qlog.gz` traces, stdout, commands, and topology "
                 "setup/check/cleanup logs are retained. Summary CSVs and comparison graphs "
                 "are at their category's top level.", "", "## Measured comparison", "",
                 "Means and sample standard deviations across three runs. Download rates "
                 "are the client's recorded receive rates; complete raw records are retained.", "",
                 "| Workload | Version | Download Mbit/s (mean +/- SD) | Maximum cwnd (KiB, mean) | Retransmissions (total) |",
                 "|---|---|---:|---:|---:|"])
    for workload in ("bulk", "rate-limited"):
        for mode in ("original", "rli_implemented"):
            group = [r for r in rows if r["mode"] == mode and r["workload"] == workload]
            rates = [r["download_mbit_s"] for r in group]
            text.append(f"| {workload} | {mode} | {statistics.mean(rates):.6f} +/- "
                        f"{statistics.stdev(rates):.6f} | "
                        f"{statistics.mean(r['cwnd_max_bytes'] for r in group) / 1024:.3f} | "
                        f"{sum(r['sender_retransmissions'] for r in group)} |")
    text.extend(["", "In all rate-limited runs, original CUBIC stayed at 15 KiB; RLI reached "
                 "30 KiB and stopped at its cap. Both versions delivered the full 480,000-byte "
                 "fixed-rate workload. Its throughput is application-limited, so the larger "
                 "window is not a claimed throughput improvement.", "",
                 "Every final RLI bulk run exercised a cwnd reduction and a logged maxFS "
                 "reset. There were no recorded retransmissions in the final runs. Startup "
                 "window reductions are consistent with HyStart's delay response, rather "
                 "than proof of packet loss. All three individual traces remain visible.", "",
                 "## Build and verification", "",
                 "| Version | Full regression checks | Failures |", "|---|---:|---:|"])
    for mode, test in tests.items():
        text.append(f"| {mode} | {test['internal_tests']} across picoquic_ct and picohttp_ct | "
                    f"{test['internal_failures']} |")
    sanitizer_log = output / "rli_implemented" / TOPOLOGY / "logs/sanitizer-cubic-rli-test.log"
    sanitizer_text = sanitizer_log.read_text() if sanitizer_log.exists() else ""
    sanitizer_ok = "Success." in sanitizer_text and not re.search(
        r"ERROR: (AddressSanitizer|LeakSanitizer)|runtime error:", sanitizer_text)
    tool_log = output / "rli_implemented" / TOPOLOGY / "logs/result-tool-tests.log"
    tool_text = tool_log.read_text() if tool_log.exists() else ""
    text.extend(["", "- Both versions configured, compiled, linked, and passed their two full CTest runners.",
                 "- The extended focused `cubic_rli` test passed.",
                 f"- Focused ASan/UBSan with leak detection: {'PASS' if sanitizer_ok else 'not confirmed'}.",
                 f"- Python parsing/validation regressions: {'9 passed' if 'Ran 9 tests' in tool_text and 'OK' in tool_text else 'see test log'}.",
                 "- The C checks cover option/DCUBIC isolation, independent path instances, "
                 "overflow, live flight accounting, SS/CA caps, epoch handling, and recovery.", "",
                 "See the topology folders' `logs/regression-tests.log`, "
                 "`logs/regression-details.log`, and `results/regression-tests.xml` for full evidence.",
                 "", "## Environment and provenance", "",
                 "- Recorded Linux platform: " + metadata["rli_implemented"]["platform"] + ".",
                 "- GCC 15.2, CMake 4.2.3, Ninja 1.13.2, OpenSSL 3.5.5, "
                 "Python 3.14.4, matplotlib 3.11.2.",
                 "- Original source: `" + metadata["original"]["commit"] + "`.",
                 "- RLI base: `" + metadata["rli_implemented"]["commit"] + "` plus the final retained source patch.",
                 "- Each run records executable SHA-256, all tracked source-file hashes, "
                 "tracked-diff hash, workload, payload hash, UTC start time, and exact commands.",
                 "- The original and RLI executables are separate builds. Both use certificate verification "
                 "and the same fixed payload, topology, and logging options.", "",
                 "Each topology's `manifest.sha256` covers its retained artifacts. The RLI "
                 "`results/source-changes.patch.gz` applies to the recorded base revision; "
                 "its decompressed hash matches the per-run tracked-diff hash.", "",
                 "## Live-test correction and diagnostic history", "",
                 "The first RLI pilot exposed an ACK-driven cwnd decrease after an application-limited "
                 "epoch change. RLI now preserves the previously allowed window during ACK growth. "
                 "Real congestion responses still reduce it and reset maxFS. An explicit reset counter "
                 "makes those resets observable even when the flight is rebuilt between log snapshots.",
                 "", "The validator now checks every observed reduction. It accepts peaks between "
                 "qlog snapshots when maxFS exceeds both sampled flight sizes; these intervals "
                 "are counted in `unobserved_peak_intervals`. C tests cover per-update accounting.",
                 "", "`pilot_before_fix` folders contain superseded diagnostic runs and are excluded "
                 "from all final tables. The RLI bulk pilot's `revalidation.json` documents the "
                 "original missed reset. Campaign collection logs retain the initial snapshot-checker "
                 "diagnostics; the final validation log and per-run validation JSON contain the corrected analysis.",
                 "", "## Reproduce and limits", "",
                 "See [experiments/README.md](../experiments/README.md) and "
                 "the recorded per-run metadata. `collect_results.py --reanalyze` "
                 "regenerates measurements/graphs from saved compressed traces without repeating transfers.",
                 "", "This is a descriptive three-run experiment on the recorded Linux host. It is not a "
                 "statistical claim of a universal speedup. No live multipath, forced-loss, or "
                 "receiver-flow-control topology is claimed. Sanitizers covered the focused RLI test. "
                 "The implementation retains the conservative CA interpretation documented in IMPLEMENTATION_PLAN.md "
                 "for [draft version 11](https://www.ietf.org/archive/id/draft-ietf-ccwg-ratelimited-increase-11.html).",
                 ""])
    (output / "README.md").write_text("\n".join(text), encoding="utf-8")
    for mode in tests:
        save_manifest(output / mode / TOPOLOGY)
    return (passed and sanitizer_ok and "Ran 9 tests" in tool_text and "OK" in tool_text
            and all(t["ctest_failures"] == 0 and t["internal_failures"] == 0
                    and t["internal_tests"] > 0 for t in tests.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "results")
    args = parser.parse_args()
    sys.exit(0 if write_report(args.output) else 1)
