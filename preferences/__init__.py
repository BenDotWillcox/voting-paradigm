"""
Preference elicitation package.

Bayesian active preference learning for inferring a user's latent political
values from pairwise tradeoff comparisons. Uses a Thurstone pairwise model
with Laplace-approximated Gaussian posterior.
"""

from .types import (
    Question,
    QuestionOption,
    QuestionType,
    Response,
    PreferenceState,
)

__all__ = [
    "Question",
    "QuestionOption",
    "QuestionType",
    "Response",
    "PreferenceState",
]
