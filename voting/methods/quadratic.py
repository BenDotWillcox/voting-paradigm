"""
Quadratic Voting resolution method.

Each candidate's net vote total is the sum of votes received across all
non-abstaining ballots. Positive votes add, negative votes subtract.
The candidate with the highest net total wins.

Quadratic voting uses credit-based ballots where the cost to cast v votes
is v², encouraging voters to express preference intensity while spreading
votes across candidates they care about.
"""

from dataclasses import dataclass

from ..ballots.quadratic import (
    QuadraticBallot,
    is_quadratic_abstention,
)
from ..types import (
    Candidate,
    CandidateId,
    ElectionResult,
    TiebreakFunction,
    random_tiebreak,
)


@dataclass
class QuadraticResult(ElectionResult):
    """Extended result with quadratic-voting-specific data."""
    # Net vote total per candidate (sum of positive and negative votes)
    vote_totals: dict[CandidateId, int]
    # Total credits spent across all non-abstaining ballots
    total_credits_spent: int
    # Total credits available across all non-abstaining ballots
    total_credits_available: int
    # Overall utilization: total spent / total available
    overall_utilization: float
    # Mean of individual voter utilization rates
    avg_voter_utilization: float
    # Number of candidates with net-negative vote totals
    candidates_with_negative_totals: int


def resolve_quadratic(
    candidates: list[Candidate],
    ballots: list[QuadraticBallot],
    tiebreak: TiebreakFunction = random_tiebreak,
) -> QuadraticResult:
    """
    Resolve an election using quadratic voting.

    Each candidate's total is the sum of votes from all non-abstaining ballots.
    Votes for unknown candidates are silently ignored.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties (defaults to random selection)

    Returns:
        QuadraticResult with winner, totals, and utilization metrics
    """
    candidate_ids = {c.id for c in candidates}

    # Initialize vote totals
    vote_totals: dict[CandidateId, int] = {cid: 0 for cid in candidate_ids}

    # Track credits and abstentions
    abstentions = 0
    total_credits_spent = 0
    total_credits_available = 0
    voter_utilizations: list[float] = []
    counted_vote_allocations = 0

    for ballot in ballots:
        if is_quadratic_abstention(ballot):
            abstentions += 1
            continue

        # Add votes for known candidates only
        known_cost = 0
        for cid, votes in ballot.allocations.items():
            if cid in candidate_ids:
                vote_totals[cid] += votes
                counted_vote_allocations += 1
                known_cost += votes * votes

        # Track credit metrics
        total_credits_spent += known_cost
        total_credits_available += ballot.credit_budget
        if ballot.credit_budget == 0:
            voter_utilizations.append(0.0)
        else:
            voter_utilizations.append(known_cost / ballot.credit_budget)

    # Calculate aggregate utilization
    if total_credits_available > 0:
        overall_utilization = total_credits_spent / total_credits_available
    else:
        overall_utilization = 0.0

    if voter_utilizations:
        avg_voter_utilization = sum(voter_utilizations) / len(voter_utilizations)
    else:
        avg_voter_utilization = 0.0

    # Count candidates with net-negative totals
    candidates_with_negative_totals = sum(
        1 for total in vote_totals.values() if total < 0
    )

    # Determine winner. If no known-candidate votes were cast, treat as no-result.
    if counted_vote_allocations == 0:
        winners: list[CandidateId] = []
        tiebreak_applied = False
    else:
        # Find highest net total
        max_total = max(vote_totals.values()) if vote_totals else 0

        # Find all candidates with highest total
        tied = [cid for cid, total in vote_totals.items() if total == max_total]

        if len(tied) == 1:
            winners = tied
            tiebreak_applied = False
        else:
            winners = [tiebreak(tied)]
            tiebreak_applied = True

    # Use vote_totals as vote_counts for base class compatibility
    vote_counts = vote_totals.copy()

    return QuadraticResult(
        winners=winners,
        vote_counts=vote_counts,
        total_ballots=len(ballots),
        abstentions=abstentions,
        tiebreak_applied=tiebreak_applied,
        vote_totals=vote_totals,
        total_credits_spent=total_credits_spent,
        total_credits_available=total_credits_available,
        overall_utilization=overall_utilization,
        avg_voter_utilization=avg_voter_utilization,
        candidates_with_negative_totals=candidates_with_negative_totals,
    )
