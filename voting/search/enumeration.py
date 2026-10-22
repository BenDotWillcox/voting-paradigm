"""
Exhaustive enumeration of anonymous profiles.

A profile of n voters over k candidates splits n among the k! rankings, so
there are C(n + k! - 1, k! - 1) of them. They are generated in one fixed
order: rankings in candidate order, and count vectors over those rankings in
descending lexicographic order. That order is what "first" means when two
specimens have the same number of voters.
"""

import itertools
import math
from collections.abc import Iterator, Sequence

from ..ballots.ranked_profile import RankedProfile
from ..types import CandidateId


def rankings(candidates: Sequence[CandidateId]) -> tuple[tuple[CandidateId, ...], ...]:
    """Every strict ranking of the candidates, in canonical order."""
    return tuple(itertools.permutations(candidates))


def profile_count(num_candidates: int, voters: int) -> int:
    """How many distinct profiles of this many voters exist."""
    types = math.factorial(num_candidates)
    return math.comb(voters + types - 1, types - 1)


def profiles(candidates: Sequence[CandidateId], voters: int) -> Iterator[RankedProfile]:
    """Every profile of exactly `voters` voters, in canonical order."""
    candidate_tuple = tuple(candidates)
    types = rankings(candidate_tuple)
    for counts in _count_vectors(voters, len(types)):
        # Rankings come in canonical order and zero rows are dropped, so the
        # rows are already canonical
        yield RankedProfile(
            candidates=candidate_tuple,
            rows=tuple((count, ranking) for count, ranking in zip(counts, types) if count),
        )


def _count_vectors(total: int, parts: int) -> Iterator[tuple[int, ...]]:
    """Non-negative integer vectors of length `parts` summing to `total`."""
    if parts == 1:
        yield (total,)
        return
    for first in range(total, -1, -1):
        for rest in _count_vectors(total - first, parts - 1):
            yield (first,) + rest
