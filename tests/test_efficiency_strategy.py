import unittest

from mahjong_advisor.efficiency_bot import EfficiencyBot
from mahjong_advisor.efficiency_strategy import EfficiencyStrategy


class EfficiencyStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = EfficiencyStrategy()
        self.hand = [
            "1m",
            "2m",
            "3m",
            "1p",
            "2p",
            "3p",
            "1s",
            "2s",
            "3s",
            "4s",
            "5s",
            "E",
            "E",
            "C",
        ]
        self.visible = [0] * 34

    def test_non_riichi_discard_matches_efficiency_baseline(self) -> None:
        baseline = EfficiencyBot(0)
        baseline.hand = self.hand.copy()
        baseline.visible_counts = self.visible.copy()

        decision = self.strategy.decide(self.hand, self.visible)

        self.assertEqual(decision.discard_tile, baseline._choose_discard())
        self.assertFalse(decision.declare_riichi)

    def test_selects_tenpai_discard_when_riichi_is_available(self) -> None:
        decision = self.strategy.decide(
            self.hand, self.visible, riichi_available=True
        )

        self.assertEqual(decision.discard_tile, "C")
        self.assertEqual(decision.shanten, 0)
        self.assertTrue(decision.declare_riichi)

    def test_does_not_declare_riichi_when_it_is_unavailable(self) -> None:
        decision = self.strategy.decide(self.hand, self.visible)

        self.assertEqual(decision.shanten, 0)
        self.assertFalse(decision.declare_riichi)

    def test_rejects_riichi_when_no_discard_reaches_tenpai(self) -> None:
        hand = [
            "1m",
            "4m",
            "7m",
            "2p",
            "5p",
            "8p",
            "3s",
            "6s",
            "9s",
            "E",
            "S",
            "W",
            "N",
            "C",
        ]

        with self.assertRaisesRegex(ValueError, "no tenpai discard"):
            self.strategy.decide(hand, self.visible, riichi_available=True)

    def test_rejects_invalid_fixed_meld_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "fixed_melds"):
            self.strategy.decide(self.hand, self.visible, fixed_melds=5)


if __name__ == "__main__":
    unittest.main()
