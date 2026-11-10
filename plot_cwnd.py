#!/usr/bin/env python3
"""Plot picoquic congestion metrics from a qlog file.

The script works with the Step 4 baseline logs and also understands the RLI
fields produced by the Step 6 implementation. qlog metrics are deltas, so the
parser carries the last value of every metric forward.

Usage:
    python3 plot_cwnd.py <sender.qlog> [output.png]
"""

import argparse
import gzip
import json
import os
import re
import sys


METRICS = (
    "cwnd",
    "bytes_in_flight",
    "app_limited",
    "rli_max_flight_size",
    "rli_cwnd_limit",
    "rli_capped",
    "rli_reset_count",
    "latest_rtt",
    "smoothed_rtt",
    "min_rtt",
)


def open_qlog(path):
    """Read either a plain qlog or a losslessly compressed retained trace."""
    opener = gzip.open if str(path).endswith(".gz") else open
    return opener(path, "rt", encoding="utf-8", errors="strict")


def detect_time_divisor(path):
    """Return the number of qlog time units per second."""
    with open_qlog(path) as qlog_file:
        preamble = qlog_file.read(2000)
    match = re.search(r'"time_units"\s*:\s*"(s|ms|us|ns)"', preamble)
    if match:
        return {"s": 1.0, "ms": 1_000.0, "us": 1_000_000.0,
                "ns": 1_000_000_000.0}[match.group(1)]
    return 1_000_000.0


def parse_qlog(path, selected_path=None):
    """Return per-path snapshots for recovery:metrics_updated events.

    Picoquic can emit either the usual four-element qlog event or a
    five-element event containing a numeric path/flow ID after the timestamp.
    State is maintained independently for every path so delta events from
    multipath traces cannot contaminate each other.
    """
    divisor = detect_time_divisor(path)
    states = {}
    samples = []

    with open_qlog(path) as qlog_file:
        for raw_line in qlog_file:
            line = raw_line.strip().rstrip(",")
            if not line.startswith("["):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not (isinstance(event, list) and len(event) >= 4):
                continue

            if len(event) >= 5 and isinstance(event[1], (int, float)):
                raw_time, path_id, category, name, data = event[:5]
            else:
                raw_time, category, name, data = event[:4]
                path_id = 0

            if category != "recovery" or name != "metrics_updated":
                continue
            if not isinstance(data, dict):
                continue
            if selected_path is not None and path_id != selected_path:
                continue

            state = states.setdefault(
                path_id, {metric: None for metric in METRICS}
            )
            # The qlog writer's delta cache starts at zero for these fields.
            # An omitted first zero therefore means false/zero, not unknown.
            for metric in ("app_limited", "rli_capped", "bytes_in_flight"):
                if state[metric] is None:
                    state[metric] = 0

            for metric in METRICS:
                if metric in data:
                    # Preserve uint64 values exactly for overflow validation.
                    state[metric] = data[metric]

            if state["cwnd"] is not None:
                sample = dict(state)
                sample["time"] = float(raw_time) / divisor
                sample["path_id"] = path_id
                samples.append(sample)

    return sorted(samples, key=lambda sample: (sample["time"], sample["path_id"]))


def kib(value):
    return value / 1024.0


def plot_metrics(samples, output_path):
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "matplotlib is required; run: python3 -m pip install -r "
            "experiments/requirements.txt"
        ) from error

    path_ids = sorted({sample["path_id"] for sample in samples})
    if len(path_ids) != 1:
        raise RuntimeError(
            "qlog contains multiple paths; select one with --path-id "
            + ",".join(str(path_id) for path_id in path_ids)
        )

    times = [sample["time"] for sample in samples]
    cwnd = [kib(sample["cwnd"]) for sample in samples]
    has_rli = any(sample["rli_cwnd_limit"] is not None for sample in samples)

    figure, axis = plt.subplots(figsize=(11, 5.5))
    axis.plot(times, cwnd, label="cwnd", color="#1f77b4", linewidth=1.3)

    if any(sample["bytes_in_flight"] is not None for sample in samples):
        flight = [
            kib(sample["bytes_in_flight"] or 0.0) for sample in samples
        ]
        axis.plot(
            times,
            flight,
            label="bytes in flight",
            color="#7f7f7f",
            linewidth=0.9,
            alpha=0.75,
        )

    if has_rli:
        max_flight = [
            kib(sample["rli_max_flight_size"] or 0.0) for sample in samples
        ]
        limit = [kib(sample["rli_cwnd_limit"] or 0.0) for sample in samples]
        axis.plot(times, max_flight, label="RLI maxFS", color="#2ca02c")
        axis.plot(
            times,
            limit,
            label="RLI cwnd limit",
            color="#d62728",
            linestyle="--",
        )

        capped_times = [
            sample["time"] for sample in samples if sample["rli_capped"] == 1
        ]
        capped_cwnd = [
            kib(sample["cwnd"])
            for sample in samples
            if sample["rli_capped"] == 1
        ]
        if capped_times:
            axis.scatter(
                capped_times,
                capped_cwnd,
                label="RLI cap active",
                color="#d62728",
                marker="x",
                s=18,
                zorder=3,
            )

    axis.set_title(
        "Picoquic CUBIC congestion metrics"
        + (" with Rate-Limited Increase" if has_rli else " (baseline)")
    )
    axis.set_xlabel("Time (seconds)")
    axis.set_ylabel("Window / flight size (KiB)")
    axis.grid(True, linestyle="--", alpha=0.5)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=300)
    plt.close(figure)

    print(f"Saved plot to: {output_path}")
    print(
        f"cwnd range: min={min(cwnd):.1f} KiB, max={max(cwnd):.1f} KiB, "
        f"avg={sum(cwnd) / len(cwnd):.1f} KiB, duration={times[-1]:.2f} s"
    )
    if has_rli:
        capped_count = sum(sample["rli_capped"] == 1 for sample in samples)
        print(f"RLI cap-active samples: {capped_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Plot picoquic congestion metrics from a sender qlog."
    )
    parser.add_argument("qlog", help="sender qlog")
    parser.add_argument("output", nargs="?", default="cubic_cwnd.png")
    parser.add_argument(
        "--path-id", type=int, default=None,
        help="path ID to plot when the qlog contains multiple paths",
    )
    args = parser.parse_args()

    qlog_path = args.qlog
    output_path = args.output
    if not os.path.isfile(qlog_path):
        print(f"Error: {qlog_path} not found")
        return 1

    samples = parse_qlog(qlog_path, args.path_id)
    print(f"Extracted {len(samples)} congestion metric samples")
    if not samples:
        print("Error: no recovery:metrics_updated samples containing cwnd found")
        return 1

    try:
        plot_metrics(samples, output_path)
    except RuntimeError as error:
        print(f"Error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
