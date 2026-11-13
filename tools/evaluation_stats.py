"""Rotation-grouped statistics shared by evaluation reports."""

import random
from collections import Counter
from collections.abc import Mapping, Sequence


def grouped_mean_interval(
    values_by_group: Mapping[str, Sequence[float]],
    bootstrap_samples: int = 4000,
    random_seed: int = 1729,
) -> dict[str, float | int | None]:
    group_means = [
        sum(values) / len(values)
        for _, values in sorted(values_by_group.items())
        if values
    ]
    if not group_means:
        raise ValueError("at least one non-empty seed group is required")
    estimate = sum(group_means) / len(group_means)
    if len(group_means) == 1:
        return {
            "mean": estimate,
            "lower_95": None,
            "upper_95": None,
            "groups": 1,
        }
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")

    generator = random.Random(random_seed)
    group_count = len(group_means)
    bootstrap_means = []
    for _ in range(bootstrap_samples):
        sample_total = sum(
            group_means[generator.randrange(group_count)]
            for _ in range(group_count)
        )
        bootstrap_means.append(sample_total / group_count)
    bootstrap_means.sort()
    return {
        "mean": estimate,
        "lower_95": _percentile(bootstrap_means, 0.025),
        "upper_95": _percentile(bootstrap_means, 0.975),
        "groups": group_count,
    }


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = position - lower_index
    return (
        sorted_values[lower_index] * (1 - fraction)
        + sorted_values[upper_index] * fraction
    )


def complete_rotation_groups(
    rotations: Mapping[str, set[tuple[str, ...]]],
) -> set[str]:
    """Return seeds represented by all four distinct seat rotations."""
    complete: set[str] = set()
    for seed, arrangements in rotations.items():
        if len(arrangements) != 4:
            continue
        configurations = list(arrangements)
        if any(len(configuration) != 4 for configuration in configurations):
            continue
        players = Counter(configurations[0])
        if all(Counter(configuration) == players for configuration in configurations):
            complete.add(seed)
    return complete
