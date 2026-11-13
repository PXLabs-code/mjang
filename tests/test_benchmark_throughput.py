import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from benchmark_throughput import (  # noqa: E402
    memory_mib,
    parse_docker_stats,
    run_game,
)


class BenchmarkThroughputTests(unittest.TestCase):
    def test_converts_docker_memory_units(self) -> None:
        self.assertEqual(memory_mib("512MiB / 4GiB"), 512)
        self.assertEqual(memory_mib("1GiB / 4GiB"), 1024)

    def test_sums_only_containers_not_running_before_the_benchmark(self) -> None:
        output = (
            "existing123|20.00%|100MiB / 4GiB\n"
            "newcontainer|125.00%|512MiB / 4GiB\n"
        )

        cpu_cores, memory_mib_total, active = parse_docker_stats(
            output, {"existing123"}
        )

        self.assertEqual((cpu_cores, memory_mib_total, active), (1.25, 512, 1))

    def test_rejects_malformed_docker_memory(self) -> None:
        with self.assertRaises(ValueError):
            memory_mib("512unknown / 4GiB")

    @patch("benchmark_throughput.subprocess.run")
    def test_records_simulation_errors_as_invalid_games(self, run_process) -> None:
        def finish_game(command, **_kwargs):
            game_dir = Path(command[command.index("--logs-dir") + 1])
            (game_dir / "experiment.json").write_text(
                json.dumps(
                    {"seat_bots": ["efficiency", "mortal", "mortal", "mortal"]}
                ),
                encoding="utf-8",
            )
            (game_dir / "summary.json").write_text(
                json.dumps({"rank": [1, 2, 3, 4], "kyoku": []}),
                encoding="utf-8",
            )
            (game_dir / "errors.json").write_text(
                json.dumps([{"error_type": "invalid"}]), encoding="utf-8"
            )
            (game_dir / "player_logs.1.stdout.txt").write_text(
                '{"type":"dahai","meta":{"eval_time_ns":1000000}}\n',
                encoding="utf-8",
            )
            for seat in (2, 3):
                (game_dir / f"player_logs.{seat}.stdout.txt").write_text(
                    "", encoding="utf-8"
                )
            return SimpleNamespace(returncode=0)

        run_process.side_effect = finish_game
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_game(
                1,
                3000,
                28090,
                Path(temp_dir),
                Path("efficiency.zip"),
                Path("mortal.zip"),
                "mortal:cpu",
                2.0,
            )

        self.assertFalse(result["valid"])
        self.assertEqual(result["simulation_errors"], 1)
        self.assertEqual(result["mortal_inference_count"], 1)


if __name__ == "__main__":
    unittest.main()
