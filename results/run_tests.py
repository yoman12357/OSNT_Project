#!/usr/bin/env python3
"""Build and test the unchanged baseline and the current implementation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
BASE_COMMIT = "5a4eba475555a2b0d67fbd9000714be35b3db4b4"
BASE = ROOT / ".local-deps" / "report-baseline"
TESTS = OUT / "tests"
TESTS.mkdir(parents=True, exist_ok=True)
records = []


def run(name, command, cwd=ROOT):
    print(f"START {name}: {command}", flush=True)
    start = time.monotonic()
    with (TESTS / f"{name}.log").open("w") as log:
        log.write(f"cwd={cwd}\ncommand={command!r}\n")
        log.flush()
        result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    records.append({"name": name, "command": command, "cwd": str(cwd),
                    "exit_code": result.returncode,
                    "elapsed_seconds": time.monotonic() - start})
    (TESTS / "status.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"END {name}: exit={result.returncode}", flush=True)
    if result.returncode:
        print((TESTS / f"{name}.log").read_text()[-8000:], flush=True)
        raise SystemExit(result.returncode)


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


BASE.mkdir(parents=True, exist_ok=True)
if not (BASE / "CMakeLists.txt").exists():
    archive = subprocess.Popen(["git", "archive", BASE_COMMIT], cwd=ROOT,
                               stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(BASE)], stdin=archive.stdout, check=True)
    archive.stdout.close()
    if archive.wait():
        raise SystemExit("git archive failed")

common = ["-G", "Ninja", "-DPICOQUIC_FETCH_PTLS=Y", "-DWITH_OPENSSL=ON",
          "-DCMAKE_BUILD_TYPE=RelWithDebInfo"]
picotls = ROOT / "build/_deps/picotls-src"
if picotls.is_dir():
    common.append(f"-DFETCHCONTENT_SOURCE_DIR_PICOTLS={picotls}")
# Prefer the Linux system development package; retain the original local-header fallback.
local_headers = ROOT / ".local-deps/libssl-dev/usr/include"
if (local_headers / "openssl/ssl.h").is_file():
    common.extend([
        f"-DCMAKE_C_FLAGS=-I{local_headers / 'x86_64-linux-gnu'}",
        f"-DCMAKE_CXX_FLAGS=-I{local_headers / 'x86_64-linux-gnu'}",
        f"-DOPENSSL_INCLUDE_DIR={local_headers}",
    ])
run("baseline-configure", ["cmake", "-S", str(BASE), "-B", str(BASE / "build"), *common])
run("baseline-build", ["cmake", "--build", str(BASE / "build"), "--parallel", str(min(os.cpu_count() or 2, 8))])
run("baseline-ctest", ["ctest", "--test-dir", str(BASE / "build"), "--output-on-failure"])
shutil.copytree(BASE / "build/Testing", TESTS / "baseline-Testing", dirs_exist_ok=True)
run("rli-build", ["cmake", "--build", "build", "--parallel", str(min(os.cpu_count() or 2, 8))])
run("rli-ctest", ["ctest", "--test-dir", "build", "--output-on-failure"])
shutil.copytree(ROOT / "build/Testing", TESTS / "rli-Testing", dirs_exist_ok=True)
run("cubic-rli", [str(ROOT / "build/picoquic_ct"), "cubic_rli"], cwd=ROOT / "build")

metadata = {
    "verification_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "baseline_commit": BASE_COMMIT,
    "implementation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "baseline_binary_sha256": sha(BASE / "build/picoquicdemo"),
    "rli_binary_sha256": sha(ROOT / "build/picoquicdemo"),
    "uname": subprocess.check_output(["uname", "-a"], text=True).strip(),
    "os_release": Path("/etc/os-release").read_text(),
    "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
    "cmake": subprocess.check_output(["cmake", "--version"], text=True).splitlines()[0],
    "working_tree": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True),
    "notes": "New report artifacts are untracked; no implementation code was edited for this verification. Baseline source is extracted from the exact pre-RLI commit, not simulated by RLI-off only.",
}
(OUT / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
print("PASS: builds, both full CTest suites, and focused cubic_rli test", flush=True)
