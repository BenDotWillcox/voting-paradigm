"""
Transformations between profiles, for criteria that compare two electorates.

- Monotonicity: some voters raise the winner (raise_candidate).
- Participation: more voters turn out (add_voters).
- Consistency: two electorates are pooled (combine).
- Independence of irrelevant alternatives: a loser withdraws
  (remove_candidate).
- Independence of clones: a candidate gains a clone, a candidate ranked next
  to it by every voter (are_clones, and remove_candidate to undo it).

Each function returns a new canonical profile and leaves its input unchanged.
"""

from ..ballots.ranked_profile import (
    InvalidProfileError,
    RankedProfile,
    create_ranked_profile,
)
from ..types import CandidateId


def raise_candidate(
    profile: RankedProfile,
    ranking: tuple[CandidateId, ...],
    candidate: CandidateId,
    position: int,
    voters: int,
) -> RankedProfile:
    """
    Move a candidate up to a position for some of the voters with a ranking.

    The candidate's rivals keep their relative order. Position 0 is first.

    Raises:
        InvalidProfileError: If fewer than `voters` voters cast `ranking`,
            `voters` is not positive, or the move would not raise the
            candidate
    """
    counts = dict((row_ranking, count) for count, row_ranking in profile.rows)
    available = counts.get(ranking, 0)
    if voters < 1 or voters > available:
        raise InvalidProfileError(
            f"Cannot move {voters} of the {available} voters ranking {ranking}"
        )
    current = ranking.index(candidate)
    if not 0 <= position < current:
        raise InvalidProfileError(
            f"Position {position} does not raise {candidate} from position {current}"
        )

    rivals = [c for c in ranking if c != candidate]
    raised = tuple(rivals[:position] + [candidate] + rivals[position:])
    counts[ranking] = available - voters
    counts[raised] = counts.get(raised, 0) + voters
    return _from_counts(profile.candidates, counts)


def add_voters(
    profile: RankedProfile,
    ranking: tuple[CandidateId, ...],
    voters: int,
) -> RankedProfile:
    """
    Add voters who all cast the same ranking.

    Raises:
        InvalidProfileError: If `voters` is not positive
        InvalidRankingError: If `ranking` is not a complete strict ranking
    """
    if voters < 1:
        raise InvalidProfileError(f"Must add at least one voter, got {voters}")
    rows = [(count, row) for count, row in profile.rows] + [(voters, ranking)]
    return create_ranked_profile(profile.candidates, rows)


def combine(first: RankedProfile, second: RankedProfile) -> RankedProfile:
    """
    Pool two electorates over the same candidates.

    Raises:
        InvalidProfileError: If the candidates differ
    """
    if first.candidates != second.candidates:
        raise InvalidProfileError("Only profiles over the same candidates combine")
    counts = dict((ranking, count) for count, ranking in first.rows)
    for count, ranking in second.rows:
        counts[ranking] = counts.get(ranking, 0) + count
    return _from_counts(first.candidates, counts)


def remove_candidate(profile: RankedProfile, candidate: CandidateId) -> RankedProfile:
    """
    Remove a candidate from the race; every voter keeps the rest of their order.

    Raises:
        InvalidProfileError: If the candidate is not in the profile or is the
            only candidate
    """
    if candidate not in profile.candidates:
        raise InvalidProfileError(f"{candidate} is not a candidate")
    remaining = tuple(c for c in profile.candidates if c != candidate)
    if not remaining:
        raise InvalidProfileError("Cannot remove the only candidate")
    counts: dict[tuple[CandidateId, ...], int] = {}
    for count, ranking in profile.rows:
        reduced = tuple(c for c in ranking if c != candidate)
        counts[reduced] = counts.get(reduced, 0) + count
    return _from_counts(remaining, counts)


def are_clones(profile: RankedProfile, first: CandidateId, second: CandidateId) -> bool:
    """
    Whether every voter ranks the two candidates next to each other.

    An empty profile has no voter who separates them, so any two candidates
    are clones in it.
    """
    return all(
        abs(ranking.index(first) - ranking.index(second)) == 1
        for _, ranking in profile.rows
    )


def _from_counts(
    candidates: tuple[CandidateId, ...],
    counts: dict[tuple[CandidateId, ...], int],
) -> RankedProfile:
    """Canonicalize counts whose rankings came from a valid profile."""
    return create_ranked_profile(
        candidates,
        ((count, ranking) for ranking, count in counts.items()),
        validate=False,
    )
