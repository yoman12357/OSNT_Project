#!/usr/bin/env python3
"""Compile the self-contained LaTeX report and capture Linux output checks."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
compiler = shutil.which("tectonic") or str(ROOT / ".local-deps/report-tools/tectonic")
if not Path(compiler).exists():
    raise SystemExit("Install Tectonic or use pdflatex twice, then inspect the PDF.")
with (OUT / "latex-build.log").open("w") as log:
    result = subprocess.run([compiler, "--keep-logs", "report.tex"], cwd=OUT,
                            stdout=log, stderr=subprocess.STDOUT)
if result.returncode:
    print((OUT / "latex-build.log").read_text()[-8000:])
    raise SystemExit(result.returncode)
checks = {"latex_compiler_exit_code": result.returncode}
team = json.loads((OUT / "team.json").read_text())
for command, output in ((["pdfinfo", "report.pdf"], "pdfinfo.txt"),
                        (["pdffonts", "report.pdf"], "pdffonts.txt"),
                        (["pdfimages", "-list", "report.pdf"], "pdfimages.txt")):
    result = subprocess.run(command, cwd=OUT, capture_output=True, text=True, check=True)
    (OUT / output).write_text(result.stdout)
subprocess.run(["pdftotext", "-layout", "report.pdf", "report-extracted.txt"], cwd=OUT, check=True)
info = (OUT / "pdfinfo.txt").read_text()
checks["pages"] = int(re.search(r"Pages:\s+(\d+)", info).group(1))
author = re.search(r"Author:\s+(.+)", info).group(1)
checks["pdf_author_is_correct"] = all(name in author for name in team)
text = " ".join(unicodedata.normalize("NFKC", (OUT / "report-extracted.txt").read_text()).split())
checks["text_extracts"] = len(text) > 15000
checks["expected_sections_present"] = all(word in text for word in (
    "Baseline definition", "Implementation and changed files", "Experimental results",
    "All twelve fresh", "Aryan Bokolia"))
engine_log = (OUT / "report.log").read_text(errors="replace")
checks["undefined_references_or_citations"] = bool(re.search(
    r"(?:Reference|Citation) .+ undefined|There were undefined references", engine_log))
checks["overfull_boxes"] = len(re.findall(r"Overfull \\[hv]box", engine_log))
checks["embedded_plot_images"] = sum(len(line.split()) > 2 and line.split()[2] == "image"
                                     for line in (OUT / "pdfimages.txt").read_text().splitlines())
checks["pdf_size_bytes"] = (OUT / "report.pdf").stat().st_size
cover_text = subprocess.check_output(["pdftotext", "-f", "1", "-l", "1", "report.pdf", "-"], cwd=OUT, text=True)
normalized_cover = " ".join(unicodedata.normalize("NFKC", cover_text).split())
checks["all_five_names_on_cover"] = all(name in normalized_cover for name in team)
checks["technical_pdf_checks_pass"] = (
    checks["pdf_author_is_correct"] and checks["text_extracts"] and
    checks["expected_sections_present"] and not checks["undefined_references_or_citations"]
    and checks["all_five_names_on_cover"] and checks["overfull_boxes"] == 0 and checks["embedded_plot_images"] == 19)
(OUT / "pdf-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
print(json.dumps(checks, indent=2))
if not checks["technical_pdf_checks_pass"]:
    raise SystemExit("PDF needs review; inspect report.log and pdf-checks.json")
render = OUT / "pdf-preview"
render.mkdir(exist_ok=True)
subprocess.run(["pdftoppm", "-scale-to", "1100", "-png", "report.pdf", str(render / "page")], cwd=OUT, check=True)
print("PASS: LaTeX compiled, PDF metadata/text/images checked, all pages rendered to PNG for visual review")
