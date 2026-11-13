import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from profile_game_timing import (  # noqa: E402
    parse_runner_log,
    profile_game,
    write_report,
)


class ProfileGameTimingTests(unittest.TestCase):
    def test_splits_request_time_from_container_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runner.log"
            log_path.write_text(
                "\n".join(
                    [
                        "2026-01-01 00:00:00.000 +00:00 | INFO | game - "
                        "Start docker container for player0",
                        "2026-01-01 00:00:00.500 +00:00 | INFO | game - "
                        "Done. Player 0 is ready!",
                        "2026-01-01 00:00:00.600 +00:00 | DEBUG | "
                        "mjai.player:react:100 - 0 <- b'[]'",
                        "2026-01-01 00:00:00.800 +00:00 | DEBUG | "
                        "mjai.player:react:110 - 0 -> {\"type\":\"none\"}",
                        "2026-01-01 00:00:02.000 +00:00 | INFO | game - "
                        "Delete player containers...",
                        "2026-01-01 00:00:02.500 +00:00 | INFO | game - "
                        "Delete player containers... DONE!",
                    ]
                ),
                encoding="utf-8",
            )

            timing = parse_runner_log(log_path, timeout_seconds=2.0)

        self.assertAlmostEqual(timing.startup_seconds, 0.5)
        self.assertAlmostEqual(timing.cleanup_seconds, 0.5)
        self.assertAlmostEqual(timing.request_seconds, 0.2)
        self.assertEqual(timing.request_count, 1)
        self.assertEqual(timing.response_count, 1)
        self.assertFalse(timing.errors)

    def test_profiles_inference_advisor_protocol_and_simulator_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir) / "game_0001"
            game_dir.mkdir()
            (game_dir / "experiment.json").write_text(
                json.dumps({"seat_bots": ["efficiency", "mortal", "mortal", "mortal"]}),
                encoding="utf-8",
            )
            (game_dir / "runner.log").write_text(
                "\n".join(
                    [
                        "2026-01-01 00:00:00.000 +00:00 | INFO | game - "
                        "Start docker container for player0",
                        "2026-01-01 00:00:00.500 +00:00 | INFO | game - "
                        "Done. Player 0 is ready!",
                        "2026-01-01 00:00:00.600 +00:00 | DEBUG | "
                        "mjai.player:react:100 - 0 <- b'[]'",
                        "2026-01-01 00:00:00.800 +00:00 | DEBUG | "
                        "mjai.player:react:110 - 0 -> {\"type\":\"none\"}",
                        "2026-01-01 00:00:02.000 +00:00 | INFO | game - "
                        "Delete player containers...",
                        "2026-01-01 00:00:02.500 +00:00 | INFO | game - "
                        "Delete player containers... DONE!",
                    ]
                ),
                encoding="utf-8",
            )
            (game_dir / "player_logs.1.stdout.txt").write_text(
                '{"type":"dahai","meta":{"eval_time_ns":100000000}}\n',
                encoding="utf-8",
            )
            (game_dir / "player_logs.0.stderr.txt").write_text(
                "ADVISOR_DECISION_NS=50000000\n",
                encoding="utf-8",
            )

            profile = profile_game(
                game_dir,
                {"wall_seconds": "3.0", "valid": "True"},
                timeout_seconds=2.0,
            )

        self.assertTrue(profile["timing_complete"])
        self.assertAlmostEqual(profile["mortal_inference_seconds"], 0.1)
        self.assertAlmostEqual(profile["advisor_decision_seconds"], 0.05)
        self.assertAlmostEqual(profile["protocol_seconds"], 0.05)
        self.assertAlmostEqual(profile["simulator_seconds"], 1.8)
        self.assertEqual(profile["mortal_inference_count"], 1)
        self.assertEqual(profile["advisor_decision_count"], 1)

    def test_uses_timeout_for_unmatched_request_and_marks_profile_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runner.log"
            log_path.write_text(
                "2026-01-01 00:00:00.000 +00:00 | DEBUG | "
                "mjai.player:react:100 - 2 <- b'[]'\n",
                encoding="utf-8",
            )

            timing = parse_runner_log(log_path, timeout_seconds=2.0)

        self.assertEqual(timing.unmatched_requests, 1)
        self.assertEqual(timing.request_seconds, 2.0)
        self.assertTrue(timing.errors)

    def test_report_calculates_each_component_share_of_wall_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            (logs_dir / "games.csv").write_text(
                "game,seed,valid,efficiency_rank,mortal_ranks\n"
                "game_0001,3000,True,2,\"1,2,3\"\n",
                encoding="utf-8",
            )
            row = {
                "game": "game_0001",
                "seed_group": "3000",
                "wall_seconds": 2.0,
                "mortal_inference_seconds": 0.5,
                "advisor_decision_seconds": 0.25,
                "container_startup_seconds": 0.2,
                "container_cleanup_seconds": 0.1,
                "protocol_seconds": 0.45,
                "simulator_seconds": 0.5,
                "container_protocol_seconds": 0.75,
                "timing_complete": True,
                "timing_error": "",
                "valid": "True",
            }

            summary = write_report(logs_dir, [row])

        self.assertAlmostEqual(
            summary["component_share_of_wall"]["mortal_inference_seconds"], 0.25
        )
        self.assertAlmostEqual(
            summary["component_share_of_wall"]["advisor_decision_seconds"], 0.125
        )
        self.assertAlmostEqual(
            summary["component_share_of_wall"]["container_protocol_seconds"], 0.375
        )
        self.assertAlmostEqual(
            summary["component_share_of_wall"]["simulator_seconds"], 0.25
        )


if __name__ == "__main__":
    unittest.main()
