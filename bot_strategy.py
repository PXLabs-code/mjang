"""mjai adapter for efficiency discard selection and automatic riichi."""

import json
import sys
from typing import Any

from mjai import Bot

from mahjong_advisor.core import hand_counts, tile_index
from mahjong_advisor.efficiency_strategy import EfficiencyStrategy


class EfficiencyRiichiBot(Bot):
    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.strategy = EfficiencyStrategy()
        self.fixed_melds = 0
        self.pending_riichi_discard: str | None = None

    def react(self, input_str: str) -> str:
        events: Any = json.loads(input_str)
        if not isinstance(events, list):
            raise ValueError("expected an event list")
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("each event must be an object")
            event_type = event.get("type")
            if event_type == "start_kyoku":
                self.fixed_melds = 0
                self.pending_riichi_discard = None
            elif (
                event.get("actor") == self.player_id
                and event_type in {"chi", "pon", "daiminkan", "ankan"}
            ):
                self.fixed_melds += 1
        return super().react(input_str)

    def think(self) -> str:
        if self.can_tsumo_agari:
            return self.action_tsumo_agari()
        if self.can_ron_agari:
            return self.action_ron_agari()

        if self.pending_riichi_discard is not None:
            if not self.can_discard:
                return self.action_nothing()
            tile = self.pending_riichi_discard
            self.pending_riichi_discard = None
            return self.action_discard(tile)

        if self.can_riichi:
            decision = self._decide_discard(riichi_available=True)
            self.pending_riichi_discard = decision.discard_tile
            return self.action_riichi()

        if self.can_discard:
            decision = self._decide_discard(riichi_available=False)
            return self.action_discard(decision.discard_tile)

        return self.action_nothing()

    def _decide_discard(self, riichi_available: bool):
        hand = self.tehai_mjai
        held_counts = hand_counts(hand)
        visible_counts = [0] * 34
        for tile, count in self.tiles_seen.items():
            visible_counts[tile_index(tile)] = count
        for index, held in enumerate(held_counts):
            visible_counts[index] -= held

        return self.strategy.decide(
            hand,
            visible_counts,
            fixed_melds=self.fixed_melds,
            riichi_available=riichi_available,
        )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python bot.py PLAYER_ID")
    bot = EfficiencyRiichiBot(int(sys.argv[1]))
    bot.start()


if __name__ == "__main__":
    main()
