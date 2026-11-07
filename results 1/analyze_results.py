#!/usr/bin/env python3
"""Derive all reported numbers from the twelve fresh experiment traces."""
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT))
from plot_cwnd import parse_qlog
from experiments.validate_rli import summarize, validate

for name in ("plots", "comparisons", "validation"):
    (OUT / name).mkdir(exist_ok=True)


def esc(text):
    return str(text).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&").replace("#", r"\#")


records = []
for workload in ("rate-limited", "bulk"):
    for repetition in (1, 2, 3):
        pair = {}
        for mode in ("baseline", "rli"):
            directory = OUT / "runs" / workload / mode / f"run-{repetition}"
            paths = list(directory.glob("*.server.qlog"))
            assert len(paths) == 1, f"Expected exactly one sender qlog in {directory}"
            qlog = paths[0]
            # Ensure the entire qlog is valid JSON, not just parseable metric lines.
            json.loads(qlog.read_text())
            samples = parse_qlog(qlog)
            assert samples and len({s['path_id'] for s in samples}) == 1
            if mode == "rli":
                # The logger's cap flag starts at zero and is emitted on change.
                # Include its initial zero interval in a whole-trace fraction.
                for sample in samples:
                    if sample["rli_capped"] is None:
                        sample["rli_capped"] = 0.0
            metrics = summarize(samples)
            with (directory / "server-performance.csv").open() as file:
                perf_rows = list(csv.DictReader(file, skipinitialspace=True))
            assert len(perf_rows) == 1
            perf = {k.strip(): v.strip() for k, v in perf_rows[0].items()}
            assert int(perf["is_client"]) == 0 and int(perf["ccalgo"]) == 2
            expected = 480000 if workload == "rate-limited" else 20 * 1024 * 1024
            assert int(perf["Sent"]) >= expected, "Transfer incomplete"
            throughput = float(perf["Mpbs_S"])
            assert abs(throughput - int(perf["Sent"]) * 8 / float(perf["Duration"]) / 1e6) < 0.00001
            errors, counters = ([], {})
            if mode == "rli":
                errors, counters = validate(samples, require_cap=workload == "rate-limited",
                                             expect_reduction=workload == "bulk")
                assert not errors, errors
                (OUT / "validation" / f"{workload}-{mode}-{repetition}.txt").write_text(
                    "PASS: observed qlog invariants\n" + json.dumps(counters, indent=2) + "\n")
            else:
                assert all(s["rli_max_flight_size"] is None for s in samples), "Baseline unexpectedly reports RLI"
            if workload == "rate-limited":
                assert metrics["cwnd_final_bytes"] == (15360 if mode == "baseline" else 30720)
                if mode == "rli":
                    assert all(s["rli_max_flight_size"] == 15360 for s in samples
                               if s["rli_max_flight_size"] is not None)
            record = dict(workload=workload, mode=mode, repetition=repetition,
                          throughput_mbps=throughput,
                          application_bytes_sent=int(perf["Sent"]), retransmissions=int(perf["retrans."]),
                          final_cc_state=int(perf["cc_state"]), smoothed_rtt_us=int(perf["srtt"]),
                          min_rtt_us=int(perf["minrtt"]),
                          spurious_retransmissions=int(perf["spurious"]), samples=len(samples),
                          qlog=str(qlog.relative_to(OUT)), **metrics)
            # Distinguish performance-CSV connection time from qlog metric time.
            record["connection_duration_seconds"] = float(perf["Duration"])
            record["validation"] = "PASS" if mode == "rli" else "baseline / not applicable"
            record["counters"] = counters
            png = directory / f"cubic-{mode}-{workload}.png"
            assert png.stat().st_size > 5000
            shutil.copy2(png, OUT / "plots" / f"{workload}-{mode}-{repetition}.png")
            records.append(record)
            pair[mode] = record
        baseline_qlog = OUT / pair["baseline"]["qlog"]
        rli_qlog = OUT / pair["rli"]["qlog"]
        command = [sys.executable, str(ROOT / "experiments/validate_rli.py"), "compare",
                   str(baseline_qlog), str(rli_qlog), "--workload", workload,
                   "--output", str(OUT / "comparisons" / f"{workload}-{repetition}.csv")]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        (OUT / "comparisons" / f"{workload}-{repetition}.log").write_text(result.stdout +
            "\nReport analysis includes the logger's initial zero cap interval when calculating rli_capped_time_fraction. The report CSV supersedes that field in the raw tool output.\n")
        metric_names = list(summarize(parse_qlog(baseline_qlog)))
        with (OUT / "comparisons" / f"{workload}-{repetition}.csv").open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["metric", "baseline", "rli", "delta", "rli_change_percent"])
            for metric in metric_names:
                b, r = pair["baseline"][metric], pair["rli"][metric]
                delta = r - b if b is not None and r is not None else None
                percent = delta / b * 100 if delta is not None and b != 0 else None
                writer.writerow([metric, b, r, delta, percent])

fields = [k for k in records[0] if k != "counters"]
with (OUT / "measurements.csv").open("w", newline="") as file:
    writer = csv.DictWriter(file, fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)

groups = {}
for workload in ("rate-limited", "bulk"):
    groups[workload] = {}
    for mode in ("baseline", "rli"):
        rows = [r for r in records if r["workload"] == workload and r["mode"] == mode]
        metrics = {}
        for key in ("throughput_mbps", "connection_duration_seconds", "cwnd_time_average_bytes",
                    "cwnd_final_bytes", "cwnd_max_bytes", "flight_max_bytes", "retransmissions"):
            values = [r[key] for r in rows]
            metrics[key] = {"mean": statistics.mean(values), "sample_stddev": statistics.stdev(values),
                            "minimum": min(values), "maximum": max(values)}
        groups[workload][mode] = metrics
    for metric in ("throughput_mbps", "cwnd_time_average_bytes", "cwnd_final_bytes"):
        baseline = groups[workload]["baseline"][metric]["mean"]
        rli = groups[workload]["rli"][metric]["mean"]
        groups[workload][metric + "_change_percent"] = (rli / baseline - 1) * 100

tests = json.loads((OUT / "tests/status.json").read_text())
assert {t["name"] for t in tests} == {"baseline-configure", "baseline-build", "baseline-ctest",
                                     "rli-build", "rli-ctest", "cubic-rli"}
assert all(t["exit_code"] == 0 for t in tests)
suite_counts = {}
for mode in ("baseline", "rli"):
    ctest_log = (OUT / "tests" / f"{mode}-ctest.log").read_text()
    assert "100% tests passed, 0 tests failed out of 2" in ctest_log
    detailed = (OUT / "tests" / f"{mode}-Testing/Temporary/LastTest.log").read_text()
    suite_counts[mode] = re.findall(r"Tried (\d+) tests, (\d+) fails", detailed)
    assert suite_counts[mode] and all(int(fails) == 0 for _, fails in suite_counts[mode])

summary = {"records": records, "groups": groups, "suite_counts": suite_counts,
           "experiment_count": len(records), "verdict": "PASS for the tested conditions",
           "scope": "Two workloads, three repetitions each, two separately built source revisions; 20 Mbit/s bottleneck and ~50 ms base RTT. No universal throughput gain is claimed."}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

# Plot a compact comparison independently of the twelve detailed traces.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), layout="constrained")
for axis, workload, metric, scale, title, ylabel in (
    (axes[0], "rate-limited", "cwnd_time_average_bytes", 1024, "Rate-limited: permitted window", "Mean time-weighted cwnd (KiB)"),
    (axes[1], "bulk", "throughput_mbps", 1, "Bulk control: transfer rate", "Server throughput (Mbit/s)"),
):
    means = [groups[workload][m][metric]["mean"] / scale for m in ("baseline", "rli")]
    stds = [groups[workload][m][metric]["sample_stddev"] / scale for m in ("baseline", "rli")]
    axis.bar(["Baseline", "RLI"], means, yerr=stds, capsize=5, color=["#406882", "#2e8b57"])
    for x, value in enumerate(means):
        axis.text(x, value * 1.03, f"{value:.3f}", ha="center", fontsize=10)
    axis.set_ylim(0, max(means) * 1.2)
    axis.set(title=title, ylabel=ylabel)
    axis.grid(axis="y", alpha=.2)
fig.savefig(OUT / "plots/overview.png", dpi=180)
plt.close(fig)

tex = [r"% Generated exclusively from the fresh logs by analyze_results.py."]
env = json.loads((OUT / "environment.json").read_text())
for name, key in (("BaselineCommit", "baseline_commit"), ("ImplementationCommit", "implementation_commit")):
    tex.append("\\newcommand{\\" + name + "}{" + env[key][:12] + "}")
tex += [r"\newcommand{\WindowChange}{" + f'{groups["rate-limited"]["cwnd_time_average_bytes_change_percent"]:.2f}' + "}",
        r"\newcommand{\BulkChange}{" + f'{groups["bulk"]["throughput_mbps_change_percent"]:.2f}' + "}",
        r"\newcommand{\ObservedRateFlight}{" + str(int(groups["rate-limited"]["rli"]["flight_max_bytes"]["maximum"])) + "}"]
for prefix, workload in (("Rate", "rate-limited"), ("Bulk", "bulk")):
    for mode, label in (("baseline", "Baseline"), ("rli", "Rli")):
        for suffix, key, scale in (("Throughput", "throughput_mbps", 1),
                                   ("Cwnd", "cwnd_time_average_bytes", 1024)):
            tex.append("\\newcommand{\\" + prefix + label + suffix + "}{" +
                       f'{groups[workload][mode][key]["mean"] / scale:.3f}' + "}")
tex.append(r"\newcommand{\TestCountSummary}{" + "; ".join(
    mode + ": " + " + ".join(count for count, _ in suite_counts[mode]) + " subtests"
    for mode in ("baseline", "rli")) + "}")
(OUT / "generated-values.tex").write_text("\n".join(tex) + "\n")

tables = []
for workload in ("rate-limited", "bulk"):
    title = "Rate-limited" if workload == "rate-limited" else "Bulk control"
    tables += [r"\begin{table}[H]\centering\small",
               r"\begin{tabular}{llrrrrr}\toprule",
               r"Run & Mode & Final cwnd & Avg. cwnd & Rate & Time & Retrans.\\",
               r" & & (KiB) & (KiB) & (Mbit/s) & (s) & \\\midrule"]
    for row in [r for r in records if r["workload"] == workload]:
        tables.append(f'{row["repetition"]} & {row["mode"]} & {row["cwnd_final_bytes"]/1024:.2f} & '
                      f'{row["cwnd_time_average_bytes"]/1024:.2f} & {row["throughput_mbps"]:.3f} & '
                      f'{row["connection_duration_seconds"]:.3f} & {row["retransmissions"]} ' + r"\\")
    tables += [r"\bottomrule\end{tabular}",
               r"\caption{" + title + r" workload: fresh measured results. Time is connection duration from the performance CSV.}\end{table}"]
(OUT / "generated-tables.tex").write_text("\n".join(tables) + "\n")

figures = []
for workload in ("rate-limited", "bulk"):
    for repetition in (1, 2, 3):
        title = ("Rate-limited" if workload == "rate-limited" else "Bulk control") + f", repetition {repetition}"
        prefix = r"\clearpage" if figures else ""
        figures += [prefix + r"\subsection{" + title + "}"]
        for mode in ("baseline", "rli"):
            record = next(r for r in records if r["workload"] == workload and r["mode"] == mode and r["repetition"] == repetition)
            figures += [r"\begin{figure}[H]\centering",
                        r"\includegraphics[width=0.92\textwidth]{plots/" + f"{workload}-{mode}-{repetition}.png" + "}"]
            caption = (f'{mode.capitalize()}: final cwnd {record["cwnd_final_bytes"]/1024:.2f} KiB; '
                       f'time-weighted mean {record["cwnd_time_average_bytes"]/1024:.2f} KiB; '
                       f'throughput {record["throughput_mbps"]:.3f} Mbit/s.')
            figures += [r"\caption{" + caption + r"}\end{figure}"]
        explanation = ("These matched traces isolate rate-limited window growth. RLI permits bounded ACK-driven growth; application supply still controls throughput."
                       if workload == "rate-limited" else
                       "These matched traces test a continuously backlogged sender. Normal CUBIC growth and congestion responses dominate; compare measured throughput rather than window height alone.")
        figures.append(explanation)
(OUT / "generated-figures.tex").write_text("\n".join(figures) + "\n")

lines = ["# Fresh experiment summary", "", "All numbers below come from this folder's new runs, not the older Step 7 evidence.", "",
         "| Workload | Mean baseline throughput | Mean RLI throughput | Change | Mean cwnd change |",
         "|---|---:|---:|---:|---:|"]
for workload in groups:
    g = groups[workload]
    lines.append(f'| {workload} | {g["baseline"]["throughput_mbps"]["mean"]:.6f} Mbit/s | '
                 f'{g["rli"]["throughput_mbps"]["mean"]:.6f} Mbit/s | '
                 f'{g["throughput_mbps_change_percent"]:+.3f}% | {g["cwnd_time_average_bytes_change_percent"]:+.3f}% |')
lines += ["", "RLI passed all six trace validations; the rate-limited runs require an observed active cap, and the bulk runs require a visible cwnd reduction with maxFS reset.",
          "", "A larger permitted cwnd is a behavioral improvement for this workload, not proof of faster data delivery. Three local repeats do not establish statistical significance or general network performance.",
          "", "Exact per-run values are in measurements.csv; raw traces and performance logs are under runs/. Both source revisions passed all registered CTest suites."]
(OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
print(json.dumps({"verdict": summary["verdict"], "groups": groups, "suite_counts": suite_counts}, indent=2))
