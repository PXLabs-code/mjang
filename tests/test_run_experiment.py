import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_experiment  # noqa: E402


class RunExperimentTests(unittest.TestCase):
    @patch("run_experiment.mjai.Simulator")
    def test_rotations_reuse_seed_and_preserve_distinct_seat_mappings(
        self, simulator
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            arguments = ["run_experiment.py"]
            for index in range(4):
                arguments.extend(["--submission", f"bot_{index}.zip"])
            for index in range(4):
                arguments.extend(["--bot-name", f"bot_{index}"])
            arguments.extend(
                [
                    "--logs-dir",
                    str(logs_dir),
                    "--rotate",
                    "--seed",
                    "4321",
                    "--port-base",
                    "28100",
                ]
            )

            with patch.object(sys, "argv", arguments):
                run_experiment.main()

            self.assertEqual(simulator.call_count, 4)
            for call in simulator.call_args_list:
                self.assertEqual(call.kwargs["seed"], (10000, 4321))
                self.assertEqual(call.kwargs["port"], 28100)
            for seat in range(4):
                metadata = json.loads(
                    (logs_dir / f"rotation_{seat}" / "experiment.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(metadata["seed"], [10000, 4321])
                self.assertEqual(
                    metadata["seat_bots"],
                    [f"bot_{(seat + offset) % 4}" for offset in range(4)],
                )


if __name__ == "__main__":
    unittest.main()
