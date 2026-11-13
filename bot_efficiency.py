"""mjai entrypoint for the pure shanten/ukeire baseline bot."""

import json
import sys

from mahjong_advisor.efficiency_bot import EfficiencyBot


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python bot.py PLAYER_ID")
    try:
        bot = EfficiencyBot(int(sys.argv[1]))
        for line in sys.stdin:
            if line.strip():
                action = bot.react(line)
                sys.stdout.write(json.dumps(action, separators=(",", ":")) + "\n")
                sys.stdout.flush()
    except (ValueError, json.JSONDecodeError) as error:
        sys.stderr.write(f"bot input error: {error}\n")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
