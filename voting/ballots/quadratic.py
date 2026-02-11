"""
Quadratic ballot: voter allocates votes from a credit budget where cost = votes².

Used by: Quadratic Voting

Voters distribute an artificial currency (credits) across candidates.
The cost to cast v votes for a candidate is v². Negative votes (opposition)
are allowed by default. A ballot with no allocations is an abstention.

Example with 100 credits:
  - 5 votes for Alice costs 25 credits
  - 3 votes against Bob costs 9 credits
  - Total spent: 34, remaining: 66
"""

import math
from dataclasses import dataclass, field

from ..types import Ballot, CandidateId, VoterId


# Default credit budget per voter per election
DEFAULT_CREDIT_BUDGET = 100

# Allocations: candidate_id -> vote count (positive = support, negative = oppose)
Allocations = dict[CandidateId, int]


@dataclass
class QuadraticBallot(Ballot):
    """
    A ballot where the voter allocates votes with quadratic cost.

    Candidates not in allocations receive 0 votes.
    An empty allocations dict represents an abstention.
    """
    allocations: Allocations = field(default_factory=dict)
    credit_budget: int = DEFAULT_CREDIT_BUDGET


class InvalidQuadraticBallotError(ValueError):
    """Raised when a quadratic ballot violates constraints."""
    pass


def create_quadratic_ballot(
    voter_id: VoterId,
    allocations: Allocations | None = None,
    credit_budget: int = DEFAULT_CREDIT_BUDGET,
    allow_negative: bool = True,
    validate: bool = True,
) -> QuadraticBallot:
    """
    Create a quadratic ballot.

    Args:
        voter_id: The voter's identifier
        allocations: Dict mapping candidate IDs to vote counts, or None for abstention
        credit_budget: Total credits available (default 100)
        allow_negative: If True, negative votes (opposition) are allowed
        validate: If True, raises InvalidQuadraticBallotError for invalid ballots

    Raises:
        InvalidQuadraticBallotError: If validation fails
    """
    if allocations is None:
        return QuadraticBallot(
            voter_id=voter_id, allocations={}, credit_budget=credit_budget
        )

    if validate:
        for candidate_id, votes in allocations.items():
            if not isinstance(votes, int):
                raise InvalidQuadraticBallotError(
                    f"Votes for {candidate_id} must be an integer, "
                    f"got {type(votes).__name__}"
                )
            if votes == 0:
                raise InvalidQuadraticBallotError(
                    f"Votes for {candidate_id} must be non-zero "
                    f"(remove candidate to allocate 0 votes)"
                )
            if not allow_negative and votes < 0:
                raise InvalidQuadraticBallotError(
                    f"Negative votes not allowed: {candidate_id} has {votes} votes"
                )

        total_cost = sum(v * v for v in allocations.values())
        if total_cost > credit_budget:
            raise InvalidQuadraticBallotError(
                f"Total cost {total_cost} exceeds credit budget {credit_budget}"
            )

    return QuadraticBallot(
        voter_id=voter_id, allocations=dict(allocations), credit_budget=credit_budget
    )


def is_quadratic_abstention(ballot: QuadraticBallot) -> bool:
    """Check if a ballot is an abstention (no allocations)."""
    return len(ballot.allocations) == 0


def quadratic_cost(votes: int) -> int:
    """Calculate the credit cost for a number of votes: v²."""
    return votes * votes


def quadratic_total_cost(ballot: QuadraticBallot) -> int:
    """Calculate total credits spent on this ballot."""
    return sum(v * v for v in ballot.allocations.values())


def credits_remaining(ballot: QuadraticBallot) -> int:
    """Calculate credits remaining after all allocations."""
    return ballot.credit_budget - quadratic_total_cost(ballot)


def get_votes(ballot: QuadraticBallot, candidate_id: CandidateId) -> int:
    """Get the vote count for a candidate. Returns 0 if unallocated."""
    return ballot.allocations.get(candidate_id, 0)


def candidates_voted_for(ballot: QuadraticBallot) -> int:
    """Return the number of candidates with allocations on this ballot."""
    return len(ballot.allocations)


def credit_utilization(ballot: QuadraticBallot) -> float:
    """Return the fraction of the credit budget used (0.0 to 1.0)."""
    if ballot.credit_budget == 0:
        return 0.0
    return quadratic_total_cost(ballot) / ballot.credit_budget


def max_votes_for_budget(credit_budget: int) -> int:
    """Return the maximum votes castable for a single candidate given a budget."""
    return int(math.isqrt(credit_budget))
