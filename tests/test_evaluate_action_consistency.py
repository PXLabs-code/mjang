import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.evaluate_action_consistency import (
    evaluate_logs,
    find_following_discard,
    sanitize_event,
    score_game,
)
from mahjong_advisor.efficiency_strategy import StrategyDecision


class EvaluateActionConsistencyTests(unittest.TestCase):
    def test_replay_does_not_carry_riichi_discard_to_mortal_branch(self) -> None:
        class FakeBot:
            def __init__(self, player_id: int) -> None:
                self.player_id = player_id
                self.calls = 0
                self.pending_riichi_discard = None
                self.last_decision = None
                self.tehai_mjai = ["1m"] * 4 + ["2m"] * 4 + ["3m"] * 4 + ["E", "E"]
                self.fixed_melds = 0

            def react(self, input_str: str) -> str:
                event = json.loads(input_str)[0]
                if event.get("type") == "tsumo" and event.get("actor") == self.player_id:
                    self.calls += 1
                    if self.pending_riichi_discard is not None:
                        action = {"type": "dahai", "pai": self.pending_riichi_discard}
                        self.pending_riichi_discard = None
                    else:
                        tile = "9p" if self.calls == 1 else "1m"
                        self.pending_riichi_discard = tile
                        self.last_decision = StrategyDecision(
                            discard_tile=tile,
                            shanten=0,
                            effective_draws=4,
                            declare_riichi=True,
                        )
                        action = {"type": "reach"}
                    return json.dumps(action)
                return json.dumps({"type": "none"})

        events = [
            {"type": "start_kyoku", "tehais": [["1m"] * 13 for _ in range(4)]},
            {"type": "tsumo", "actor": 0, "pai": "1m"},
            {"type": "dahai", "actor": 0, "pai": "1m"},
            {"type": "tsumo", "actor": 0, "pai": "1m"},
            {"type": "dahai", "actor": 0, "pai": "1m"},
        ]
        with patch(
            "tools.evaluate_action_consistency.RecordingEfficiencyBot", FakeBot
        ):
            rows, skipped = score_game("sample", "[1,2]", events, [0])

        self.assertEqual(skipped, {})
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["assistant_tile"] for row in rows], ["9p", "1m"])

    def test_confidence_intervals_use_only_complete_rotation_groups(self) -> None:
        rotations = [
            (["efficiency", "mortal", "mortal", "mortal"], [1, 2, 3, 4]),
            (["mortal", "efficiency", "mortal", "mortal"], [1, 4, 2, 3]),
            (["mortal", "mortal", "efficiency", "mortal"], [1, 3, 2, 4]),
            (["mortal", "mortal", "mortal", "efficiency"], [1, 2, 4, 3]),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, (bots, ranks) in enumerate(rotations + [rotations[0]]):
                group_seed = 7 if index < 4 else 8
                game_dir = root / f"game_{index:04d}"
                game_dir.mkdir()
                (game_dir / "experiment.json").write_text(
                    json.dumps({"seat_bots": bots, "seed": [10000, group_seed]}),
                    encoding="utf-8",
                )
                (game_dir / "summary.json").write_text(
                    json.dumps({"rank": ranks, "kyoku": [{"error_info": None}]}),
                    encoding="utf-8",
                )
                (game_dir / "mjai_log.json").write_text(
                    '{"type":"start_game"}\n', encoding="utf-8"
                )

            def fake_score_game(game, group_id, events, seats):
                self.assertTrue(events)
                self.assertTrue(seats)
                return (
                    [
                        {
                            "game": game,
                            "seed_group": group_id,
                            "exact_match": True,
                            "tile_type_match": True,
                            "turn_phase": "early",
                            "opponent_riichi": False,
                            "assistant_tenpai": False,
                            "mortal_tenpai": False,
                        }
                    ],
                    {},
                )

            with patch(
                "tools.evaluate_action_consistency.score_game", fake_score_game
            ):
                report, _ = evaluate_logs(root)

        self.assertEqual(report["valid_games"], 5)
        self.assertEqual(report["attempted_seed_groups"], 2)
        self.assertEqual(report["seed_groups"], 1)
        self.assertEqual(report["incomplete_rotation_groups"], 1)
        self.assertEqual(report["decision_samples"], 5)
        self.assertEqual(report["inferential_decision_samples"], 4)
        overall = report["agreement"]["overall"]
        self.assertEqual(overall["exact_tile_agreement"]["mean"], 1.0)
        self.assertEqual(overall["seed_groups"], 1)

    def test_sanitizes_other_players_private_hands_and_draws(self) -> None:
        start = {
            "type": "start_kyoku",
            "tehais": [["1m"] * 13, ["2m"] * 13, ["3m"] * 13, ["4m"] * 13],
            "dora_marker": "E",
            "meta": {"private": True},
        }
        draw = {"type": "tsumo", "actor": 2, "pai": "5mr", "meta": {"q": [1]}}

        safe_start = sanitize_event(start, player_id=2)
        safe_draw = sanitize_event(draw, player_id=2)

        self.assertEqual(safe_start["tehais"][2], ["3m"] * 13)
        self.assertEqual(safe_start["tehais"][0], ["?"] * 13)
        self.assertNotIn("meta", safe_start)
        self.assertEqual(safe_draw["pai"], "5mr")
        self.assertNotIn("meta", safe_draw)
        self.assertEqual(sanitize_event(draw, player_id=1)["pai"], "?")
        self.assertEqual(draw["pai"], "5mr")

    def test_pairs_riichi_discard_but_ignores_non_discard_actions(self) -> None:
        events = [
            {"type": "tsumo", "actor": 1},
            {"type": "reach", "actor": 1},
            {"type": "reach_accepted", "actor": 1},
            {"type": "dahai", "actor": 1, "pai": "E"},
        ]
        self.assertEqual(
            find_following_discard(events, 0, 1),
            {"type": "dahai", "actor": 1, "pai": "E"},
        )

        events[1] = {"type": "ankan", "actor": 1}
        self.assertIsNone(find_following_discard(events, 0, 1))


if __name__ == "__main__":
    unittest.main()
