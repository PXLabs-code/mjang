"""只按向听数和有效进张选择弃牌的 mjai 基线 bot。"""

import json
import re
from collections import Counter
from typing import Any

from mahjong.shanten import Shanten


_SUIT_INDEX = {"m": 0, "p": 1, "s": 2}
_HONOR_INDEX = {"E": 27, "S": 28, "W": 29, "N": 30, "P": 31, "F": 32, "C": 33}
_TILE_PATTERN = re.compile(r"([0-9])([mps])r?")


def tile_index(tile: str) -> int:
    """Return a 0-33 tile index; red fives share their normal tile index."""
    if tile in _HONOR_INDEX:
        return _HONOR_INDEX[tile]
    match = _TILE_PATTERN.fullmatch(tile)
    if match is None:
        raise ValueError(f"unsupported mjai tile: {tile!r}")

    rank = int(match.group(1))
    suit = match.group(2)
    if rank == 0:
        rank = 5
    if rank < 1 or rank > 9:
        raise ValueError(f"invalid suited tile: {tile!r}")
    return _SUIT_INDEX[suit] * 9 + rank - 1


def hand_counts(tiles: list[str]) -> list[int]:
    counts = [0] * 34
    for tile in tiles:
        counts[tile_index(tile)] += 1
    return counts


class EfficiencyBot:
    def __init__(self, player_id: int) -> None:
        if player_id not in range(4):
            raise ValueError("player_id must be between 0 and 3")
        self.player_id = player_id
        self.hand: list[str] = []
        self.visible_counts = [0] * 34
        self.shanten = Shanten()

    def react(self, raw_events: str) -> dict[str, Any]:
        events = json.loads(raw_events)
        if not isinstance(events, list) or not events:
            raise ValueError("expected a non-empty JSON event list")

        for event in events:
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ValueError("each event must be an event object")
            self._update_state(event)

        event = events[-1]
        if event["type"] == "tsumo" and event.get("actor") == self.player_id:
            if len(self.hand) != 14:
                raise ValueError(f"expected 14 tiles on own turn, got {len(self.hand)}")
            drawn_tile = event.get("pai")
            if not isinstance(drawn_tile, str):
                raise ValueError("tsumo event must include a tile in 'pai'")
            discard = self._choose_discard()
            return {
                "type": "dahai",
                "actor": self.player_id,
                "pai": discard,
                "tsumogiri": discard == drawn_tile,
            }

        return {"type": "none"}

    def _update_state(self, event: dict[str, Any]) -> None:
        event_type = event["type"]
        if event_type == "start_kyoku":
            hands = event.get("tehais")
            if not isinstance(hands, list) or len(hands) != 4:
                raise ValueError("start_kyoku event must include four hands")
            hand = hands[self.player_id]
            if not isinstance(hand, list) or any(not isinstance(tile, str) for tile in hand):
                raise ValueError("own hand in start_kyoku must be a tile list")
            self.hand = hand.copy()
            self.visible_counts = [0] * 34
            marker = event.get("dora_marker")
            if isinstance(marker, str) and marker != "?":
                self._mark_visible(marker)
        elif event_type == "tsumo" and event.get("actor") == self.player_id:
            tile = event.get("pai")
            if isinstance(tile, str) and tile != "?":
                self.hand.append(tile)
        elif event_type == "dahai":
            tile = event.get("pai")
            if isinstance(tile, str) and tile != "?":
                self._mark_visible(tile)
                if event.get("actor") == self.player_id:
                    try:
                        self.hand.remove(tile)
                    except ValueError as error:
                        raise ValueError(f"discarded tile {tile!r} is not in own hand") from error
        elif event_type in {"chi", "pon", "daiminkan", "ankan", "kakan"}:
            for key in ("pai",):
                tile = event.get(key)
                if isinstance(tile, str) and tile != "?":
                    self._mark_visible(tile)
            consumed = event.get("consumed", [])
            if isinstance(consumed, list):
                for tile in consumed:
                    if isinstance(tile, str) and tile != "?":
                        self._mark_visible(tile)

    def _mark_visible(self, tile: str) -> None:
        self.visible_counts[tile_index(tile)] += 1

    def _choose_discard(self) -> str:
        own_counts = hand_counts(self.hand)
        cache: dict[tuple[int, ...], int] = {}

        def shanten_for(counts: list[int]) -> int:
            key = tuple(counts)
            if key not in cache:
                cache[key] = self.shanten.calculate_shanten(counts)
            return cache[key]

        best_score: tuple[int, int, int, str] | None = None
        best_tile: str | None = None
        seen_types: set[int] = set()

        for tile in self.hand:
            index = tile_index(tile)
            if index in seen_types:
                continue
            seen_types.add(index)

            after_discard = own_counts.copy()
            after_discard[index] -= 1
            current_shanten = shanten_for(after_discard)
            effective_draws = 0
            for draw_index in range(34):
                remaining = 4 - self.visible_counts[draw_index] - after_discard[draw_index]
                if remaining <= 0:
                    continue
                after_draw = after_discard.copy()
                after_draw[draw_index] += 1
                if shanten_for(after_draw) < current_shanten:
                    effective_draws += remaining

            score = (current_shanten, -effective_draws, index, tile)
            if best_score is None or score < best_score:
                best_score = score
                best_tile = tile

        if best_tile is None:
            raise ValueError("cannot choose a discard from an empty hand")
        return best_tile
