"""
Score ballot: voter rates each candidate on a numeric scale (0-10).

Used by: Score Tally (Range Voting)

Voters assign a score from 0 to 10 to each candidate. Partial scoring
is allowed — unscored candidates receive 0 points. A ballot with no
scores is an abstention.
"""

from dataclasses import dataclass, field

from ..types import Ballot, CandidateId, VoterId


# Minimum and maximum allowed scores
MIN_SCORE = 0
MAX_SCORE = 10

# Scores per candidate: candidate_id -> score (0-10)
Scores = dict[CandidateId, int]


@dataclass
class ScoreBallot(Ballot):
    """
    A ballot where the voter assigns scores (0-10) to candidates.

    Candidates not in the scores dict receive 0 points.
    An empty scores dict represents an abstention.
    """
    scores: Scores = field(default_factory=dict)


class InvalidScoreError(ValueError):
    """Raised when a score is outside the valid range."""
    pass


def create_score_ballot(
    voter_id: VoterId,
    scores: Scores | None = None,
    validate: bool = True,
) -> ScoreBallot:
    """
    Create a score ballot.

    Args:
        voter_id: The voter's identifier
        scores: Dict mapping candidate IDs to scores (0-10), or None for abstention
        validate: If True, raises InvalidScoreError for out-of-range scores

    Raises:
        InvalidScoreError: If any score is outside 0-10 range (when validate=True)
    """
    if scores is None:
        return ScoreBallot(voter_id=voter_id, scores={})

    if validate:
        for candidate_id, score in scores.items():
            if not isinstance(score, int):
                raise InvalidScoreError(
                    f"Score for {candidate_id} must be an integer, got {type(score).__name__}"
                )
            if score < MIN_SCORE or score > MAX_SCORE:
                raise InvalidScoreError(
                    f"Score for {candidate_id} must be {MIN_SCORE}-{MAX_SCORE}, got {score}"
                )

    return ScoreBallot(voter_id=voter_id, scores=dict(scores))


def is_abstention(ballot: ScoreBallot) -> bool:
    """Check if a ballot is an abstention (no scores given)."""
    return len(ballot.scores) == 0


def get_score(ballot: ScoreBallot, candidate_id: CandidateId) -> int:
    """
    Get the score for a candidate. Returns 0 if not scored.
    """
    return ballot.scores.get(candidate_id, 0)


def candidates_scored(ballot: ScoreBallot) -> int:
    """Return the number of candidates scored on this ballot."""
    return len(ballot.scores)


def total_points_given(ballot: ScoreBallot) -> int:
    """Return the total points assigned on this ballot."""
    return sum(ballot.scores.values())


def max_score_on_ballot(ballot: ScoreBallot) -> int | None:
    """Return the highest score given on this ballot, or None if abstention."""
    if is_abstention(ballot):
        return None
    return max(ballot.scores.values())


def min_score_on_ballot(ballot: ScoreBallot) -> int | None:
    """Return the lowest score given on this ballot, or None if abstention."""
    if is_abstention(ballot):
        return None
    return min(ballot.scores.values())
