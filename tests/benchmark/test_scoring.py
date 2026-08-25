import unittest

from benchmark.tracks.closeness import (
    aggregate_closeness,
    frame_key,
    score_frame_closeness,
)


ARTIFACT = {
    "trace": [
        {
            "frame_key": frame_key([[0, 2]]),
            "closeness": 0.0,
            "remaining_actions": 2,
        },
        {
            "frame_key": frame_key([[2, 0]]),
            "closeness": 0.5,
            "remaining_actions": 1,
        },
    ]
}


class ClosenessScoringTests(unittest.TestCase):
    def test_saved_solution_trace_state_has_exact_closeness(self):
        score = score_frame_closeness(
            ARTIFACT, [[2, 0]], completed=False
        )

        self.assertTrue(score["available"])
        self.assertEqual(score["closeness"], 0.5)
        self.assertEqual(score["remaining_actions"], 1)
        self.assertEqual(score["basis"], "replay_verified_solution_trace")

    def test_completed_level_is_always_100_percent(self):
        score = score_frame_closeness(
            ARTIFACT, [[9, 9]], completed=True
        )

        self.assertTrue(score["available"])
        self.assertEqual(score["percent"], 100.0)
        self.assertEqual(score["basis"], "level_completed")

    def test_off_trace_state_is_unavailable_not_zero(self):
        score = score_frame_closeness(
            ARTIFACT, [[8, 8]], completed=False
        )

        self.assertFalse(score["available"])
        self.assertIsNone(score["closeness"])
        self.assertEqual(score["basis"], "off_saved_solution_trace")

    def test_aggregate_excludes_unavailable_games_and_reports_coverage(self):
        result = aggregate_closeness(
            [
                {
                    "alias": "a",
                    "closeness": score_frame_closeness(
                        ARTIFACT, [[2, 0]], completed=False
                    ),
                },
                {
                    "alias": "b",
                    "closeness": score_frame_closeness(
                        ARTIFACT, [[8, 8]], completed=False
                    ),
                },
            ]
        )

        self.assertEqual(result["summary"]["mean_level_closeness"], 0.5)
        self.assertEqual(result["summary"]["coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
