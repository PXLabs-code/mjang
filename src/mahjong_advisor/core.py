"""Tile and hand-analysis primitives shared by the advice strategies."""

import re
from dataclasses import dataclass
from typing import Sequence

from mahjong.shanten import Shanten


_SUITS = ("m", "p", "s")
_HONORS = ("E", "S", "W", "N", "P", "F", "C")
_HONOR_INDEX = {tile: 27 + index for index, tile in enumerate(_HONORS)}
_RED_FIVE_INDICES = {4, 13, 22}
_TILE_PATTERN = re.compile(r"([0-9])([mps])(r?)")


@dataclass(frozen=True)
class Tile:
    """A physical tile, retaining red-five identity alongside its 34-type index."""

    index: int
    red: bool = False

    def __post_init__(self) -> None:
        if type(self.index) is not int or not 0 <= self.index < 34:
            raise ValueError(f"tile index must be between 0 and 33: {self.index!r}")
        if self.red and self.index not in _RED_FIVE_INDICES:
            raise ValueError("only suited fives can be red")

    @classmethod
    def from_mjai(cls, code: str) -> "Tile":
        if not isinstance(code, str):
            raise ValueError(f"tile code must be a string: {code!r}")
        if code in _HONOR_INDEX:
            return cls(_HONOR_INDEX[code])

        match = _TILE_PATTERN.fullmatch(code)
        if match is None:
            raise ValueError(f"unsupported mjai tile: {code!r}")
        rank = int(match.group(1))
        suit = match.group(2)
        red = rank == 0 or bool(match.group(3))
        if rank == 0:
            rank = 5
        if not 1 <= rank <= 9:
            raise ValueError(f"invalid suited tile: {code!r}")
        if red and rank != 5:
            raise ValueError(f"only fives can be red: {code!r}")
        return cls(_SUITS.index(suit) * 9 + rank - 1, red)

    def to_mjai(self) -> str:
        if self.index >= 27:
            return _HONORS[self.index - 27]
        suit = _SUITS[self.index // 9]
        rank = self.index % 9 + 1
        if self.red:
            return f"5{suit}r"
        return f"{rank}{suit}"


def tile_index(tile: str | Tile) -> int:
    return tile.index if isinstance(tile, Tile) else Tile.from_mjai(tile).index


def hand_counts(tiles: Sequence[str | Tile]) -> list[int]:
    counts = [0] * 34
    for tile in tiles:
        counts[tile_index(tile)] += 1
    return counts


def _validated_counts(counts: Sequence[int]) -> tuple[int, ...]:
    if len(counts) != 34:
        raise ValueError(f"expected 34 tile counts, got {len(counts)}")
    if any(type(count) is not int or not 0 <= count <= 4 for count in counts):
        raise ValueError("tile counts must be integers between 0 and 4")
    if sum(counts) > 14:
        raise ValueError("a concealed hand cannot contain more than 14 tiles")
    return tuple(counts)


def _validated_visible_counts(counts: Sequence[int]) -> tuple[int, ...]:
    if len(counts) != 34:
        raise ValueError(f"expected 34 visible counts, got {len(counts)}")
    if any(type(count) is not int or not 0 <= count <= 4 for count in counts):
        raise ValueError("visible counts must be integers between 0 and 4")
    return tuple(counts)


@dataclass(frozen=True)
class ShantenValues:
    regular: int
    chiitoitsu: int | None
    kokushi: int | None

    @property
    def minimum(self) -> int:
        values = [self.regular]
        if self.chiitoitsu is not None:
            values.append(self.chiitoitsu)
        if self.kokushi is not None:
            values.append(self.kokushi)
        return min(values)


class HandAnalyzer:
    def __init__(self) -> None:
        self._calculator = Shanten()
        self._cache: dict[tuple[tuple[int, ...], int], ShantenValues] = {}

    def shanten_values(
        self, counts: Sequence[int], open_melds: int = 0
    ) -> ShantenValues:
        hand = _validated_counts(counts)
        if type(open_melds) is not int or not 0 <= open_melds <= 4:
            raise ValueError("open_melds must be an integer between 0 and 4")
        if open_melds and sum(hand) not in (
            13 - 3 * open_melds,
            14 - 3 * open_melds,
        ):
            raise ValueError("concealed tile count does not match open_melds")

        key = (hand, open_melds)
        if key not in self._cache:
            tiles = list(hand)
            self._cache[key] = ShantenValues(
                regular=self._calculator.calculate_shanten_for_regular_hand(tiles),
                chiitoitsu=(
                    self._calculator.calculate_shanten_for_chiitoitsu_hand(tiles)
                    if open_melds == 0
                    else None
                ),
                kokushi=(
                    self._calculator.calculate_shanten_for_kokushi_hand(tiles)
                    if open_melds == 0
                    else None
                ),
            )
        return self._cache[key]

    def calculate_shanten(
        self, counts: Sequence[int], open_melds: int = 0
    ) -> int:
        return self.shanten_values(counts, open_melds).minimum

    def effective_draws(
        self,
        counts: Sequence[int],
        visible_counts: Sequence[int],
        open_melds: int = 0,
    ) -> list[tuple[int, int]]:
        hand = _validated_counts(counts)
        visible = _validated_visible_counts(visible_counts)
        self.shanten_values(hand, open_melds)
        if sum(hand) != 13 - 3 * open_melds:
            raise ValueError("effective-draw calculation requires a 13-tile hand")
        if any(held + shown > 4 for held, shown in zip(hand, visible)):
            raise ValueError("hand and visible counts exceed four copies of a tile")

        current_shanten = self.calculate_shanten(hand, open_melds)
        draws: list[tuple[int, int]] = []
        for index, held in enumerate(hand):
            remaining = 4 - held - visible[index]
            if remaining <= 0:
                continue
            after_draw = list(hand)
            after_draw[index] += 1
            if self.calculate_shanten(after_draw, open_melds) < current_shanten:
                draws.append((index, remaining))
        return draws


def calculate_shanten(counts: Sequence[int], open_melds: int = 0) -> int:
    return HandAnalyzer().calculate_shanten(counts, open_melds)
