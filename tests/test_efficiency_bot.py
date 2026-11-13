import unittest

from mahjong_advisor.efficiency_bot import EfficiencyBot, hand_counts, tile_index


class EfficiencyBotTests(unittest.TestCase):
    def test_red_five_has_same_shanten_index_as_five(self) -> None:
        self.assertEqual(tile_index("5mr"), tile_index("5m"))
        self.assertEqual(tile_index("0m"), tile_index("5m"))

    def test_chooses_a_tile_from_own_hand(self) -> None:
        bot = EfficiencyBot(0)
        events = (
            '[{"type":"start_kyoku","dora_marker":"1p",'
            '"tehais":[["1m","2m","3m","4m","5m","6m","7p","8p","9p",'
            '"2s","3s","4s","E"],["?","?","?","?","?","?","?","?","?","?","?","?","?"],'
            '["?","?","?","?","?","?","?","?","?","?","?","?","?"],'
            '["?","?","?","?","?","?","?","?","?","?","?","?","?"]]},'
            '{"type":"tsumo","actor":0,"pai":"C"}]'
        )

        action = bot.react(events)

        self.assertEqual(action["type"], "dahai")
        self.assertIn(action["pai"], bot.hand)
        self.assertEqual(action["actor"], 0)
        self.assertFalse(action["tsumogiri"])

    def test_tracks_public_discards_and_ignores_hidden_draws(self) -> None:
        bot = EfficiencyBot(1)
        start = (
            '[{"type":"start_kyoku","dora_marker":"1p",'
            '"tehais":[["?","?","?","?","?","?","?","?","?","?","?","?","?"],'
            '["1m","2m","3m","4m","5m","6m","7p","8p","9p","2s","3s","4s","E"],'
            '["?","?","?","?","?","?","?","?","?","?","?","?","?"],'
            '["?","?","?","?","?","?","?","?","?","?","?","?","?"]]},'
            '{"type":"tsumo","actor":2,"pai":"?"},'
            '{"type":"dahai","actor":2,"pai":"E","tsumogiri":true}]'
        )

        bot.react(start)

        self.assertEqual(bot.visible_counts[tile_index("E")], 1)
        self.assertEqual(len(bot.hand), 13)

    def test_hand_counts_include_red_tiles(self) -> None:
        self.assertEqual(hand_counts(["5mr", "5m"])[tile_index("5m")], 2)


if __name__ == "__main__":
    unittest.main()
