"""Summarize mjai match ranks by bot name and write one CSV row per match."""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation_stats import complete_rotation_groups, grouped_mean_interval


def find_summaries(inputs: list[Path]) -> list[Path]:
    summaries: set[Path] = set()
    for path in inputs:
        if path.is_file():
            if path.name != "summary.json":
                raise ValueError(f"expected a summary.json file: {path}")
            summaries.add(path.resolve())
        elif path.is_dir():
            if (path / "experiment.json").is_file():
                summaries.add((path / "summary.json").resolve())
            else:
                summaries.update(
                    candidate.resolve()
                    for candidate in path.rglob("summary.json")
                )
                summaries.update(
                    (metadata.parent / "summary.json").resolve()
                    for metadata in path.rglob("experiment.json")
                )
        else:
            raise FileNotFoundError(f"input path does not exist: {path}")
    if not summaries:
        raise ValueError("no summary.json files found")
    return sorted(summaries)


def read_match(summary_path: Path, default_bots: list[str]) -> tuple[list[str], list[int]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError(f"{summary_path} must contain a JSON object")
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


def summarize(
    inputs: list[Path], csv_path: Path, default_bots: list[str]
) -> dict[str, Any]:
    summaries = find_summaries(inputs)
    rows: list[dict[str, Any]] = []
    bot_group_ranks: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    bot_group_first: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    bot_group_fourth: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    bot_games: dict[str, set[str]] = defaultdict(set)
    rotations: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    invalid_details: list[dict[str, str]] = []
    valid_matches = 0

    for summary_path in summaries:
        game = str(summary_path.parent)
        row: dict[str, Any] = {
            "game": game,
            "valid": False,
            "seed_group": "",
            "error": "",
        }
        try:
            bots, ranks = read_match(summary_path, default_bots)
            metadata_path = summary_path.parent / "experiment.json"
            if metadata_path.is_file():
                metadata: Any = json.loads(
                    metadata_path.read_text(encoding="utf-8")
                )
                seed = metadata.get("seed") if isinstance(metadata, dict) else None
                if seed is not None and (
                    not isinstance(seed, list)
                    or not seed
                    or any(type(value) is not int for value in seed)
                ):
                    raise ValueError(f"invalid seed tuple in {metadata_path}")
                group = (
                    json.dumps(seed, separators=(",", ":"))
                    if seed is not None
                    else f"unseeded:{game}"
                )
            else:
                group = f"unseeded:{game}"
        except (OSError, ValueError) as error:
            message = str(error)
            invalid_details.append({"game": game, "reason": message})
            row["error"] = message
            for seat in range(4):
                row[f"seat_{seat}_bot"] = ""
                row[f"seat_{seat}_rank"] = ""
            rows.append(row)
            continue

        valid_matches += 1
        rotations[group].add(tuple(bots))
        row["valid"] = True
        row["seed_group"] = group
        for seat, (bot, rank) in enumerate(zip(bots, ranks)):
            row[f"seat_{seat}_bot"] = bot
            row[f"seat_{seat}_rank"] = rank
            bot_group_ranks[bot][group].append(float(rank))
            bot_group_first[bot][group].append(float(rank == 1))
            bot_group_fourth[bot][group].append(float(rank == 4))
            bot_games[bot].add(game)
        rows.append(row)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["game"] + [
        "valid",
        "seed_group",
        "error",
    ] + [
        field
        for seat in range(4)
        for field in (f"seat_{seat}_bot", f"seat_{seat}_rank")
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    complete_groups = complete_rotation_groups(rotations)
    metrics: dict[str, dict[str, Any]] = {}
    for bot, group_ranks in sorted(bot_group_ranks.items()):
        complete_ranks = {
            group: values
            for group, values in group_ranks.items()
            if group in complete_groups
        }
        complete_first = {
            group: values
            for group, values in bot_group_first[bot].items()
            if group in complete_groups
        }
        complete_fourth = {
            group: values
            for group, values in bot_group_fourth[bot].items()
            if group in complete_groups
        }
        rank_interval = _summary_interval(complete_ranks, group_ranks)
        first_interval = _summary_interval(complete_first, bot_group_first[bot])
        fourth_interval = _summary_interval(complete_fourth, bot_group_fourth[bot])
        metrics[bot] = {
            "matches": len(bot_games[bot]),
            "placements": sum(len(values) for values in group_ranks.values()),
            "seed_groups": rank_interval["groups"],
            "estimate_basis": (
                "complete four-seat rotations"
                if complete_ranks
                else "descriptive only; no complete four-seat rotation"
            ),
            "average_rank": rank_interval["mean"],
            "average_rank_ci_95": [
                rank_interval["lower_95"],
                rank_interval["upper_95"],
            ],
            "first_rate": first_interval["mean"],
            "first_rate_ci_95": [
                first_interval["lower_95"],
                first_interval["upper_95"],
            ],
            "fourth_rate": fourth_interval["mean"],
            "fourth_rate_ci_95": [
                fourth_interval["lower_95"],
                fourth_interval["upper_95"],
            ],
        }
    return {
        "attempted_matches": len(summaries),
        "valid_matches": valid_matches,
        "invalid_matches": len(invalid_details),
        "invalid_rate": len(invalid_details) / len(summaries),
        "attempted_seed_groups": len(rotations),
        "seed_groups": len(complete_groups),
        "incomplete_rotation_groups": len(rotations) - len(complete_groups),
        "invalid_details": invalid_details,
        "bots": metrics,
    }


def _summary_interval(
    complete_values: dict[str, list[float]],
    all_values: dict[str, list[float]],
) -> dict[str, float | int | None]:
    if complete_values:
        return grouped_mean_interval(complete_values)
    values = [value for group_values in all_values.values() for value in group_values]
    return {
        "mean": statistics.mean(values) if values else None,
        "lower_95": None,
        "upper_95": None,
        "groups": 0,
    }


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

    report = summarize(args.logs, args.csv, default_bots)
    print(
        f"Matches: {report['valid_matches']}/{report['attempted_matches']} valid; "
        f"{report['invalid_matches']} invalid "
        f"({report['invalid_rate']:.1%}); "
        f"complete rotation groups: {report['seed_groups']}/"
        f"{report['attempted_seed_groups']}"
    )
    print(
        "Bot           Matches  Placements  Groups  Average rank (95% CI)  "
        "First rate  Fourth rate"
    )
    for bot, values in report["bots"].items():
        ci = values["average_rank_ci_95"]
        ci_text = (
            "not estimable"
            if ci[0] is None
            else f"[{ci[0]:.2f}, {ci[1]:.2f}]"
        )
        print(
            f"{bot:<13} {int(values['matches']):>7}  "
            f"{int(values['placements']):>10}  "
            f"{int(values['seed_groups']):>6}  "
            f"{values['average_rank']:>6.3f} {ci_text:<20}  "
            f"{values['first_rate']:>10.1%}  {values['fourth_rate']:>11.1%}"
        )
    if report["invalid_details"]:
        print("Invalid matches:")
        for item in report["invalid_details"]:
            print(f"  {item['game']}: {item['reason']}")
    print(f"CSV: {args.csv.resolve()}")


if __name__ == "__main__":
    main()
