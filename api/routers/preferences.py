"""
HTTP router for preference elicitation.

Thin layer: validate input, call into `preferences` domain package, shape the
response. No domain logic lives here.

Sessions are stateless per-call: the state snapshot travels with every
request. The model that owns a state is recovered from its `model_version`,
so a session started with one model is always resumed by the same family.
"""

from fastapi import APIRouter, HTTPException

from preferences.engine import ElicitationEngine, EngineConfig
from preferences.model import create_model, model_for_version
from preferences.questions.bank import QuestionBank
from preferences.serialization import state_from_dict, state_to_dict
from preferences.types import Evidence, EvidenceSource, UnsupportedEvidenceError

from ..schemas.preferences import (
    EvidenceSchema,
    ItemSchema,
    ItemsResponse,
    PreferenceStateSchema,
    ProgressSchema,
    QuestionOptionSchema,
    QuestionSchema,
    StartSessionRequest,
    StartSessionResponse,
    SubmitEvidenceRequest,
    SubmitEvidenceResponse,
    SummaryRequest,
    SummaryResponse,
)

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

# Load the question bank once at module import.
_BANK = QuestionBank.load_default()


def _engine(
    model,
    target_questions: int = 25,
    selection_policy: str = "max_variance",
) -> ElicitationEngine:
    """Construct a fresh engine per request (stateless API)."""
    return ElicitationEngine(
        model=model,
        question_bank=_BANK,
        config=EngineConfig(
            target_questions=target_questions,
            selection_policy=selection_policy,
        ),
    )


def _question_to_schema(question) -> QuestionSchema:
    return QuestionSchema(
        id=question.id,
        question_type=(
            question.question_type.value
            if hasattr(question.question_type, "value")
            else str(question.question_type)
        ),
        prompt=question.prompt,
        options=[
            QuestionOptionSchema(
                item_id=opt.item_id,
                text=opt.text,
                description=opt.description,
            )
            for opt in question.options
        ],
        domain=question.domain,
        source=question.source,
        metadata=question.metadata,
    )


def _state_to_schema(state) -> PreferenceStateSchema:
    return PreferenceStateSchema(**state_to_dict(state))


def _state_from_schema(schema: PreferenceStateSchema):
    return state_from_dict(schema.model_dump())


def _evidence_from_schema(schema: EvidenceSchema) -> Evidence:
    return Evidence(
        source=EvidenceSource(schema.source),
        item_a=schema.item_a,
        item_b=schema.item_b,
        value=schema.value,
        confidence=schema.confidence,
        prompt_id=schema.prompt_id,
        raw_response=schema.raw_response,
        extracted_claims=list(schema.extracted_claims),
        response_time_ms=schema.response_time_ms,
        timestamp=schema.timestamp,
        metadata=dict(schema.metadata),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/start",
    response_model=StartSessionResponse,
    summary="Start an elicitation session",
)
def start_session(req: StartSessionRequest):
    """Create a fresh preference state and return the first question.

    `model` picks the posterior family (gaussian_linear | bradley_terry);
    `selection_policy` picks how questions are chosen (max_variance | random).
    """
    engine = _engine(
        create_model(req.model),
        req.target_questions,
        req.selection_policy,
    )
    state, question = engine.start_session(
        user_id=req.user_id, session_id=req.session_id
    )
    return StartSessionResponse(
        state=_state_to_schema(state),
        question=_question_to_schema(question),
        target_questions=req.target_questions,
    )


@router.post(
    "/sessions/evidence",
    response_model=SubmitEvidenceResponse,
    summary="Submit typed evidence",
)
def submit_evidence(req: SubmitEvidenceRequest):
    """Apply one piece of typed evidence and return the next question (or null).

    Evidence sources without an implemented likelihood (free_text_extraction,
    correction, override) are part of the declared contract but rejected with
    422 until their handlers land.
    """
    state = _state_from_schema(req.state)
    try:
        model = model_for_version(state.model_version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    engine = _engine(model, req.target_questions, req.selection_policy)
    evidence = _evidence_from_schema(req.evidence)
    try:
        new_state, next_q = engine.submit_evidence(state, evidence)
    except UnsupportedEvidenceError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    progress = engine.get_progress(new_state)
    return SubmitEvidenceResponse(
        state=_state_to_schema(new_state),
        next_question=(_question_to_schema(next_q) if next_q else None),
        progress=ProgressSchema(
            n_answered=progress.n_answered,
            target_questions=progress.target_questions,
            convergence_pct=progress.convergence_pct,
            is_complete=progress.is_complete,
        ),
    )


@router.post(
    "/sessions/summary",
    response_model=SummaryResponse,
    summary="Summarize a session's posterior",
)
def get_summary(req: SummaryRequest):
    """Return ranked values (posterior mean +/- std) for the given state."""
    state = _state_from_schema(req.state)
    try:
        model = model_for_version(state.model_version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    engine = _engine(model, req.target_questions)
    summary = engine.get_summary(state)
    return SummaryResponse(**summary)


@router.get(
    "/items",
    response_model=ItemsResponse,
    summary="List the civic-value item bank",
)
def list_items():
    """Return the full item bank (for debugging/inspection)."""
    return ItemsResponse(
        items=[
            ItemSchema(
                id=it.id,
                text=it.text,
                description=it.description,
                domain=it.domain,
            )
            for it in _BANK.items
        ],
        domains=_BANK.domains(),
    )
