#!/usr/bin/env python3
"""Compile the retained final-report source and verify the resulting PDF."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

OUT = Path(__file__).resolve().parent
SOURCE = OUT / "report-source"


def main():
    compiler = os.environ.get("PDFLATEX") or shutil.which("pdflatex")
    if not compiler:
        raise SystemExit("Install TeX Live with pdfLaTeX, or set PDFLATEX to its executable.")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("Install pypdf in the active Python environment.")

    build = SOURCE / "build"
    build.mkdir(exist_ok=True)
    command = [compiler, "-interaction=nonstopmode", "-halt-on-error",
               "-file-line-error", "-output-directory=build", "main.tex"]
    for repetition in (1, 2):
        result = subprocess.run(command, cwd=SOURCE, capture_output=True)
        (build / f"compile-{repetition}.log").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(f"pdfLaTeX failed; inspect {build / f'compile-{repetition}.log'}")

    pdf = build / "main.pdf"
    reader = PdfReader(pdf)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    log = (build / "main.log").read_text(encoding="utf-8", errors="replace")
    missing_references = bool(re.search(
        r"(?:Reference|Citation) .+ undefined|There were undefined references", log))
    old_paths = bool(re.search(r"project[_\s]*docs|results\s+1/|results1/", text, re.I))
    names = ["Aryan Bokolia", "Affan Arshad", "Soumyadeep Raj",
             "Kevin Shiju George", "Aryan Palimkar"]
    checks = {
        "source": "report-source/main.tex",
        "output": "Final report.pdf",
        "pages": len(reader.pages),
        "text_extracts": len(text) > 15000,
        "all_five_names_on_cover": all(name in reader.pages[0].extract_text() for name in names),
        "undefined_references_or_citations": missing_references,
        "obsolete_local_paths": old_paths,
        "overfull_boxes": len(re.findall(r"Overfull \\[hv]box", log)),
        "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "scope": "Report compilation and PDF checks; no new network experiments or C regression run.",
    }
    checks["pass"] = (checks["text_extracts"] and checks["all_five_names_on_cover"]
                      and not missing_references and not old_paths
                      and checks["overfull_boxes"] == 0)
    (OUT / "final-report-checks.json").write_text(
        json.dumps(checks, indent=2) + "\n", encoding="utf-8", newline="\n")
    if not checks["pass"]:
        raise SystemExit(json.dumps(checks, indent=2))
    shutil.copyfile(pdf, OUT / "Final report.pdf")
    print(json.dumps(checks, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
