#!/usr/bin/env python3
"""Build the plain-English report variant without changing the original report."""
import hashlib
import csv
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import statistics
import unicodedata

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent


def read(name):
    return (OUT / name).read_text()


def save(name, value):
    (OUT / name).write_text(value)


original = read("report.tex")
source = read("report1.tex")
original_pdf_hash = hashlib.sha256((OUT / "report.pdf").read_bytes()).hexdigest()

with (OUT / "measurements.csv").open() as file:
    measurements = list(csv.DictReader(file))
summary = json.loads(read("summary.json"))
table_parts = []
main_means_match = True
for workload in ("rate-limited", "bulk"):
    table_parts += [r"\begin{table}[H]\centering\small",
        r"\begin{tabular}{lrrrrr}\toprule",
        r"Mode & Final cwnd & Avg. cwnd & Rate & Time & Retrans.\\",
        r" & (KiB) & (KiB) & (Mbit/s) & (s) & \\\midrule"]
    for mode in ("baseline", "rli"):
        rows = [row for row in measurements if row["workload"] == workload and row["mode"] == mode]
        assert len(rows) == 3
        means = {metric: statistics.mean(float(row[metric]) for row in rows) for metric in (
            "cwnd_final_bytes", "cwnd_time_average_bytes", "throughput_mbps", "connection_duration_seconds", "retransmissions")}
        main_means_match &= all(math.isclose(value, summary["groups"][workload][mode][metric]["mean"], rel_tol=1e-10, abs_tol=1e-10)
                                for metric, value in means.items())
        table_parts.append(f'{mode} & {means["cwnd_final_bytes"]/1024:.2f} & '
            f'{means["cwnd_time_average_bytes"]/1024:.2f} & {means["throughput_mbps"]:.3f} & '
            f'{means["connection_duration_seconds"]:.3f} & {means["retransmissions"]:.1f} ' + r"\\")
    title = "Rate-limited workload" if workload == "rate-limited" else "Bulk workload"
    table_parts += [r"\bottomrule\end{tabular}", r"\caption{" + title +
        r": means of all three repetitions. Time uses the server connection duration.}\end{table}"]
tables = "\n".join(table_parts) + "\n"
save("report1-tables.tex", tables)

main_figures = read("generated-figures.tex").replace("Rli:", "RLI:").replace(
    "These matched traces isolate rate-limited window growth. RLI permits bounded ACK-driven growth; application supply still controls throughput.",
    "RLI allows window growth up to its cap. The application supplies the same limited data in both runs."
).replace(
    "These matched traces test a continuously backlogged sender. Normal CUBIC growth and congestion responses dominate; compare measured throughput rather than window height alone.",
    "Both senders have continuous data. Use the measured throughput to compare the runs; cwnd height alone does not show transfer speed."
)
main_figures = r"\clearpage".join(block for block in main_figures.split(r"\clearpage")
    if r"\subsection{Rate-limited, repetition 1}" in block or r"\subsection{Bulk control, repetition 1}" in block)
save("report1-figures.tex", main_figures)

extra_figures = read("generated-dumbbell-figures.tex").replace("Rli:", "RLI:").replace(
    "The two lines show the congestion windows of competing flows. Window height and temporary differences in allocation should be interpreted alongside the transfer rates and Jain index.",
    "The lines show cwnd for the two competing flows. The results table gives their transfer rates and Jain index."
)
extra_figures = extra_figures.split(r"\clearpage")[0]
save("report1-dumbbell-figures.tex", extra_figures)

aggregates = json.loads(read("dumbbell/aggregate.json"))
runs = json.loads(read("dumbbell/summary.json"))["runs"]
table_lines = [r"\begin{table}[H]\centering\small", r"\begin{tabular}{lrrrrr}\toprule",
    r"Mode & Flow 1 & Flow 2 & Combined & Jain index & Retrans.\\",
    r" & (Mbit/s) & (Mbit/s) & (Mbit/s) & & \\\midrule"]
dumbbell_means_match = True
for mode in ("baseline", "rli"):
    selected = [run for run in runs if run["mode"] == mode]
    assert len(selected) == 3
    flow_rates = [statistics.mean(run["flows"][flow]["throughput_mbps"] for run in selected) for flow in (0, 1)]
    combined = statistics.mean(run["combined_wall_throughput_mbps"] for run in selected)
    fairness = statistics.mean(run["jain_fairness"] for run in selected)
    retrans = statistics.mean(sum(flow["retransmissions"] for flow in run["flows"]) for run in selected)
    dumbbell_means_match &= all(math.isclose(value, aggregates[mode][metric], rel_tol=1e-10) for metric, value in (
        ("wall_throughput_mbps", combined), ("jain_fairness", fairness), ("retransmissions", retrans)))
    table_lines.append(f'{mode} & {flow_rates[0]:.3f} & {flow_rates[1]:.3f} & {combined:.3f} & {fairness:.4f} & {retrans:.1f} ' + r"\\")
table_lines += [r"\bottomrule\end{tabular}",
    r"\caption{Two-flow dumbbell: means of all three repetitions. Retransmissions are the mean total across both flows.}\end{table}"]
table = "\n".join(table_lines)
paragraph = (
    f'Mean combined throughput was {aggregates["baseline"]["wall_throughput_mbps"]:.3f} Mbit/s for baseline '
    f'and {aggregates["rli"]["wall_throughput_mbps"]:.3f} Mbit/s for RLI '
    f'({aggregates["throughput_change_percent"]:+.2f}\\%).\n'
    "The common interval starts at client launch and ends when both clients exit.\n"
    "It excludes the later wait for server shutdown.\n"
    "Each flow rate uses that server's own connection interval.\n"
    "The sum of those rates therefore differs from the combined wall-time rate.\n"
    "The Jain index uses the two per-connection rates.\n"
    "Values closer to one mean a more even split across these connection lifetimes.\n"
    "This measure does not show instantaneous fairness or fairness against other congestion algorithms.\n"
)
save("report1-dumbbell.tex", table + "\n" + paragraph)

references = original[original.index(r"\begin{thebibliography}"):original.index(r"\end{thebibliography}") + len(r"\end{thebibliography}")]
save("report1-references.tex", references + "\n")


def data_rows(text):
    return [line.strip() for line in text.splitlines() if re.match(r"^\s*\d+\s*&", line)]


def image_paths(text):
    return set(re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", text))


checks = {
    "main_averages_match_all_three_saved_runs": main_means_match,
    "dumbbell_averages_match_all_three_saved_runs": dumbbell_means_match,
    "references_unchanged": read("report1-references.tex").strip() == references,
    "same_measured_value_macros": r"\input{generated-values.tex}" in source,
}
old_images = image_paths(original + read("generated-figures.tex") + read("generated-dumbbell-figures.tex"))
new_images = image_paths(source + main_figures + extra_figures)
expected_images = {"plots/overview.png", "plots/rate-limited-baseline-1.png", "plots/rate-limited-rli-1.png",
    "plots/bulk-baseline-1.png", "plots/bulk-rli-1.png", "plots/dumbbell/baseline-1.png", "plots/dumbbell/rli-1.png"}
checks["only_repetition_one_and_overview_shown"] = new_images == expected_images and new_images <= old_images

# This is a plain sentence-length screen, not an ASD-STE100 certification.
values = dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", read("generated-values.tex")))


def prose(text):
    text = re.sub(r"\\begin\{(lstlisting|tabularx|tabular|longtable|titlepage)\}.*?\\end\{\1\}", "\n\n", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", " equation ", text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", " equation ", text, flags=re.S)
    text = re.sub(r"\\(?:section|subsection)\*?\{[^}]*\}|\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}", "\n\n", text)
    text = re.sub(r"\\item(?:\[[^]]*\])?", "\n\n", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}", "\n\n", text)
    text = re.sub(r"\\(?:code|path|url|texttt|emph|textbf)\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:cite|label|ref)\{[^}]*\}", "", text)
    for name, value in values.items():
        text = re.sub(r"\\" + name + r"\b(?:\{\})?", lambda match: value, text)
    text = re.sub(r"\\(?:clearpage|centering|small|toprule|midrule|bottomrule)\b", "", text)
    text = text.replace(r"\%", "%").replace("{", "").replace("}", "")
    return text


body = source[source.index(r"\section*{Abstract}"):source.index(r"\input{report1-references.tex}")]
sentences = []
for paragraph_text in re.split(r"\n\s*\n", prose(body + "\n\n" + paragraph)):
    paragraph_text = " ".join(paragraph_text.split())
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph_text):
        if sentence and not sentence.startswith("%"):
            sentences.append((len(sentence.split()), sentence))
long_sentences = [{"words": count, "sentence": sentence} for count, sentence in sentences if count > 25]
checks["descriptive_sentence_screen_limit"] = 25
checks["descriptive_sentence_screen_max"] = max(count for count, _ in sentences)
checks["sentences_over_25_words"] = long_sentences
procedure = source[source.index(r"\section{Reproduction and evidence files}"):source.index(r"\begin{tabularx}", source.index(r"\section{Reproduction and evidence files}"))]
procedure_sentences = [" ".join(sentence.split()) for sentence in re.split(r"(?<=[.!?])\s+", prose(procedure)) if sentence.strip()]
checks["procedural_sentence_screen_limit"] = 20
checks["procedural_sentence_screen_max"] = max(len(sentence.split()) for sentence in procedure_sentences)
checks["procedural_sentences_over_20_words"] = [sentence for sentence in procedure_sentences if len(sentence.split()) > 20]
save("report1-checks.json", json.dumps(checks, indent=2) + "\n")
if long_sentences or checks["procedural_sentences_over_20_words"]:
    raise SystemExit(json.dumps(checks, indent=2))
assert all(checks[key] for key in ("main_averages_match_all_three_saved_runs", "dumbbell_averages_match_all_three_saved_runs", "references_unchanged", "same_measured_value_macros", "only_repetition_one_and_overview_shown"))

compiler = shutil.which("tectonic") or str(ROOT / ".local-deps/report-tools/tectonic")
with (OUT / "report1-build.log").open("w") as log:
    result = subprocess.run([compiler, "--keep-logs", "report1.tex"], cwd=OUT, stdout=log, stderr=subprocess.STDOUT)
checks["latex_exit_code"] = result.returncode
if result.returncode:
    raise SystemExit(read("report1-build.log")[-6000:])
info = subprocess.check_output(["pdfinfo", "report1.pdf"], cwd=OUT, text=True)
save("report1-pdfinfo.txt", info)
checks["pages"] = int(re.search(r"Pages:\s+(\d+)", info).group(1))
team = json.loads(read("team.json"))
author = re.search(r"Author:\s+(.+)", info).group(1)
checks["all_five_authors_in_metadata"] = all(name in author for name in team)
cover = subprocess.check_output(["pdftotext", "-f", "1", "-l", "1", "report1.pdf", "-"], cwd=OUT, text=True)
cover = " ".join(unicodedata.normalize("NFKC", cover).split())
checks["all_five_names_on_cover"] = all(name in cover for name in team)
subprocess.run(["pdftotext", "-layout", "report1.pdf", "report1-extracted.txt"], cwd=OUT, check=True)
extracted = " ".join(unicodedata.normalize("NFKC", read("report1-extracted.txt")).split())
checks["all_sections_present"] = all(section in extracted for section in (
    "Baseline definition", "Implementation and changed files", "Experimental results", "Limitations and further tests", "Conclusion"))
images = subprocess.check_output(["pdfimages", "-list", "report1.pdf"], cwd=OUT, text=True)
checks["embedded_graphs"] = sum(len(line.split()) > 2 and line.split()[2] == "image" for line in images.splitlines())
log = read("report1.log")
checks["undefined_references_or_citations"] = bool(re.search(r"(?:Reference|Citation) .+ undefined|There were undefined references", log))
checks["overfull_boxes"] = len(re.findall(r"Overfull \\[hv]box", log))
checks["original_report_pdf_unchanged"] = hashlib.sha256((OUT / "report.pdf").read_bytes()).hexdigest() == original_pdf_hash
checks["pass"] = (
    checks["all_five_names_on_cover"] and checks["all_five_authors_in_metadata"] and checks["all_sections_present"]
    and checks["embedded_graphs"] == 7 and checks["overfull_boxes"] == 0
    and not checks["undefined_references_or_citations"] and checks["original_report_pdf_unchanged"])
save("report1-checks.json", json.dumps(checks, indent=2) + "\n")
print(json.dumps(checks, indent=2))
assert checks["pass"], "Inspect report1.log and report1-checks.json"
preview = OUT / "report1-preview"
preview.mkdir(exist_ok=True)
for file in preview.iterdir():
    if file.is_file() and re.fullmatch(r"(?:page-\d+|contact-\d+)\.png", file.name):
        file.unlink()
subprocess.run(["pdftoppm", "-scale-to", "1100", "-png", "report1.pdf", str(preview / "page")], cwd=OUT, check=True)
try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
if Image is not None:
    pages = sorted(preview.glob("page-*.png"))
    assert len(pages) == checks["pages"]
    for start in range(0, len(pages), 4):
        sheet = Image.new("RGB", (1560, 2240), "#cbd5dc")
        draw = ImageDraw.Draw(sheet)
        for offset, page in enumerate(pages[start:start + 4]):
            picture = Image.open(page).convert("RGB")
            picture.thumbnail((760, 1075))
            x, y = 10 + (offset % 2) * 780, 30 + (offset // 2) * 1120
            sheet.paste(picture, (x, y))
            draw.text((x + 6, y - 20), f"PDF page {start + offset + 1}", fill="black")
        sheet.save(preview / f"contact-{start // 4 + 1}.png")

# Extend the existing manifest without rebuilding or changing original evidence.
manifest = OUT / "SHA256SUMS"
entries = {}
for line in manifest.read_text().splitlines():
    digest, relative = line.split("  ", 1)
    entries[relative] = digest
variant_files = [OUT / "build_report1.py", *OUT.glob("report1*.tex"),
                 OUT / "report1.pdf", OUT / "report1-build.log",
                 OUT / "report1-checks.json", OUT / "report1-pdfinfo.txt"]
for file in variant_files:
    with file.open("rb") as content:
        entries[str(file.relative_to(OUT))] = hashlib.file_digest(content, "sha256").hexdigest()
manifest.write_text("\n".join(f"{entries[name]}  {name}" for name in sorted(entries)) + "\n")
subprocess.run(["sha256sum", "--check", "--quiet", "SHA256SUMS"], cwd=OUT, check=True)
print("PASS: report1 compiled, its measurements and references match, and all pages rendered")
