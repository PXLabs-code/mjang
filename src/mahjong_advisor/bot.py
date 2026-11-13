"""最小 mjai 摸切 bot，用于验证输入输出协议。"""

import json
from typing import Any


class TsumogiriBot:
    def __init__(self, player_id: int) -> None:
        if player_id not in range(4):
            raise ValueError("player_id must be between 0 and 3")
        self.player_id = player_id

    def react(self, raw_events: str) -> dict[str, Any]:
        events = json.loads(raw_events)
        if not isinstance(events, list) or not events:
            raise ValueError("expected a non-empty JSON event list")

        event = events[-1]
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError("the last event must be an event object")

        if event["type"] == "tsumo" and event.get("actor") == self.player_id:
            pai = event.get("pai")
            if not isinstance(pai, str):
                raise ValueError("tsumo event must include a tile in 'pai'")
            return {
                "type": "dahai",
                "actor": self.player_id,
                "pai": pai,
                "tsumogiri": True,
            }

        return {"type": "none"}
