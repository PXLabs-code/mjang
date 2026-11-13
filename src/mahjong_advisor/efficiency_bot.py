"""只按向听数和有效进张选择弃牌的 mjai 基线 bot。"""

import json
from typing import Any

from .core import HandAnalyzer, hand_counts, tile_index


class EfficiencyBot:
    def __init__(self, player_id: int) -> None:
        if player_id not in range(4):
            raise ValueError("player_id must be between 0 and 3")
        self.player_id = player_id
        self.hand: list[str] = []
        self.visible_counts = [0] * 34
        self.analyzer = HandAnalyzer()

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
            if event_type == "kakan":
                tile = event.get("pai")
                if isinstance(tile, str) and tile != "?":
                    self._mark_visible(tile)
            consumed = event.get("consumed", [])
            if isinstance(consumed, list) and event_type != "kakan":
                for tile in consumed:
                    if isinstance(tile, str) and tile != "?":
                        self._mark_visible(tile)

    def _mark_visible(self, tile: str) -> None:
        self.visible_counts[tile_index(tile)] += 1

    def _choose_discard(self) -> str:
        own_counts = hand_counts(self.hand)

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
            current_shanten = self.analyzer.calculate_shanten(after_discard)
            effective_draws = sum(
                remaining
                for _, remaining in self.analyzer.effective_draws(
                    after_discard, self.visible_counts
                )
            )

            score = (current_shanten, -effective_draws, index, tile)
            if best_score is None or score < best_score:
                best_score = score
                best_tile = tile

        if best_tile is None:
            raise ValueError("cannot choose a discard from an empty hand")
        return best_tile
