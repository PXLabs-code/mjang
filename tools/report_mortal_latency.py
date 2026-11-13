"""Report Mortal inference latency from mjai client stdout logs."""

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def collect_latencies(logs_dir: Path) -> list[float]:
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
            for line in log_path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                meta = event.get("meta") if isinstance(event, dict) else None
                eval_time_ns = meta.get("eval_time_ns") if isinstance(meta, dict) else None
                if isinstance(eval_time_ns, (int, float)):
                    latencies_ms.append(eval_time_ns / 1_000_000)
    if not latencies_ms:
        raise ValueError(f"no Mortal eval_time_ns values found under {logs_dir}")
    return latencies_ms


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


if __name__ == "__main__":
    main()
