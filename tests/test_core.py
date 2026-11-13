import unittest

from mahjong_advisor.core import (
    HandAnalyzer,
    Tile,
    calculate_shanten,
    hand_counts,
    tile_index,
)


def hand_counts_from_parts(
    man: str = "", pin: str = "", sou: str = "", honors: str = ""
) -> list[int]:
    indices = {
        **{f"{rank}m": rank - 1 for rank in range(1, 10)},
        **{f"{rank}p": rank + 8 for rank in range(1, 10)},
        **{f"{rank}s": rank + 17 for rank in range(1, 10)},
        **{
            tile: 27 + index
            for index, tile in enumerate(("E", "S", "W", "N", "P", "F", "C"))
        },
    }
    counts = [0] * 34
    for tile in man:
        counts[indices[f"{tile}m"]] += 1
    for tile in pin:
        counts[indices[f"{tile}p"]] += 1
    for tile in sou:
        counts[indices[f"{tile}s"]] += 1
    for tile in honors:
        counts[indices[tile]] += 1
    return counts


class TileTests(unittest.TestCase):
    def test_red_fives_keep_identity_but_share_normal_tile_index(self) -> None:
        red_five = Tile.from_mjai("0m")

        self.assertEqual(red_five, Tile.from_mjai("5mr"))
        self.assertTrue(red_five.red)
        self.assertEqual(red_five.to_mjai(), "5mr")
        self.assertEqual(tile_index(red_five), tile_index("5m"))
        self.assertEqual(hand_counts(["5m", "5mr"])[4], 2)

    def test_rejects_non_five_red_and_invalid_tile_codes(self) -> None:
        for tile in ("1mr", "0z", "10m", "X"):
            with self.subTest(tile=tile), self.assertRaises(ValueError):
                Tile.from_mjai(tile)


class HandAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = HandAnalyzer()

    def test_reports_regular_chiitoitsu_and_kokushi_shanten(self) -> None:
        regular = hand_counts_from_parts(
            man="123", pin="123", sou="123", honors="EEESS"
        )
        chiitoitsu = hand_counts_from_parts(man="11223344556677")
        kokushi = hand_counts_from_parts(
            man="19", pin="19", sou="19", honors="EESWNPFC"
        )

        self.assertEqual(self.analyzer.shanten_values(regular).minimum, -1)
        self.assertEqual(self.analyzer.shanten_values(chiitoitsu).chiitoitsu, -1)
        self.assertEqual(self.analyzer.shanten_values(kokushi).kokushi, -1)
        self.assertEqual(calculate_shanten(regular), -1)

    def test_open_melds_disable_closed_hand_special_shapes(self) -> None:
        counts = hand_counts_from_parts(
            man="123", pin="123", sou="123", honors="E"
        )

        result = self.analyzer.shanten_values(counts, open_melds=1)

        self.assertIsNone(result.chiitoitsu)
        self.assertIsNone(result.kokushi)

    def test_counts_only_tiles_that_reduce_shanten(self) -> None:
        tenpai = hand_counts_from_parts(
            man="123", pin="123", sou="12345", honors="EE"
        )
        visible = [0] * 34
        visible[23] = 2

        self.assertEqual(
            self.analyzer.effective_draws(tenpai, visible),
            [(20, 3), (23, 2)],
        )

    def test_rejects_invalid_count_shapes_and_visible_tiles(self) -> None:
        with self.assertRaises(ValueError):
            self.analyzer.calculate_shanten([0] * 33)

        counts = [0] * 34
        counts[0] = 5
        with self.assertRaises(ValueError):
            self.analyzer.calculate_shanten(counts)

        hand = hand_counts_from_parts(
            man="123", pin="123", sou="12345", honors="EE"
        )
        visible = [0] * 34
        visible[20] = 4
        with self.assertRaises(ValueError):
            self.analyzer.effective_draws(hand, visible)


if __name__ == "__main__":
    unittest.main()
