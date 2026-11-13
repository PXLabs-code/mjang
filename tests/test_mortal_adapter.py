import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot_mortal import react  # noqa: E402


class FakeMortalBot:
    def __init__(self, reactions: list[str | None]) -> None:
        self.reactions = iter(reactions)
        self.events: list[dict[str, str]] = []

    def react(self, raw_event: str) -> str | None:
        self.events.append(json.loads(raw_event))
        return next(self.reactions)


class MortalAdapterTests(unittest.TestCase):
    def test_processes_each_event_and_returns_final_action(self) -> None:
        bot = FakeMortalBot(
            [
                None,
                None,
                '{"type":"dahai","actor":0,"pai":"5m","tsumogiri":false}',
            ]
        )

        action = react(
            bot,
            '[{"type":"start_game"},{"type":"start_kyoku"},'
            '{"type":"tsumo","actor":0,"pai":"5m"}]',
        )

        self.assertEqual(action["type"], "dahai")
        self.assertEqual(len(bot.events), 3)
        self.assertEqual(bot.events[-1]["type"], "tsumo")

    def test_returns_none_when_mortal_has_no_reaction(self) -> None:
        bot = FakeMortalBot([None, None])

        self.assertEqual(
            react(bot, '[{"type":"start_game"},{"type":"end_kyoku"}]'),
            {"type": "none"},
        )


if __name__ == "__main__":
    unittest.main()
