"""
Pydantic request/response models for the preferences router.

The API is stateless: the client (Next.js) is responsible for persisting the
PreferenceState between calls. Every request carries the current state; every
response returns the updated state.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core schemas (mirror the dataclasses in preferences.types)
# ---------------------------------------------------------------------------


class QuestionOptionSchema(BaseModel):
    item_id: str
    text: str
    description: Optional[str] = None


class QuestionSchema(BaseModel):
    id: str
    question_type: str
    prompt: str
    options: list[QuestionOptionSchema]
    domain: Optional[str] = None
    source: str = "bank"
    metadata: dict = Field(default_factory=dict)


class ResponseSchema(BaseModel):
    question_id: str
    chosen_option_id: str
    strength: Optional[float] = None
    response_time_ms: Optional[int] = None
    timestamp: Optional[str] = None


class PreferenceStateSchema(BaseModel):
    user_id: str
    session_id: str
    item_ids: list[str]
    mu: list[float]
    sigma_flat: list[float]
    responses: list[ResponseSchema] = Field(default_factory=list)
    n_questions_asked: int = 0
    asked_question_ids: list[str] = Field(default_factory=list)
    model_version: str = "thurstone_v1"


# ---------------------------------------------------------------------------
# Request/response envelopes
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    user_id: str
    session_id: str
    target_questions: int = 25


class StartSessionResponse(BaseModel):
    state: PreferenceStateSchema
    question: QuestionSchema
    target_questions: int


class SubmitResponseRequest(BaseModel):
    state: PreferenceStateSchema
    response: ResponseSchema
    question_options: list[str]  # item ids in the order presented (length 2 pairwise)
    target_questions: int = 25


class ProgressSchema(BaseModel):
    n_answered: int
    target_questions: int
    convergence_pct: float
    is_complete: bool


class SubmitResponseResponse(BaseModel):
    state: PreferenceStateSchema
    next_question: Optional[QuestionSchema] = None
    progress: ProgressSchema


class SummaryRequest(BaseModel):
    state: PreferenceStateSchema
    target_questions: int = 25


class ValueSummarySchema(BaseModel):
    item_id: str
    text: str
    description: str
    domain: Optional[str] = None
    mean: float
    std: float
    rank: int


class SummaryResponse(BaseModel):
    progress: ProgressSchema
    values: list[ValueSummarySchema]
    model_version: str


class ItemSchema(BaseModel):
    id: str
    text: str
    description: Optional[str] = None
    domain: Optional[str] = None


class ItemsResponse(BaseModel):
    items: list[ItemSchema]
    domains: list[str]
