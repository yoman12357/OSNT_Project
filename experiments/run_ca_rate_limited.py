#!/usr/bin/env python3
"""Collect bulk -> limited -> burst streams within one QUIC connection."""

import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scenario(warmup_bytes, frames, burst_bytes):
    # previous_id has its own '='. G=frames keeps the limited phase on one stream.
    return (f"=warm:397:{warmup_bytes};"
            f"=limited:=warm:s20:n{frames}:1200:G{frames}:I1200;"
            f"=burst:=limited:397:{burst_bytes};")


def compress_raw(directory):
    for path in sorted(directory.iterdir()):
        if path.suffix not in (".qlog", ".b"):
            continue
        target = path.with_name(path.name + ".gz")
        if target.exists():
            raise RuntimeError(f"Refusing to overwrite {target}")
        original = sha(path)
        with path.open("rb") as source, gzip.open(target, "wb", compresslevel=6) as dest:
            shutil.copyfileobj(source, dest)
        with gzip.open(target, "rb") as source:
            assert hashlib.file_digest(source, "sha256").hexdigest() == original
        path.unlink()  # Only this runner's new trace; identical compressed data is retained.


def logged(command, path):
    with path.open("w") as output:
        subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)


def collect(args):
    if os.geteuid() != 0:
        raise SystemExit("Run inside a root-mapped user/network/mount namespace.")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite an existing campaign: {output}")
    output.mkdir(parents=True)
    environment = json.loads((ROOT / "results/environment.json").read_text())
    text = scenario(args.warmup_mib * 1024**2, args.frames, args.burst_mib * 1024**2)
    binaries = {"baseline": ROOT / ".local-deps/report-baseline/build/picoquicdemo",
                "rli": ROOT / "build/picoquicdemo"}
    for mode, binary in binaries.items():
        assert sha(binary) == environment[mode + "_binary_sha256"], f"Untested binary: {binary}"
    for name, digest in environment["topology_sha256"].items():
        assert sha(ROOT / name) == digest, f"Topology differs from recorded campaign: {name}"
    metadata = {"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "scenario": text, "warmup_bytes": args.warmup_mib * 1024**2,
                "limited_frames": args.frames, "limited_frame_bytes": 1200,
                "limited_fps": 20, "burst_bytes": args.burst_mib * 1024**2,
                "repetitions": args.repetitions, "mode": args.mode,
                "topology": environment["topology"],
                "source_environment": environment, "collector_sha256": sha(Path(__file__)),
                "runtime_source_edited": False, "runs": []}
    save = lambda: (output / "collection.json").write_text(json.dumps(metadata, indent=2) + "\n")
    save()
    try:
        logged(["bash", "topology/setup.sh"], output / "topology-setup.log")
        logged(["bash", "topology/check.sh"], output / "topology-check.log")
        for repetition in range(1, args.repetitions + 1):
            modes = [args.mode] if args.mode != "both" else (
                ["rli", "baseline"] if repetition % 2 == 0 else ["baseline", "rli"])
            for mode in modes:
                directory = output / mode / f"run-{repetition}"
                directory.mkdir(parents=True)
                binary = binaries[mode]
                common = ["-G", "cubic", "-H", "rli=on" if mode == "rli" else "rli=off"]
                server_command = ["ip", "netns", "exec", "rls-server", str(binary), "-1", "-p", "4443",
                    "-c", str(ROOT / "certs/cert.pem"), "-k", str(ROOT / "certs/key.pem"),
                    *common, "-q", str(directory), "-L", "-F", str(directory / "server-performance.csv")]
                client_command = ["ip", "netns", "exec", "rls-client", str(binary), "-D", "-a", "perf",
                    *common, "-t", str(ROOT / "certs/test-ca.crt"), "-n", "test.example.com",
                    "-q", str(directory), "-L", "-F", str(directory / "client-performance.csv"),
                    "10.10.2.2", "4443", text]
                print(f"START {mode} repetition {repetition}: {text}", flush=True)
                started = time.monotonic()
                with (directory / "server.stdout.log").open("w") as server_log, (
                        directory / "client.stdout.log").open("w") as client_log:
                    # Separate working directories prevent ticket caches crossing between runs.
                    server = subprocess.Popen(server_command, cwd=directory, stdout=server_log, stderr=subprocess.STDOUT)
                    try:
                        time.sleep(1)
                        client = subprocess.run(client_command, cwd=directory, stdout=client_log,
                                                stderr=subprocess.STDOUT, timeout=args.timeout)
                        assert client.returncode == 0, f"Client failed; inspect {directory}"
                        assert server.wait(timeout=20) == 0, f"Server failed; inspect {directory}"
                    finally:
                        if server.poll() is None:
                            server.terminate()
                            server.wait(timeout=10)
                row = {"mode": mode, "repetition": repetition,
                       "source_commit": environment["baseline_commit" if mode == "baseline" else "implementation_commit"],
                       "binary_sha256": sha(binary), "server_command": server_command,
                       "client_command": client_command, "elapsed_seconds": time.monotonic() - started}
                compress_raw(directory)
                (directory / "metadata.json").write_text(json.dumps(row, indent=2) + "\n")
                metadata["runs"].append(row)
                save()
                print(f"END {mode} repetition {repetition}: {row['elapsed_seconds']:.2f} s", flush=True)
    finally:
        logged(["bash", "topology/cleanup.sh"], output / "cleanup.log")
    metadata["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata["complete"] = len(metadata["runs"]) == args.repetitions * (2 if args.mode == "both" else 1)
    save()
    print(f"PASS: {len(metadata['runs'])} three-phase connections completed: {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--warmup-mib", type=int, default=20)
    parser.add_argument("--burst-mib", type=int, default=5)
    parser.add_argument("--frames", type=int, default=400)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--mode", choices=("baseline", "rli", "both"), default="both")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    assert min(args.warmup_mib, args.burst_mib, args.frames, args.repetitions, args.timeout) > 0
    collect(args)


if __name__ == "__main__":
    main()
