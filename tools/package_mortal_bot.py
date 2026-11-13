"""Package the verified Mortal checkpoint and mjai adapter into a bot zip."""

import argparse
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def package_mortal_bot(model: Path, output: Path) -> Path:
    model = model.resolve()
    if not model.is_file():
        raise FileNotFoundError(f"Mortal model does not exist: {model}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "bot_mortal.py", "bot.py")
        archive.write(model, "mortal.pth")
        archive.writestr(
            "mortal_config.toml",
            '[control]\nstate_file = "/workspace/mortal.pth"\n',
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "models" / "mortal-v3.pth",
        help="verified Mortal checkpoint",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "mortal-bot.zip",
        help="destination bot zip",
    )
    args = parser.parse_args()
    output = package_mortal_bot(args.model, args.output)
    print(f"Created {output}")


if __name__ == "__main__":
    main()
