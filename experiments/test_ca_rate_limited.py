"""Checks for same-connection phase analysis and cap-coverage reporting."""

import unittest
from experiments.analyze_ca_rate_limited import (
    clip_samples, merge_range, phase_cap_errors, state_at, stream_evidence)
from experiments.run_ca_rate_limited import scenario


def packet(time, event, offset, length, fin=False):
    return (time, "transport", event, {"frames": [{"frame_type": "stream", "id": 8,
        "offset": offset, "length": length, "fin": fin}]})


class CAExperimentTest(unittest.TestCase):
    def test_scenario_dependencies_and_one_limited_stream(self):
        text = scenario(20971520, 400, 5242880)
        self.assertEqual(text, "=warm:397:20971520;=limited:=warm:s20:n400:1200:G400:I1200;=burst:=limited:397:5242880;")

    def test_merge_unique_bytes_and_gap(self):
        self.assertEqual(merge_range([(0, 100), (200, 300)], 50, 250), [(0, 300)])
        self.assertEqual(merge_range([(100, 200)], 300, 400), [(100, 200), (300, 400)])

    def test_completion_waits_for_missing_bytes_not_early_fin(self):
        evidence = stream_evidence([packet(1, "packet_received", 100, 100, True),
                                   packet(2, "packet_received", 0, 100)], "packet_received", {8: 200})
        self.assertEqual(evidence[8]["fin_time"], 1)
        self.assertEqual(evidence[8]["complete_time"], 2)
        self.assertEqual(evidence[8]["unique_bytes"], 200)

    def test_duplicate_bytes_do_not_inflate_completion(self):
        evidence = stream_evidence([packet(1, "packet_received", 0, 100),
                                   packet(2, "packet_received", 0, 100, True)], "packet_received", {8: 200})
        self.assertEqual(evidence[8]["unique_bytes"], 100)
        self.assertIsNone(evidence[8]["complete_time"])

    def test_state_at_boundary_includes_transition(self):
        changes = [(0, 0), (.6, 2)]
        self.assertEqual(state_at(changes, .5), 0)
        self.assertEqual(state_at(changes, .6), 2)

    def test_window_clipping_carries_previous_sample(self):
        values = [{"time": 0, "cwnd": 10}, {"time": 2, "cwnd": 20}, {"time": 4, "cwnd": 30}]
        self.assertEqual(clip_samples(values, 1, 3),
                         [{"time": 1, "cwnd": 10}, {"time": 2, "cwnd": 20}, {"time": 3, "cwnd": 20}])

    def test_existing_window_above_new_cap_is_not_forced_down(self):
        values = [{"time": 0, "cwnd": 10000, "rli_max_flight_size": 1000, "rli_cwnd_limit": 2440},
                  {"time": 1, "cwnd": 10000, "rli_max_flight_size": 1000, "rli_cwnd_limit": 2440}]
        self.assertEqual(phase_cap_errors(values, 1440), [])
        values[1]["cwnd"] = 10001
        self.assertTrue(phase_cap_errors(values, 1440))

    def test_ca_formula_uses_additive_not_slow_start_cap(self):
        values = [{"time": 0, "cwnd": 1000, "rli_max_flight_size": 2000, "rli_cwnd_limit": 4000},
                  {"time": 1, "cwnd": 1200, "rli_max_flight_size": 2000, "rli_cwnd_limit": 4000}]
        self.assertTrue(phase_cap_errors(values, 1440))


if __name__ == "__main__":
    unittest.main()
