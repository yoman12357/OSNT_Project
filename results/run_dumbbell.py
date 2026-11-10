#!/usr/bin/env python3
"""Test two concurrent QUIC bulk flows across the full six-namespace dumbbell."""
import csv
import datetime
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(OUT / "evaluated-tools"))
from plot_cwnd import parse_qlog
from experiments.validate_rli import validate

DEST = OUT / "dumbbell"
DEST.mkdir(exist_ok=True)
environment = json.loads((OUT / "environment.json").read_text())


def command_log(command, destination):
    with destination.open("w") as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)


def perf_row(path):
    with path.open() as file:
        rows = list(csv.DictReader(file, skipinitialspace=True))
    assert len(rows) == 1
    return {k.strip(): v.strip() for k, v in rows[0].items()}


records = []
try:
    command_log(["bash", "topology/setup_dumbbell.sh"], DEST / "topology-setup.log")
    command_log(["bash", "topology/check_dumbbell.sh"], DEST / "topology-check.log")
    command_log(["ip", "netns", "list"], DEST / "namespaces.log")
    for repetition in (1, 2, 3):
        for mode in (("rli", "baseline") if repetition == 2 else ("baseline", "rli")):
            print(f"START dumbbell {mode} repetition {repetition}", flush=True)
            run = DEST / mode / f"run-{repetition}"
            if run.exists():
                raise RuntimeError(f"Refusing to overwrite existing evidence: {run}")
            run.mkdir(parents=True)
            binary = ROOT / (".local-deps/report-baseline/build/picoquicdemo" if mode == "baseline" else "build/picoquicdemo")
            option = "rli=on" if mode == "rli" else "rli=off"
            common = ["-G", "cubic", "-H", option]
            processes, streams, servers, clients = [], [], [], []
            try:
                for number, namespace in ((1, "rls-server"), (2, "rls-server2")):
                    flow = run / f"flow-{number}"
                    flow.mkdir()
                    log = (flow / "server.stdout.log").open("w")
                    streams.append(log)
                    server = subprocess.Popen(["ip", "netns", "exec", namespace, str(binary), "-1", "-p", "4443",
                        "-c", str(ROOT / "certs/cert.pem"), "-k", str(ROOT / "certs/key.pem"),
                        "-w", str(ROOT), *common, "-q", str(flow), "-L", "-F", str(flow / "server-performance.csv")],
                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                    servers.append(server)
                    processes.append(server)
                time.sleep(1)
                started = time.monotonic()
                for number, namespace, address in ((1, "rls-client", "10.10.2.2"), (2, "rls-client2", "10.10.4.2")):
                    flow = run / f"flow-{number}"
                    log = (flow / "client.stdout.log").open("w")
                    streams.append(log)
                    client = subprocess.Popen(["ip", "netns", "exec", namespace, str(binary), "-D", *common,
                        "-t", str(ROOT / "certs/test-ca.crt"), "-n", "test.example.com", "-q", str(flow),
                        "-L", "-F", str(flow / "client-performance.csv"), address, "4443", "/file_20M.bin"],
                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                    clients.append(client)
                    processes.append(client)
                for client in clients:
                    assert client.wait(timeout=90) == 0
                elapsed = time.monotonic() - started
                for server in servers:
                    assert server.wait(timeout=15) == 0
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                for log in streams:
                    log.close()
            flow_records = []
            for number in (1, 2):
                flow = run / f"flow-{number}"
                server_qlogs = list(flow.glob("*.server.qlog"))
                assert len(server_qlogs) == 1
                qlog = server_qlogs[0]
                json.loads(qlog.read_text())
                samples = parse_qlog(qlog)
                perf = perf_row(flow / "server-performance.csv")
                client_perf = perf_row(flow / "client-performance.csv")
                assert int(perf["Sent"]) >= 20 * 1024 * 1024
                assert int(client_perf["Received"]) >= 20 * 1024 * 1024
                errors, counters = [], {}
                if mode == "rli":
                    errors, counters = validate(samples)
                    assert not errors, errors
                flow_records.append({"flow": number, "qlog": str(qlog.relative_to(OUT)),
                    "throughput_mbps": float(perf["Mpbs_S"]), "duration_seconds": float(perf["Duration"]),
                    "sent_bytes": int(perf["Sent"]), "received_bytes": int(client_perf["Received"]),
                    "retransmissions": int(perf["retrans."]), "validation_errors": errors, "counters": counters})
            byte_sum = sum(flow["sent_bytes"] for flow in flow_records)
            rates = [flow["throughput_mbps"] for flow in flow_records]
            row = {"mode": mode, "repetition": repetition, "client_wall_seconds": elapsed,
                "combined_wall_throughput_mbps": byte_sum * 8 / elapsed / 1e6,
                "sum_of_connection_rates_mbps": sum(rates),
                "jain_fairness": sum(rates) ** 2 / (2 * sum(rate ** 2 for rate in rates)),
                "source_commit": environment["baseline_commit" if mode == "baseline" else "implementation_commit"],
                "binary_sha256": hashlib.file_digest(binary.open("rb"), "sha256").hexdigest(),
                "flows": flow_records}
            (run / "metadata.json").write_text(json.dumps(row, indent=2) + "\n")
            records.append(row)
            (DEST / "summary.json").write_text(json.dumps({"runs": records}, indent=2) + "\n")
            print(f'END dumbbell {mode} repetition {repetition}: wall rate={row["combined_wall_throughput_mbps"]:.3f} Mbit/s', flush=True)
finally:
    command_log(["bash", "topology/cleanup.sh"], DEST / "cleanup.log")
print("PASS: six two-flow dumbbell experiments, twelve complete connections", flush=True)
