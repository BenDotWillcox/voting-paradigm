"""
Borda Count resolution method.

Each candidate receives points based on their ranking position.
Standard Borda: with n candidates, 1st place gets n-1 points,
2nd gets n-2, ..., last place gets 0 points.

The candidate with the highest total points wins.
"""

from dataclasses import dataclass

from ..ballots.ranked_choice import RankedChoiceBallot, is_abstention
from ..types import (
    Candidate,
    CandidateId,
    ElectionResult,
    TiebreakFunction,
    random_tiebreak,
)


# Points per candidate: candidate_id -> total points
PointTotals = dict[CandidateId, int]


@dataclass
class BordaResult(ElectionResult):
    """Extended result with Borda-specific data."""
    # Total points per candidate
    point_totals: PointTotals
    # Points available per ballot (n-1 for 1st choice with n candidates)
    max_points_per_ballot: int
    # Average points received per candidate
    avg_points_per_candidate: float


def resolve_borda(
    candidates: list[Candidate],
    ballots: list[RankedChoiceBallot],
    tiebreak: TiebreakFunction = random_tiebreak,
) -> BordaResult:
    """
    Resolve an election using Borda Count.

    Standard scoring: with n candidates, rank 1 gets n-1 points,
    rank 2 gets n-2 points, ..., rank n gets 0 points.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties (defaults to random selection)

    Returns:
        Borda result with winner, point totals, and metadata
    """
    n = len(candidates)
    max_points = n - 1 if n > 0 else 0

    # Initialize point totals
    point_totals: PointTotals = {c.id: 0 for c in candidates}

    # Count abstentions and tally points
    abstentions = 0
    for ballot in ballots:
        if is_abstention(ballot):
            abstentions += 1
            continue

        # Award points based on ranking position
        # Index 0 (1st place) gets n-1 points, index 1 gets n-2, etc.
        for position, candidate_id in enumerate(ballot.ranking):
            if candidate_id in point_totals:
                points = max_points - position
                point_totals[candidate_id] += points

    # Find highest point total
    max_total = max(point_totals.values()) if point_totals else 0

    # Find all candidates with highest points
    tied = [cid for cid, total in point_totals.items() if total == max_total]

    # Determine winner
    if len(tied) == 0:
        winners = []
        tiebreak_applied = False
    elif len(tied) == 1:
        winners = tied
        tiebreak_applied = False
    else:
        winners = [tiebreak(tied)]
        tiebreak_applied = True

    # Calculate average points
    if n > 0:
        total_points = sum(point_totals.values())
        avg_points = total_points / n
    else:
        avg_points = 0.0

    # Build vote_counts as point totals for compatibility
    vote_counts = point_totals.copy()

    return BordaResult(
        winners=winners,
        vote_counts=vote_counts,
        total_ballots=len(ballots),
        abstentions=abstentions,
        tiebreak_applied=tiebreak_applied,
        point_totals=point_totals,
        max_points_per_ballot=max_points,
        avg_points_per_candidate=avg_points,
    )
