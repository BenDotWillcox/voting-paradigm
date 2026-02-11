"""Resolution methods for tallying ballots."""

from .plurality import resolve_plurality
from .approval import resolve_approval, ApprovalResult
from .irv import resolve_irv, IRVResult, IRVRound
from .borda import resolve_borda, BordaResult
from .ranked_pairs import resolve_ranked_pairs, RankedPairsResult, PairwiseMatrix
from .score import resolve_score, ScoreResult
from .quadratic import resolve_quadratic, QuadraticResult

__all__ = [
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
    "resolve_quadratic",
    "QuadraticResult",
]
