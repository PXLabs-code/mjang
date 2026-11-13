import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mahjong_advisor.bot import TsumogiriBot  # noqa: E402


class TsumogiriBotTests(unittest.TestCase):
    def test_discards_drawn_tile_on_own_turn(self) -> None:
        bot = TsumogiriBot(2)

        action = bot.react('[{"type":"tsumo","actor":2,"pai":"5mr"}]')

        self.assertEqual(
            action,
            {"type": "dahai", "actor": 2, "pai": "5mr", "tsumogiri": True},
        )

    def test_declines_action_when_another_player_draws(self) -> None:
        bot = TsumogiriBot(2)

        self.assertEqual(
            bot.react('[{"type":"tsumo","actor":1,"pai":"1m"}]'),
            {"type": "none"},
        )

    def test_rejects_empty_or_invalid_events(self) -> None:
        bot = TsumogiriBot(0)

        for raw_events in ("[]", "not-json"):
            with self.subTest(raw_events=raw_events):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    bot.react(raw_events)

    def test_rejects_invalid_player_id(self) -> None:
        with self.assertRaises(ValueError):
            TsumogiriBot(4)


if __name__ == "__main__":
    unittest.main()
