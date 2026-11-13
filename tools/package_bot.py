"""将 mjai bot 入口和本地包代码打包到提交 zip。"""

import argparse
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def package_bot(output: Path, entrypoint: str = "bot.py") -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if entrypoint not in {"bot.py", "bot_efficiency.py", "bot_strategy.py"}:
        raise ValueError(f"unsupported bot entrypoint: {entrypoint}")

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / entrypoint, "bot.py")
        package_dir = ROOT / "src" / "mahjong_advisor"
        for source in package_dir.rglob("*.py"):
            archive.write(source, source.relative_to(ROOT / "src").as_posix())

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "tsumogiri-bot.zip",
        help="destination zip path",
    )
    parser.add_argument(
        "--entrypoint",
        choices=("bot.py", "bot_efficiency.py", "bot_strategy.py"),
        default="bot.py",
        help="bot implementation to package",
    )
    args = parser.parse_args()
    output = package_bot(args.output, args.entrypoint)
    print(f"Created {output}")


if __name__ == "__main__":
    main()
