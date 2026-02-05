"""
Plurality (First-Past-The-Post) resolution method.

The candidate with the most votes wins. In case of an exact tie,
a random tiebreaker selects the winner.

Note: This method can elect a winner with less than majority support
when there are more than two candidates.
"""

from ..ballots.single_choice import SingleChoiceBallot, is_abstention
from ..types import (
    Candidate,
    CandidateId,
    ElectionResult,
    VoteCounts,
    TiebreakFunction,
    random_tiebreak,
)


def resolve_plurality(
    candidates: list[Candidate],
    ballots: list[SingleChoiceBallot],
    tiebreak: TiebreakFunction = random_tiebreak,
) -> ElectionResult:
    """
    Resolve an election using plurality voting.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties (defaults to random selection)

    Returns:
        Election result with winner, vote counts, and metadata
    """
    # Initialize vote counts for all candidates to 0
    vote_counts: VoteCounts = {candidate.id: 0 for candidate in candidates}

    # Count votes and abstentions
    abstentions = 0
    for ballot in ballots:
        if is_abstention(ballot):
            abstentions += 1
        elif ballot.choice in vote_counts:
            # Only count votes for valid candidates
            vote_counts[ballot.choice] += 1
        # Votes for unknown candidates are silently ignored

    # Find the highest vote count
    max_votes = max(vote_counts.values()) if vote_counts else 0

    # Find all candidates with the highest vote count
    tied = [
        candidate_id
        for candidate_id, count in vote_counts.items()
        if count == max_votes
    ]

    # Determine winner
    if len(tied) == 0:
        # No candidates
        winners = []
        tiebreak_applied = False
    elif len(tied) == 1:
        # Clear winner
        winners = tied
        tiebreak_applied = False
    else:
        # Tie - use tiebreaker
        winners = [tiebreak(tied)]
        tiebreak_applied = True

    return ElectionResult(
        winners=winners,
        vote_counts=vote_counts,
        total_ballots=len(ballots),
        abstentions=abstentions,
        tiebreak_applied=tiebreak_applied,
    )
