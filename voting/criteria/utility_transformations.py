"""
Transformations between utility profiles, for criteria judged under a ballot
model (rated methods).

A utility profile here is treated as a multiset of voter types: utility
vectors with counts. Row order carries no meaning for these criteria, so
results are compared with utility_counts().

- Monotonicity: some voters raise the winner (move_voters with is_raise).
- Participation: more voters turn out (add_voters).
- Consistency: two electorates are pooled (combine).
- Independence of irrelevant alternatives: a loser withdraws
  (remove_candidate).
- Independence of clones: an exact clone joins (add_clone), rated exactly
  like the original by every voter and ranked right after it.
"""

from ..ballot_models.utility_profile import (
    UTILITY_SCALE,
    UtilityProfile,
    create_utility_profile,
)
from ..ballots.ranked_profile import InvalidProfileError
from ..types import CandidateId

Utilities = tuple[int, ...]


def utility_counts(profile: UtilityProfile) -> dict[Utilities, int]:
    """How many voters hold each utility vector; zero counts dropped."""
    counts: dict[Utilities, int] = {}
    for count, utilities in profile.rows:
        if count:
            counts[utilities] = counts.get(utilities, 0) + count
    return counts


def from_counts(
    candidates: tuple[CandidateId, ...],
    counts: dict[Utilities, int],
) -> UtilityProfile:
    """A utility profile with one row per utility vector, in the order given."""
    return create_utility_profile(
        candidates,
        [
            (count, dict(zip(candidates, utilities)))
            for utilities, count in counts.items()
            if count
        ],
    )


def is_raise(before: Utilities, after: Utilities, candidate: int) -> bool:
    """
    Whether `after` raises one candidate's utility and leaves the others as
    they were, up to a positive rescaling (which no sincere ballot model in
    this package distinguishes).

    The other candidates fix the rescaling; the raised candidate must then
    sit strictly higher than before.
    """
    others = [i for i in range(len(before)) if i != candidate]
    if len(others) < 2:
        return after[candidate] > before[candidate]
    first, second = others[0], others[1]
    span = before[first] - before[second]
    if span == 0:
        return False
    scale = (after[first] - after[second]) / span
    if scale <= 0:
        return False
    shift = after[first] - scale * before[first]
    if any(abs(after[i] - (scale * before[i] + shift)) > 1e-9 for i in others):
        return False
    return after[candidate] > scale * before[candidate] + shift + 1e-9


def move_voters(
    profile: UtilityProfile,
    before: Utilities,
    after: Utilities,
    voters: int,
) -> UtilityProfile:
    """
    Move some voters from one utility vector to another.

    Raises:
        InvalidProfileError: If fewer than `voters` voters hold `before`, or
            `voters` is not positive
    """
    counts = utility_counts(profile)
    if voters < 1 or counts.get(before, 0) < voters:
        raise InvalidProfileError(f"Cannot move {voters} voters holding {before}")
    counts[before] -= voters
    counts[after] = counts.get(after, 0) + voters
    return from_counts(profile.candidates, counts)


def add_voters(profile: UtilityProfile, utilities: Utilities, voters: int) -> UtilityProfile:
    """
    Add voters who all hold the same utilities.

    Raises:
        InvalidProfileError: If `voters` is not positive
    """
    if voters < 1:
        raise InvalidProfileError(f"Must add at least one voter, got {voters}")
    counts = utility_counts(profile)
    counts[utilities] = counts.get(utilities, 0) + voters
    return from_counts(profile.candidates, counts)


def combine(first: UtilityProfile, second: UtilityProfile) -> UtilityProfile:
    """
    Pool two electorates over the same candidates.

    Raises:
        InvalidProfileError: If the candidates differ
    """
    if first.candidates != second.candidates:
        raise InvalidProfileError("Only profiles over the same candidates combine")
    counts = utility_counts(first)
    for utilities, count in utility_counts(second).items():
        counts[utilities] = counts.get(utilities, 0) + count
    return from_counts(first.candidates, counts)


def remove_candidate(profile: UtilityProfile, candidate: CandidateId) -> UtilityProfile:
    """
    Remove a candidate; every voter keeps their utilities for the rest.

    Raises:
        InvalidProfileError: If the candidate is not in the profile or is the
            only candidate
    """
    if candidate not in profile.candidates:
        raise InvalidProfileError(f"{candidate} is not a candidate")
    index = profile.candidates.index(candidate)
    remaining = tuple(c for c in profile.candidates if c != candidate)
    if not remaining:
        raise InvalidProfileError("Cannot remove the only candidate")
    counts: dict[Utilities, int] = {}
    for utilities, count in utility_counts(profile).items():
        reduced = utilities[:index] + utilities[index + 1:]
        counts[reduced] = counts.get(reduced, 0) + count
    return from_counts(remaining, counts)


def add_clone(profile: UtilityProfile, candidate: CandidateId, clone: CandidateId) -> UtilityProfile:
    """
    Add an exact clone: a new last candidate every voter rates exactly like
    `candidate`, so it ranks right after it.

    Raises:
        InvalidProfileError: If `candidate` is unknown or `clone` already runs
    """
    if candidate not in profile.candidates or clone in profile.candidates:
        raise InvalidProfileError(f"Cannot clone {candidate} as {clone}")
    index = profile.candidates.index(candidate)
    counts = {
        utilities + (utilities[index],): count
        for utilities, count in utility_counts(profile).items()
    }
    return from_counts(profile.candidates + (clone,), counts)


__all__ = [
    "UTILITY_SCALE",
    "Utilities",
    "add_clone",
    "add_voters",
    "combine",
    "from_counts",
    "is_raise",
    "move_voters",
    "remove_candidate",
    "utility_counts",
]
