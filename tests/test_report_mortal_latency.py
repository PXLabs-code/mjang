import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from report_mortal_latency import collect_latencies  # noqa: E402


class ReportMortalLatencyTests(unittest.TestCase):
    def test_reads_mortal_latency_only_for_mortal_seats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "experiment.json").write_text(
                json.dumps({"seat_bots": ["mortal", "baseline", "mortal", "baseline"]}),
                encoding="utf-8",
            )
            for seat, values in ((0, [10_000_000, 20_000_000]), (2, [30_000_000])):
                (folder / f"player_logs.{seat}.stdout.txt").write_text(
                    "".join(
                        json.dumps({"type": "dahai", "meta": {"eval_time_ns": value}})
                        + "\n"
                        for value in values
                    ),
                    encoding="utf-8",
                )
            (folder / "player_logs.1.stdout.txt").write_text(
                '{"type":"none","meta":{"eval_time_ns":999999999}}\n',
                encoding="utf-8",
            )

            self.assertEqual(collect_latencies(folder), [10.0, 20.0, 30.0])


if __name__ == "__main__":
    unittest.main()
