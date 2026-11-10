#!/usr/bin/env python3
"""Summarize and plot the supplementary two-flow dumbbell measurements."""
import csv
import json
from pathlib import Path
import statistics
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent))
from plot_cwnd import parse_qlog
from experiments.validate_rli import validate
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

data = json.loads((OUT / "dumbbell/summary.json").read_text())
runs = data["runs"]
assert len(runs) == 6 and {(r["mode"], r["repetition"]) for r in runs} == {
    (mode, repetition) for mode in ("baseline", "rli") for repetition in (1, 2, 3)}
plots = OUT / "plots/dumbbell"
plots.mkdir(exist_ok=True)
csv_rows, validation_rows = [], []
for run in runs:
    fig, axis = plt.subplots(figsize=(11, 5))
    for flow in run["flows"]:
        samples = parse_qlog(OUT / flow["qlog"])
        if run["mode"] == "rli":
            errors, counters = validate(samples)
            assert not errors, errors
            validation_rows.append({"mode": run["mode"], "repetition": run["repetition"],
                "flow": flow["flow"], "result": "PASS", **counters})
        assert flow["received_bytes"] >= 20 * 1024 * 1024
        initial = samples[0]["time"]
        axis.plot([sample["time"] - initial for sample in samples],
                  [sample["cwnd"] / 1024 for sample in samples],
                  label=f'Flow {flow["flow"]} cwnd ({flow["throughput_mbps"]:.2f} Mbit/s)', linewidth=1.1)
    axis.set(xlabel="Time since first metric (seconds)", ylabel="Congestion window (KiB)",
             title=f'Two concurrent bulk flows: {run["mode"]}, repetition {run["repetition"]}')
    axis.legend()
    axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(plots / f'{run["mode"]}-{run["repetition"]}.png', dpi=180)
    plt.close(fig)
    csv_rows.append({"mode": run["mode"], "repetition": run["repetition"],
        "flow_1_mbps": run["flows"][0]["throughput_mbps"],
        "flow_2_mbps": run["flows"][1]["throughput_mbps"],
        "wall_throughput_mbps": run["combined_wall_throughput_mbps"],
        "jain_fairness": run["jain_fairness"],
        "retransmissions": sum(f["retransmissions"] for f in run["flows"])})
with (OUT / "dumbbell/measurements.csv").open("w", newline="") as file:
    writer = csv.DictWriter(file, csv_rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(csv_rows)
(OUT / "dumbbell/validation.json").write_text(json.dumps(validation_rows, indent=2) + "\n")
aggregate = {}
for mode in ("baseline", "rli"):
    selected = [row for row in csv_rows if row["mode"] == mode]
    aggregate[mode] = {metric: statistics.mean(row[metric] for row in selected)
        for metric in ("wall_throughput_mbps", "jain_fairness", "retransmissions")}
aggregate["throughput_change_percent"] = (
    aggregate["rli"]["wall_throughput_mbps"] / aggregate["baseline"]["wall_throughput_mbps"] - 1) * 100
(OUT / "dumbbell/aggregate.json").write_text(json.dumps(aggregate, indent=2) + "\n")
tex = [r"% Generated from the six supplementary dumbbell experiments.",
       r"\begin{table}[H]\centering\small",
       r"\begin{tabular}{llrrrrr}\toprule",
       r"Run & Mode & Flow 1 & Flow 2 & Combined & Jain index & Retrans.\\",
       r" & & (Mbit/s) & (Mbit/s) & (Mbit/s) & & \\\midrule"]
for row in sorted(csv_rows, key=lambda row: (row["repetition"], row["mode"])):
    tex.append(f'{row["repetition"]} & {row["mode"]} & {row["flow_1_mbps"]:.3f} & {row["flow_2_mbps"]:.3f} & '
               f'{row["wall_throughput_mbps"]:.3f} & {row["jain_fairness"]:.3f} & {row["retransmissions"]} ' + r"\\")
tex += [r"\bottomrule\end{tabular}",
        r"\caption{Two-flow dumbbell results. Flow rates use each server's connection CSV. Combined rate uses both byte counts divided by the common client wall time, including connection completion.}\end{table}",
        "The mean combined wall-time rates were " + f'{aggregate["baseline"]["wall_throughput_mbps"]:.3f}' +
        " Mbit/s for baseline and " + f'{aggregate["rli"]["wall_throughput_mbps"]:.3f}' +
        " Mbit/s for RLI (" + f'{aggregate["throughput_change_percent"]:+.2f}' + r"\%). " +
        "The combined wall interval starts at client launch and ends when both clients exit; it excludes the later wait for server shutdown. " +
        "The per-flow CSV rates use each server's own connection interval, so their sum is not the combined wall-time rate. " +
        "The Jain index uses the two per-connection rates; values closer to one indicate a more even split. " +
        "It describes this pair of flows over their connection lifetimes, not instantaneous fairness or fairness against other congestion algorithms."]
(OUT / "generated-dumbbell.tex").write_text("\n".join(tex) + "\n")
figures = []
for repetition in (1, 2, 3):
    prefix = r"\clearpage" if figures else ""
    figures.append(prefix + r"\subsection{Two-flow dumbbell, repetition " + str(repetition) + "}")
    for mode in ("baseline", "rli"):
        figures += [r"\begin{figure}[H]\centering",
                    r"\includegraphics[width=0.92\textwidth]{plots/dumbbell/" + f"{mode}-{repetition}.png" + "}",
                    r"\caption{" + mode.capitalize() + ": both client/server pairs transfer 20 MiB concurrently over the shared bottleneck.}" + r"\end{figure}"]
    figures.append("The two lines show the congestion windows of competing flows. Window height and temporary differences in allocation should be interpreted alongside the transfer rates and Jain index.")
(OUT / "generated-dumbbell-figures.tex").write_text("\n".join(figures) + "\n")
print(json.dumps(aggregate, indent=2))
print("PASS: six two-flow plots, twelve complete transfers, and six RLI trace checks")
