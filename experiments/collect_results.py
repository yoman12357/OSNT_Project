#!/usr/bin/env python3
"""Collect paired, reproducible Linux netns experiments in one results tree.

Requires two already built checkouts: the actual pre-RLI revision and the
RLI implementation. This script never checks out or edits either source tree.
"""

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from plot_cwnd import METRICS, parse_qlog, plot_metrics
from experiments.validate_rli import summarize, validate

TOPOLOGY = "dumbbell_access1000mbps_5ms_core20mbps_25ms"
NAMESPACES = ("rls-client", "rls-r1", "rls-r2", "rls-server")
SCENARIOS = {"rate-limited": "=rli:s20:n400:1200:G20:I1200;",
             "bulk": "/file_20M.bin"}


def digest(path):
    sha = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def capture(command, cwd=None):
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def logged(command, log_path, cwd=None, timeout=120):
    with log_path.open("w", encoding="utf-8") as output:
        output.write("$ " + shlex.join(map(str, command)) + "\n")
        output.flush()
        subprocess.run(command, cwd=cwd, stdout=output,
                       stderr=subprocess.STDOUT, check=True, timeout=timeout)


def provenance(source):
    files = capture(["git", "ls-files"], source).splitlines()
    hashes = {name: digest(source / name) for name in files
              if (source / name).is_file()}
    diff = subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=source)
    return {"commit": capture(["git", "rev-parse", "HEAD"], source),
            "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
            "binary_sha256": digest(source / "build/picoquicdemo"),
            "tracked_file_sha256": hashes,
            "kernel": platform.release(), "platform": platform.platform(),
            "python": sys.version, "source_root": str(source)}


def perf_record(path):
    with path.open(encoding="utf-8") as source:
        records = list(csv.DictReader(source, skipinitialspace=True))
    if len(records) != 1:
        raise RuntimeError(f"Expected one connection in {path}: {len(records)}")
    return {key.strip(): value.strip() for key, value in records[0].items()}


def export_samples(samples, path):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=("time", "path_id", *METRICS))
        writer.writeheader()
        writer.writerows(samples)


def save_manifest(root):
    entries = [f"{digest(path)}  {path.relative_to(root).as_posix()}"
               for path in sorted(root.rglob("*"))
               if path.is_file() and path.name != "manifest.sha256"]
    (root / "manifest.sha256").write_text("\n".join(entries) + "\n", encoding="utf-8")


def analyze_run(folders, mode, workload, repetition):
    run_id = f"run_{repetition:02d}"
    log_dir, result_dir = folders["logs"], folders["results"]
    summary_path = result_dir / "summary.json"
    sender_logs = list(log_dir.glob("*.server.qlog")) + list(log_dir.glob("*.server.qlog.gz"))
    if len(sender_logs) != 1:
        raise RuntimeError(f"Expected one sender qlog, found {len(sender_logs)}")
    samples = parse_qlog(sender_logs[0])
    if not samples:
        raise RuntimeError("Sender qlog has no congestion metrics")
    export_samples(samples, result_dir / "congestion-metrics.csv")
    plot_metrics(samples, str(folders["graphs"] / "congestion-window.png"))
    server_perf = perf_record(result_dir / "server-performance.csv")
    client_perf = perf_record(result_dir / "client-performance.csv")
    errors, counters = (validate(samples, require_cap=workload == "rate-limited",
                                 expect_reduction=workload == "bulk")
                        if mode == "rli_implemented" else ([], {}))
    received = int(client_perf["Received"])
    minimum = 400 * 1200 if workload == "rate-limited" else 20 * 1024 * 1024
    if received < minimum:
        errors.append(f"Incomplete transfer: {received} < {minimum} bytes")
    validation = {"status": "FAIL" if errors else "PASS", "errors": errors,
                  "counters": counters, "scope": "observed qlog samples and transfer completion"}
    write_json(result_dir / "validation.json", validation)
    row = {"mode": mode, "workload": workload, "repetition": repetition,
           **summarize(samples), "received_bytes": received,
           "client_duration_seconds": float(client_perf["Duration"]),
           "download_mbit_s": float(client_perf["Mbps_R"]),
           "sender_retransmissions": int(server_perf["retrans."]),
           "sender_spurious": int(server_perf["spurious"]),
           "sender_final_rtt_us": int(server_perf["srtt"]),
           "status": validation["status"], "validation_errors": errors,
           "validation_counters": counters}
    write_json(summary_path, row)
    # Retain the complete raw traces without swelling the repository.
    for path in log_dir.glob("*.qlog"):
        with path.open("rb") as incoming, gzip.open(str(path) + ".gz", "wb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        path.unlink()
    print(f"{row['status']}: {mode}/{workload}/{run_id}, "
          f"{row['download_mbit_s']:.3f} Mbit/s, "
          f"cwnd max={row['cwnd_max_bytes']:.0f} bytes", flush=True)
    return row


def collect_one(args, mode, source, workload, repetition, environment):
    base = args.output / mode / TOPOLOGY
    run_id = f"run_{repetition:02d}"
    folders = {name: base / name / workload / run_id
               for name in ("graphs", "results", "logs")}
    summary_path = folders["results"] / "summary.json"
    if summary_path.exists():
        saved = json.loads(summary_path.read_text())
        metadata = json.loads((folders["results"] / "metadata.json").read_text())
        if metadata["binary_sha256"] != environment["binary_sha256"]:
            raise RuntimeError(f"Refusing to mix binaries in {summary_path}; use a new output folder")
        if args.reanalyze:
            return analyze_run(folders, mode, workload, repetition)
        if saved.get("status") != "PASS":
            raise RuntimeError(f"Existing run needs investigation: {summary_path}")
        print(f"Retained: {mode}/{workload}/{run_id}", flush=True)
        return saved
    if any(path.exists() and any(path.iterdir()) for path in folders.values()):
        raise RuntimeError(f"Refusing to overwrite an unfinished run: {folders['logs']}")
    for path in folders.values():
        path.mkdir(parents=True, exist_ok=True)

    log_dir, result_dir = folders["logs"], folders["results"]
    server = None
    started = datetime.now(timezone.utc).isoformat()
    commands = {}
    try:
        # Use the Linux checkout's scripts: an external working tree can contain
        # CRLF shell scripts even when its Git blobs contain portable LF.
        topology_root = args.rli_root.resolve() / "topology"
        logged(["bash", str(topology_root / "setup.sh")], log_dir / "topology-setup.log")
        logged(["bash", str(topology_root / "check.sh")], log_dir / "topology-check.log")
        with tempfile.TemporaryDirectory(prefix="osnt-experiment-") as temporary:
            scratch = Path(temporary)
            for name in ("web", "client", "server"):
                (scratch / name).mkdir()
            payload = scratch / "web/file_20M.bin"
            # Fixed content and size for every original/RLI transfer.
            with payload.open("wb") as output:
                for _ in range(20):
                    output.write(bytes(range(256)) * 4096)
            binary = str(source / "build/picoquicdemo")
            option = ["-H", "rli=on"] if mode == "rli_implemented" else []
            common = ["-G", "cubic", *option, "-q", str(log_dir), "-L"]
            server_command = ["ip", "netns", "exec", "rls-server", binary,
                              "-1", "-p", "4443", "-c", str(source / "certs/cert.pem"),
                              "-k", str(source / "certs/key.pem"),
                              "-w", str(scratch / "web"), *common,
                              "-F", str(result_dir / "server-performance.csv")]
            client_command = ["ip", "netns", "exec", "rls-client", binary, "-D",
                              *(["-a", "perf"] if workload == "rate-limited" else []),
                              *common, "-t", str(source / "certs/test-ca.crt"),
                              "-n", "test.example.com", "-F",
                              str(result_dir / "client-performance.csv"),
                              "10.10.2.2", "4443", SCENARIOS[workload]]
            commands = {"server": server_command, "client": client_command}
            write_json(result_dir / "metadata.json", {
                **environment, "started_utc": started, "mode": mode,
                "workload": workload, "repetition": repetition,
                "topology": TOPOLOGY, "rate_mbit": 20, "one_way_delay_ms": 25,
                "access_rate_mbit": 1000, "access_one_way_delay_ms": 5,
                "nominal_base_rtt_ms": 70,
                "queue_packets": 1000, "payload_sha256": digest(payload),
                "payload_bytes": payload.stat().st_size,
                "scenario": SCENARIOS[workload], "commands": commands})
            with (log_dir / "server.stdout.log").open("w") as output:
                output.write("$ " + shlex.join(server_command) + "\n")
                output.flush()
                server = subprocess.Popen(server_command, cwd=scratch / "server",
                                          stdout=output, stderr=subprocess.STDOUT)
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError(f"Server exited before listening: {server.returncode}")
                    ready = capture(["ip", "netns", "exec", "rls-server", "ss", "-H", "-lun",
                                     "sport = :4443"])
                    if ready:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Server did not listen within 10 seconds")
                logged(client_command, log_dir / "client.stdout.log", scratch / "client", 120)
                server_status = server.wait(timeout=30)
                if server_status:
                    raise RuntimeError(f"Server exited with {server_status}")
                server = None

        return analyze_run(folders, mode, workload, repetition)
    except Exception as error:
        write_json(result_dir / "failure.json", {"error": str(error), "commands": commands})
        raise
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        logged(["bash", str(args.rli_root.resolve() / "topology/cleanup.sh")], log_dir / "topology-cleanup.log")


def comparison_plots(args, workload, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharex=True, sharey=True)
    labels = {"original": "Original CUBIC", "rli_implemented": "CUBIC with RLI"}
    for axis, mode in zip(axes, labels):
        base = args.output / mode / TOPOLOGY
        for row in rows:
            if row["mode"] != mode or row["workload"] != workload:
                continue
            path = base / "results" / workload / f"run_{row['repetition']:02d}" / "congestion-metrics.csv"
            with path.open() as incoming:
                samples = list(csv.DictReader(incoming))
            times = [float(s["time"]) for s in samples]
            windows = [float(s["cwnd"]) / 1024 for s in samples]
            axis.plot(times, windows, linewidth=1, label=f"Run {row['repetition']}")
        axis.set_title(labels[mode])
        axis.set_xlabel("Elapsed time (seconds)")
        axis.grid(alpha=0.3)
        axis.legend()
    axes[0].set_ylabel("Congestion window (KiB)")
    figure.suptitle(f"{TOPOLOGY}: {workload}; matched axes, all repetitions")
    figure.tight_layout()
    for mode in labels:
        figure.savefig(args.output / mode / TOPOLOGY / "graphs" / f"{workload}-comparison.png", dpi=180)
    plt.close(figure)


def aggregate(args, rows):
    for mode in ("original", "rli_implemented"):
        base = args.output / mode / TOPOLOGY
        selected = [row for row in rows if row["mode"] == mode]
        fields = [name for name in selected[0] if name not in ("validation_errors", "validation_counters")]
        with (base / "results/run-summary.csv").open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(selected)
        comparisons = []
        for workload in SCENARIOS:
            group = {m: [r for r in rows if r["mode"] == m and r["workload"] == workload]
                     for m in ("original", "rli_implemented")}
            for metric in ("download_mbit_s", "client_duration_seconds", "cwnd_max_bytes",
                           "cwnd_time_average_bytes", "sender_retransmissions"):
                original = statistics.mean(r[metric] for r in group["original"])
                rli = statistics.mean(r[metric] for r in group["rli_implemented"])
                comparisons.append({"workload": workload, "metric": metric,
                                    "original_mean": original, "rli_mean": rli,
                                    "rli_change_percent": 100 * (rli - original) / original if original else None})
        with (base / "results/comparison.csv").open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=list(comparisons[0]))
            writer.writeheader()
            writer.writerows(comparisons)
    for workload in SCENARIOS:
        comparison_plots(args, workload, rows)
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(2, 3, figsize=(13, 7))
    metrics = (("download_mbit_s", "Download rate (Mbit/s)"),
               ("sender_retransmissions", "Retransmitted packets"),
               ("sender_final_rtt_us", "Final smoothed RTT (ms)"))
    for row_index, workload in enumerate(("bulk", "rate-limited")):
        for column, (metric, label) in enumerate(metrics):
            axis = axes[row_index][column]
            for position, mode in enumerate(("original", "rli_implemented")):
                values = [r[metric] / (1000 if metric.endswith("_us") else 1)
                          for r in rows if r["mode"] == mode and r["workload"] == workload]
                mean = statistics.mean(values)
                spread = statistics.stdev(values) if len(values) > 1 else 0
                axis.bar(position, mean, yerr=spread, alpha=0.55,
                         color=("#4477aa", "#228833")[position], capsize=4)
                axis.scatter([position] * len(values), values, color="black", s=15, zorder=3)
            axis.set_xticks([0, 1], ["Original", "RLI"])
            axis.set_ylabel(label)
            axis.set_title(workload)
            axis.set_ylim(bottom=0)
            axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Matched experiments: dots = runs; bars = mean; whiskers = sample SD")
    figure.tight_layout()
    for mode in ("original", "rli_implemented"):
        figure.savefig(args.output / mode / TOPOLOGY / "graphs/throughput-rtt-loss-comparison.png", dpi=180)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--rli-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "results")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--reanalyze", action="store_true",
                        help="Recheck retained traces without repeating completed transfers")
    args = parser.parse_args()
    if os.name != "posix" or os.geteuid() != 0:
        parser.error("Run inside Linux as root (the topology requires network administration)")
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    args.output = args.output.resolve()
    roots = {"original": args.original_root.resolve(), "rli_implemented": args.rli_root.resolve()}
    existing = {line.split()[0] for line in capture(["ip", "netns", "list"]).splitlines()}
    if existing.intersection(NAMESPACES):
        parser.error("Project namespaces already exist; clean up your earlier experiment first")
    provenance_by_mode = {mode: provenance(source) for mode, source in roots.items()}
    rows = []
    for repetition in range(1, args.repetitions + 1):
        for workload in ("bulk", "rate-limited"):
            modes = list(roots) if repetition % 2 else list(reversed(roots))
            for mode in modes:
                rows.append(collect_one(args, mode, roots[mode], workload, repetition,
                                        provenance_by_mode[mode]))
    aggregate(args, rows)
    for mode in roots:
        save_manifest(args.output / mode / TOPOLOGY)
    failures = sum(row["status"] != "PASS" for row in rows)
    print(f"Collected {len(rows)} runs; {failures} failed validation", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
