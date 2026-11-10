#!/usr/bin/env python3
"""Analyze phase boundaries, controller state, CA caps, and burst completion."""

import argparse
from bisect import bisect_right
import csv
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plot_cwnd import parse_qlog
from experiments.validate_rli import time_weighted_average, validate


def event_parts(event):
    if len(event) >= 5 and isinstance(event[1], (int, float)):
        return event[0], event[2], event[3], event[4]
    return event[0], event[1], event[2], event[3]


def read_trace(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        trace = json.load(stream)["traces"][0]
    units = trace.get("configuration", {}).get("time_units", "us")
    divisor = {"s": 1, "ms": 1000, "us": 1_000_000, "ns": 1_000_000_000}[units]
    events = []
    for event in trace["events"]:
        time, category, name, data = event_parts(event)
        events.append((time / divisor, category, name, data))
    return trace["description"], events


def merge_range(ranges, start, end):
    """Retain unique stream-byte ranges, including out-of-order arrivals."""
    merged = []
    for left, right in sorted(ranges + [(start, end)]):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    return merged


def stream_evidence(events, event_name, expected):
    streams = {}
    for time, category, name, data in events:
        if category != "transport" or name != event_name:
            continue
        for frame in data.get("frames", []):
            if frame.get("frame_type") != "stream":
                continue
            sid = int(frame["id"])
            item = streams.setdefault(sid, {"first_time": time, "last_time": time,
                "fin_time": None, "complete_time": None, "ranges": [], "unique_bytes": 0})
            offset, length = int(frame.get("offset", 0)), int(frame.get("length", 0))
            item["last_time"] = time
            if length:
                item["ranges"] = merge_range(item["ranges"], offset, offset + length)
            if frame.get("fin", False) and item["fin_time"] is None:
                item["fin_time"] = time
            item["unique_bytes"] = sum(right - left for left, right in item["ranges"])
            if (sid in expected and item["complete_time"] is None and item["fin_time"] is not None
                    and item["ranges"] and item["ranges"][0][0] == 0
                    and item["ranges"][0][1] >= expected[sid]):
                item["complete_time"] = time
    return streams


def state_at(changes, time):
    index = bisect_right([entry[0] for entry in changes], time) - 1
    return changes[index][1] if index >= 0 else 0


def clip_samples(samples, start, end):
    assert start < end
    index = bisect_right([s["time"] for s in samples], start) - 1
    if index < 0:
        raise ValueError("No metric sample before phase start")
    result = [dict(samples[index], time=start)]
    result += [s for s in samples[index + 1:] if start < s["time"] < end]
    result.append(dict(result[-1], time=end))
    return result


def phase_cap_errors(samples, mtu):
    """Check CA candidate limits, without forcing an existing window down."""
    errors = []
    for previous, current in zip(samples, samples[1:]):
        maxfs, limit = current["rli_max_flight_size"], current["rli_cwnd_limit"]
        if maxfs is None or limit is None:
            errors.append("Missing CA RLI metrics")
            continue
        if limit != min(2**64 - 1, maxfs + mtu):
            errors.append(f'At {current["time"]:.6f}: CA limit is not maxFS + send MTU')
        if current["cwnd"] > previous["cwnd"] and current["cwnd"] > limit:
            errors.append(f'At {current["time"]:.6f}: CA growth exceeded the recorded cap')
    return errors


def performance(path):
    with path.open() as file:
        rows = list(csv.DictReader(file, skipinitialspace=True))
    assert len(rows) == 1
    return {key.strip(): value.strip() for key, value in rows[0].items()}


def analyze_run(directory, collection, mode, repetition):
    expected = {0: collection["warmup_bytes"],
                4: collection["limited_frames"] * collection["limited_frame_bytes"],
                8: collection["burst_bytes"]}
    server_path = next(directory.glob("*.server.qlog.gz"))
    client_path = next(directory.glob("*.client.qlog.gz"))
    server_id, server = read_trace(server_path)
    client_id, client = read_trace(client_path)
    assert server_id == client_id, "Client and server logs are not one connection"
    requests = stream_evidence(server, "packet_received", {})
    transmitted = stream_evidence(server, "packet_sent", expected)
    received = stream_evidence(client, "packet_received", expected)
    client_requests = stream_evidence(client, "packet_sent", {})
    assert set(requests) == set(transmitted) == set(received) == set(expected), "Expected exactly three dependent streams"
    for sid, size in expected.items():
        assert transmitted[sid]["unique_bytes"] == received[sid]["unique_bytes"] == size
        assert transmitted[sid]["complete_time"] is not None and received[sid]["complete_time"] is not None
    # Dependency proof in one clock domain: each new request follows completion
    # of the preceding response at the client. No cross-host clock subtraction.
    assert client_requests[4]["first_time"] >= received[0]["complete_time"]
    assert client_requests[8]["first_time"] >= received[4]["complete_time"]
    changes = [(0.0, 0)] + [(time, int(data["new"])) for time, category, name, data in server
                            if category == "recovery" and name == "congestion_state_updated"]
    samples = parse_qlog(server_path)
    for item in samples:
        item["cc_state"] = state_at(changes, item["time"])
    phases = {phase: {"request_received": requests[sid]["first_time"],
                      "first_payload_sent": transmitted[sid]["first_time"],
                      "last_payload_sent": transmitted[sid]["complete_time"],
                      "stream_id": sid, "bytes": expected[sid]}
              for phase, sid in (("warmup", 0), ("limited", 4), ("burst", 8))}
    low_start = phases["limited"]["first_payload_sent"]
    low_end = phases["limited"]["last_payload_sent"]
    interior_start, interior_end = low_start + .5, low_end - .5
    window = clip_samples(samples, interior_start, interior_end)
    actual = [s for s in samples if interior_start <= s["time"] <= interior_end]
    assert len(actual) > 10
    errors = []
    if state_at(changes, phases["limited"]["request_received"]) != 2:
        errors.append("Limited phase did not start in congestion avoidance")
    if any(s["cc_state"] != 2 for s in window):
        errors.append("Controller left congestion avoidance during the limited interior")
    if any(state != 2 for time, state in changes if interior_start <= time <= interior_end):
        errors.append("A raw state transition left CA during the limited interior")
    limited_fraction = time_weighted_average(window, "app_limited")
    if limited_fraction is None or limited_fraction < .8:
        errors.append("The low-rate interior was not predominantly application limited")
    perf = performance(directory / "server-performance.csv")
    client_perf = performance(directory / "client-performance.csv")
    assert int(client_perf["Received"]) >= sum(expected.values())
    counters = {}
    if mode == "rli":
        whole_errors, counters = validate(samples, expect_reduction=True)
        errors.extend(whole_errors)
        errors.extend(phase_cap_errors(window, int(perf["max_mtu_sent"])))
    cap_count = sum(s["rli_capped"] == 1 for s in actual) if mode == "rli" else 0
    burst_duration = received[8]["complete_time"] - client_requests[8]["first_time"]
    assert burst_duration > 0
    row = {"mode": mode, "repetition": repetition, "connection_id": server_id,
        "limited_seconds": low_end - low_start, "limited_interior_seconds": interior_end - interior_start,
        "ca_state_at_limited_start": state_at(changes, phases["limited"]["request_received"]),
        "limited_cwnd_start_bytes": window[0]["cwnd"], "limited_cwnd_end_bytes": window[-1]["cwnd"],
        "limited_cwnd_growth_bytes": window[-1]["cwnd"] - window[0]["cwnd"],
        "limited_cwnd_mean_bytes": time_weighted_average(window, "cwnd"),
        "limited_flight_mean_bytes": time_weighted_average(window, "bytes_in_flight"),
        "limited_app_limited_fraction": limited_fraction,
        "limited_srtt_mean_ms": time_weighted_average(window, "smoothed_rtt") / 1000,
        "limited_cap_active_samples": cap_count,
        "limited_cap_time_fraction": time_weighted_average(window, "rli_capped") if mode == "rli" else 0,
        "burst_request_to_completion_seconds": burst_duration,
        "burst_payload_rate_mbps": collection["burst_bytes"] * 8 / burst_duration / 1e6,
        "server_retransmissions_whole_connection": int(perf["retrans."]),
        "all_three_streams_complete": True, "validation_errors": errors,
        "ca_cap_exercised": cap_count > 0 if mode == "rli" else None,
        "phases": phases, "cc_state_changes": changes, "whole_trace_counters": counters}
    return row, samples


def plot_run(row, samples, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    for axis, zoom in zip(axes, (False, True)):
        axis.plot([s["time"] for s in samples], [s["cwnd"]/1024 for s in samples], label="cwnd")
        axis.plot([s["time"] for s in samples], [s["bytes_in_flight"]/1024 for s in samples],
                  color="gray", alpha=.6, linewidth=.7, label="bytes in flight")
        if row["mode"] == "rli":
            for metric, color, label in (("rli_max_flight_size", "green", "maxFS"),
                                         ("rli_cwnd_limit", "red", "RLI limit")):
                axis.plot([s["time"] for s in samples], [(s[metric] or 0)/1024 for s in samples],
                          color=color, linestyle="--", linewidth=.8, label=label)
        for (name, phase), color in zip(row["phases"].items(), ("#dae8f5", "#e2efda", "#ffe2c2")):
            axis.axvspan(phase["request_received"], phase["last_payload_sent"], color=color, alpha=.3,
                         label=name if not zoom else None)
        if zoom:
            phase = row["phases"]["limited"]
            axis.set_xlim(phase["first_payload_sent"] + .5, phase["last_payload_sent"] - .5)
            interior = clip_samples(samples, *axis.get_xlim())
            values = [s["cwnd"]/1024 for s in interior]
            if row["mode"] == "rli":
                values += [s["rli_cwnd_limit"]/1024 for s in interior]
            margin = max(1, (max(values)-min(values))*.15)
            axis.set_ylim(min(values)-margin, max(values)+margin)
            axis.set_title("Congestion-avoidance limited phase: window-only zoom (different Y scale)")
        else:
            axis.set_title(f'{row["mode"]}, repetition {row["repetition"]}: one connection, three phases')
        axis.set(xlabel="Time since server connection start (s)", ylabel="Window / flight (KiB)")
        axis.grid(alpha=.25)
        axis.legend(fontsize=8, ncol=4)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def comparison_plots(rows, collection, out):
    import matplotlib.pyplot as plt
    for repetition in sorted({r["repetition"] for r in rows}):
        pair = [r for r in rows if r["repetition"] == repetition]
        if {r["mode"] for r in pair} != {"baseline", "rli"}:
            continue
        fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
        for row, color in zip(sorted(pair, key=lambda r:r["mode"]), ("#406882", "#2e8b57")):
            directory = out / row["mode"] / f"run-{repetition}"
            samples = parse_qlog(next(directory.glob("*.server.qlog.gz")))
            low = row["phases"]["limited"]
            selected = clip_samples(samples, low["first_payload_sent"] + .5, low["last_payload_sent"] - .5)
            times = [s["time"]-low["first_payload_sent"] for s in selected]
            axes[0].plot(times, [s["cwnd"]/1024 for s in selected], color=color, label=row["mode"] + " cwnd")
            axes[1].plot(times, [(s["cwnd"]-selected[0]["cwnd"])/1024 for s in selected], color=color,
                         label=row["mode"] + " cwnd change")
            if row["mode"] == "rli":
                axes[0].plot(times, [s["rli_cwnd_limit"]/1024 for s in selected],
                             linestyle="--", color="#c44e52", label="RLI CA limit")
        for axis in axes:
            axis.set(xlabel="Time since limited phase begins (s)", ylabel="Window (KiB)")
            axis.grid(alpha=.25)
            axis.legend()
        axes[0].set_title(f"Repetition {repetition}: application-limited congestion avoidance, shared Y axis")
        axes[1].set_title("Change from the first interior sample; flat does not mean missing data")
        fig.savefig(out / "plots" / f"comparison-{repetition}.png", dpi=180)
        plt.close(fig)
    if {r["mode"] for r in rows} != {"baseline", "rli"}:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for axis, metric, scale, title, unit in (
        (axes[0], "limited_cwnd_mean_bytes", 1024,
         "Window inherited from warm-up (no limited-phase growth)" if all(r["limited_cwnd_growth_bytes"] == 0 for r in rows) else "CA-limited window",
         "Mean cwnd (KiB)"),
        (axes[1], "burst_request_to_completion_seconds", 1, f'{collection["burst_bytes"]/1024**2:g} MiB burst: lower is faster', "Request-to-completion (s)")):
        values = [[row[metric]/scale for row in rows if row["mode"] == mode] for mode in ("baseline", "rli")]
        means = [statistics.mean(v) for v in values]
        deviations = [statistics.stdev(v) if len(v)>1 else 0 for v in values]
        axis.bar(["baseline", "rli"], means, yerr=deviations, capsize=5, color=["#406882", "#2e8b57"])
        axis.set(title=title, ylabel=unit)
        axis.grid(axis="y", alpha=.2)
        axis.set_ylim(0, max(m+d for m,d in zip(means,deviations))*1.25)
        for i, value in enumerate(means):
            axis.text(i, value + deviations[i] + max(means)*.02, f"{value:.3f}", ha="center")
    fig.savefig(out / "plots/overview.png", dpi=180)
    plt.close(fig)


def write_summary(out, collection, summary):
    rows = summary["records"]
    lines = ["# Same-connection congestion-avoidance experiment", "",
        f'Each connection contains a {collection["warmup_bytes"]/1024**2:g} MiB bulk warm-up, a limited stream, and a {collection["burst_bytes"]/1024**2:g} MiB burst.',
        f'The limited stream sends {collection["limited_frames"]} frames of {collection["limited_frame_bytes"]} bytes at {collection["limited_fps"]} frames per second.',
        f'The nominal offered rate is {collection["limited_frame_bytes"]*collection["limited_fps"]*8/1000:g} kbit/s.',
        "All phases use one connection and the same CUBIC controller state.", "",
        "Access links: 1000 Mbit/s and 5 ms per direction. Core: 20 Mbit/s and 25 ms per direction.",
        "Nominal base RTT: 70 ms. The analysis excludes 0.5 seconds at both ends of the limited phase.", "",
        "## Checks and cap coverage", "",
        f'- Measurement and invariant checks: {"PASS" if summary["checks_pass"] else "FAIL"}.',
        f'- Cap exercised in every RLI limited interval: {"yes" if summary["ca_cap_exercised_in_all_rli_runs"] else "no"}.',
        f'- Overall coverage verdict: {summary["verdict"]}.', "",
        "The checker uses qlog congestion_state_updated events to verify CA state 2 before the limited phase.",
        "It verifies that state 2 persists throughout the measured limited interior.",
        "Stream IDs 0, 4, and 8 identify warm-up, limited traffic, and the burst.",
        "Client-side byte-range accounting confirms complete delivery and the dependency order.",
        "Duplicate or out-of-order frames cannot falsely complete a stream.", "",
        "## Per-run measurements", "",
        "| Mode | Run | CA at limited start | Limited cwnd change (bytes) | Active CA-cap samples | Burst completion (s) | Whole-connection retransmissions |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f'| {row["mode"]} | {row["repetition"]} | {row["ca_state_at_limited_start"]} | '
                     f'{row["limited_cwnd_growth_bytes"]} | {row["limited_cap_active_samples"]} | '
                     f'{row["burst_request_to_completion_seconds"]:.6f} | {row["server_retransmissions_whole_connection"]} |')
    lines += ["", "## Interpretation", "",
        "The CA formula check validates the implemented conservative ceiling, maxFS plus the sender MTU.",
        "It does not independently establish that this adaptation is the exact CUBIC limit required by the IETF draft.",
        "A passing bound check without an active cap does not prove the cap constrained growth.",
        "CUBIC may hold cwnd constant if its normal growth candidate does not exceed the existing window.",
        "Different window heights can be inherited from warm-up; they do not demonstrate new growth during congestion avoidance.",
        "A non-binding cap is a coverage limitation, not automatically an implementation failure.",
        "An existing window above a newly lower ceiling is not forcibly reduced by this growth limiter.", ""]
    if {r["mode"] for r in rows} == {"baseline", "rli"}:
        baseline = summary["groups"]["baseline"]["burst_request_to_completion_seconds"]["mean"]
        rli = summary["groups"]["rli"]["burst_request_to_completion_seconds"]["mean"]
        lines += [f"Mean burst completion: baseline {baseline:.6f} seconds; RLI {rli:.6f} seconds.",
                  f"Observed time change: {(rli/baseline-1)*100:+.3f}%. Negative means faster completion.",
                  "Three repetitions do not establish statistical significance or a general performance gain.", ""]
    lines += ["Burst completion uses the client's first request-packet timestamp and the timestamp of complete payload reception with FIN.",
        "Both timestamps use the same clock. This interval includes request latency and delivery, not just server sending time.",
        "The current final report and earlier 18-experiment campaign remain unchanged.", "",
        "## Files", "",
        "- plots/: full traces, limited-window zooms, paired comparisons, and the three-run overview where available.",
        "- measurements.csv: numeric per-run measurements.",
        "- summary.json: measurements, phase boundaries, state transitions, and validation errors.",
        "- collection.json: commands, source revisions, binary hashes, topology, and run order.",
        "- baseline/ and rli/: local compressed qlogs and per-run evidence; these raw directories are ignored by Git.",
        "- The parent folder's raw-evidence.tar.gz preserves the compressed traces for distribution.", ""]
    (out / "SUMMARY.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--require-ca-cap", action="store_true")
    args = parser.parse_args()
    out = args.campaign.resolve()
    collection = json.loads((out / "collection.json").read_text())
    assert collection["complete"]
    expected_count = collection["repetitions"] * (2 if collection["mode"] == "both" else 1)
    assert len(collection["runs"]) == expected_count
    plots = out / "plots"
    plots.mkdir(exist_ok=True)
    rows = []
    for run in collection["runs"]:
        mode, repetition = run["mode"], run["repetition"]
        directory = out / mode / f"run-{repetition}"
        row, samples = analyze_run(directory, collection, mode, repetition)
        rows.append(row)
        (directory / "analysis.json").write_text(json.dumps(row, indent=2) + "\n")
        plot_run(row, samples, plots / f"{mode}-{repetition}.png")
        print(f'{mode} {repetition}: CA={row["ca_state_at_limited_start"]}, '
              f'limited growth={row["limited_cwnd_growth_bytes"]} B, cap samples={row["limited_cap_active_samples"]}, '
              f'burst={row["burst_request_to_completion_seconds"]:.6f} s, errors={len(row["validation_errors"])}', flush=True)
    groups = {}
    metrics = ("limited_cwnd_growth_bytes", "limited_cwnd_mean_bytes", "limited_srtt_mean_ms",
               "burst_request_to_completion_seconds", "burst_payload_rate_mbps",
               "limited_cap_active_samples", "server_retransmissions_whole_connection")
    for mode in sorted({r["mode"] for r in rows}):
        selected = [r for r in rows if r["mode"] == mode]
        groups[mode] = {metric: {"mean": statistics.mean(r[metric] for r in selected),
            "sample_stddev": statistics.stdev(r[metric] for r in selected) if len(selected)>1 else None}
            for metric in metrics}
    checks_pass = all(not row["validation_errors"] for row in rows)
    ca_cap_exercised = all(r["ca_cap_exercised"] for r in rows if r["mode"] == "rli")
    verdict = "PASS" if checks_pass and ca_cap_exercised else (
        "INCOMPLETE: no active cap in some CA-limited intervals" if checks_pass else "FAIL: observed validation errors")
    summary = {"verdict": verdict, "checks_pass": checks_pass, "ca_cap_exercised_in_all_rli_runs": ca_cap_exercised,
               "completed_connections": len(rows), "complete_streams": len(rows)*3,
               "groups": groups, "records": rows,
               "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "scope": "Same-connection bulk, application-limited CA, then burst. This checks the implemented conservative CA ceiling, not independent standards conformance."}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fields = [key for key, value in rows[0].items() if not isinstance(value, (dict, list))]
    with (out / "measurements.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    comparison_plots(rows, collection, out)
    write_summary(out, collection, summary)
    print(verdict, flush=True)
    return 0 if checks_pass and (ca_cap_exercised or not args.require_ca_cap) else 1


if __name__ == "__main__":
    raise SystemExit(main())
