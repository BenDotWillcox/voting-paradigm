"""
Preference elicitation package.

Bayesian active preference learning for inferring a user's latent civic
values from tradeoff comparisons. All elicitation modalities are normalized
into typed `Evidence`; deterministic models (Gaussian linear, Bradley-Terry
+ Laplace) own the posterior; acquisition policies pick the next question.
"""

from .types import (
    Evidence,
    EvidenceSource,
    IMPLEMENTED_EVIDENCE_SOURCES,
    PreferenceState,
    Question,
    QuestionOption,
    QuestionType,
    UnsupportedEvidenceError,
)

__all__ = [
    "Evidence",
    "EvidenceSource",
    "IMPLEMENTED_EVIDENCE_SOURCES",
    "PreferenceState",
    "Question",
    "QuestionOption",
    "QuestionType",
    "UnsupportedEvidenceError",
]
