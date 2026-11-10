#!/usr/bin/env python3
"""Check retained evidence inventory, raw archive, and portable checksums."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent


def audit():
    errors = []
    required = ["Final report.pdf", "environment.json", "summary.json",
                "measurements.csv", "tests/status.json", "dumbbell/summary.json",
                "dumbbell/validation.json", "raw-evidence.tar.gz",
                "report-source/main.tex", "run_single_comparison.sh"]
    for name in required:
        if not (OUT / name).is_file():
            errors.append(f"Missing {name}")
    if errors:
        return {"pass": False, "errors": errors}

    environment = json.loads((OUT / "environment.json").read_text(encoding="utf-8"))
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    supplement = json.loads((OUT / "dumbbell/summary.json").read_text(encoding="utf-8"))
    tests = json.loads((OUT / "tests/status.json").read_text(encoding="utf-8"))
    validation = json.loads((OUT / "dumbbell/validation.json").read_text(encoding="utf-8"))
    if "Linux " not in environment["uname"] or "Ubuntu" not in environment["os_release"]:
        errors.append("Recorded campaign environment does not identify Ubuntu Linux")
    if len(summary["records"]) != 12 or len(supplement["runs"]) != 6:
        errors.append("Expected twelve main runs and six supplementary runs")
    matrix = Counter((r["workload"], r["mode"]) for r in summary["records"])
    expected_matrix = {(w, m): 3 for w in ("bulk", "rate-limited") for m in ("baseline", "rli")}
    if matrix != expected_matrix:
        errors.append("Main workload/mode matrix is incomplete")
    if len(tests) != 6 or any(t["exit_code"] for t in tests):
        errors.append("Retained build/regression/focused-test status is incomplete or failed")
    if len(validation) != 6 or any(v["result"] != "PASS" for v in validation):
        errors.append("Supplementary RLI validation is incomplete or failed")
    for row in summary["records"]:
        if row["mode"] == "rli" and row["validation"] != "PASS":
            errors.append(f"Failed main RLI validation: {row['qlog']}")
    for name in ("topology/setup_dumbbell.sh", "topology/check_dumbbell.sh", "topology/cleanup.sh"):
        if not (ROOT / name).is_file():
            errors.append(f"Missing reproduction dependency {name}")

    members = {}
    with tarfile.open(OUT / "raw-evidence.tar.gz", "r:gz") as archive:
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                errors.append(f"Unsafe raw archive member {member.name}")
                continue
            if member.isfile():
                with archive.extractfile(member) as file:
                    members[member.name] = hashlib.file_digest(file, "sha256").hexdigest()
    raw_qlogs = sum(name.endswith(".qlog") for name in members)
    if len(members) != 240 or raw_qlogs != 48:
        errors.append("Expected 240 raw evidence files, including 48 qlogs")
    for row in summary["records"]:
        if row["qlog"] not in members:
            errors.append(f"Missing main sender trace {row['qlog']}")
    for run in supplement["runs"]:
        if len(run["flows"]) != 2:
            errors.append("A supplementary experiment does not contain two flows")
        for flow in run["flows"]:
            if flow["qlog"] not in members:
                errors.append(f"Missing supplementary trace {flow['qlog']}")

    plot_count = len(list((OUT / "plots").rglob("*.png")))
    if plot_count != 19:
        errors.append(f"Expected nineteen plots, found {plot_count}")
    pdf = (OUT / "Final report.pdf").read_bytes()
    if not pdf.startswith(b"%PDF-"):
        errors.append("Final report does not have a PDF signature")
    original_manifest = dict(line.split("  ", 1)[::-1] for line in
                             (OUT / "SHA256SUMS.original").read_text(encoding="utf-8").splitlines())
    with (OUT / "raw-evidence.tar.gz").open("rb") as file:
        archive_digest = hashlib.file_digest(file, "sha256").hexdigest()
    if archive_digest != original_manifest["raw-evidence.tar.gz"]:
        errors.append("Raw archive differs from the original distribution")
    strict = json.loads((OUT / "current-validator-checks.json").read_text(encoding="utf-8"))
    for relative in ("project_docs", "results 1", "results1"):
        if (ROOT / relative).exists():
            errors.append(f"Obsolete top-level folder remains: {relative}")
    return {
        "pass": not errors,
        "main_experiments": len(summary["records"]),
        "supplementary_experiments": len(supplement["runs"]),
        "completed_connections": len(summary["records"]) + sum(len(r["flows"]) for r in supplement["runs"]),
        "raw_files": len(members), "raw_qlogs": raw_qlogs, "plots": plot_count,
        "current_validator_traces_with_errors": strict["traces_with_errors"],
        "validation_note": "Inventory completeness is separate from the newer validator's findings; see current-validator-checks.json.",
        "recorded_linux_uname": environment["uname"],
        "scope": "Inventory and archive checks of retained evidence; no new network experiments or C regression run.",
        "errors": errors,
    }


def check_manifest():
    errors = []
    count = 0
    for line in (OUT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = OUT / name
        if not path.is_file():
            errors.append(f"Manifest file missing: {name}")
            continue
        with path.open("rb") as file:
            actual = hashlib.file_digest(file, "sha256").hexdigest()
        if actual != digest:
            errors.append(f"Checksum mismatch: {name}")
        count += 1
    return count, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-audit", action="store_true",
                        help="Write inventory audit before regenerating the distribution manifest")
    args = parser.parse_args()
    result = audit()
    if args.write_audit:
        (OUT / "bundle-checks.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    else:
        result["manifest_files_checked"], errors = check_manifest()
        result["errors"].extend(errors)
        result["pass"] = not result["errors"]
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
