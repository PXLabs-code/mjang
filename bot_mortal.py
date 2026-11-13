"""mjai adapter for the official Mortal inference engine."""

import json
import os
import sys
from pathlib import Path
from typing import Any


def create_mortal_bot(player_id: int) -> Any:
    os.environ["MORTAL_CFG"] = str(Path("mortal_config.toml").resolve())

    import prelude  # noqa: F401
    import torch
    from config import config
    from engine import MortalEngine
    from libriichi.mjai import Bot
    from model import Brain, DQN

    torch.set_num_threads(1)
    device = torch.device("cpu")
    state = torch.load(
        config["control"]["state_file"],
        weights_only=True,
        map_location=device,
    )
    model_config = state["config"]
    version = model_config["control"]["version"]
    if version not in {3, 4}:
        raise ValueError(f"unsupported Mortal model version: {version}")

    brain = Brain(
        version=version,
        num_blocks=model_config["resnet"]["num_blocks"],
        conv_channels=model_config["resnet"]["conv_channels"],
    ).eval()
    dqn = DQN(version=version).eval()
    brain.load_state_dict(state["mortal"])
    dqn.load_state_dict(state["current_dqn"])
    engine = MortalEngine(
        brain,
        dqn,
        version=version,
        is_oracle=False,
        device=device,
        enable_amp=False,
        enable_quick_eval=True,
        enable_rule_based_agari_guard=True,
        name="mortal",
    )
    return Bot(engine, player_id)


def react(bot: Any, raw_events: str) -> dict[str, Any]:
    events = json.loads(raw_events)
    if not isinstance(events, list) or not events:
        raise ValueError("expected a non-empty mjai event list")

    action: dict[str, Any] | None = None
    for event in events:
        reaction = bot.react(json.dumps(event, separators=(",", ":")))
        if reaction:
            action = json.loads(reaction) if isinstance(reaction, str) else reaction
            if not isinstance(action, dict):
                raise ValueError("Mortal returned a non-object action")
    return action if action is not None else {"type": "none"}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python bot.py PLAYER_ID")
    try:
        player_id = int(sys.argv[1])
        if player_id not in range(4):
            raise ValueError("player_id must be between 0 and 3")
        bot = create_mortal_bot(player_id)
        for line in sys.stdin:
            if line.strip():
                action = react(bot, line)
                sys.stdout.write(json.dumps(action, separators=(",", ":")) + "\n")
                sys.stdout.flush()
    except (ValueError, json.JSONDecodeError) as error:
        sys.stderr.write(f"Mortal bot error: {error}\n")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
