"""
HTTP router for liquid democracy.

HTTP only: request and response validation, dependencies, error mapping.
The work is in api.services.delegation and the delegation package.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ..schemas.delegation import (
    CityVoteResponse,
    BacktestRequest,
    BacktestResponse,
    CityResponse,
    ErrorResponse,
    JudgmentsRequest,
    JudgmentsResponse,
    ProfileResponse,
    ResolveRequest,
    ResolveResponse,
    ScenarioResponse,
    TraceRequest,
    TraceResponse,
    ValidateRequest,
    ValidateResponse,
)
from ..services.delegation import (
    city_vote_response,
    backtest_response,
    DelegationRequestError,
    LiveSource,
    RuntimeStores,
    city_response,
    default_source,
    default_stores,
    judgments_response,
    profile_response,
    resolve_response,
    scenario_response,
    trace_response,
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


@router.get(
    "/city",
    response_model=CityResponse,
    summary="Every closed question across the city",
    description=(
        "For each closed question: how many ballots counted with delegation "
        "and how many people voted themselves, the share of votes decided by "
        "someone else, the largest share held by one person, and whether "
        "delegation changed the result. Also the same per ballot paper, the "
        "totals, and the people who decided the most votes for others. Read "
        "from the closed ballot papers only, so it never changes."
    ),
)
def city() -> CityResponse:
    return city_response()


@router.post(
    "/trace",
    response_model=TraceResponse,
    summary="Route one question through the network and show the working",
    description=(
        "Takes a curated question, or a yes/no measure the caller drafts, and "
        "routes it through today's network. Returns the decision model's "
        "probability for every category in use, the categories votes left "
        "under, who ends up deciding them, why the rest stayed with their "
        "voters, concentration measures, and the same question routed at each "
        "threshold from 0.50 to 0.95. A curated question reads recorded "
        "judgments only. A draft uses recorded judgments for its exact wording "
        "first; the rest are asked of the decision model only when the server "
        "has live judgments switched on and the day's allowance of drafted "
        "measures is not used up. Without judgments nobody's vote is "
        "delegated, and the response says why."
    ),
    responses=_INVALID,
)
def trace(request: TraceRequest, stores: Stores, source: Source) -> TraceResponse:
    try:
        return trace_response(request, stores, source)
    except DelegationRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/backtest",
    response_model=BacktestResponse,
    summary="Replay the closed questions under a change to the viewer's delegations",
    description=(
        "Routes the viewer's vote on every closed question that was issued to "
        "them twice, through the network of the day each ballot paper closed: "
        "with the delegations they have now, and with the change they are "
        "considering. Returns, for each set, how many votes would have gone to "
        "a delegate and how often that delegate chose what the account's own "
        "position chooses, and lists the questions that would have gone "
        "somewhere else with what each resolver actually chose. Votes the "
        "viewer cast themself in the past are set aside. Reads recorded "
        "judgments only; a category the viewer wrote that was never judged "
        "against a closed question keeps that question with the viewer and is "
        "named in the response."
    ),
    responses=_INVALID,
)
def backtest(request: BacktestRequest, stores: Stores) -> BacktestResponse:
    try:
        return backtest_response(request, stores)
    except DelegationRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/city/votes/{question_id}",
    response_model=CityVoteResponse,
    summary="One closed question, resident by resident, for a map",
    description=(
        "For everyone a closed question was issued to: whether they voted "
        "themself, someone else decided their vote or they cast nothing, who "
        "decided it, and the ballot that counted for them. Also the measure's "
        "sites in the unit square, how far a site's pull reaches, and the "
        "counted ballots per option in each district. Votes are public in "
        "this simulated city. Read from the closed ballot papers only, so it "
        "never changes."
    ),
    responses=_INVALID,
)
def city_vote(question_id: str) -> CityVoteResponse:
    try:
        return city_vote_response(question_id)
    except DelegationRequestError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
