"""Summarize mjai match ranks by bot name and write one CSV row per match."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def find_summaries(inputs: list[Path]) -> list[Path]:
    summaries: set[Path] = set()
    for path in inputs:
        if path.is_file():
            if path.name != "summary.json":
                raise ValueError(f"expected a summary.json file: {path}")
            summaries.add(path.resolve())
        elif path.is_dir():
            summaries.update(candidate.resolve() for candidate in path.rglob("summary.json"))
        else:
            raise FileNotFoundError(f"input path does not exist: {path}")
    if not summaries:
        raise ValueError("no summary.json files found")
    return sorted(summaries)


def read_match(summary_path: Path, default_bots: list[str]) -> tuple[list[str], list[int]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ranks = summary.get("rank")
    if (
        not isinstance(ranks, list)
        or len(ranks) != 4
        or any(type(rank) is not int for rank in ranks)
        or sorted(ranks) != [1, 2, 3, 4]
    ):
        raise ValueError(f"{summary_path} must contain a four-player rank permutation")
    rounds = summary.get("kyoku")
    if not isinstance(rounds, list) or not rounds or any(
        not isinstance(round_data, dict) or round_data.get("error_info") is not None
        for round_data in rounds
    ):
        raise ValueError(f"{summary_path} contains missing or invalid round results")

    errors_path = summary_path.parent / "errors.json"
    if errors_path.exists():
        errors = json.loads(errors_path.read_text(encoding="utf-8"))
        if not isinstance(errors, list) or any(
            not isinstance(error, dict) or error for error in errors
        ):
            raise ValueError(f"{errors_path} reports simulation errors")

    metadata_path = summary_path.parent / "experiment.json"
    if metadata_path.exists():
        metadata: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
        bots = metadata.get("seat_bots") if isinstance(metadata, dict) else None
    else:
        bots = default_bots
    if not isinstance(bots, list) or len(bots) != 4 or any(
        not isinstance(name, str) or not name for name in bots
    ):
        raise ValueError(f"invalid seat_bots mapping for {summary_path}")
    return bots, ranks


def summarize(inputs: list[Path], csv_path: Path, default_bots: list[str]) -> dict[str, dict[str, float]]:
    summaries = find_summaries(inputs)
    rows: list[dict[str, Any]] = []
    bot_ranks: dict[str, list[int]] = defaultdict(list)
    bot_games: dict[str, set[str]] = defaultdict(set)

    for summary_path in summaries:
        bots, ranks = read_match(summary_path, default_bots)
        game = str(summary_path.parent)
        row: dict[str, Any] = {"game": game}
        for seat, (bot, rank) in enumerate(zip(bots, ranks)):
            row[f"seat_{seat}_bot"] = bot
            row[f"seat_{seat}_rank"] = rank
            bot_ranks[bot].append(rank)
            bot_games[bot].add(game)
        rows.append(row)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["game"] + [
        field
        for seat in range(4)
        for field in (f"seat_{seat}_bot", f"seat_{seat}_rank")
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    metrics: dict[str, dict[str, float]] = {}
    for bot, ranks in sorted(bot_ranks.items()):
        metrics[bot] = {
            "matches": len(bot_games[bot]),
            "placements": len(ranks),
            "average_rank": sum(ranks) / len(ranks),
            "first_rate": ranks.count(1) / len(ranks),
            "fourth_rate": ranks.count(4) / len(ranks),
        }
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path, help="match log directories or summary.json files")
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="path for the per-match CSV output",
    )
    parser.add_argument(
        "--default-bots",
        default="seat_0,seat_1,seat_2,seat_3",
        help="comma-separated names used if experiment.json is absent",
    )
    args = parser.parse_args()
    default_bots = [name.strip() for name in args.default_bots.split(",")]
    if len(default_bots) != 4 or any(not name for name in default_bots):
        parser.error("--default-bots must contain four non-empty names")

    metrics = summarize(args.logs, args.csv, default_bots)
    print("Bot           Matches  Placements  Average rank  First rate  Fourth rate")
    for bot, values in metrics.items():
        print(
            f"{bot:<13} {int(values['matches']):>7}  "
            f"{int(values['placements']):>10}  "
            f"{values['average_rank']:>12.3f}  "
            f"{values['first_rate']:>10.1%}  {values['fourth_rate']:>11.1%}"
        )
    print(f"CSV: {args.csv.resolve()}")


if __name__ == "__main__":
    main()
