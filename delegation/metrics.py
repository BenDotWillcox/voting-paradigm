"""
Measures of what delegation did to one question.

These describe concentration and reach. They say nothing about whether the
delegated outcome is better than the direct one.
"""

from __future__ import annotations

from collections import Counter

from voting.types import ElectionResult

from .graph import QuestionResolution


def delegated_share(resolution: QuestionResolution) -> float:
    """The share of voters whose vote is resolved by someone else."""
    total = len(resolution.traces)
    if total == 0:
        return 0.0
    return sum(trace.delegated for trace in resolution.traces.values()) / total


def largest_share(resolution: QuestionResolution) -> float:
    """The share of all votes held by the single heaviest resolver."""
    total = len(resolution.traces)
    if total == 0:
        return 0.0
    return max(resolution.weights().values()) / total


def weight_gini(resolution: QuestionResolution) -> float:
    """
    The Gini coefficient of effective voting weight.

    The population is every voter plus every resolver. A voter whose vote
    someone else resolves has weight zero; a resolver has one unit per vote
    they hold. Direct voting gives 0; one person holding every vote
    approaches 1 as the population grows.
    """
    weights = resolution.weights()
    population = set(resolution.traces) | set(weights)
    values = sorted(weights.get(person, 0) for person in population)
    count = len(values)
    total = sum(values)
    if count == 0 or total == 0:
        return 0.0
    ranked = sum(rank * value for rank, value in enumerate(values, start=1))
    return (2 * ranked) / (count * total) - (count + 1) / count


def chain_length_counts(resolution: QuestionResolution) -> dict[int, int]:
    """How many votes were passed on 0 times, once, twice, and so on."""
    counts = Counter(trace.hops for trace in resolution.traces.values())
    return {hops: counts[hops] for hops in sorted(counts)}


def winners_differ(direct: ElectionResult, delegated: ElectionResult) -> bool:
    """Whether delegation changed who won, compared with direct voting."""
    return set(direct.winners) != set(delegated.winners)
