"""Report Mortal inference latency from mjai client stdout logs."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation_stats import complete_rotation_groups, grouped_mean_interval
from summarize_results import read_match


def read_mortal_latencies(
    logs_dir: Path, allow_missing_logs: bool = False
) -> list[float]:
    metadata_files = sorted(logs_dir.rglob("experiment.json"))
    if not metadata_files:
        raise ValueError(f"no experiment.json files found under {logs_dir}")

    latencies_ms: list[float] = []
    for metadata_path in metadata_files:
        metadata: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
        bots = metadata.get("seat_bots") if isinstance(metadata, dict) else None
        if not isinstance(bots, list) or len(bots) != 4:
            raise ValueError(f"invalid seat_bots mapping in {metadata_path}")

        for seat, bot_name in enumerate(bots):
            if bot_name != "mortal":
                continue
            log_path = metadata_path.parent / f"player_logs.{seat}.stdout.txt"
            if not log_path.exists() and allow_missing_logs:
                continue
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                meta = event.get("meta") if isinstance(event, dict) else None
                eval_time_ns = meta.get("eval_time_ns") if isinstance(meta, dict) else None
                if isinstance(eval_time_ns, (int, float)):
                    latencies_ms.append(eval_time_ns / 1_000_000)
    return latencies_ms


def collect_latencies(logs_dir: Path) -> list[float]:
    latencies_ms = read_mortal_latencies(logs_dir)
    if not latencies_ms:
        raise ValueError(f"no Mortal eval_time_ns values found under {logs_dir}")
    return latencies_ms


def count_mortal_inferences(
    logs_dir: Path, allow_missing_logs: bool = False
) -> int:
    return len(
        read_mortal_latencies(logs_dir, allow_missing_logs=allow_missing_logs)
    )


def match_context(logs_dir: Path) -> dict[str, Any]:
    metadata_files = sorted(logs_dir.rglob("experiment.json"))
    rank_groups: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    match_rank_values: dict[str, list[float]] = defaultdict(list)
    rotations: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    valid_matches = 0
    invalid_matches = 0

    for metadata_path in metadata_files:
        try:
            bots, ranks = read_match(
                metadata_path.parent / "summary.json", []
            )
            metadata: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
            seed = metadata.get("seed") if isinstance(metadata, dict) else None
            if seed is not None and (
                not isinstance(seed, list)
                or not seed
                or any(type(value) is not int for value in seed)
            ):
                raise ValueError(f"invalid seed tuple in {metadata_path}")
        except (OSError, ValueError):
            invalid_matches += 1
            continue

        valid_matches += 1
        group = (
            json.dumps(seed, separators=(",", ":"))
            if seed is not None
            else f"unseeded:{metadata_path.parent}"
        )
        rotations[group].add(tuple(bots))
        for bot, rank in zip(bots, ranks):
            rank_groups[bot][group].append(float(rank))
        for bot in set(bots):
            match_rank_values[bot].append(
                statistics.mean(
                    float(rank)
                    for seat_bot, rank in zip(bots, ranks)
                    if seat_bot == bot
                )
            )

    complete_groups = complete_rotation_groups(rotations)
    rank_summary: dict[str, Any] = {}
    for bot, groups in sorted(rank_groups.items()):
        complete_values = {
            group: values for group, values in groups.items() if group in complete_groups
        }
        if complete_values:
            interval = grouped_mean_interval(complete_values)
            average_rank = interval["mean"]
        else:
            interval = {
                "lower_95": None,
                "upper_95": None,
                "groups": 0,
            }
            average_rank = statistics.mean(match_rank_values[bot])
        rank_summary[bot] = {
            "average_rank": average_rank,
            "ci_95": [interval["lower_95"], interval["upper_95"]],
            "seed_groups": interval["groups"],
            "estimate_basis": (
                "complete four-seat rotations"
                if complete_values
                else "descriptive only; no complete four-seat rotation"
            ),
        }
    return {
        "attempted_matches": len(metadata_files),
        "valid_matches": valid_matches,
        "invalid_matches": invalid_matches,
        "invalid_rate": (
            invalid_matches / len(metadata_files) if metadata_files else 0.0
        ),
        "attempted_seed_groups": len(rotations),
        "seed_groups": len(complete_groups),
        "incomplete_rotation_groups": len(rotations) - len(complete_groups),
        "source_game_rank_context": rank_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs_dir", type=Path, help="root of run_experiment logs")
    args = parser.parse_args()
    latencies = sorted(collect_latencies(args.logs_dir))
    p95 = latencies[int((len(latencies) - 1) * 0.95)]
    print(f"Mortal inference actions: {len(latencies)}")
    print(f"Mean:   {statistics.mean(latencies):.2f} ms")
    print(f"Median: {statistics.median(latencies):.2f} ms")
    print(f"P95:    {p95:.2f} ms")
    print(f"Max:    {max(latencies):.2f} ms")
    context = match_context(args.logs_dir)
    print(
        f"Source matches: {context['valid_matches']}/"
        f"{context['attempted_matches']} valid; "
        f"{context['invalid_matches']} invalid "
        f"({context['invalid_rate']:.1%}); "
        f"complete rotation groups: {context['seed_groups']}/"
        f"{context['attempted_seed_groups']}"
    )
    for bot, values in context["source_game_rank_context"].items():
        ci = values["ci_95"]
        ci_text = (
            "not estimable"
            if ci[0] is None
            else f"[{ci[0]:.2f}, {ci[1]:.2f}]"
        )
        print(
            f"{bot} source-match average rank: {values['average_rank']:.2f} "
            f"(95% rotation-group CI {ci_text}; "
            f"{values['seed_groups']} groups; {values['estimate_basis']})"
        )


if __name__ == "__main__":
    main()
