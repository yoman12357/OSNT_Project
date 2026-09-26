#!/usr/bin/env python3
"""
Plot picoquic CUBIC cwnd evolution from a qlog file.

qlog format used by picoquic:
    Preamble declares "configuration": {"time_units": "us"} or "ms".
    Each event is a JSON array: [time, category, event_name, data_dict].
    cwnd is inside data_dict of "metrics_updated" events in the "recovery"
    category.

Usage:
    python3 plot_cwnd.py <server.qlog> [output.png]
"""
import sys
import json
import os
import matplotlib.pyplot as plt


def detect_time_divisor(path):
    """Return (seconds_divisor) based on 'time_units' in the qlog preamble."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        head = f.read(2000)
    if '"time_units": "ms"' in head:
        return 1_000.0
    if '"time_units": "us"' in head:
        return 1_000_000.0
    # picoquic default is microseconds
    return 1_000_000.0


def parse_qlog(path):
    """Extract (time_sec, cwnd_bytes) samples from a picoquic qlog file."""
    divisor = detect_time_divisor(path)
    print(f"Detected time unit divisor: {divisor:g}")

    times = []
    cwnds = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("["):
                continue
            line = line.rstrip(",")
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not (isinstance(ev, list) and len(ev) >= 4):
                continue
            t_raw = ev[0]
            category = ev[1]
            name = ev[2]
            data = ev[3]

            if category != "recovery" or name != "metrics_updated":
                continue
            if not isinstance(data, dict) or "cwnd" not in data:
                continue

            times.append(t_raw / divisor)
            cwnds.append(float(data["cwnd"]))

    return times, cwnds


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 plot_cwnd.py <server.qlog> [output.png]")
        sys.exit(1)

    qlog_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "cubic_cwnd.png"

    if not os.path.exists(qlog_path):
        print(f"Error: {qlog_path} not found")
        sys.exit(1)

    print(f"Parsing {qlog_path} ...")
    times, cwnds = parse_qlog(qlog_path)
    print(f"Extracted {len(cwnds)} cwnd samples")

    if not cwnds:
        print("ERROR: no cwnd samples found. Check the qlog format.")
        sys.exit(1)

    # Sort by time
    pairs = sorted(zip(times, cwnds))
    times = [p[0] for p in pairs]
    cwnds_kb = [p[1] / 1024.0 for p in pairs]

    plt.figure(figsize=(10, 5))
    plt.plot(times, cwnds_kb, label="CUBIC cwnd", color="#1f77b4", linewidth=1.2)
    plt.title("Picoquic CUBIC Congestion Window — Baseline (20 Mbps, 50 ms RTT)")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Congestion Window (KB)")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    print(f"Saved plot to: {out_path}")
    print(f"cwnd range: min={min(cwnds_kb):.1f} KB, max={max(cwnds_kb):.1f} KB, "
          f"avg={sum(cwnds_kb)/len(cwnds_kb):.1f} KB, "
          f"duration={times[-1]:.2f} s")


if __name__ == "__main__":
    main()
