"""Compare the advisor's discard with Mortal on the same recorded decision states."""

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot_strategy import EfficiencyRiichiBot  # noqa: E402
from mahjong_advisor.core import HandAnalyzer, hand_counts, tile_index  # noqa: E402
from mahjong_advisor.efficiency_strategy import StrategyDecision  # noqa: E402
from evaluation_stats import complete_rotation_groups, grouped_mean_interval  # noqa: E402
from summarize_results import read_match  # noqa: E402


NON_DISCARD_ACTIONS = {"ankan", "chi", "daiminkan", "hora", "kakan", "pon"}


class RecordingEfficiencyBot(EfficiencyRiichiBot):
    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.last_decision: StrategyDecision | None = None

    def _decide_discard(self, riichi_available: bool) -> StrategyDecision:
        self.last_decision = super()._decide_discard(riichi_available)
        return self.last_decision


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError(f"{path}:{line_number} is not an mjai event object")
        events.append(event)
    if not events:
        raise ValueError(f"{path} contains no mjai events")
    return events


def sanitize_event(event: dict[str, Any], player_id: int) -> dict[str, Any]:
    """Hide all private draws and initial hands before replaying a seat."""
    safe_event = deepcopy(event)
    safe_event.pop("meta", None)
    if safe_event["type"] == "start_kyoku":
        hands = safe_event.get("tehais")
        if not isinstance(hands, list) or len(hands) != 4:
            raise ValueError("start_kyoku must contain four hands")
        for seat, hand in enumerate(hands):
            if seat != player_id:
                if not isinstance(hand, list):
                    raise ValueError("every start_kyoku hand must be a tile list")
                hands[seat] = ["?"] * len(hand)
    elif (
        safe_event["type"] == "tsumo"
        and safe_event.get("actor") != player_id
    ):
        safe_event["pai"] = "?"
    return safe_event


def find_following_discard(
    events: list[dict[str, Any]], start_index: int, player_id: int
) -> dict[str, Any] | None:
    for event in events[start_index + 1 :]:
        event_type = event["type"]
        if event_type in {"end_kyoku", "start_kyoku"}:
            return None
        if event.get("actor") != player_id:
            continue
        if event_type == "dahai":
            return event
        if event_type in NON_DISCARD_ACTIONS:
            return None
    return None


def _shanten_after_discard(
    bot: RecordingEfficiencyBot, discard: str
) -> int:
    counts = hand_counts(bot.tehai_mjai)
    counts[tile_index(discard)] -= 1
    return HandAnalyzer().calculate_shanten(counts, bot.fixed_melds)


def _decision_tile(
    bot: RecordingEfficiencyBot, action: dict[str, Any]
) -> tuple[str | None, int | None]:
    if action.get("type") == "dahai":
        tile = action.get("pai")
    elif action.get("type") == "reach" and bot.last_decision is not None:
        tile = bot.last_decision.discard_tile
    else:
        return None, None
    if not isinstance(tile, str):
        return None, None
    shanten = (
        bot.last_decision.shanten
        if bot.last_decision is not None
        else _shanten_after_discard(bot, tile)
    )
    return tile, shanten


def score_game(
    game_name: str,
    group_id: str,
    events: list[dict[str, Any]],
    mortal_seats: list[int],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    bots = {seat: RecordingEfficiencyBot(seat) for seat in mortal_seats}
    turns = {seat: 0 for seat in mortal_seats}
    accepted_riichi: set[int] = set()
    analyzer = HandAnalyzer()
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()

    for index, event in enumerate(events):
        event_type = event["type"]
        actor = event.get("actor")
        if event_type == "start_kyoku":
            turns = {seat: 0 for seat in mortal_seats}
            accepted_riichi.clear()
        elif event_type == "reach_accepted" and type(actor) is int:
            accepted_riichi.add(actor)

        if event_type == "tsumo" and actor in bots:
            seat = int(actor)
            turns[seat] += 1
            actual_event = find_following_discard(events, index, seat)
            safe_event = sanitize_event(event, seat)
            bot = bots[seat]
            bot.last_decision = None
            try:
                response = bot.react(json.dumps([safe_event], separators=(",", ":")))
                action = json.loads(response)
            except (TypeError, ValueError):
                skipped["assistant replay error"] += 1
                continue
            finally:
                # The replay follows Mortal's branch, not the advisor's staged riichi.
                bot.pending_riichi_discard = None
            if not isinstance(action, dict):
                skipped["assistant returned a non-object action"] += 1
                continue
            if actual_event is None:
                skipped["Mortal did not discard after draw"] += 1
            else:
                assistant_tile, assistant_shanten = _decision_tile(bot, action)
                actual_tile = actual_event.get("pai")
                if assistant_tile is None or not isinstance(actual_tile, str):
                    skipped[f"assistant chose {action.get('type', 'unknown')}"] += 1
                else:
                    mortal_counts = hand_counts(bot.tehai_mjai)
                    mortal_counts[tile_index(actual_tile)] -= 1
                    mortal_shanten = analyzer.calculate_shanten(
                        mortal_counts, bot.fixed_melds
                    )
                    turn_number = turns[seat]
                    turn_phase = (
                        "early"
                        if turn_number <= 6
                        else "late"
                        if turn_number >= 13
                        else "middle"
                    )
                    rows.append(
                        {
                            "game": game_name,
                            "seed_group": group_id,
                            "seat": seat,
                            "own_turn": turn_number,
                            "turn_phase": turn_phase,
                            "opponent_riichi": any(
                                other != seat for other in accepted_riichi
                            ),
                            "assistant_tenpai": assistant_shanten == 0,
                            "mortal_tenpai": mortal_shanten == 0,
                            "assistant_shanten": assistant_shanten,
                            "mortal_shanten": mortal_shanten,
                            "assistant_tile": assistant_tile,
                            "mortal_tile": actual_tile,
                            "exact_match": assistant_tile == actual_tile,
                            "tile_type_match": tile_index(assistant_tile)
                            == tile_index(actual_tile),
                        }
                    )

        for seat, bot in bots.items():
            if event_type == "start_game" or event_type != "tsumo" or actor != seat:
                safe_event = sanitize_event(event, seat)
                try:
                    bot.react(json.dumps([safe_event], separators=(",", ":")))
                except (TypeError, ValueError):
                    skipped["assistant replay error"] += 1

    return rows, skipped


def _interval_for_rows(
    rows: list[dict[str, Any]],
    field: str,
    complete_groups: set[str],
) -> dict[str, float | int | None]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["seed_group"] in complete_groups:
            grouped[row["seed_group"]].append(float(row[field]))
    if not grouped:
        return {
            "mean": statistics.mean(float(row[field]) for row in rows) if rows else None,
            "lower_95": None,
            "upper_95": None,
            "groups": 0,
        }
    return grouped_mean_interval(grouped)


def _agreement_metrics(
    rows: list[dict[str, Any]], complete_groups: set[str]
) -> dict[str, Any]:
    return {
        "decisions": len(rows),
        "inferential_decisions": sum(
            row["seed_group"] in complete_groups for row in rows
        ),
        "seed_groups": len(
            {row["seed_group"] for row in rows if row["seed_group"] in complete_groups}
        ),
        "exact_tile_agreement": _interval_for_rows(
            rows, "exact_match", complete_groups
        ),
        "tile_type_agreement": _interval_for_rows(
            rows, "tile_type_match", complete_groups
        ),
    }


def _source_rank_context(
    ranks_by_bot: dict[str, dict[str, list[float]]],
    complete_groups: set[str],
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for bot, group_values in sorted(ranks_by_bot.items()):
        complete_values = {
            group: values
            for group, values in group_values.items()
            if group in complete_groups
        }
        if complete_values:
            interval = grouped_mean_interval(complete_values)
            average_rank = interval["mean"]
        else:
            all_ranks = [rank for values in group_values.values() for rank in values]
            interval = {
                "lower_95": None,
                "upper_95": None,
                "groups": 0,
            }
            average_rank = statistics.mean(all_ranks)
        context[bot] = {
            "average_rank": average_rank,
            "average_rank_ci_95": [
                interval["lower_95"],
                interval["upper_95"],
            ],
            "seed_groups": interval["groups"],
            "estimate_basis": (
                "complete four-seat rotations"
                if complete_values
                else "descriptive only; no complete four-seat rotation"
            ),
            "note": "Ranks are from the source matches, not a result of offline replay.",
        }
    return context


def evaluate_logs(logs_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    game_dirs = sorted(
        metadata_path.parent for metadata_path in logs_dir.rglob("experiment.json")
    )
    if not game_dirs:
        raise ValueError(f"no experiment.json files found under {logs_dir}")

    all_rows: list[dict[str, Any]] = []
    invalid_games: list[dict[str, str]] = []
    skipped: Counter[str] = Counter()
    ranks_by_bot: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    rotations: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    valid_games = 0

    for game_dir in game_dirs:
        try:
            metadata_path = game_dir / "experiment.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError(f"{metadata_path} must contain a JSON object")
            bots, ranks = read_match(game_dir / "summary.json", [])
            seed = metadata.get("seed")
            if (
                not isinstance(seed, list)
                or not seed
                or any(type(value) is not int for value in seed)
            ):
                raise ValueError(f"invalid seed tuple in {metadata_path}")
            group_id = json.dumps(seed, separators=(",", ":"))
            mortal_seats = [
                seat for seat, bot_name in enumerate(bots) if bot_name == "mortal"
            ]
            if not mortal_seats:
                raise ValueError("match has no Mortal seats")
            events = load_events(game_dir / "mjai_log.json")
            decision_rows, skipped_rows = score_game(
                game_dir.name, group_id, events, mortal_seats
            )
        except (OSError, ValueError) as error:
            invalid_games.append(
                {
                    "game": game_dir.name,
                    "reason": str(error).replace(str(game_dir), "<game>"),
                }
            )
            continue

        valid_games += 1
        rotations[group_id].add(tuple(bots))
        all_rows.extend(decision_rows)
        skipped.update(skipped_rows)
        for bot_name, rank in zip(bots, ranks):
            ranks_by_bot[bot_name][group_id].append(float(rank))

    complete_groups = complete_rotation_groups(rotations)
    agreement: dict[str, Any] = {
        "overall": _agreement_metrics(all_rows, complete_groups)
    }
    for dimension, labels in (
        ("turn_phase", ("early", "middle", "late")),
        ("opponent_riichi", (False, True)),
        ("assistant_tenpai", (False, True)),
        ("mortal_tenpai", (False, True)),
    ):
        agreement[dimension] = {}
        for label in labels:
            subset = [
                row
                for row in all_rows
                if row[dimension] == label
            ]
            agreement[dimension][str(label)] = _agreement_metrics(
                subset, complete_groups
            )

    report = {
        "attempted_games": len(game_dirs),
        "valid_games": valid_games,
        "invalid_games": len(invalid_games),
        "invalid_rate": len(invalid_games) / len(game_dirs),
        "attempted_seed_groups": len(rotations),
        "seed_groups": len(complete_groups),
        "incomplete_rotation_groups": len(rotations) - len(complete_groups),
        "decision_samples": len(all_rows),
        "inferential_decision_samples": sum(
            row["seed_group"] in complete_groups for row in all_rows
        ),
        "unscored_decisions": dict(sorted(skipped.items())),
        "agreement": agreement,
        "source_game_rank_context": _source_rank_context(
            ranks_by_bot, complete_groups
        )
        if ranks_by_bot
        else {},
        "invalid_game_details": invalid_games,
        "interpretation": (
            "Action agreement is a proxy metric, not a win-rate or strength estimate."
        ),
    }
    return report, all_rows


def write_report(
    logs_dir: Path, report: dict[str, Any], rows: list[dict[str, Any]]
) -> tuple[Path, Path]:
    csv_path = logs_dir / "consistency_decisions.csv"
    fields = [
        "game",
        "seed_group",
        "seat",
        "own_turn",
        "turn_phase",
        "opponent_riichi",
        "assistant_tenpai",
        "mortal_tenpai",
        "assistant_shanten",
        "mortal_shanten",
        "assistant_tile",
        "mortal_tile",
        "exact_match",
        "tile_type_match",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    report_path = logs_dir / "consistency_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return csv_path, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs_dir", type=Path, help="root of Mortal match logs")
    args = parser.parse_args()
    report, rows = evaluate_logs(args.logs_dir)
    csv_path, report_path = write_report(args.logs_dir, report, rows)

    print(
        f"Matches: {report['valid_games']}/{report['attempted_games']} valid; "
        f"{report['invalid_games']} invalid "
        f"({report['invalid_rate']:.1%}); complete rotation groups: "
        f"{report['seed_groups']}/{report['attempted_seed_groups']}"
    )
    print(f"Discard decisions: {report['decision_samples']}")
    print(
        "Decisions from complete rotation groups: "
        f"{report['inferential_decision_samples']}"
    )
    overall = report["agreement"]["overall"]
    for label, key in (
        ("Exact physical tile", "exact_tile_agreement"),
        ("Tile type", "tile_type_agreement"),
    ):
        interval = overall[key]
        if interval["mean"] is None:
            print(f"{label} agreement: no scored decisions")
        else:
            lower = interval["lower_95"]
            upper = interval["upper_95"]
            ci = "not estimable" if lower is None else f"[{lower:.1%}, {upper:.1%}]"
            print(
                f"{label} agreement: {interval['mean']:.1%} "
                f"(95% rotation-group bootstrap CI {ci}; "
                f"{interval['groups']} groups)"
            )
    print("Source-match average-rank CI context:")
    for bot, values in report["source_game_rank_context"].items():
        ci = values["average_rank_ci_95"]
        ci_text = "not estimable" if ci[0] is None else f"[{ci[0]:.2f}, {ci[1]:.2f}]"
        print(
            f"  {bot}: {values['average_rank']:.2f} "
            f"(95% rotation-group CI {ci_text}; "
            f"{values['seed_groups']} groups; {values['estimate_basis']})"
        )
    print(report["interpretation"])
    print(f"Decision CSV: {csv_path.resolve()}")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    main()
