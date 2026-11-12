"""
HTTP router for liquid democracy.

HTTP only: request and response validation, dependencies, error mapping.
The work is in api.services.delegation and the delegation package.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ..schemas.delegation import (
    ErrorResponse,
    JudgmentsRequest,
    JudgmentsResponse,
    ProfileResponse,
    ResolveRequest,
    ResolveResponse,
    ScenarioResponse,
    ValidateRequest,
    ValidateResponse,
)
from ..services.delegation import (
    DelegationRequestError,
    LiveSource,
    RuntimeStores,
    default_source,
    default_stores,
    judgments_response,
    profile_response,
    resolve_response,
    scenario_response,
    validate_response,
)

router = APIRouter(prefix="/api/delegation", tags=["delegation"])

Stores = Annotated[RuntimeStores, Depends(default_stores)]
Source = Annotated[LiveSource | None, Depends(default_source)]

_INVALID: dict[int | str, dict[str, Any]] = {
    422: {
        "model": ErrorResponse,
        "description": "The request cannot be honoured as sent",
    }
}


@router.get(
    "/scenario",
    response_model=ScenarioResponse,
    summary="The simulated network, the ballot papers and the viewer's account",
    description=(
        "A seeded synthetic city: residents of three districts, some people "
        "who live outside it, each with a made-up name and a unique username, "
        "and the categories they have handed to one another. The ballot "
        "papers form a timeline, issued to the whole city or to one district: "
        "closed papers are everyone's history and open ones are still to be "
        "voted on. The viewer is a District 1 resident whose account starts "
        "with eight delegations. Deterministic: the same seed always gives "
        "the same network."
    ),
)
def scenario(source: Source) -> ScenarioResponse:
    return scenario_response(live=source is not None)


@router.post(
    "/delegations/validate",
    response_model=ValidateResponse,
    summary="Check one delegation before the viewer adds it",
    description=(
        "Runs the creation checks on a proposed delegation. It is rejected "
        "when it would close a loop through delegations of the identical "
        "category, and the response gives the chain. A loop between "
        "differently worded categories depends on the question, so it is "
        "allowed and reported as warnings: the open questions on which the "
        "delegation would come back to the viewer. Reads recorded judgments "
        "only."
    ),
    responses=_INVALID,
)
def validate(request: ValidateRequest, stores: Stores) -> ValidateResponse:
    try:
        return validate_response(request, stores)
    except DelegationRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/judgments",
    response_model=JudgmentsResponse,
    summary="Get a category judged against the open questions",
    description=(
        "Returns the decision model's probability that each open question "
        "is primarily about the category, and whether the category sits "
        "inside, or contains, the viewer's other categories. Pool categories "
        "are already on record. For a category the viewer wrote, recorded "
        "answers are used first; the rest are asked of the decision model and "
        "recorded only when the server has live judgments switched on and the "
        "day's allowance of new categories is not used up. Otherwise they are "
        "reported as missing, and the routing rule keeps the viewer's votes "
        "for that category."
    ),
    responses=_INVALID,
)
def judgments(
    request: JudgmentsRequest, stores: Stores, source: Source
) -> JudgmentsResponse:
    try:
        return judgments_response(request, stores, source)
    except DelegationRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/resolve",
    response_model=ResolveResponse,
    summary="Process a ballot paper through the delegation network",
    description=(
        "Issues a curated ballot paper to the residents of its jurisdiction "
        "and resolves every question: each vote is routed by whoever holds it "
        "until someone keeps it, and everyone on a loop keeps the decision. "
        "Each voter's ballot is then a copy of their resolver's ballot, "
        "counted by plurality. Returns, per question, the delegated tally "
        "beside the tally with everyone voting for themself, concentration "
        "measures, the viewer's receipt, and the votes the viewer answers for. "
        "A closed paper is history: it is returned as it was resolved, with "
        "the account the viewer started with, whatever the request carries. "
        "Reads recorded judgments only, so the same request always gives the "
        "same response."
    ),
    responses=_INVALID,
)
def resolve(request: ResolveRequest, stores: Stores) -> ResolveResponse:
    try:
        return resolve_response(request, stores)
    except DelegationRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/people/{person_id}",
    response_model=ProfileResponse,
    summary="One person's profile and voting history",
    description=(
        "Who the person is, what they have handed over and been handed, a few "
        "counts, and every closed question that was issued to them or that "
        "reached them through someone else's delegation: whether they voted "
        "themself or a delegate decided, under which category, through whom, "
        "and what was cast. Votes are public in this demo's world. Read from "
        "the closed ballot papers only, so it never changes."
    ),
    responses=_INVALID,
)
def profile(person_id: str) -> ProfileResponse:
    try:
        return profile_response(person_id)
    except DelegationRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
