"""Run four mjai submissions, optionally rotating their seats."""

import argparse
import json
from functools import partial
from pathlib import Path

import mjai
from mjai import game as mjai_game
from mjai.player import MjaiPlayerClient


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--submission",
        action="append",
        type=Path,
        required=True,
        help="bot zip for a seat; provide exactly four",
    )
    parser.add_argument(
        "--bot-name",
        action="append",
        required=True,
        help="name for each seat's bot; provide exactly four",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        required=True,
        help="root directory for game logs",
    )
    parser.add_argument("--rotate", action="store_true", help="run all four seat rotations")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument(
        "--seed",
        type=int,
        default=2000,
        help="second component of the mjai seed (the default preserves the existing seed)",
    )
    parser.add_argument(
        "--port-base",
        type=int,
        default=28090,
        help="first host port used by this simulator",
    )
    parser.add_argument(
        "--docker-image",
        help="optional custom mjai-client-compatible image for all submissions",
    )
    args = parser.parse_args()

    if len(args.submission) != 4 or len(args.bot_name) != 4:
        parser.error("--submission and --bot-name must each be provided four times")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.seed < 0:
        parser.error("--seed must be non-negative")
    if not 1 <= args.port_base <= 65532:
        parser.error("--port-base must allow four consecutive TCP ports")
    if args.docker_image:
        mjai_game.MjaiPlayerClient = partial(
            MjaiPlayerClient, docker_image_name=args.docker_image
        )

    seed = (10000, args.seed)
    for seat in range(4 if args.rotate else 1):
        rotation_dir = args.logs_dir / f"rotation_{seat}" if args.rotate else args.logs_dir
        submissions = args.submission[seat:] + args.submission[:seat]
        seat_bots = args.bot_name[seat:] + args.bot_name[:seat]
        rotation_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "seat_bots": seat_bots,
            "submissions": [str(path.resolve()) for path in submissions],
            "docker_image": args.docker_image or "docker.io/smly/mjai-client:v3",
            "seed": list(seed),
            "port_base": args.port_base,
        }
        (rotation_dir / "experiment.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        print(f"Running {rotation_dir} with seats: {', '.join(seat_bots)}")
        mjai.Simulator(
            [str(path.resolve()) for path in submissions],
            logs_dir=str(rotation_dir),
            timeout=args.timeout,
            port=args.port_base,
            seed=seed,
        ).run()


if __name__ == "__main__":
    main()
