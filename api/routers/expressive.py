"""Stateless previews for directly authored expressive ballots."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from api.schemas.expressive import (
    BudgetErrorDetail,
    BudgetErrorResponse,
    BudgetPreviewRequest,
    BudgetPreviewResponse,
    BudgetValidationIssue,
    BudgetValidationResponse,
)
from api.schemas.expressive_scalar import (
    ScalarErrorDetail,
    ScalarErrorResponse,
    ScalarPreviewRequest,
    ScalarPreviewResponse,
)
from api.services.expressive import preview_budget_transfers
from api.services.expressive_scalar import preview_scalar_ballot
from api.schemas.expressive_comparison import ScalarComparisonRequest, ScalarComparisonResponse
from api.services.expressive_comparison import compare_scalar_ballots
from expressive import InvalidBudgetError
from expressive.scalar import InvalidScalarError

class BudgetRoute(APIRoute):
    """Keep validation responses JSON-safe without echoing invalid NaN inputs."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def validated(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                errors = BudgetValidationResponse(detail=[
                    BudgetValidationIssue(loc=list(issue["loc"]), msg=issue["msg"], type=issue["type"])
                    for issue in exc.errors()
                ])
                return JSONResponse(status_code=422, content=errors.model_dump())

        return validated


router = APIRouter(prefix="/api/expressive", tags=["expressive"], route_class=BudgetRoute)


@router.post(
    "/budget/preview",
    response_model=BudgetPreviewResponse,
    responses={
        400: {"model": BudgetErrorResponse, "description": "Invalid authored budget."},
        422: {"model": BudgetValidationResponse, "description": "Invalid request fields."},
    },
    summary="Preview transfers under an authored budget utility function",
    description=(
        "Each proposed transfer starts independently from the ideal allocation. "
        "Directional flexibility is the percentage-point departure that halves a "
        "category's score. The whole-budget score multiplies six category scores. "
        "The illustrative $1 million neighborhood fund includes scalable programs "
        "and fixed projects funded at zero or their complete cost. Infeasible "
        "transfers return funding issues and null scores; they do not invalidate "
        "other previews. This explicit independent-penalty model is not inferred "
        "welfare, a probability distribution, a collective tally, or an exclusion rule."
    ),
)
def preview_budget(request: BudgetPreviewRequest) -> BudgetPreviewResponse:
    try:
        return preview_budget_transfers(request)
    except InvalidBudgetError as exc:
        detail = BudgetErrorDetail(code="invalid_budget", message=str(exc))
        raise HTTPException(status_code=400, detail=detail.model_dump()) from exc


@router.post(
    "/scalar/preview",
    response_model=ScalarPreviewResponse,
    responses={
        400: {"model": ScalarErrorResponse, "description": "Invalid authored scalar ballot."},
        422: {"model": BudgetValidationResponse, "description": "Invalid request fields."},
    },
    summary="Preview a clipped scalar utility curve over an illustrative tax rate",
    description=(
        "The theoretical policy domain is 0 to 100 percent. Directional half-widths determine "
        "the unchanged Gaussian-shaped taper; both approval bounds are inclusive. "
        "The 2001-point base grid uses 0.05-point steps and is augmented by exact ideal, "
        "approval-bound, half-score, and probe values. "
        "Curve samples are unclipped for plotting; the probe score is zero outside "
        "approval. No probability normalization, collective tally, or veto is implied."
    ),
)
def preview_scalar_curve(request: ScalarPreviewRequest) -> ScalarPreviewResponse:
    try:
        return preview_scalar_ballot(request)
    except InvalidScalarError as exc:
        detail = ScalarErrorDetail(code="invalid_scalar_ballot", message=str(exc))
        raise HTTPException(status_code=400, detail=detail.model_dump()) from exc


@router.post(
    "/scalar/compare",
    response_model=ScalarComparisonResponse,
    responses={422: {"model": BudgetValidationResponse, "description": "Invalid ballot or binary choice."}},
    summary="Compare Colorado Proposition 121's tax-rate question with declared scores",
    description=(
        "The question uses Colorado's 2022 Proposition 121 rates. One seeded, fictional "
        "electorate contains 99 varied prepared curves and the submitted user ballot. "
        "Prepared yes/no choices compare each curve at the two offered rates; score ties "
        "abstain. The user's explicit yes/no choice is preserved even if their curve differs. "
        "Every result uses these exact same 100 voters. A strict yes-over-no majority "
        "reduces the rate from 4.55% to 4.40%; ties retain 4.55%. Mean declared 0--1 scores "
        "are compared first on the same pair, then on 2001 rates from 0 to 100% in "
        "0.05-point steps, including both offered rates exactly. All score maximizers "
        "within an absolute 1e-12 tolerance "
        "are returned. Approval never vetoes a candidate; scores are not measured welfare. "
        "The graphical probe does not enter any tally. This synthetic population "
        "does not represent Colorado voters or the actual election result."
    ),
)
def compare_scalar(request: ScalarComparisonRequest) -> ScalarComparisonResponse:
    return compare_scalar_ballots(request)
