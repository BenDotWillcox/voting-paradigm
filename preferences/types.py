"""
Core types for the preference elicitation package.

The model operates on `items` (civic value statements). A `Question` is a
prompt built from items. `Evidence` is the stable internal contract for
anything that updates the model: every elicitation modality (pairwise cards,
sliders, free-text extraction, ...) is normalized into typed `Evidence`
before it touches a posterior. LLM components may *produce* evidence; only
deterministic model code may *apply* it.

`PreferenceState` is a serializable snapshot of the model's belief about a
user, including the full evidence trail for auditability and replay.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Type aliases
ItemId = str
QuestionId = str
UserId = str
SessionId = str


class QuestionType(str, Enum):
    PAIRWISE = "pairwise"  # Two items, slider from -10 to +10
    SLIDER = "slider"  # Scalar position between two poles (future UI variant)
    MULTIPLE_CHOICE = "multiple_choice"  # Pick best of 3-4 options (future)


class EvidenceSource(str, Enum):
    """Where a piece of evidence came from.

    Pairwise, slider, confirmed free-text extraction, and confirmed
    corrections share the same typed pairwise likelihood. The remaining
    source is retained for audit without training:

    - FREE_TEXT_EXTRACTION: structured claims parsed from a free-text answer;
      Phase 4C permits this source only after per-claim user confirmation.
    - CORRECTION: a dimension-level user correction ("you are underweighting
      X vs Y"), translated into evidence after confirmation.
    - OVERRIDE: a ballot-level override of an agent's predicted vote. By
      design overrides are recorded for audit but NEVER update the posterior.
    """

    PAIRWISE = "pairwise"
    SLIDER = "slider"
    FREE_TEXT_EXTRACTION = "free_text_extraction"
    CORRECTION = "correction"
    OVERRIDE = "override"


# Sources that models know how to turn into the common pairwise likelihood.
IMPLEMENTED_EVIDENCE_SOURCES = frozenset(
    {
        EvidenceSource.PAIRWISE,
        EvidenceSource.SLIDER,
        EvidenceSource.FREE_TEXT_EXTRACTION,
        EvidenceSource.CORRECTION,
    }
)


class UnsupportedEvidenceError(ValueError):
    """Raised when a model receives evidence it has no likelihood for."""


@dataclass
class QuestionOption:
    """A single option within a question — typically a value/item."""
    item_id: ItemId
    text: str
    description: Optional[str] = None


@dataclass
class Question:
    """A single question presented to the user.

    For pairwise questions, `options` has exactly 2 entries mapping to -10 and +10
    on the slider (options[0] is the left/negative pole, options[1] is the right/positive).
    """
    id: QuestionId
    question_type: QuestionType
    prompt: str
    options: list[QuestionOption]
    domain: Optional[str] = None  # e.g., "economic", "social", "governance"
    source: str = "bank"  # "bank" or "llm_generated"
    metadata: dict = field(default_factory=dict)


@dataclass
class Evidence:
    """One typed observation about the user's preferences.

    The observation always concerns a pair of items `(item_a, item_b)`.
    `value` is signed in [-10, +10]: positive means item_a is preferred over
    item_b with strength |value|; negative means item_b is preferred;
    0 means stated indifference. For sliders between two poles the position
    maps onto the same scale, so both sources share one likelihood.

    `confidence` in (0, 1] scales the observation weight — direct user input
    is 1.0. Extractor confidence remains separate audit metadata unless an
    evaluated weighting policy explicitly changes this. `event_id` is present
    on durable Phase 4C evidence but optional for legacy and synthetic states.
    Inferred and correction sources require both that ID and the typed
    `confirmed_by_participant` flag before a model accepts them.
    `prompt_id` links back to the question (or LLM prompt) that produced the
    evidence; `raw_response` and `extracted_claims` preserve provenance for
    non-structured sources. Evaluator/seed metadata goes in `metadata` (the
    owning state records `model_version`).
    """
    source: EvidenceSource
    item_a: ItemId
    item_b: ItemId
    value: float
    confidence: float = 1.0
    prompt_id: Optional[QuestionId] = None
    raw_response: Optional[str] = None
    extracted_claims: list[str] = field(default_factory=list)
    response_time_ms: Optional[int] = None
    timestamp: Optional[str] = None  # ISO 8601 string, set by engine
    metadata: dict = field(default_factory=dict)
    event_id: Optional[str] = None
    confirmed_by_participant: bool = False

    def preferred_item(self) -> Optional[ItemId]:
        """The preferred item id, or None for stated indifference."""
        if self.value > 0:
            return self.item_a
        if self.value < 0:
            return self.item_b
        return None


@dataclass
class PreferenceState:
    """Serializable snapshot of the user's preference posterior.

    Stores the Gaussian posterior N(mu, Sigma) over item utilities as flat arrays
    for easy JSON serialization. `item_ids` is the canonical ordering; mu[i] and
    Sigma[i,:] correspond to item_ids[i].

    `evidence` is the canonical replay source: models that refit from history
    (e.g. Bradley-Terry MAP) reconstruct their posterior from it, and the eval
    harness treats it — not the DB audit table — as ground truth for a session.
    """
    user_id: UserId
    session_id: SessionId
    item_ids: list[ItemId]
    # Posterior mean of utilities, shape (n_items,)
    mu: list[float]
    # Flattened lower-triangle of posterior covariance, length n*(n+1)/2
    # Stored row-major: sigma_flat[i*(i+1)/2 + j] = Sigma[i,j] for j <= i
    sigma_flat: list[float]
    evidence: list[Evidence] = field(default_factory=list)
    n_questions_asked: int = 0
    asked_question_ids: list[QuestionId] = field(default_factory=list)
    model_version: str = "gaussian_linear_v1"


@dataclass
class ValueEstimate:
    """Summary statistic for a single item/value."""
    item_id: ItemId
    mean: float
    std: float
    rank: int  # 0-indexed, 0 = highest utility


@dataclass
class SessionProgress:
    """Summary of elicitation progress for the UI."""
    n_answered: int
    target_questions: int
    convergence_pct: float  # 0-100
    is_complete: bool
