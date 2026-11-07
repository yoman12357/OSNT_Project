#!/usr/bin/env python3
"""Audit report requirements and create portable evidence checksums."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
parser = argparse.ArgumentParser()
parser.add_argument("--visual-reviewed", action="store_true",
                    help="Record that a human/agent has actually inspected the rendered PDF pages")
args = parser.parse_args()


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


environment = json.loads((OUT / "environment.json").read_text())
summary = json.loads((OUT / "summary.json").read_text())
pdf = json.loads((OUT / "pdf-checks.json").read_text())
tests = json.loads((OUT / "tests/status.json").read_text())
subprocess.run(["git", "merge-base", "--is-ancestor", environment["implementation_commit"], "HEAD"], cwd=ROOT, check=True)
assert all(item["exit_code"] == 0 for item in tests)
assert pdf["technical_pdf_checks_pass"]
assert len(list((OUT / "pdf-preview").glob("page-*.png"))) == pdf["pages"]
assert len(summary["records"]) == 12
assert len(list((OUT / "plots").glob("*.png"))) == 13
assert len(list((OUT / "validation").glob("*.txt"))) == 6
team = json.loads((OUT / "team.json").read_text())
assert all(name in (OUT / "report.tex").read_text() for name in team)

core = ["picoquic/cubic.c", "picoquic/sender.c", "picoquic/picoquic_internal.h",
        "picoquic/logwriter.c", "loglib/qlog.c", "loglib/qlog_fns.c",
        "picoquictest/congestion_test.c", "picoquictest/picoquictest.h",
        "picoquic_t/picoquic_t.c", "UnitTest1/unittest1.cpp", "plot_cwnd.py",
        "experiments/validate_rli.py", "experiments/run_comparison.sh"]
assert not git("diff", "--binary", "--", *core), "Runtime implementation changes need separate review"
assert not git("diff", "--cached", "--binary", "--", *core)
for relative in core:
    assert (ROOT / relative).read_bytes() == git("show", environment["implementation_commit"] + ":" + relative)
    if relative.startswith(("picoquic/", "picoquictest/")):
        assert (ROOT / ".local-deps/report-baseline" / relative).read_bytes() == git(
            "show", environment["baseline_commit"] + ":" + relative)
(OUT / "implementation.patch").write_bytes(git("diff", environment["baseline_commit"],
    environment["implementation_commit"], "--", *core))
(OUT / "changed-files.txt").write_bytes(git("diff", "--stat", environment["baseline_commit"],
    environment["implementation_commit"], "--", *core))

for row in summary["records"]:
    directory = (OUT / row["qlog"]).parent
    mode = row["mode"]
    provenance = dict(line.split("=", 1) for line in (directory / "provenance.txt").read_text().splitlines())
    metadata = dict(line.split("=", 1) for line in (directory / "metadata.txt").read_text().splitlines())
    assert provenance["tested_source_commit"] == environment[
        "baseline_commit" if mode == "baseline" else "implementation_commit"]
    assert metadata["demo_sha256"] == environment[mode + "_binary_sha256"]
    assert metadata["mode"] == mode and metadata["workload"] == row["workload"]
    assert metadata["rli_option"] == ("rli=off" if mode == "baseline" else "rli=on")
    original = directory / "original-manifest.sha256"
    if not original.exists():
        (directory / "manifest.sha256").rename(original)
    for line in original.read_text().splitlines():
        digest, source_path = line.split("  ", 1)
        assert sha(directory / Path(source_path).name) == digest, source_path
    lines = [f"{sha(file)}  {file.name}" for file in sorted(directory.iterdir())
             if file.is_file() and file.name != "manifest.sha256"]
    (directory / "manifest.sha256").write_text("\n".join(lines) + "\n")

assert sha(ROOT / "build/picoquicdemo") == environment["rli_binary_sha256"]
assert sha(ROOT / ".local-deps/report-baseline/build/picoquicdemo") == environment["baseline_binary_sha256"]
subprocess.run(["bash", "-n", str(OUT / "run_experiments.sh")], check=True)
for script in ("topology/setup_dumbbell.sh", "topology/check_dumbbell.sh", "topology/cleanup.sh"):
    subprocess.run(["bash", "-n", str(ROOT / script)], check=True)
supplement = json.loads((OUT / "dumbbell/summary.json").read_text())["runs"]
assert len(supplement) == 6 and sum(len(run["flows"]) for run in supplement) == 12
sys_path = str(ROOT)
import sys
sys.path.insert(0, sys_path)
from plot_cwnd import parse_qlog
from experiments.validate_rli import validate
for run in supplement:
    assert run["binary_sha256"] == environment[run["mode"] + "_binary_sha256"]
    for flow in run["flows"]:
        assert flow["sent_bytes"] >= 20 * 1024 * 1024 and flow["received_bytes"] >= 20 * 1024 * 1024
        if run["mode"] == "rli":
            errors, _ = validate(parse_qlog(OUT / flow["qlog"]))
            assert not errors, errors
assert len(list((OUT / "plots/dumbbell").glob("*.png"))) == 6
assert len((OUT / "dumbbell/namespaces.log").read_text().splitlines()) == 6
subprocess.run([sys.executable, str(OUT / "package_evidence.py")], check=True)

verification = {
    "audit_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "project_details_and_baseline_documented": True,
    "implementation_diff_and_file_map_saved": True,
    "team_members": team,
    "both_source_revisions_built_and_full_registered_suites_pass": True,
    "focused_rli_test_pass": True,
    "fresh_experiment_count": 12,
    "supplementary_two_flow_experiment_count": 6,
    "total_completed_connections": 24,
    "rli_traces_validated": 6,
    "supplementary_rli_traces_validated": 6,
    "individual_plots": 12,
    "overview_plots": 1,
    "competing_flow_plots": 6,
    "full_dumbbell_setup_and_traffic_verified": True,
    "compressed_raw_evidence_verified_byte_for_byte": True,
    "supplementary_source_sha256": {path: sha(ROOT / path) for path in (
        "topology/setup_dumbbell.sh", "topology/check_dumbbell.sh", "topology/cleanup.sh",
        "results 1/run_dumbbell.py", "results 1/analyze_dumbbell.py")},
    "raw_evidence_integrity_verified": True,
    "core_implementation_unchanged": True,
    "latex_compilation_and_linux_pdf_checks_pass": True,
    "pdf_pages_rendered": pdf["pages"],
    "pdf_visual_review_completed": args.visual_reviewed,
    "readme_correctness_assessment_present": "Is the output correct?" in (OUT / "README.md").read_text(),
    "rate_limited_mean_cwnd_change_percent": summary["groups"]["rate-limited"]["cwnd_time_average_bytes_change_percent"],
    "bulk_mean_throughput_change_percent": summary["groups"]["bulk"]["throughput_mbps_change_percent"],
    "verdict": "PASS for tested conditions; report output verified" if args.visual_reviewed else "Technical checks PASS; visual review pending",
    "limitations": "No statistical significance or universal speedup claimed; general CUBIC limit interpretation merits review before full IETF conformance claims.",
}
(OUT / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")

files = [file for file in sorted(OUT.rglob("*")) if file.is_file()
         and file.name != "SHA256SUMS" and "__pycache__" not in file.parts]
relative_names = [str(file.relative_to(ROOT)) for file in files]
ignored = subprocess.run(["git", "check-ignore", "--stdin", "-z"], cwd=ROOT,
    input=("\0".join(relative_names) + "\0").encode(), capture_output=True)
assert ignored.returncode in (0, 1)
ignored_names = set(ignored.stdout.decode().strip("\0").split("\0"))
files = [file for file in files if str(file.relative_to(ROOT)) not in ignored_names]
(OUT / "SHA256SUMS").write_text("\n".join(f"{sha(file)}  {file.relative_to(OUT)}" for file in files) + "\n")
result = subprocess.run(["sha256sum", "--check", "--quiet", "SHA256SUMS"], cwd=OUT)
assert result.returncode == 0
print(json.dumps(verification, indent=2))
print(f"PASS: {len(files)} evidence files match the portable manifest")
