"""Split game wall time into inference, advisor, container/protocol, and engine time."""

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from report_mortal_latency import read_mortal_latencies


TIMESTAMP_RE = re.compile(
    r"^(?P<value>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} [+-]\d{2}:\d{2}) \|"
)
PLAYER_MESSAGE_RE = re.compile(
    r"mjai\.player:react:\d+ - (?P<player>\d+) (?P<direction><-|->)"
)
PLAYER_START_RE = re.compile(r"Start docker container for player(?P<player>\d+)")
PLAYER_READY_RE = re.compile(r"Done\. Player (?P<player>\d+) is ready!")
ADVISOR_TIME_RE = re.compile(r"ADVISOR_DECISION_NS=(\d+)")


@dataclass(frozen=True)
class RunnerTiming:
    startup_seconds: float
    cleanup_seconds: float
    request_seconds: float
    request_count: int
    response_count: int
    unmatched_requests: int
    log_span_seconds: float
    errors: tuple[str, ...]


def _timestamp(line: str) -> datetime | None:
    match = TIMESTAMP_RE.match(line)
    if match is None:
        return None
    return datetime.strptime(match.group("value"), "%Y-%m-%d %H:%M:%S.%f %z")


def parse_runner_log(path: Path, timeout_seconds: float) -> RunnerTiming:
    pending_requests: dict[int, deque[datetime]] = defaultdict(deque)
    launch_starts: dict[int, datetime] = {}
    delete_started: datetime | None = None
    timestamps: list[datetime] = []
    startup_seconds = 0.0
    cleanup_seconds = 0.0
    request_seconds = 0.0
    request_count = 0
    response_count = 0
    errors: list[str] = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        timestamp = _timestamp(line)
        if timestamp is None:
            continue
        timestamps.append(timestamp)
        message = line.split(" - ", 1)[-1]

        start_match = PLAYER_START_RE.search(message)
        if start_match:
            player = int(start_match.group("player"))
            if player in launch_starts:
                errors.append(f"player {player} launch started twice without readiness")
            launch_starts[player] = timestamp
            continue

        ready_match = PLAYER_READY_RE.search(message)
        if ready_match:
            player = int(ready_match.group("player"))
            started = launch_starts.pop(player, None)
            if started is None:
                errors.append(f"player {player} readiness has no launch start")
            else:
                startup_seconds += (timestamp - started).total_seconds()
            continue

        if message == "Delete player containers...":
            if delete_started is not None:
                errors.append("container deletion started twice without completion")
            delete_started = timestamp
            continue
        if message == "Delete player containers... DONE!":
            if delete_started is None:
                errors.append("container deletion completed without a start")
            else:
                cleanup_seconds += (timestamp - delete_started).total_seconds()
                delete_started = None
            continue

        player_message = PLAYER_MESSAGE_RE.search(line)
        if player_message is None:
            continue
        player = int(player_message.group("player"))
        if player_message.group("direction") == "<-":
            pending_requests[player].append(timestamp)
            request_count += 1
            continue
        starts = pending_requests[player]
        if not starts:
            errors.append(f"player {player} response has no request")
            continue
        request_seconds += (timestamp - starts.popleft()).total_seconds()
        response_count += 1

    if launch_starts:
        errors.append(f"{len(launch_starts)} container launch(es) lack readiness")
    if delete_started is not None:
        errors.append("container deletion has no completion timestamp")
    unmatched_requests = sum(len(starts) for starts in pending_requests.values())
    if unmatched_requests:
        request_seconds += unmatched_requests * timeout_seconds
        errors.append(
            f"{unmatched_requests} request(s) lack a response; "
            f"counted at the configured {timeout_seconds:g}s timeout"
        )
    log_span_seconds = (
        (timestamps[-1] - timestamps[0]).total_seconds() if timestamps else 0.0
    )
    if not timestamps:
        errors.append("runner.log has no parseable timestamps")

    return RunnerTiming(
        startup_seconds=startup_seconds,
        cleanup_seconds=cleanup_seconds,
        request_seconds=request_seconds,
        request_count=request_count,
        response_count=response_count,
        unmatched_requests=unmatched_requests,
        log_span_seconds=log_span_seconds,
        errors=tuple(errors),
    )


def _read_benchmark_rows(logs_dir: Path) -> dict[str, dict[str, str]]:
    path = logs_dir / "games.csv"
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as file:
        return {row["game"]: row for row in csv.DictReader(file)}


def _advisor_decision_times(game_dir: Path) -> list[int]:
    times: list[int] = []
    for path in sorted(game_dir.glob("player_logs.*.stderr.txt")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = ADVISOR_TIME_RE.search(line)
            if match:
                times.append(int(match.group(1)))
    return times


def profile_game(
    game_dir: Path,
    benchmark_row: dict[str, str] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    runner_timing = parse_runner_log(game_dir / "runner.log", timeout_seconds)
    latencies_ms = read_mortal_latencies(game_dir, allow_missing_logs=True)
    advisor_times_ns = _advisor_decision_times(game_dir)
    if benchmark_row and benchmark_row.get("wall_seconds"):
        wall_seconds = float(benchmark_row["wall_seconds"])
    else:
        wall_seconds = runner_timing.log_span_seconds
    metadata = json.loads(
        (game_dir / "experiment.json").read_text(encoding="utf-8")
    )
    seed = metadata.get("seed") if isinstance(metadata, dict) else None
    seed_group = (
        json.dumps(seed, separators=(",", ":"))
        if isinstance(seed, list) and seed
        else str(benchmark_row.get("seed", game_dir.name))
        if benchmark_row
        else game_dir.name
    )

    inference_seconds = sum(latencies_ms) / 1000
    advisor_seconds = sum(advisor_times_ns) / 1_000_000_000
    protocol_seconds = (
        runner_timing.request_seconds - inference_seconds - advisor_seconds
    )
    lifecycle_seconds = runner_timing.startup_seconds + runner_timing.cleanup_seconds
    simulator_seconds = (
        wall_seconds - runner_timing.request_seconds - lifecycle_seconds
    )
    errors = list(runner_timing.errors)
    if not latencies_ms:
        errors.append("no Mortal inference timings found")
    if not advisor_times_ns:
        errors.append("no advisor decision timings found")
    if protocol_seconds < 0:
        errors.append("inference/advisor time exceeds measured request time")
    if simulator_seconds < 0:
        errors.append("request and container time exceed measured game wall time")

    return {
        "game": game_dir.name,
        "seed_group": seed_group,
        "wall_seconds": wall_seconds,
        "mortal_inference_seconds": inference_seconds,
        "advisor_decision_seconds": advisor_seconds,
        "container_startup_seconds": runner_timing.startup_seconds,
        "container_cleanup_seconds": runner_timing.cleanup_seconds,
        "protocol_seconds": protocol_seconds,
        "simulator_seconds": simulator_seconds,
        "container_protocol_seconds": lifecycle_seconds + protocol_seconds,
        "mortal_inference_count": len(latencies_ms),
        "advisor_decision_count": len(advisor_times_ns),
        "request_count": runner_timing.request_count,
        "response_count": runner_timing.response_count,
        "unmatched_requests": runner_timing.unmatched_requests,
        "valid": benchmark_row.get("valid", "") if benchmark_row else "",
        "timing_complete": not errors,
        "timing_error": "; ".join(errors),
    }


def profile_logs(logs_dir: Path, timeout_seconds: float) -> list[dict[str, Any]]:
    game_dirs = sorted(logs_dir.glob("game_*"))
    if not game_dirs:
        raise ValueError(f"no game_* directories found under {logs_dir}")
    benchmark_rows = _read_benchmark_rows(logs_dir)
    return [
        profile_game(
            game_dir,
            benchmark_rows.get(game_dir.name),
            timeout_seconds,
        )
        for game_dir in game_dirs
    ]


def rank_context(
    benchmark_rows: dict[str, dict[str, str]]
) -> dict[str, Any]:
    game_ranks: dict[str, list[float]] = {
        "efficiency": [],
        "mortal": [],
    }
    for row in benchmark_rows.values():
        if row.get("valid", "").lower() != "true":
            continue
        efficiency_rank = row.get("efficiency_rank", "")
        if efficiency_rank:
            game_ranks["efficiency"].append(float(efficiency_rank))
        mortal_ranks = row.get("mortal_ranks", "")
        if mortal_ranks:
            game_ranks["mortal"].append(
                statistics.mean(float(rank) for rank in mortal_ranks.split(","))
            )

    context: dict[str, Any] = {}
    for bot, ranks in game_ranks.items():
        context[bot] = {
            "average_rank": statistics.mean(ranks) if ranks else None,
            "ci_95": [None, None],
            "seed_groups": 0,
            "descriptive_games": len(ranks),
            "estimate_basis": (
                "descriptive only; throughput runs do not rotate seats"
            ),
        }
    return context


def write_report(logs_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    csv_path = logs_dir / "timing_profile.csv"
    fieldnames = list(rows[0])
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    complete_rows = [row for row in rows if row["timing_complete"]]
    benchmark_rows = _read_benchmark_rows(logs_dir)
    valid_games = sum(
        row.get("valid", "").lower() == "true"
        for row in benchmark_rows.values()
    )
    distinct_seeds = {
        row.get("seed", "") for row in benchmark_rows.values() if row.get("seed")
    }
    valid_seeds = {
        row.get("seed", "")
        for row in benchmark_rows.values()
        if row.get("valid", "").lower() == "true" and row.get("seed")
    }
    timing_fields = (
        "wall_seconds",
        "mortal_inference_seconds",
        "advisor_decision_seconds",
        "container_startup_seconds",
        "container_cleanup_seconds",
        "protocol_seconds",
        "simulator_seconds",
        "container_protocol_seconds",
    )
    mean_seconds = {
        field: statistics.mean(row[field] for row in complete_rows)
        for field in timing_fields
    } if complete_rows else {}
    summary: dict[str, Any] = {
        "attempted_games": len(rows),
        "valid_games": valid_games,
        "invalid_games": len(rows) - valid_games,
        "invalid_rate": (len(rows) - valid_games) / len(rows),
        "distinct_seed_values": len(distinct_seeds),
        "valid_seed_values": len(valid_seeds),
        "attempted_rotation_groups": 0,
        "valid_rotation_groups": 0,
        "source_game_rank_context": rank_context(benchmark_rows),
        "timing_complete_games": len(complete_rows),
        "timing_incomplete_games": len(rows) - len(complete_rows),
        "mean_seconds_per_complete_game": mean_seconds,
        "component_share_of_wall": {
            field: mean_seconds[field] / mean_seconds["wall_seconds"]
            for field in (
                "mortal_inference_seconds",
                "advisor_decision_seconds",
                "container_protocol_seconds",
                "simulator_seconds",
            )
        }
        if mean_seconds and mean_seconds["wall_seconds"] > 0
        else {},
        "timing_errors": {
            error: sum(
                error in row["timing_error"].split("; ") for row in rows
            )
            for error in sorted(
                {
                    part
                    for row in rows
                    for part in row["timing_error"].split("; ")
                    if part
                }
            )
        },
        "per_game_csv": str(csv_path.resolve()),
    }
    summary_path = logs_dir / "timing_profile.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs_dir", type=Path, help="throughput benchmark log root")
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    rows = profile_logs(args.logs_dir, args.timeout)
    summary = write_report(args.logs_dir, rows)
    print(
        f"Timing profiles: {summary['timing_complete_games']}/"
        f"{summary['attempted_games']} complete; "
        f"{summary['valid_games']} valid, {summary['invalid_games']} invalid "
        f"({summary['invalid_rate']:.1%}); "
        f"{summary['valid_rotation_groups']}/"
        f"{summary['attempted_rotation_groups']} complete rotation groups; "
        f"{summary['valid_seed_values']}/{summary['distinct_seed_values']} "
        "distinct seeds"
    )
    if summary["mean_seconds_per_complete_game"]:
        means = summary["mean_seconds_per_complete_game"]
        shares = summary["component_share_of_wall"]
        print(
            "Mean seconds/game: "
            f"wall {means['wall_seconds']:.2f}; "
            f"Mortal {means['mortal_inference_seconds']:.2f}s "
            f"({shares['mortal_inference_seconds']:.1%}), "
            f"advisor {means['advisor_decision_seconds']:.3f}s "
            f"({shares['advisor_decision_seconds']:.1%}), "
            f"container/protocol {means['container_protocol_seconds']:.2f}s "
            f"({shares['container_protocol_seconds']:.1%}) "
            f"(startup {means['container_startup_seconds']:.2f}, "
            f"cleanup {means['container_cleanup_seconds']:.2f}, "
            f"protocol {means['protocol_seconds']:.2f}), "
            f"simulator {means['simulator_seconds']:.2f}s "
            f"({shares['simulator_seconds']:.1%})"
        )
    for bot, values in summary["source_game_rank_context"].items():
        ci = values["ci_95"]
        ci_text = (
            "not estimable"
            if ci[0] is None
            else f"[{ci[0]:.2f}, {ci[1]:.2f}]"
        )
        print(
            f"{bot} source-match average rank: {values['average_rank']} "
            f"(95% rotation-group CI {ci_text}; "
            f"{values['seed_groups']} groups; {values['estimate_basis']})"
        )
    print(f"Per-game CSV: {summary['per_game_csv']}")
    print(f"Summary: {(args.logs_dir / 'timing_profile.json').resolve()}")


if __name__ == "__main__":
    main()
