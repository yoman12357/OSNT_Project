#!/usr/bin/env python3
"""Validate a fresh campaign and update the report's measured tables and figures."""

import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
SOURCE = OUT / "report-source"
sys.path.insert(0, str(ROOT))
from plot_cwnd import parse_qlog
from experiments.validate_rli import validate


def load(name):
    return json.loads((OUT / name).read_text())


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + "\n")


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def mean(rows, metric):
    return statistics.mean(row[metric] for row in rows)


def write_topology():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig, axis = plt.subplots(figsize=(12, 3.8))
    axis.set(xlim=(0, 12), ylim=(0, 3.8))
    axis.axis("off")
    nodes = ((.1, "Client\nrls-client\n10.10.1.2"),
             (3.25, "Router 1\nrls-r1\n10.10.12.1"),
             (6.4, "Router 2\nrls-r2\n10.10.12.2"),
             (9.55, "Server\nrls-server\n10.10.2.2"))
    for x, label in nodes:
        axis.add_patch(FancyBboxPatch((x, 1.25), 2.25, 1.05,
                                     boxstyle="round,pad=0.08", facecolor="#edf4f8",
                                     edgecolor="#173b59", linewidth=1.5))
        axis.text(x + 1.125, 1.775, label, ha="center", va="center", fontsize=11)
    for left, right, text in ((2.43, 3.17, "Access: 1000 Mbit/s\n5 ms per direction"),
                              (5.58, 6.32, "Core: 20 Mbit/s\n25 ms per direction"),
                              (8.73, 9.47, "Access: 1000 Mbit/s\n5 ms per direction")):
        axis.annotate("", (right, 1.775), (left, 1.775),
                      arrowprops={"arrowstyle": "<->", "color": "#173b59", "lw": 1.8})
        axis.text((left + right) / 2, 2.65, text, ha="center", va="center", fontsize=10)
    axis.text(6, .55, "Nominal base RTT = 2 × (5 + 25 + 5) = 70 ms\n"
              "Queue limit: 1000 packets on every shaped interface", ha="center", fontsize=11)
    fig.tight_layout()
    fig.savefig(SOURCE / "images/topology.png", dpi=200)
    plt.close(fig)


def refresh_report(summary, environment, supplement, aggregate):
    groups = summary["groups"]
    records = summary["records"]

    def selected(workload, mode):
        return [r for r in records if r["workload"] == workload and r["mode"] == mode]

    def rows(workload):
        lines = []
        for mode, label in (("baseline", "Original"), ("rli", "RLI")):
            items = selected(workload, mode)
            lines.append(f'{label} & {mean(items, "throughput_mbps"):.6f} & '
                         f'{mean(items, "cwnd_final_bytes")/1024:.2f} & '
                         f'{mean(items, "cwnd_time_average_bytes")/1024:.2f} & '
                         f'{mean(items, "smoothed_rtt_us")/1000:.3f} ' + r"\\")
        return "\n".join(lines)

    def figure(name, caption):
        return (r"\begin{center}" + "\n" +
                r"\includegraphics[width=\linewidth,height=.25\textheight,keepaspectratio]{images/native-" + name + ".png}\n" +
                r"\captionof{figure}{" + caption + "}\n" + r"\end{center}" + "\n")

    kernel = environment["uname"].split()[2]
    bulk_change = groups["bulk"]["throughput_mbps_change_percent"]
    paired = [selected("bulk", "rli")[i]["throughput_mbps"] -
              selected("bulk", "baseline")[i]["throughput_mbps"] for i in range(3)]
    flight = max(row["flight_max_bytes"] for row in selected("rate-limited", "rli"))
    retrans = sum(row["retransmissions"] for row in records)
    text = r"""\clearpage
\section*{5. Result and Analysis}
\label{sec:results}
\subsection*{5.1 Experimental parameters}

""" + f"The campaign ran on 10 November 2026, on Ubuntu 26.04 LTS with kernel \\texttt{{{kernel}}}. " + r"""GCC 15.2.0 and CMake 4.2.3 built both revisions \cite{ref13}.
Each access link has 1000 Mbit/s bandwidth and 5 ms delay in each direction.
The core link has 20 Mbit/s bandwidth and 25 ms delay in each direction.
Each shaped interface has a 1000-packet queue limit.
The nominal base RTT is 70 ms; the corresponding bandwidth-delay product is about 171 KiB.
Ping and qdisc checks verified both endpoint pairs.

Single-flow throughput uses the server's application bytes and connection duration.
Window and flight-size samples come from sender qlogs; final RTT comes from the server performance CSV.
Detailed graphs show repetition one. Tables use all three repetitions per mode.
The previous campaign is retained in a local backup, separate from these measurements.
\begin{center}
\includegraphics[width=\linewidth,height=.32\textheight,keepaspectratio]{images/native-overview.png}
\captionof{figure}{Fresh three-run means with sample standard-deviation bars for fixed-rate cwnd and bulk throughput.}
\end{center}

\subsection*{5.2 Fixed-rate workload}
\begin{center}\small\begin{tabular}{lrrrr}
Mode & Rate (Mbit/s) & Final cwnd (KiB) & Mean cwnd (KiB) & Final RTT (ms) \\ \hline
""" + rows("rate-limited") + "\n" + r"""\end{tabular}\end{center}

Each transfer delivers 480,000 bytes at an offered rate of approximately 192 kbit/s.
""" + f"The largest observed RLI flight is {flight:.0f} bytes. " + r"""The initialized 15 KiB maxFS sets the 30 KiB slow-start ceiling.
A larger permitted window does not increase the application's supply of data.
The experiment does not measure the completion time of a later burst.
""" + figure("rate-limited-baseline-1", "Original CUBIC, fresh fixed-rate repetition one.") + figure(
        "rate-limited-rli-1", "CUBIC with RLI, fresh fixed-rate repetition one.")
    text += r"""
\subsection*{5.3 Single-flow bulk transfers}
\begin{center}\small\begin{tabular}{lrrrr}
Mode & Rate (Mbit/s) & Final cwnd (KiB) & Mean cwnd (KiB) & Final RTT (ms) \\ \hline
""" + rows("bulk") + "\n" + r"""\end{tabular}\end{center}

""" + f"The observed mean throughput change is {bulk_change:+.2f}\\%.\n" + (
        "Paired RLI-minus-baseline differences are " + ", ".join(f"{x:+.3f}" for x in paired) + " Mbit/s.\n") + r"""Three repetitions describe this configuration; they do not establish a general performance gain or regression.
Final smoothed RTT is an endpoint statistic, not a direct queue-occupancy measurement.
""" + f"The twelve single-flow runs record {retrans} retransmissions in total.\n" + figure(
        "bulk-baseline-1", "Original CUBIC, fresh bulk repetition one.") + figure(
        "bulk-rli-1", "CUBIC with RLI, fresh bulk repetition one.")
    text += r"""
\subsection*{5.4 Two flows sharing the dumbbell}
\begin{center}\small\begin{tabular}{lrrr}
Mode & Combined Mbit/s & Jain index & Mean retransmissions \\ \hline
"""
    for mode, label in (("baseline", "Original"), ("rli", "RLI")):
        row = aggregate[mode]
        text += (f'{label} & {row["wall_throughput_mbps"]:.3f} & {row["jain_fairness"]:.5f} & '
                 f'{row["retransmissions"]:.1f} ' + r"\\" + "\n")
    text += r"""\end{tabular}\end{center}

Combined throughput uses the interval from client launch until both clients exit.
Each flow's connection rate uses its server's own connection interval.
The Jain index uses those two per-connection rates; it does not measure instantaneous fairness.
Both connections use the same algorithm in each experiment.
""" + f'The mean combined-throughput change is {aggregate["throughput_change_percent"]:+.2f}\\%.\n' + figure(
        "dumbbell-baseline-1", "Two competing flows with original CUBIC, fresh repetition one.") + figure(
        "dumbbell-rli-1", "Two competing flows with RLI, fresh repetition one.")
    text += r"""
\subsection*{5.5 Validation and comparison}

The current trace validator passes all six single-flow RLI traces and all six competing RLI connections.
Fixed-rate cases require an active cap. RLI bulk cases additionally require a window reduction and an observable flight-history reset.
Both builds pass their registered CTest suites. The separate cubic\_rli test also passes.
Reset counters make history resets observable even when flight size rebuilds between snapshots.

\begin{center}\small
\begin{tabularx}{\linewidth}{@{}p{0.25\linewidth}XX@{}}
\textbf{Aspect} & \textbf{Reference behavior} & \textbf{Observed result}\\ \hline
Application limitation & RFC 9438 suppresses growth in application-limited intervals \cite{ref2}. & RLI grows cwnd from 15 to 30 KiB at the slow-start cap.\\[3pt]
Growth bound & The RLI draft bounds increases using flight history \cite{ref1}. & Fixed-rate runs exercise the slow-start cap. The focused test checks the selected congestion-avoidance cap.\\[3pt]
Window retention & RFC 7661 considers windows that have not been exercised \cite{ref6}. & These experiments evaluate bounded growth, not window aging.\\
\end{tabularx}
\end{center}
\label{sec:results-end}
"""
    (SOURCE / "sections/05-results-analysis.tex").write_text(text)
    abstract = SOURCE / "sections/00-abstract.tex"
    abstract.write_text(abstract.read_text().replace("approximately 50 ms base round-trip time", "approximately 70 ms base round-trip time"))
    approach = SOURCE / "sections/03-proposed-approach.tex"
    old = approach.read_text()
    start = old.index("The main topology has two endpoint namespaces")
    end = old.index("\n\n", start)
    paragraph = r"""The main topology has two endpoint namespaces and two forwarding namespaces.
Each access link uses 1000 Mbit/s and 5 ms delay in each direction.
The core link uses 20 Mbit/s and 25 ms delay in each direction.
All shaped interfaces have a 1000-packet queue limit.
The nominal base RTT is 2 times (5 + 25 + 5), or 70 ms.
The supplementary dumbbell adds a second client/server pair with identical access-link settings.
Each supplementary run starts both transfers together \cite{ref12,ref13}."""
    approach.write_text(old[:start] + paragraph + old[end:])
    appendix = r"""\clearpage
\section*{Appendix A. Run records}
\label{sec:appendix}
\begin{center}\small\begin{tabular}{lrrrrr}
Workload & Mode & Run & Mbit/s & Duration (s) & Final cwnd (KiB) \\ \hline
"""
    for row in records:
        appendix += (f'{row["workload"]} & {row["mode"]} & {row["repetition"]} & '
                     f'{row["throughput_mbps"]:.6f} & {row["connection_duration_seconds"]:.6f} & '
                     f'{row["cwnd_final_bytes"]/1024:.2f} ' + r"\\" + "\n")
    appendix += r"""\end{tabular}\end{center}
\subsection*{A.1 Source and trace records}
""" + f'The original build uses commit \\texttt{{{environment["baseline_commit"][:8]}}}.\n' + (
        f'The RLI build uses commit \\texttt{{{environment["implementation_commit"][:8]}}}.\n') + r"""Topology and analysis changes were uncommitted during this campaign.
The environment record saves executable and topology-script hashes.
The raw archive contains all 24 connections' qlogs and performance logs.
Each main run records the actual source revision in provenance.txt.
The supplementary records are under \path{dumbbell/} \cite{ref13}.
\label{sec:appendix-end}
"""
    (SOURCE / "sections/08-appendix.tex").write_text(appendix)
    references = SOURCE / "sections/07-references.tex"
    lines = references.read_text().splitlines()
    lines = [r"\bibitem{ref13} OSNT Project. Ubuntu network-namespace campaign, 10 November 2026. The local \path{results/} bundle contains source identifiers, binary hashes, measurements, figures, and raw qlogs. The previous campaign is retained separately. \url{https://github.com/yoman12357/OSNT_Project}" if line.startswith(r"\bibitem{ref13}") else line for line in lines]
    references.write_text("\n".join(lines) + "\n")
    main = SOURCE / "main.tex"
    main.write_text(main.read_text().replace("9 November 2026", "10 November 2026"))
    for name in ("overview", "rate-limited-baseline-1", "rate-limited-rli-1", "bulk-baseline-1", "bulk-rli-1"):
        shutil.copy2(OUT / "plots" / (name + ".png"), SOURCE / "images" / ("native-" + name + ".png"))
    for mode in ("baseline", "rli"):
        shutil.copy2(OUT / "plots/dumbbell" / (mode + "-1.png"), SOURCE / "images" / ("native-dumbbell-" + mode + "-1.png"))
    for name in ("environment.json", "measurements.csv"):
        shutil.copy2(OUT / name, SOURCE / "data" / name)
    shutil.copy2(OUT / "dumbbell/measurements.csv", SOURCE / "data/dumbbell-measurements.csv")
    write_topology()


def refresh_readme(summary, environment, aggregate):
    groups = summary["groups"]
    text = """# Rate-limited CUBIC: current results

Project #16. Fresh Linux campaign: 10 November 2026.

Open [Final report.pdf](Final%20report.pdf). Its matching source is
[report-source/main.tex](report-source/main.tex).

## Network configuration

Both outer access links use **1000 Mbit/s and 5 ms per direction**.
The shared core uses **20 Mbit/s and 25 ms per direction**.
Every shaped interface has a 1000-packet queue limit.
The nominal base RTT is 2 * (5 + 25 + 5) = **70 ms**.
Topology logs include connectivity tests and each interface's actual qdisc.

The single-flow topology uses four namespaces. The competing-flow topology
uses six namespaces, with identical settings on both pairs' access links.

## Builds and tests

""" + f'Baseline source: `{environment["baseline_commit"]}`.\n\n' + (
        f'RLI source: `{environment["implementation_commit"]}`.\n\n') + """Both versions were rebuilt separately. Both passed their two registered CTest
suites. Baseline ran 562 picoquic and 105 picohttp subtests; RLI ran 563 and 105.
The separate `cubic_rli` test and nine Python result-tool tests also passed.
These are registered regression suites, not every optional stress or fuzz test.

The campaign contains twelve single-flow experiments and six two-flow
experiments: **24 completed connections**. Each workload/mode has three repeats.
All twelve RLI sender traces pass the current validator, including reset checks.
Limited runs require an active cap; main RLI bulk runs also require a reduction
and an observable history reset. These checks do not certify every protocol state.

## Measured results

| Workload | Baseline throughput | RLI throughput | Observed change |
|---|---:|---:|---:|
"""
    for workload in ("rate-limited", "bulk"):
        group = groups[workload]
        text += (f'| {workload} | {group["baseline"]["throughput_mbps"]["mean"]:.6f} Mbit/s | '
                 f'{group["rli"]["throughput_mbps"]["mean"]:.6f} Mbit/s | '
                 f'{group["throughput_mbps_change_percent"]:+.3f}% |\n')
    text += (f'| Two competing flows, combined wall rate | {aggregate["baseline"]["wall_throughput_mbps"]:.6f} Mbit/s | '
             f'{aggregate["rli"]["wall_throughput_mbps"]:.6f} Mbit/s | {aggregate["throughput_change_percent"]:+.3f}% |\n')
    text += """
Fixed-rate final cwnd is 15 KiB for baseline and 30 KiB for RLI.
The application still supplies only 480,000 bytes at about 192 kbit/s.
The initialized 15 KiB maxFS permits a bounded 30 KiB slow-start window.
A larger window is not a doubling of throughput.

Three repeats support descriptive comparisons, not general or statistically
proven performance gains. Do not attribute differences from the previous
campaign solely to access-link shaping: the RLI source revision also changed.
Source identifiers and executable hashes distinguish the campaigns.

## Graphs and evidence

- `plots/rate-limited-{baseline,rli}-{1,2,3}.png`: six fixed-rate graphs.
- `plots/bulk-{baseline,rli}-{1,2,3}.png`: six bulk graphs.
- `plots/overview.png`: three-run means and sample standard deviations.
- `plots/dumbbell/{baseline,rli}-{1,2,3}.png`: six competing-flow graphs.
- `raw-evidence.tar.gz`: lossless qlogs and performance logs for this campaign.
- `measurements.csv`, `summary.json`, `SUMMARY.md`: main measurements.
- `dumbbell/`: competing-flow measurements and validation.
- `tests/`: fresh build, regression, focused-test, and Python-tool logs.
- `campaign-checks.json`: source, binary, topology, and campaign audit.
- `current-validator-checks.json`: current per-trace invariant checks.
- `final-report-checks.json`: checks for the regenerated final PDF.
- `SHA256SUMS`: current portable distribution checksums.

The earlier distribution and topology are backed up under `archive/`.
The exact backup path and digest are recorded in `campaign-checks.json`.
The backup is ignored by Git and remains local. Historical report editions,
their checks, `SHA256SUMS.original`, and `evaluated-tools/` are retained for
reference. Only `Final report.pdf` and `report-source/` describe this campaign.

## Reproduce

Preserve the current evidence before another run. Main collection archives
existing `runs/`; competing-flow collection refuses to overwrite its raw runs.
Use the Linux dependencies and namespace commands in `../experiments/README.md`.

```bash
.venv/bin/python results/run_tests.py
unshare --user --map-root-user --net --mount bash results/run_experiments.sh
.venv/bin/python results/analyze_results.py
unshare --user --map-root-user --net --mount sh -c \\
  'mount --make-rprivate /; mount -t tmpfs tmpfs /run; mkdir -p /run/netns; exec .venv/bin/python results/run_dumbbell.py'
.venv/bin/python results/analyze_dumbbell.py
.venv/bin/python results/refresh_campaign.py --previous-archive <path-to-backup.tar.gz>
.venv/bin/python results/build_final_report.py
.venv/bin/python results/refresh_campaign.py --finalize
.venv/bin/python results/check_bundle.py
```

To restore raw traces after cloning, run `results/package_evidence.py --unpack`.
It refuses to overwrite differing local evidence. To check distribution hashes,
run `sha256sum --check --quiet SHA256SUMS` inside this directory.

No runtime C/C++ source was edited for this campaign. The report documents the
selected congestion-avoidance interpretation and the limits of the evaluation.
Commit and push remain with the repository owner.

## Additional same-connection CA test

The later [three-phase experiment](ca-rate-limited/README.md) is saved separately.
It adds three baseline and three RLI connections, plus an excluded pilot.
All matched transfers and observed checks pass, but no cap activates in the limited CA intervals.
Its cap-coverage verdict is incomplete. The final PDF above does not include this additional test.
"""
    (OUT / "README.md").write_text(text)


def finalize(visual_reviewed):
    pdf = load("final-report-checks.json")
    assert pdf["pass"], "Final report checks did not pass"
    if visual_reviewed:
        pdf["visual_review_completed"] = True
        save("final-report-checks.json", pdf)
    subprocess.run([sys.executable, str(OUT / "check_bundle.py"), "--write-audit"], check=True)
    files = [p for p in sorted(OUT.rglob("*")) if p.is_file()
             and p.name != "SHA256SUMS" and "__pycache__" not in p.parts]
    names = [str(p.relative_to(ROOT)) for p in files]
    result = subprocess.run(["git", "check-ignore", "--stdin", "-z"], cwd=ROOT,
                            input=("\0".join(names) + "\0").encode(), capture_output=True)
    assert result.returncode in (0, 1)
    ignored = set(result.stdout.decode().strip("\0").split("\0"))
    files = [p for p in files if str(p.relative_to(ROOT)) not in ignored]
    (OUT / "SHA256SUMS").write_text("\n".join(f"{sha(p)}  {p.relative_to(OUT)}" for p in files) + "\n")
    subprocess.run([sys.executable, str(OUT / "check_bundle.py")], check=True)
    print(f"PASS: {len(files)} distribution files match the current manifest")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-archive", type=Path)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--visual-reviewed", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        finalize(args.visual_reviewed)
        return
    assert args.previous_archive is not None, "Supply --previous-archive for campaign refresh"
    args.previous_archive = args.previous_archive.resolve()
    assert args.previous_archive.is_file(), "Previous campaign backup is missing"
    environment = load("environment.json")
    summary = load("summary.json")
    supplement = load("dumbbell/summary.json")["runs"]
    aggregate = load("dumbbell/aggregate.json")
    tests = load("tests/status.json")
    tool_tests = (OUT / "tests/result-tools.log").read_text()
    assert len(summary["records"]) == 12 and len(supplement) == 6
    assert len(tests) == 6 and all(row["exit_code"] == 0 for row in tests)
    assert "Ran 9 tests" in tool_tests and "\nOK\n" in tool_tests
    assert environment["topology"]["nominal_base_rtt_ms"] == 70
    core = ["picoquic/cubic.c", "picoquic/sender.c", "picoquic/picoquic_internal.h",
            "picoquic/logwriter.c", "loglib/qlog.c", "loglib/qlog_fns.c",
            "picoquictest/congestion_test.c"]
    for name in core:
        assert (ROOT / name).read_bytes() == subprocess.check_output(
            ["git", "show", environment["implementation_commit"] + ":" + name], cwd=ROOT)
    records = []
    for row in summary["records"]:
        directory = (OUT / row["qlog"]).parent
        provenance = dict(line.split("=", 1) for line in (directory / "provenance.txt").read_text().splitlines())
        metadata = dict(line.split("=", 1) for line in (directory / "metadata.txt").read_text().splitlines())
        mode = row["mode"]
        assert provenance["tested_source_commit"] == environment["baseline_commit" if mode == "baseline" else "implementation_commit"]
        assert metadata["demo_sha256"] == environment[mode + "_binary_sha256"]
        if mode == "rli":
            errors, counters = validate(parse_qlog(OUT / row["qlog"]),
                require_cap=row["workload"] == "rate-limited", expect_reduction=row["workload"] == "bulk")
            records.append({"trace": row["qlog"], "errors": errors, "counters": counters})
    for run in supplement:
        assert run["binary_sha256"] == environment[run["mode"] + "_binary_sha256"]
        for flow in run["flows"]:
            assert flow["sent_bytes"] >= 20 * 1024 * 1024 and flow["received_bytes"] >= 20 * 1024 * 1024
            if run["mode"] == "rli":
                errors, counters = validate(parse_qlog(OUT / flow["qlog"]))
                records.append({"trace": flow["qlog"], "errors": errors, "counters": counters})
    strict = {"validator": "experiments/validate_rli.py", "traces_checked": len(records),
              "traces_passing": sum(not r["errors"] for r in records),
              "traces_with_errors": sum(bool(r["errors"]) for r in records),
              "scope": "Current validator on the fresh 70 ms campaign, including observable reset-counter checks.",
              "records": records}
    save("current-validator-checks.json", strict)
    assert strict["traces_checked"] == 12 and strict["traces_with_errors"] == 0, strict
    for name, expected in environment["topology_sha256"].items():
        assert sha(ROOT / name) == expected, f"Topology changed after testing: {name}"
    for mode, binary in (("baseline", ROOT / ".local-deps/report-baseline/build/picoquicdemo"),
                         ("rli", ROOT / "build/picoquicdemo")):
        assert sha(binary) == environment[mode + "_binary_sha256"]
    refresh_report(summary, environment, supplement, aggregate)
    refresh_readme(summary, environment, aggregate)
    for name in ("runs", "dumbbell/baseline", "dumbbell/rli"):
        for directory in sorted({p.parent for p in (OUT / name).rglob("*.server.qlog")}):
            manifest = directory / "manifest.sha256"
            if manifest.exists() and not (directory / "original-manifest.sha256").exists():
                manifest.rename(directory / "original-manifest.sha256")
            lines = [f"{sha(p)}  {p.name}" for p in sorted(directory.iterdir()) if p.is_file() and p.name != "manifest.sha256"]
            manifest.write_text("\n".join(lines) + "\n")
    subprocess.run([sys.executable, str(OUT / "package_evidence.py")], check=True)
    checks = {"audit_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "pass": True, "main_experiments": 12, "supplementary_experiments": 6,
              "completed_connections": 24, "current_validator_traces_passed": 12,
              "both_registered_ctest_suites_pass": True, "focused_cubic_rli_pass": True,
              "python_result_tool_tests_passed": 9,
              "runtime_source_matches_implementation_commit": True,
              "implementation_commit": environment["implementation_commit"],
              "topology": environment["topology"], "plots": len(list((OUT / "plots").rglob("*.png"))),
              "raw_archive_sha256": sha(OUT / "raw-evidence.tar.gz"),
              "previous_campaign_backup": str(args.previous_archive.relative_to(ROOT)),
              "previous_campaign_backup_sha256": sha(args.previous_archive),
              "limitations": "Three repetitions and one topology. No universal performance gain or full standards certification is claimed."}
    save("campaign-checks.json", checks)
    shutil.copy2(OUT / "campaign-checks.json", SOURCE / "data/verification.json")
    save("verification.json", checks)
    patch = subprocess.check_output(["git", "diff", environment["baseline_commit"],
        environment["implementation_commit"], "--", *core], cwd=ROOT)
    (OUT / "implementation.patch").write_bytes(patch)
    (OUT / "changed-files.txt").write_bytes(subprocess.check_output(["git", "diff", "--stat",
        environment["baseline_commit"], environment["implementation_commit"], "--", *core], cwd=ROOT))
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
