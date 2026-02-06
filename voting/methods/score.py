"""
Score Tally (Range Voting) resolution method.

Each candidate's score is the sum of all scores received from voters.
Unscored candidates receive 0 from that ballot. The candidate with
the highest total score wins.

Score voting encourages honest expression of preference intensity,
as giving a high score to one candidate doesn't hurt another.
"""

from dataclasses import dataclass

from ..ballots.score import ScoreBallot, is_abstention, get_score, MAX_SCORE
from ..types import (
    Candidate,
    CandidateId,
    ElectionResult,
    TiebreakFunction,
    random_tiebreak,
)


# Total scores per candidate
ScoreTotals = dict[CandidateId, int]


@dataclass
class ScoreResult(ElectionResult):
    """Extended result with score-specific data."""
    # Total score per candidate
    score_totals: ScoreTotals
    # Average score per candidate (total / non-abstaining ballots)
    avg_scores: dict[CandidateId, float]
    # Maximum possible score (max_score * non-abstaining ballots)
    max_possible_score: int
    # Score as percentage of maximum possible
    score_percentages: dict[CandidateId, float]


def resolve_score(
    candidates: list[Candidate],
    ballots: list[ScoreBallot],
    tiebreak: TiebreakFunction = random_tiebreak,
) -> ScoreResult:
    """
    Resolve an election using score voting (range voting).

    Each candidate's total is the sum of scores from all ballots.
    Unscored candidates receive 0 from that ballot.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties (defaults to random selection)

    Returns:
        Score result with winner, totals, averages, and percentages
    """
    candidate_ids = [c.id for c in candidates]

    # Initialize score totals
    score_totals: ScoreTotals = {cid: 0 for cid in candidate_ids}

    # Count abstentions and tally scores
    abstentions = 0
    for ballot in ballots:
        if is_abstention(ballot):
            abstentions += 1
            continue

        # Add scores for each candidate
        for cid in candidate_ids:
            score_totals[cid] += get_score(ballot, cid)

    # Calculate metrics
    non_abstaining = len(ballots) - abstentions
    max_possible = MAX_SCORE * non_abstaining if non_abstaining > 0 else 0

    avg_scores: dict[CandidateId, float] = {}
    score_percentages: dict[CandidateId, float] = {}

    for cid in candidate_ids:
        if non_abstaining > 0:
            avg_scores[cid] = score_totals[cid] / non_abstaining
        else:
            avg_scores[cid] = 0.0

        if max_possible > 0:
            score_percentages[cid] = (score_totals[cid] / max_possible) * 100
        else:
            score_percentages[cid] = 0.0

    # Find highest score total
    max_total = max(score_totals.values()) if score_totals else 0

    # Find all candidates with highest total
    tied = [cid for cid, total in score_totals.items() if total == max_total]

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

    # Use score_totals as vote_counts for compatibility
    vote_counts = score_totals.copy()

    return ScoreResult(
        winners=winners,
        vote_counts=vote_counts,
        total_ballots=len(ballots),
        abstentions=abstentions,
        tiebreak_applied=tiebreak_applied,
        score_totals=score_totals,
        avg_scores=avg_scores,
        max_possible_score=max_possible,
        score_percentages=score_percentages,
    )
