"""Benchmark concurrent efficiency-versus-Mortal mjai games."""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from pathlib import Path
from typing import Any, Callable, TypeVar

from report_mortal_latency import count_mortal_inferences
from summarize_results import read_match


ROOT = Path(__file__).resolve().parents[1]
RUN_EXPERIMENT = Path(__file__).with_name("run_experiment.py")
CPU_RE = re.compile(r"^\s*([\d.]+)%\s*$")
MEMORY_RE = re.compile(r"^\s*([\d.]+)\s*([A-Za-z]+)")
MEMORY_FACTORS = {
    "B": 1 / (1024 * 1024),
    "kB": 1 / 1024,
    "KB": 1 / 1024,
    "KiB": 1 / 1024,
    "MB": 1,
    "MiB": 1,
    "GB": 1024,
    "GiB": 1024,
}
GameResult = TypeVar("GameResult")


def run_concurrent_games(
    games: int,
    concurrency: int,
    port_base: int,
    runner: Callable[[int, int], GameResult],
) -> list[GameResult]:
    available_ports: Queue[int] = Queue()
    for slot in range(concurrency):
        available_ports.put(port_base + 4 * slot)

    def run_with_port(game_index: int) -> GameResult:
        port = available_ports.get()
        try:
            return runner(game_index, port)
        finally:
            available_ports.put(port)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(run_with_port, game_index)
            for game_index in range(1, games + 1)
        ]
        return [future.result() for future in futures]


def memory_mib(value: str) -> float:
    match = MEMORY_RE.match(value)
    if match is None or match.group(2) not in MEMORY_FACTORS:
        raise ValueError(f"unrecognized Docker memory value: {value!r}")
    return float(match.group(1)) * MEMORY_FACTORS[match.group(2)]


def parse_docker_stats(
    output: str, excluded_container_ids: set[str]
) -> tuple[float, float, int]:
    cpu_percent = 0.0
    memory_mib_total = 0.0
    active_containers = 0
    for line in output.splitlines():
        fields = line.split("|", 2)
        if len(fields) != 3:
            raise ValueError(f"invalid docker stats row: {line!r}")
        container_id, cpu_value, memory_value = fields
        if any(
            container_id.startswith(container_id_prefix)
            or container_id_prefix.startswith(container_id)
            for container_id_prefix in excluded_container_ids
        ):
            continue
        cpu_match = CPU_RE.match(cpu_value)
        if cpu_match is None:
            raise ValueError(f"unrecognized Docker CPU value: {cpu_value!r}")
        memory_value = memory_value.split("/", 1)[0].strip()
        cpu_percent += float(cpu_match.group(1))
        memory_mib_total += memory_mib(memory_value)
        active_containers += 1
    return cpu_percent / 100, memory_mib_total, active_containers


def docker_container_ids() -> set[str]:
    result = subprocess.run(
        ["docker", "ps", "--quiet"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def sample_docker_usage(
    stop_event: threading.Event,
    samples: list[tuple[float, float, float, int]],
    errors: list[Exception],
    excluded_container_ids: set[str],
    interval: float,
) -> None:
    command = [
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{.ID}}|{{.CPUPerc}}|{{.MemUsage}}",
    ]
    try:
        while not stop_event.is_set():
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            cpu_cores, memory_mib_total, active = parse_docker_stats(
                result.stdout, excluded_container_ids
            )
            samples.append(
                (time.monotonic(), cpu_cores, memory_mib_total, active)
            )
            stop_event.wait(interval)
    except Exception as error:
        errors.append(error)
        stop_event.set()


def run_game(
    game_index: int,
    seed: int,
    port_base: int,
    logs_dir: Path,
    efficiency_submission: Path,
    mortal_submission: Path,
    docker_image: str,
    timeout: float,
) -> dict[str, Any]:
    game_dir = logs_dir / f"game_{game_index:04d}"
    game_dir.mkdir()
    command = [
        sys.executable,
        str(RUN_EXPERIMENT),
        "--submission",
        str(efficiency_submission),
        "--submission",
        str(mortal_submission),
        "--submission",
        str(mortal_submission),
        "--submission",
        str(mortal_submission),
        "--bot-name",
        "efficiency",
        "--bot-name",
        "mortal",
        "--bot-name",
        "mortal",
        "--bot-name",
        "mortal",
        "--logs-dir",
        str(game_dir),
        "--docker-image",
        docker_image,
        "--timeout",
        str(timeout),
        "--seed",
        str(seed),
        "--port-base",
        str(port_base),
    ]
    started = time.monotonic()
    with (game_dir / "runner.log").open("w", encoding="utf-8") as output:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
    wall_seconds = time.monotonic() - started
    summary_path = game_dir / "summary.json"
    errors_path = game_dir / "errors.json"
    errors: list[dict[str, Any]] = []
    bots: list[str] | None = None
    ranks: list[int] | None = None
    run_errors: list[str] = []
    inference_log_error = ""
    if result.returncode:
        run_errors.append(f"runner exit code {result.returncode}")

    if errors_path.is_file():
        loaded_errors = json.loads(errors_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_errors, list) or any(
            not isinstance(error, dict) for error in loaded_errors
        ):
            raise ValueError(f"{errors_path} contains an invalid error report")
        errors = loaded_errors
    elif result.returncode == 0:
        run_errors.append(f"missing {errors_path.name}")
    simulation_error_count = sum(bool(error) for error in errors)

    if summary_path.is_file():
        if simulation_error_count:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            loaded_ranks = summary.get("rank") if isinstance(summary, dict) else None
            metadata = json.loads(
                (game_dir / "experiment.json").read_text(encoding="utf-8")
            )
            loaded_bots = (
                metadata.get("seat_bots") if isinstance(metadata, dict) else None
            )
            if (
                not isinstance(loaded_ranks, list)
                or len(loaded_ranks) != 4
                or any(type(rank) is not int for rank in loaded_ranks)
                or sorted(loaded_ranks) != [1, 2, 3, 4]
                or not isinstance(loaded_bots, list)
                or len(loaded_bots) != 4
                or any(not isinstance(bot, str) or not bot for bot in loaded_bots)
            ):
                raise ValueError(f"{summary_path} has invalid ranks or bot mapping")
            ranks = loaded_ranks
            bots = loaded_bots
        elif result.returncode == 0:
            try:
                bots, ranks = read_match(
                    summary_path, ["efficiency", "mortal", "mortal", "mortal"]
                )
            except ValueError as error:
                run_errors.append(str(error))
    elif result.returncode == 0:
        run_errors.append(f"missing {summary_path.name}")

    try:
        mortal_inferences = count_mortal_inferences(
            game_dir, allow_missing_logs=True
        )
    except (OSError, ValueError) as error:
        mortal_inferences = 0
        inference_log_error = str(error)
    if not mortal_inferences and not inference_log_error:
        inference_log_error = "no Mortal inference records found"

    valid = (
        result.returncode == 0
        and simulation_error_count == 0
        and not run_errors
        and not inference_log_error
        and bots is not None
        and ranks is not None
    )
    return {
        "game": game_dir.name,
        "seed": seed,
        "wall_seconds": wall_seconds,
        "mortal_inference_count": mortal_inferences,
        "simulation_errors": simulation_error_count,
        "valid": valid,
        "runner_exit_code": result.returncode,
        "run_error": "; ".join(run_errors),
        "inference_log_error": inference_log_error,
        "efficiency_rank": (
            ranks[bots.index("efficiency")]
            if bots is not None
            and ranks is not None
            and "efficiency" in bots
            else ""
        ),
        "mortal_ranks": (
            ",".join(
                str(rank) for bot, rank in zip(bots, ranks) if bot == "mortal"
            )
            if bots is not None and ranks is not None
            else ""
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--efficiency-submission", type=Path, required=True)
    parser.add_argument("--mortal-submission", type=Path, required=True)
    parser.add_argument("--logs-dir", type=Path, required=True)
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--seed", type=int, default=3000)
    parser.add_argument("--port-base", type=int, default=28090)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--docker-image", default="majang-mortal:cpu")
    parser.add_argument("--sample-interval", type=float, default=1.0)
    args = parser.parse_args()

    if args.games < 1:
        parser.error("--games must be positive")
    if not 1 <= args.concurrency <= args.games:
        parser.error("--concurrency must be between 1 and --games")
    if args.seed < 0:
        parser.error("--seed must be non-negative")
    if args.port_base < 1 or args.port_base + 4 * args.concurrency > 65536:
        parser.error("--port-base must allow four ports per concurrent game")
    if args.timeout <= 0 or args.sample_interval <= 0:
        parser.error("--timeout and --sample-interval must be positive")
    for submission in (args.efficiency_submission, args.mortal_submission):
        if not submission.is_file():
            parser.error(f"submission does not exist: {submission}")
    if not args.logs_dir.is_dir() and args.logs_dir.exists():
        parser.error(f"logs directory is not a directory: {args.logs_dir}")
    args.logs_dir.mkdir(parents=True, exist_ok=True)
    if any((args.logs_dir / f"game_{index:04d}").exists() for index in range(1, args.games + 1)):
        parser.error("one or more game output directories already exist")

    excluded_ids = docker_container_ids()
    stop_event = threading.Event()
    samples: list[tuple[float, float, float, int]] = []
    monitor_errors: list[Exception] = []
    monitor = threading.Thread(
        target=sample_docker_usage,
        args=(
            stop_event,
            samples,
            monitor_errors,
            excluded_ids,
            args.sample_interval,
        ),
        daemon=True,
    )
    monitor.start()
    started = time.monotonic()

    def execute_game(game_index: int, port: int) -> dict[str, Any]:
        return run_game(
            game_index,
            args.seed + game_index - 1,
            port,
            args.logs_dir,
            args.efficiency_submission.resolve(),
            args.mortal_submission.resolve(),
            args.docker_image,
            args.timeout,
        )

    try:
        game_results = run_concurrent_games(
            args.games, args.concurrency, args.port_base, execute_game
        )
    finally:
        wall_seconds = time.monotonic() - started
        stop_event.set()
        monitor.join()
    if monitor_errors:
        raise RuntimeError(f"Docker resource sampling failed: {monitor_errors[0]}")

    games_csv = args.logs_dir / "games.csv"
    fieldnames = [
        "game",
        "seed",
        "wall_seconds",
        "mortal_inference_count",
        "simulation_errors",
        "valid",
        "runner_exit_code",
        "run_error",
        "inference_log_error",
        "efficiency_rank",
        "mortal_ranks",
    ]
    with games_csv.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(game_results)

    host_cpus = os.cpu_count() or 1
    mean_cpu_cores = sum(sample[1] for sample in samples) / max(1, len(samples))
    peak_cpu_cores = max((sample[1] for sample in samples), default=0.0)
    peak_memory_mib = max((sample[2] for sample in samples), default=0.0)
    valid_games = sum(row["valid"] for row in game_results)
    summary = {
        "games": args.games,
        "valid_games": valid_games,
        "failed_games": args.games - valid_games,
        "concurrency": args.concurrency,
        "seed_start": [10000, args.seed],
        "wall_seconds": wall_seconds,
        "games_per_hour": args.games * 3600 / wall_seconds,
        "valid_games_per_hour": valid_games * 3600 / wall_seconds,
        "mean_game_seconds": sum(row["wall_seconds"] for row in game_results)
        / len(game_results),
        "mean_mortal_inferences_per_game": sum(
            row["mortal_inference_count"] for row in game_results
        )
        / len(game_results),
        "docker_cpu": {
            "samples": len(samples),
            "mean_cores": mean_cpu_cores,
            "peak_cores": peak_cpu_cores,
            "mean_host_percent": mean_cpu_cores / host_cpus * 100,
            "peak_memory_mib": peak_memory_mib,
        },
    }
    (args.logs_dir / "benchmark.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(
        f"Games: {args.games} attempted, {valid_games} valid, "
        f"{args.games - valid_games} with simulation errors; "
        f"concurrency: {args.concurrency}"
    )
    print(f"Wall time: {wall_seconds:.1f} s")
    print(
        f"Throughput: {summary['games_per_hour']:.1f} attempted and "
        f"{summary['valid_games_per_hour']:.1f} valid games/hour"
    )
    print(f"Mean game time: {summary['mean_game_seconds']:.2f} s")
    print(
        "Mortal inferences/game: "
        f"{summary['mean_mortal_inferences_per_game']:.1f}"
    )
    print(
        "Docker CPU: "
        f"{mean_cpu_cores:.2f} mean cores, "
        f"{summary['docker_cpu']['mean_host_percent']:.1f}% of "
        f"{host_cpus} host CPUs; peak memory "
        f"{peak_memory_mib:.0f} MiB"
    )
    print(f"Per-game CSV: {games_csv.resolve()}")
    print(f"Summary: {(args.logs_dir / 'benchmark.json').resolve()}")


if __name__ == "__main__":
    main()
