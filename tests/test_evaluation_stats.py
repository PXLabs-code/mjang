import unittest

from tools.evaluation_stats import complete_rotation_groups, grouped_mean_interval


class EvaluationStatsTests(unittest.TestCase):
    def test_seed_groups_are_equally_weighted(self) -> None:
        result = grouped_mean_interval(
            {"seed-a": [1.0, 1.0, 1.0, 1.0], "seed-b": [3.0]},
            bootstrap_samples=100,
        )

        self.assertEqual(result["mean"], 2.0)
        self.assertEqual(result["groups"], 2)
        self.assertIsNotNone(result["lower_95"])
        self.assertIsNotNone(result["upper_95"])

    def test_single_seed_group_has_no_confidence_interval(self) -> None:
        result = grouped_mean_interval({"one-seed": [1.0, 4.0]})

        self.assertEqual(result["mean"], 2.5)
        self.assertEqual(result["groups"], 1)
        self.assertIsNone(result["lower_95"])
        self.assertIsNone(result["upper_95"])

    def test_requires_all_four_distinct_seat_rotations(self) -> None:
        rotations = {
            "complete": {
                ("advisor", "mortal", "mortal", "mortal"),
                ("mortal", "advisor", "mortal", "mortal"),
                ("mortal", "mortal", "advisor", "mortal"),
                ("mortal", "mortal", "mortal", "advisor"),
            },
            "incomplete": {
                ("advisor", "mortal", "mortal", "mortal"),
                ("mortal", "advisor", "mortal", "mortal"),
            },
        }

        self.assertEqual(complete_rotation_groups(rotations), {"complete"})


if __name__ == "__main__":
    unittest.main()
