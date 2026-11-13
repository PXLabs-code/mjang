import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from summarize_results import summarize  # noqa: E402


class SummarizeResultsTests(unittest.TestCase):
    def test_summarizes_existing_first_game_by_bot_name(self) -> None:
        logs = ROOT / "logs" / "first_game"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "results.csv"
            metrics = summarize(
                [logs],
                output,
                ["tsumogiri"] * 4,
            )

            self.assertEqual(metrics["valid_matches"], 1)
            self.assertEqual(metrics["invalid_matches"], 0)
            self.assertEqual(metrics["attempted_seed_groups"], 1)
            self.assertEqual(metrics["seed_groups"], 0)
            self.assertEqual(metrics["incomplete_rotation_groups"], 1)
            self.assertEqual(
                metrics["bots"]["tsumogiri"],
                {
                    "matches": 1,
                    "placements": 4,
                    "seed_groups": 0,
                    "estimate_basis": (
                        "descriptive only; no complete four-seat rotation"
                    ),
                    "average_rank": 2.5,
                    "average_rank_ci_95": [None, None],
                    "first_rate": 0.25,
                    "first_rate_ci_95": [None, None],
                    "fourth_rate": 0.25,
                    "fourth_rate_ci_95": [None, None],
                },
            )
            with output.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["seat_0_rank"], "1")

    def test_aggregates_rank_by_bot_across_rotated_seats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rotations = [
                (["baseline", "opponent", "opponent", "opponent"], [1, 2, 3, 4]),
                (["opponent", "baseline", "opponent", "opponent"], [1, 4, 2, 3]),
                (["opponent", "opponent", "baseline", "opponent"], [1, 3, 2, 4]),
                (["opponent", "opponent", "opponent", "baseline"], [1, 2, 4, 3]),
            ]
            for index, (bots, ranks) in enumerate(rotations):
                folder = root / f"rotation_{index}"
                folder.mkdir()
                (folder / "summary.json").write_text(
                    json.dumps({"rank": ranks, "kyoku": [{"error_info": None}]}),
                    encoding="utf-8",
                )
                (folder / "experiment.json").write_text(
                    json.dumps({"seat_bots": bots, "seed": [10000, 42]}),
                    encoding="utf-8",
                )

            metrics = summarize([root], root / "results.csv", ["x"] * 4)

            self.assertEqual(metrics["bots"]["baseline"]["average_rank"], 2.5)
            self.assertEqual(metrics["bots"]["baseline"]["first_rate"], 0.25)
            self.assertEqual(metrics["bots"]["baseline"]["fourth_rate"], 0.25)
            self.assertEqual(metrics["bots"]["baseline"]["seed_groups"], 1)
            self.assertEqual(metrics["bots"]["opponent"]["matches"], 4)
            self.assertEqual(metrics["bots"]["opponent"]["placements"], 12)
            self.assertEqual(metrics["valid_matches"], 4)
            self.assertEqual(metrics["seed_groups"], 1)
            self.assertEqual(metrics["bots"]["baseline"]["seed_groups"], 1)
            self.assertEqual(
                metrics["bots"]["baseline"]["average_rank_ci_95"],
                [None, None],
            )
            with (root / "results.csv").open(encoding="utf-8-sig", newline="") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 4)

    def test_marks_invalid_matches_and_excludes_them_from_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid = root / "valid"
            valid.mkdir()
            (valid / "summary.json").write_text(
                json.dumps({"rank": [1, 2, 3, 4], "kyoku": [{"error_info": None}]}),
                encoding="utf-8",
            )
            (valid / "experiment.json").write_text(
                json.dumps(
                    {
                        "seat_bots": ["baseline", "mortal", "mortal", "mortal"],
                        "seed": [10000, 7],
                    }
                ),
                encoding="utf-8",
            )
            invalid = root / "invalid"
            invalid.mkdir()
            (invalid / "experiment.json").write_text(
                json.dumps({"seat_bots": ["baseline", "x", "x", "x"]}),
                encoding="utf-8",
            )
            (invalid / "errors.json").write_text('[{"error_type":"timeout"}]')

            report = summarize([root], root / "results.csv", ["x"] * 4)

            self.assertEqual(report["attempted_matches"], 2)
            self.assertEqual(report["valid_matches"], 1)
            self.assertEqual(report["invalid_matches"], 1)
            self.assertEqual(report["bots"]["baseline"]["average_rank"], 1.0)
            with (root / "results.csv").open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {row["game"]: row["valid"] for row in rows},
                {str(valid): "True", str(invalid): "False"},
            )


if __name__ == "__main__":
    unittest.main()
