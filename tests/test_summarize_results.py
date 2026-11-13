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

            self.assertEqual(
                metrics["tsumogiri"],
                {
                    "matches": 1,
                    "placements": 4,
                    "average_rank": 2.5,
                    "first_rate": 0.25,
                    "fourth_rate": 0.25,
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
            ]
            for index, (bots, ranks) in enumerate(rotations):
                folder = root / f"rotation_{index}"
                folder.mkdir()
                (folder / "summary.json").write_text(
                    json.dumps({"rank": ranks, "kyoku": [{"error_info": None}]}),
                    encoding="utf-8",
                )
                (folder / "experiment.json").write_text(
                    json.dumps({"seat_bots": bots}), encoding="utf-8"
                )

            metrics = summarize([root], root / "results.csv", ["x"] * 4)

            self.assertEqual(metrics["baseline"]["average_rank"], 2.5)
            self.assertEqual(metrics["baseline"]["first_rate"], 0.5)
            self.assertEqual(metrics["baseline"]["fourth_rate"], 0.5)
            self.assertEqual(metrics["opponent"]["matches"], 2)
            self.assertEqual(metrics["opponent"]["placements"], 6)
            with (root / "results.csv").open(encoding="utf-8-sig", newline="") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 2)


if __name__ == "__main__":
    unittest.main()
