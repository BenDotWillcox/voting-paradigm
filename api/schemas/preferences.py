"""
Pydantic request/response models for the preferences router.

The API is stateless: the client (Next.js) is responsible for persisting the
PreferenceState between calls. Every request carries the current state; every
response returns the updated state.

The wire contract mirrors the internal Evidence contract: clients submit
typed evidence, never raw model parameters. All five evidence sources are
part of persisted state, but this legacy direct-submit route accepts only
structured pairwise/slider input. Confirmed inferred evidence is created by
the separate Phase 4C ledger boundary.
"""

from typing import Literal, Optional, Self

from pydantic import BaseModel, Field, model_validator

EvidenceSourceLiteral = Literal[
    "pairwise", "slider", "free_text_extraction", "correction", "override"
]

ModelNameLiteral = Literal["gaussian_linear", "bradley_terry"]
SelectionPolicyLiteral = Literal["random", "max_variance"]


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


class EvidenceSchema(BaseModel):
    """One typed observation about the user's preferences.

    `value` is signed in [-10, 10]: positive prefers item_a, negative prefers
    item_b, 0 is stated indifference. See preferences.types.Evidence.
    """

    source: EvidenceSourceLiteral
    item_a: str
    item_b: str
    value: float = Field(ge=-10.0, le=10.0)
    event_id: Optional[str] = None
    confirmed_by_participant: Literal[False] = False
    confidence: float = Field(default=1.0, gt=0.0, le=1.0)
    prompt_id: Optional[str] = None
    raw_response: Optional[str] = None
    extracted_claims: list[str] = Field(default_factory=list)
    response_time_ms: Optional[int] = None
    timestamp: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class PreferenceStateSchema(BaseModel):
    user_id: str
    session_id: str
    item_ids: list[str]
    mu: list[float]
    sigma_flat: list[float]
    evidence: Optional[list[EvidenceSchema]] = None
    # Legacy pre-Evidence states carried `responses`; passed through so
    # serialization can upgrade them instead of silently dropping the trail.
    responses: Optional[list[dict]] = None
    n_questions_asked: int = 0
    asked_question_ids: list[str] = Field(default_factory=list)
    model_version: str = "gaussian_linear_v1"

    @model_validator(mode="after")
    def state_evidence_must_come_from_direct_wire_sources(self) -> Self:
        unsupported = {
            evidence.source
            for evidence in (self.evidence or [])
            if evidence.source not in {"pairwise", "slider"}
        }
        if unsupported:
            raise ValueError(
                "wire preference state cannot contain inferred, correction, "
                "or override evidence"
            )
        return self


# ---------------------------------------------------------------------------
# Request/response envelopes
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    user_id: str
    session_id: str
    target_questions: int = 25
    model: ModelNameLiteral = "gaussian_linear"
    selection_policy: SelectionPolicyLiteral = "max_variance"


class StartSessionResponse(BaseModel):
    state: PreferenceStateSchema
    question: QuestionSchema
    target_questions: int


class SubmitEvidenceRequest(BaseModel):
    state: PreferenceStateSchema
    evidence: EvidenceSchema
    target_questions: int = 25
    selection_policy: SelectionPolicyLiteral = "max_variance"

    @model_validator(mode="after")
    def submitted_evidence_must_come_from_a_direct_wire_source(self) -> Self:
        if self.evidence.source not in {"pairwise", "slider"}:
            raise ValueError(
                f"evidence source '{self.evidence.source}' cannot be created "
                "through the direct structured-evidence endpoint"
            )
        return self


class ProgressSchema(BaseModel):
    n_answered: int
    target_questions: int
    convergence_pct: float
    is_complete: bool


class SubmitEvidenceResponse(BaseModel):
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
