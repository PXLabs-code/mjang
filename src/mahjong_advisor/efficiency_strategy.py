"""Discard selection and basic riichi decisions built on core hand analysis."""

from dataclasses import dataclass
from typing import Sequence

from .core import HandAnalyzer, hand_counts, tile_index


@dataclass(frozen=True)
class DiscardCandidate:
    tile: str
    shanten: int
    effective_draws: int


@dataclass(frozen=True)
class StrategyDecision:
    discard_tile: str
    shanten: int
    effective_draws: int
    declare_riichi: bool


class EfficiencyStrategy:
    def __init__(self) -> None:
        self.analyzer = HandAnalyzer()

    def discard_candidates(
        self,
        hand: Sequence[str],
        visible_counts: Sequence[int],
        fixed_melds: int = 0,
    ) -> list[DiscardCandidate]:
        if type(fixed_melds) is not int or not 0 <= fixed_melds <= 4:
            raise ValueError("fixed_melds must be an integer between 0 and 4")
        counts = hand_counts(hand)
        if sum(counts) != 14 - 3 * fixed_melds:
            raise ValueError("discard selection requires a 14-tile hand")

        candidates: list[tuple[tuple[int, int, int, str], DiscardCandidate]] = []
        seen_types: set[int] = set()
        for tile in hand:
            index = tile_index(tile)
            if index in seen_types:
                continue
            seen_types.add(index)

            after_discard = counts.copy()
            after_discard[index] -= 1
            shanten = self.analyzer.calculate_shanten(after_discard, fixed_melds)
            effective_draws = sum(
                remaining
                for _, remaining in self.analyzer.effective_draws(
                    after_discard, visible_counts, fixed_melds
                )
            )
            candidate = DiscardCandidate(tile, shanten, effective_draws)
            candidates.append(
                ((shanten, -effective_draws, index, tile), candidate)
            )

        if not candidates:
            raise ValueError("cannot choose a discard from an empty hand")
        candidates.sort(key=lambda item: item[0])
        return [candidate for _, candidate in candidates]

    def decide(
        self,
        hand: Sequence[str],
        visible_counts: Sequence[int],
        fixed_melds: int = 0,
        riichi_available: bool = False,
    ) -> StrategyDecision:
        candidates = self.discard_candidates(hand, visible_counts, fixed_melds)
        if riichi_available:
            tenpai = [candidate for candidate in candidates if candidate.shanten == 0]
            if not tenpai:
                raise ValueError("riichi is available but no tenpai discard was found")
            selected = tenpai[0]
        else:
            selected = candidates[0]

        return StrategyDecision(
            discard_tile=selected.tile,
            shanten=selected.shanten,
            effective_draws=selected.effective_draws,
            declare_riichi=riichi_available,
        )
