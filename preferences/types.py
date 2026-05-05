"""
Core types for the preference elicitation package.

The model operates on `items` (civic value statements). A `Question` is a
comparison between items. A `Response` is the user's answer with strength.
`PreferenceState` is a serializable snapshot of the model's belief about a user.
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
    PAIRWISE = "pairwise"  # Slider between two items, -10 to +10
    MULTIPLE_CHOICE = "multiple_choice"  # Pick best of 3-4 options (future)


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
class Response:
    """A user's answer to a question.

    For pairwise: `strength` is in [-10, +10]. Negative = prefer options[0],
    positive = prefer options[1]. `chosen_option_id` is the item id of the
    preferred option (the one on the side of the slider).
    """
    question_id: QuestionId
    chosen_option_id: ItemId
    strength: Optional[float] = None  # -10 to +10 for pairwise
    response_time_ms: Optional[int] = None
    timestamp: Optional[str] = None  # ISO 8601 string, set by engine


@dataclass
class PreferenceState:
    """Serializable snapshot of the user's preference posterior.

    Stores the Gaussian posterior N(mu, Sigma) over item utilities as flat arrays
    for easy JSON serialization. `item_ids` is the canonical ordering; mu[i] and
    Sigma[i,:] correspond to item_ids[i].
    """
    user_id: UserId
    session_id: SessionId
    item_ids: list[ItemId]
    # Posterior mean of utilities, shape (n_items,)
    mu: list[float]
    # Flattened lower-triangle of posterior covariance, length n*(n+1)/2
    # Stored row-major: sigma_flat[i*(i+1)/2 + j] = Sigma[i,j] for j <= i
    sigma_flat: list[float]
    responses: list[Response] = field(default_factory=list)
    n_questions_asked: int = 0
    asked_question_ids: list[QuestionId] = field(default_factory=list)
    model_version: str = "thurstone_v1"


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
