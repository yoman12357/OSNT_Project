#!/usr/bin/env python3
"""Validate RLI invariants and compare measured picoquic qlog runs."""

import argparse
import csv
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from plot_cwnd import parse_qlog


DEFAULT_INITIAL_CWND = 10 * 1536


def validate(samples, expect_reduction=False, require_cap=False,
             initial_cwnd=DEFAULT_INITIAL_CWND):
    """Return errors and counters derived only from observed qlog samples."""
    errors = []
    counters = {
        "samples": len(samples),
        "cwnd_increases": 0,
        "cwnd_reductions": 0,
        "maxfs_resets": 0,
        "maxfs_increases": 0,
        "cap_active_samples": 0,
    }

    if not samples:
        return ["qlog contains no congestion metric samples"], counters

    path_ids = sorted({sample["path_id"] for sample in samples})
    if len(path_ids) != 1:
        errors.append(
            "validation requires one path; select one path ID from: "
            + ", ".join(str(path_id) for path_id in path_ids)
        )
        return errors, counters

    rli_samples = [
        sample for sample in samples
        if sample["rli_max_flight_size"] is not None
        and sample["rli_cwnd_limit"] is not None
    ]
    if not rli_samples:
        errors.append("qlog does not contain both maxFS and RLI limit metrics")
        return errors, counters

    first_maxfs = rli_samples[0]["rli_max_flight_size"]
    if first_maxfs < initial_cwnd:
        errors.append(
            f"first observed maxFS {int(first_maxfs)} is below initcwnd "
            f"{initial_cwnd}"
        )

    previous = samples[0]
    for index, sample in enumerate(samples[1:], start=2):
        cwnd = sample["cwnd"]
        previous_cwnd = previous["cwnd"]
        limit = sample["rli_cwnd_limit"]
        maxfs = sample["rli_max_flight_size"]
        previous_maxfs = previous["rli_max_flight_size"]
        flight = sample["bytes_in_flight"]
        capped = sample["rli_capped"] == 1
        reduced = (
            cwnd is not None and previous_cwnd is not None
            and cwnd < previous_cwnd
        )

        if capped:
            counters["cap_active_samples"] += 1
            if limit is None:
                errors.append(f"sample {index}: cap flag set without an RLI limit")
            elif previous_cwnd is not None and cwnd > max(previous_cwnd, limit):
                errors.append(
                    f"sample {index}: capped cwnd {int(cwnd)} exceeds both the "
                    f"previous cwnd {int(previous_cwnd)} and limit {int(limit)}"
                )

        if cwnd is not None and previous_cwnd is not None:
            if cwnd > previous_cwnd:
                counters["cwnd_increases"] += 1
                if limit is None:
                    errors.append(
                        f"sample {index}: cwnd increased without an RLI limit"
                    )
                elif cwnd > limit:
                    errors.append(
                        f"sample {index}: cwnd {int(cwnd)} exceeds limit "
                        f"{int(limit)} during an increase"
                    )
            elif reduced:
                counters["cwnd_reductions"] += 1

        if maxfs is not None and previous_maxfs is not None:
            if maxfs < previous_maxfs:
                if reduced:
                    counters["maxfs_resets"] += 1
                else:
                    errors.append(
                        f"sample {index}: maxFS fell from {int(previous_maxfs)} "
                        f"to {int(maxfs)} without a visible cwnd reduction"
                    )
            elif maxfs > previous_maxfs:
                counters["maxfs_increases"] += 1

            if not reduced and flight is not None:
                expected_maxfs = max(previous_maxfs, flight)
                if maxfs != expected_maxfs:
                    errors.append(
                        f"sample {index}: maxFS {int(maxfs)} does not equal "
                        f"max(previous maxFS {int(previous_maxfs)}, "
                        f"FlightSize {int(flight)})"
                    )

        if maxfs is not None and flight is not None and not reduced and maxfs < flight:
            errors.append(
                f"sample {index}: maxFS {int(maxfs)} is below FlightSize "
                f"{int(flight)}"
            )

        previous = sample

    if counters["cwnd_increases"] == 0:
        errors.append("no cwnd increase was observed; the growth cap was not tested")
    if require_cap and counters["cap_active_samples"] == 0:
        errors.append("no active RLI cap was observed in a cap-required workload")
    if expect_reduction:
        if counters["cwnd_reductions"] == 0:
            errors.append("no cwnd reduction was observed in a reduction workload")
        if counters["maxfs_resets"] == 0:
            errors.append(
                "no maxFS reset was observed alongside a cwnd reduction"
            )

    return errors, counters


def time_weighted_average(samples, metric):
    usable = [sample for sample in samples if sample[metric] is not None]
    if not usable:
        return None
    if len(usable) == 1 or usable[-1]["time"] <= usable[0]["time"]:
        return usable[-1][metric]

    weighted = 0.0
    duration = usable[-1]["time"] - usable[0]["time"]
    for current, following in zip(usable, usable[1:]):
        weighted += current[metric] * (following["time"] - current["time"])
    return weighted / duration


def summarize(samples):
    cwnds = [sample["cwnd"] for sample in samples if sample["cwnd"] is not None]
    flights = [
        sample["bytes_in_flight"] for sample in samples
        if sample["bytes_in_flight"] is not None
    ]
    return {
        "duration_seconds": samples[-1]["time"] - samples[0]["time"],
        "cwnd_min_bytes": min(cwnds),
        "cwnd_max_bytes": max(cwnds),
        "cwnd_final_bytes": cwnds[-1],
        "cwnd_time_average_bytes": time_weighted_average(samples, "cwnd"),
        "flight_max_bytes": max(flights) if flights else None,
        "flight_time_average_bytes": time_weighted_average(
            samples, "bytes_in_flight"
        ),
        "app_limited_time_fraction": time_weighted_average(
            samples, "app_limited"
        ),
        "rli_capped_time_fraction": time_weighted_average(
            samples, "rli_capped"
        ),
    }


def print_counters(counters):
    print(", ".join(f"{key}={value}" for key, value in counters.items()))


def check_command(args):
    samples = parse_qlog(args.qlog, args.path_id)
    errors, counters = validate(
        samples,
        expect_reduction=args.expect_reduction,
        require_cap=args.require_cap,
        initial_cwnd=args.initial_cwnd,
    )
    print_counters(counters)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: observed RLI measurements satisfy the checked invariants")
    return 0


def compare_command(args):
    baseline = parse_qlog(args.baseline_qlog, args.path_id)
    rli = parse_qlog(args.rli_qlog, args.path_id)
    if not baseline or not rli:
        if not baseline:
            print("FAIL: baseline qlog contains no congestion samples")
        if not rli:
            print("FAIL: RLI qlog contains no congestion samples")
        return 1

    errors, counters = validate(
        rli,
        require_cap=args.workload == "rate-limited",
        initial_cwnd=args.initial_cwnd,
    )
    print_counters(counters)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    baseline_summary = summarize(baseline)
    rli_summary = summarize(rli)
    rows = []
    for metric, baseline_value in baseline_summary.items():
        rli_value = rli_summary[metric]
        if baseline_value is None or rli_value is None:
            delta = None
            percent = None
        else:
            delta = rli_value - baseline_value
            percent = (
                100.0 * delta / baseline_value if baseline_value != 0 else None
            )
        rows.append((metric, baseline_value, rli_value, delta, percent))

    print("metric,baseline,rli,delta,rli_change_percent")
    for row in rows:
        print(",".join(
            "" if value is None else
            value if isinstance(value, str) else
            f"{value:.6g}"
            for value in row
        ))

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as output_file:
            writer = csv.writer(output_file)
            writer.writerow(
                ["metric", "baseline", "rli", "delta", "rli_change_percent"]
            )
            writer.writerows(rows)
        print(f"Saved comparison to: {args.output}")

    print(
        "PASS: comparison uses observed values; it does not assume that a "
        "larger or smaller cwnd is inherently better"
    )
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Validate RLI qlogs or compare baseline and RLI runs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="validate one RLI qlog")
    check.add_argument("qlog")
    check.add_argument("--expect-reduction", action="store_true")
    check.add_argument("--require-cap", action="store_true")
    check.add_argument("--initial-cwnd", type=int, default=DEFAULT_INITIAL_CWND)
    check.add_argument("--path-id", type=int, default=None)
    check.set_defaults(handler=check_command)

    compare = subparsers.add_parser(
        "compare", help="compare measured baseline and RLI qlogs"
    )
    compare.add_argument("baseline_qlog")
    compare.add_argument("rli_qlog")
    compare.add_argument(
        "--workload", choices=("rate-limited", "bulk"), required=True
    )
    compare.add_argument("--output")
    compare.add_argument("--initial-cwnd", type=int, default=DEFAULT_INITIAL_CWND)
    compare.add_argument("--path-id", type=int, default=None)
    compare.set_defaults(handler=compare_command)
    return parser


def main():
    # Preserve the original one-positional-argument interface.
    arguments = sys.argv[1:]
    if arguments and arguments[0] not in ("check", "compare", "-h", "--help"):
        arguments.insert(0, "check")
    args = build_parser().parse_args(arguments)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
