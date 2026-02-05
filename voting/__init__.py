"""
Voting mechanisms package for experimenting with electoral methods.

Design principle: Ballot types (how voters express preferences) are
separate from resolution methods (how ballots are tallied).
"""

from .types import (
    CandidateId,
    Candidate,
    VoterId,
    Ballot,
    VoteCounts,
    ElectionResult,
    random_tiebreak,
)
from .ballots.single_choice import (
    SingleChoiceBallot,
    create_single_choice_ballot,
    is_abstention as is_single_choice_abstention,
)
from .ballots.approval import (
    ApprovalBallot,
    create_approval_ballot,
    is_abstention as is_approval_abstention,
    approval_count,
)
from .ballots.ranked_choice import (
    RankedChoiceBallot,
    create_ranked_choice_ballot,
    is_abstention as is_ranked_choice_abstention,
    get_rank,
    get_choice_at_rank,
    get_first_choice,
    prefers,
    InvalidRankingError,
)
from .ballots.score import (
    ScoreBallot,
    create_score_ballot,
    is_abstention as is_score_abstention,
    get_score,
    candidates_scored,
    total_points_given,
    max_score_on_ballot,
    min_score_on_ballot,
    InvalidScoreError,
    MIN_SCORE,
    MAX_SCORE,
)
from .methods.plurality import resolve_plurality
from .methods.approval import resolve_approval, ApprovalResult
from .methods.irv import resolve_irv, IRVResult, IRVRound
from .methods.borda import resolve_borda, BordaResult
from .methods.ranked_pairs import resolve_ranked_pairs, RankedPairsResult, PairwiseMatrix
from .methods.score import resolve_score, ScoreResult

__all__ = [
    # Types
    "CandidateId",
    "Candidate",
    "VoterId",
    "Ballot",
    "VoteCounts",
    "ElectionResult",
    "random_tiebreak",
    # Single choice ballots
    "SingleChoiceBallot",
    "create_single_choice_ballot",
    "is_single_choice_abstention",
    # Approval ballots
    "ApprovalBallot",
    "create_approval_ballot",
    "is_approval_abstention",
    "approval_count",
    # Ranked choice ballots
    "RankedChoiceBallot",
    "create_ranked_choice_ballot",
    "is_ranked_choice_abstention",
    "get_rank",
    "get_choice_at_rank",
    "get_first_choice",
    "prefers",
    "InvalidRankingError",
    # Score ballots
    "ScoreBallot",
    "create_score_ballot",
    "is_score_abstention",
    "get_score",
    "candidates_scored",
    "total_points_given",
    "max_score_on_ballot",
    "min_score_on_ballot",
    "InvalidScoreError",
    "MIN_SCORE",
    "MAX_SCORE",
    # Methods
    "resolve_plurality",
    "resolve_approval",
    "ApprovalResult",
    "resolve_irv",
    "IRVResult",
    "IRVRound",
    "resolve_borda",
    "BordaResult",
    "resolve_ranked_pairs",
    "RankedPairsResult",
    "PairwiseMatrix",
    "resolve_score",
    "ScoreResult",
]
