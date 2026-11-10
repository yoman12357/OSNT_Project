"""Regression checks for evidence parsing and RLI validation.

Run: python -m unittest discover -s experiments -p 'test_*.py' -v
"""

import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plot_cwnd import METRICS, parse_qlog
from experiments.validate_rli import time_weighted_average, validate


def sample(time, cwnd, **changes):
    value = dict.fromkeys(METRICS, None)
    value.update(time=time, path_id=0, cwnd=cwnd, bytes_in_flight=1200,
                 rli_max_flight_size=15360, rli_cwnd_limit=30720,
                 rli_capped=0, rli_reset_count=0)
    value.update(changes)
    return value


class ResultValidationTest(unittest.TestCase):
    def growth(self):
        return [sample(0, 15360), sample(1, 30720, rli_capped=1)]

    def test_bounded_growth_exercises_cap(self):
        errors, counters = validate(self.growth(), require_cap=True)
        self.assertEqual(errors, [])
        self.assertEqual(counters["cwnd_increases"], 1)
        self.assertEqual(counters["cap_active_samples"], 1)

    def test_cap_violation_is_rejected(self):
        values = self.growth()
        values[-1]["cwnd"] += 1
        self.assertTrue(validate(values)[0])

    def test_ack_reduction_without_reset_is_rejected(self):
        values = self.growth() + [sample(2, 20000)]
        errors, _ = validate(values)
        self.assertTrue(any("decreased without resetting" in error for error in errors))

    def test_reset_counter_survives_rebuilt_flight(self):
        values = self.growth() + [sample(2, 20000, rli_reset_count=1)]
        errors, counters = validate(values, expect_reduction=True)
        self.assertEqual(errors, [])
        self.assertEqual(counters["maxfs_resets"], 1)

    def test_old_log_reduction_without_reset_is_rejected(self):
        values = self.growth() + [sample(2, 20000)]
        for value in values:
            value.pop("rli_reset_count")
        self.assertTrue(validate(values)[0])

    def test_peak_between_qlog_snapshots_is_retained(self):
        values = self.growth() + [sample(2, 20000, rli_max_flight_size=0,
                                         rli_reset_count=1)]
        values.append(sample(3, 20000, bytes_in_flight=5000,
                             rli_max_flight_size=6000, rli_reset_count=1))
        errors, counters = validate(values)
        self.assertEqual(errors, [])
        self.assertEqual(counters["unobserved_peak_intervals"], 1)
        values[-1]["rli_max_flight_size"] = 4000
        self.assertTrue(validate(values)[0])

    def test_no_growth_cannot_pass_validation(self):
        self.assertTrue(validate([sample(0, 15360), sample(1, 15360)])[0])

    def test_time_weighted_average(self):
        values = [sample(0, 10), sample(1, 20), sample(10, 30)]
        self.assertEqual(time_weighted_average(values, "cwnd"), 19)

    def test_gzip_units_integer_precision_and_path_isolation(self):
        maximum = 2**64 - 1
        events = [[0, 0, "recovery", "metrics_updated", {"cwnd": 15360}],
                  [1, 1, "recovery", "metrics_updated", {"cwnd": 5000}],
                  [2, 0, "recovery", "metrics_updated", {"rli_max_flight_size": maximum}]]
        text = '{"configuration":{"time_units":"ms"}}\n'
        text += "\n".join(json.dumps(event) + "," for event in events)
        with tempfile.TemporaryDirectory() as directory:
            plain = Path(directory) / "trace.qlog"
            plain.write_text(text)
            compressed = Path(directory) / "trace.qlog.gz"
            with gzip.open(compressed, "wt") as output:
                output.write(text)
            parsed = parse_qlog(plain, 0)
            self.assertEqual(parsed, parse_qlog(compressed, 0))
            self.assertEqual(parsed[-1]["time"], 0.002)
            self.assertEqual(parsed[-1]["cwnd"], 15360)
            self.assertEqual(parsed[-1]["rli_max_flight_size"], maximum)
            self.assertEqual(parsed[0]["app_limited"], 0)


if __name__ == "__main__":
    unittest.main()
