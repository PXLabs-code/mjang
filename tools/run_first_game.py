"""用四个本地摸切 bot 运行一局 mjai Docker 模拟。"""

import argparse
from pathlib import Path

from package_bot import package_bot


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=ROOT / "logs" / "first_game",
        help="directory for simulator logs",
    )
    args = parser.parse_args()

    try:
        import mjai
    except ImportError as error:
        raise SystemExit(
            "mjai is not installed; run: python -m pip install -r requirements-simulation.txt"
        ) from error

    bot_zip = package_bot(ROOT / "build" / "tsumogiri-bot.zip")
    args.logs_dir.mkdir(parents=True, exist_ok=True)
    submissions = [str(bot_zip)] * 4
    mjai.Simulator(submissions, logs_dir=str(args.logs_dir)).run()
    print(f"Simulation finished. Logs: {args.logs_dir.resolve()}")


if __name__ == "__main__":
    main()
