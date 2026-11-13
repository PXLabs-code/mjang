"""mjai 容器入口：每行读取一个事件数组，每行输出一个动作。"""

import json
import sys

from mahjong_advisor.bot import TsumogiriBot


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python bot.py PLAYER_ID")
    try:
        player_id = int(sys.argv[1])
        bot = TsumogiriBot(player_id)
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
