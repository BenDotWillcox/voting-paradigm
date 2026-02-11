"""Ballot type definitions."""

from .single_choice import (
    SingleChoiceBallot,
    create_single_choice_ballot,
    is_abstention as is_single_choice_abstention,
)
from .approval import (
    ApprovalBallot,
    create_approval_ballot,
    is_abstention as is_approval_abstention,
    approval_count,
)
from .ranked_choice import (
    RankedChoiceBallot,
    create_ranked_choice_ballot,
    is_abstention as is_ranked_choice_abstention,
    get_rank,
    get_choice_at_rank,
    get_first_choice,
    prefers,
    InvalidRankingError,
)
from .score import (
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
from .quadratic import (
    QuadraticBallot,
    create_quadratic_ballot,
    is_quadratic_abstention,
    get_votes,
    candidates_voted_for,
    quadratic_cost,
    quadratic_total_cost,
    credits_remaining,
    credit_utilization,
    max_votes_for_budget,
    InvalidQuadraticBallotError,
    DEFAULT_CREDIT_BUDGET,
)

__all__ = [
    # Single choice
    "SingleChoiceBallot",
    "create_single_choice_ballot",
    "is_single_choice_abstention",
    # Approval
    "ApprovalBallot",
    "create_approval_ballot",
    "is_approval_abstention",
    "approval_count",
    # Ranked choice
    "RankedChoiceBallot",
    "create_ranked_choice_ballot",
    "is_ranked_choice_abstention",
    "get_rank",
    "get_choice_at_rank",
    "get_first_choice",
    "prefers",
    "InvalidRankingError",
    # Score
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
    # Quadratic
    "QuadraticBallot",
    "create_quadratic_ballot",
    "is_quadratic_abstention",
    "get_votes",
    "candidates_voted_for",
    "quadratic_cost",
    "quadratic_total_cost",
    "credits_remaining",
    "credit_utilization",
    "max_votes_for_budget",
    "InvalidQuadraticBallotError",
    "DEFAULT_CREDIT_BUDGET",
]
