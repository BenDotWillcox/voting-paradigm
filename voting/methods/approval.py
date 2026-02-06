"""
Approval Tally resolution method.

Each candidate's score is the number of ballots that approved them.
The candidate with the highest approval count wins. In case of a tie,
a random tiebreaker selects the winner.

This method encourages voters to express support for all acceptable
candidates, reducing the "spoiler effect" common in plurality voting.
"""

from dataclasses import dataclass

from ..ballots.approval import ApprovalBallot, is_abstention, approval_count
from ..types import (
    Candidate,
    CandidateId,
    ElectionResult,
    VoteCounts,
    TiebreakFunction,
    random_tiebreak,
)


@dataclass
class ApprovalResult(ElectionResult):
    """Extended result with approval-specific metrics."""
    # Average number of approvals per ballot (excluding abstentions)
    avg_approvals_per_ballot: float
    # Approval rate per candidate: approvals / total non-abstaining ballots
    approval_rates: dict[CandidateId, float]


def resolve_approval(
    candidates: list[Candidate],
    ballots: list[ApprovalBallot],
    tiebreak: TiebreakFunction = random_tiebreak,
) -> ApprovalResult:
    """
    Resolve an election using approval voting.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties (defaults to random selection)

    Returns:
        Approval result with winner, vote counts, rates, and metadata
    """
    # Initialize approval counts for all candidates to 0
    vote_counts: VoteCounts = {candidate.id: 0 for candidate in candidates}

    # Count approvals and abstentions
    abstentions = 0
    total_approvals = 0
    valid_candidate_ids = set(vote_counts.keys())

    for ballot in ballots:
        if is_abstention(ballot):
            abstentions += 1
        else:
            valid_approvals = ballot.approvals & valid_candidate_ids
            total_approvals += len(valid_approvals)
            for candidate_id in valid_approvals:
                vote_counts[candidate_id] += 1
            # Approvals for unknown candidates are silently ignored

    # Calculate metrics
    non_abstaining = len(ballots) - abstentions
    if non_abstaining > 0:
        avg_approvals = total_approvals / non_abstaining
    else:
        avg_approvals = 0.0

    # Calculate approval rates
    approval_rates: dict[CandidateId, float] = {}
    for candidate_id, count in vote_counts.items():
        if non_abstaining > 0:
            approval_rates[candidate_id] = count / non_abstaining
        else:
            approval_rates[candidate_id] = 0.0

    # Find the highest approval count
    max_approvals = max(vote_counts.values()) if vote_counts else 0

    # Find all candidates with the highest approval count
    tied = [
        candidate_id
        for candidate_id, count in vote_counts.items()
        if count == max_approvals
    ]

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

    return ApprovalResult(
        winners=winners,
        vote_counts=vote_counts,
        total_ballots=len(ballots),
        abstentions=abstentions,
        tiebreak_applied=tiebreak_applied,
        avg_approvals_per_ballot=avg_approvals,
        approval_rates=approval_rates,
    )
