"""
Ranked Choice ballot: voter ranks all candidates in strict order.

Used by: IRV, Borda Count, Condorcet methods

Voters must rank every candidate with unique, sequential ranks (1, 2, 3, ...).
Partial rankings are not allowed — either rank all candidates or abstain.

This ballot stores both list and dictionary representations for optimal
performance across different resolution methods:
- List: O(1) access by rank position (good for IRV, Borda)
- Dict: O(1) lookup by candidate (good for Condorcet pairwise comparisons)
"""

from dataclasses import dataclass, field

from ..types import Ballot, CandidateId, VoterId


@dataclass
class RankedChoiceBallot(Ballot):
    """
    A ballot where the voter ranks all candidates in strict order.

    Stores two representations for O(1) access patterns:
    - ranking: list where index 0 is first choice, index 1 is second, etc.
    - rank_lookup: dict mapping candidate ID to their 1-indexed rank

    An empty ranking represents an abstention.
    """
    # Ordered list of candidate IDs, from most preferred to least preferred
    # Empty list = abstention
    ranking: list[CandidateId] = field(default_factory=list)
    # Reverse lookup: candidate_id -> 1-indexed rank
    # Empty dict = abstention
    rank_lookup: dict[CandidateId, int] = field(default_factory=dict)


class InvalidRankingError(ValueError):
    """Raised when a ranking is invalid."""
    pass


def create_ranked_choice_ballot(
    voter_id: VoterId,
    ranking: list[CandidateId] | None = None,
    candidates: list[CandidateId] | None = None,
) -> RankedChoiceBallot:
    """
    Create a ranked choice ballot.

    Args:
        voter_id: The voter's identifier
        ranking: Ordered list from most to least preferred, or None for abstention
        candidates: If provided, validates that ranking contains exactly these candidates

    Raises:
        InvalidRankingError: If ranking is invalid (duplicates, missing candidates, etc.)
    """
    if ranking is None:
        return RankedChoiceBallot(voter_id=voter_id, ranking=[], rank_lookup={})

    # Check for duplicates
    if len(ranking) != len(set(ranking)):
        raise InvalidRankingError("Ranking contains duplicate candidates")

    # If candidates list provided, validate completeness
    if candidates is not None:
        candidate_set = set(candidates)
        ranking_set = set(ranking)

        if ranking_set != candidate_set:
            missing = candidate_set - ranking_set
            extra = ranking_set - candidate_set
            if missing and extra:
                raise InvalidRankingError(
                    f"Ranking has wrong candidates. Missing: {missing}, Extra: {extra}"
                )
            elif missing:
                raise InvalidRankingError(
                    f"Ranking is incomplete. Missing candidates: {missing}"
                )
            else:
                raise InvalidRankingError(
                    f"Ranking contains unknown candidates: {extra}"
                )

    # Build both representations
    ranking_copy = list(ranking)
    rank_lookup = {candidate: rank + 1 for rank, candidate in enumerate(ranking)}

    return RankedChoiceBallot(
        voter_id=voter_id,
        ranking=ranking_copy,
        rank_lookup=rank_lookup,
    )


def is_abstention(ballot: RankedChoiceBallot) -> bool:
    """Check if a ballot is an abstention (no ranking provided)."""
    return len(ballot.ranking) == 0


def get_rank(ballot: RankedChoiceBallot, candidate_id: CandidateId) -> int | None:
    """
    Get the rank of a candidate on this ballot. O(1) lookup.

    Returns:
        1-indexed rank (1 = first choice), or None if candidate not ranked
    """
    return ballot.rank_lookup.get(candidate_id)


def get_choice_at_rank(ballot: RankedChoiceBallot, rank: int) -> CandidateId | None:
    """
    Get the candidate at a specific rank.

    Args:
        ballot: The ballot to check
        rank: 1-indexed rank (1 = first choice)

    Returns:
        Candidate ID at that rank, or None if rank is out of bounds
    """
    index = rank - 1
    if 0 <= index < len(ballot.ranking):
        return ballot.ranking[index]
    return None


def get_first_choice(ballot: RankedChoiceBallot) -> CandidateId | None:
    """Get the voter's first choice, or None if abstention."""
    return get_choice_at_rank(ballot, 1)


def prefers(
    ballot: RankedChoiceBallot,
    candidate_a: CandidateId,
    candidate_b: CandidateId,
) -> bool | None:
    """
    Check if this ballot prefers candidate A over candidate B. O(1) lookup.

    Returns:
        True if A is ranked higher (lower number) than B
        False if B is ranked higher than A
        None if either candidate is not on the ballot (abstention or invalid)
    """
    rank_a = ballot.rank_lookup.get(candidate_a)
    rank_b = ballot.rank_lookup.get(candidate_b)

    if rank_a is None or rank_b is None:
        return None

    return rank_a < rank_b
