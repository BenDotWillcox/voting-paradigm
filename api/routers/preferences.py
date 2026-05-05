"""
HTTP router for preference elicitation.

Thin layer: validate input, call into `preferences` domain package, shape the
response. No domain logic lives here.
"""

from fastapi import APIRouter, HTTPException

from preferences.engine import ElicitationEngine, EngineConfig
from preferences.questions.bank import QuestionBank
from preferences.serialization import state_from_dict, state_to_dict
from preferences.types import Response

from ..schemas.preferences import (
    ItemSchema,
    ItemsResponse,
    PreferenceStateSchema,
    ProgressSchema,
    QuestionOptionSchema,
    QuestionSchema,
    StartSessionRequest,
    StartSessionResponse,
    SubmitResponseRequest,
    SubmitResponseResponse,
    SummaryRequest,
    SummaryResponse,
)

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

# Load the question bank once at module import.
_BANK = QuestionBank.load_default()


def _engine(target_questions: int = 25) -> ElicitationEngine:
    """Construct a fresh engine per request (stateless API)."""
    return ElicitationEngine(
        question_bank=_BANK,
        config=EngineConfig(target_questions=target_questions),
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions/start", response_model=StartSessionResponse)
def start_session(req: StartSessionRequest):
    """Create a new preference state and return the first question."""
    engine = _engine(req.target_questions)
    state, question = engine.start_session(
        user_id=req.user_id, session_id=req.session_id
    )
    return StartSessionResponse(
        state=_state_to_schema(state),
        question=_question_to_schema(question),
        target_questions=req.target_questions,
    )


@router.post("/sessions/respond", response_model=SubmitResponseResponse)
def submit_response(req: SubmitResponseRequest):
    """Apply a response to the state and return the next question (or None)."""
    engine = _engine(req.target_questions)
    state = _state_from_schema(req.state)
    response = Response(
        question_id=req.response.question_id,
        chosen_option_id=req.response.chosen_option_id,
        strength=req.response.strength,
        response_time_ms=req.response.response_time_ms,
        timestamp=req.response.timestamp,
    )
    try:
        new_state, next_q = engine.submit_response(
            state, response, req.question_options
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    progress = engine.get_progress(new_state)
    return SubmitResponseResponse(
        state=_state_to_schema(new_state),
        next_question=(_question_to_schema(next_q) if next_q else None),
        progress=ProgressSchema(
            n_answered=progress.n_answered,
            target_questions=progress.target_questions,
            convergence_pct=progress.convergence_pct,
            is_complete=progress.is_complete,
        ),
    )


@router.post("/sessions/summary", response_model=SummaryResponse)
def get_summary(req: SummaryRequest):
    """Return ranked values summary for the given state."""
    engine = _engine(req.target_questions)
    state = _state_from_schema(req.state)
    summary = engine.get_summary(state)
    return SummaryResponse(**summary)


@router.get("/items", response_model=ItemsResponse)
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
