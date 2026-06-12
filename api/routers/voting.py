"""
HTTP router for voting resolution and demo scenarios.

Thin layer: validate input, build ballots via the voting package's ballot
constructors, call a resolution method, return the result as a plain dict.

All demo endpoints use a deterministic tiebreak so results are reproducible.
"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from voting.ballots.approval import create_approval_ballot
from voting.ballots.quadratic import create_quadratic_ballot
from voting.ballots.ranked_choice import create_ranked_choice_ballot
from voting.ballots.score import create_score_ballot
from voting.ballots.single_choice import create_single_choice_ballot
from voting.methods.approval import resolve_approval
from voting.methods.borda import resolve_borda
from voting.methods.irv import resolve_irv
from voting.methods.plurality import resolve_plurality
from voting.methods.quadratic import resolve_quadratic
from voting.methods.ranked_pairs import resolve_ranked_pairs
from voting.methods.score import resolve_score
from voting.types import Candidate, CandidateId

from ..demo_scenarios import list_demo_scenarios, resolve_demo_scenario
from ..scenarios import get_scenario, get_scenarios

router = APIRouter(prefix="/api/elections", tags=["elections"])


# -----------------------------------------------------------------------
# Deterministic tiebreak for reproducible demos
# -----------------------------------------------------------------------


def deterministic_tiebreak(tied: list[CandidateId]) -> CandidateId:
    """Alphabetically-first candidate. Reproducible across requests."""
    return sorted(tied)[0]


# -----------------------------------------------------------------------
# Request models
# -----------------------------------------------------------------------


class CandidateInput(BaseModel):
    id: str
    name: str


class PluralityBallotInput(BaseModel):
    voter_id: str
    choice: str | None = None


class ApprovalBallotInput(BaseModel):
    voter_id: str
    approvals: list[str] = []


class RankedBallotInput(BaseModel):
    voter_id: str
    ranking: list[str] = []


class ScoreBallotInput(BaseModel):
    voter_id: str
    scores: dict[str, int] = {}


class QuadraticBallotInput(BaseModel):
    voter_id: str
    allocations: dict[str, int] = {}
    credit_budget: int = 100


class PluralityRequest(BaseModel):
    candidates: list[CandidateInput]
    ballots: list[PluralityBallotInput]


class ApprovalRequest(BaseModel):
    candidates: list[CandidateInput]
    ballots: list[ApprovalBallotInput]


class RankedRequest(BaseModel):
    candidates: list[CandidateInput]
    ballots: list[RankedBallotInput]


class ScoreRequest(BaseModel):
    candidates: list[CandidateInput]
    ballots: list[ScoreBallotInput]


class QuadraticRequest(BaseModel):
    candidates: list[CandidateInput]
    ballots: list[QuadraticBallotInput]


class DemoScenarioResolveRequest(BaseModel):
    controls: dict[str, int] = {}


def _to_candidates(inputs: list[CandidateInput]) -> list[Candidate]:
    return [Candidate(id=c.id, name=c.name) for c in inputs]


# -----------------------------------------------------------------------
# Resolution endpoints
# -----------------------------------------------------------------------


@router.post("/plurality/resolve")
def resolve_plurality_endpoint(req: PluralityRequest):
    candidates = _to_candidates(req.candidates)
    ballots = [
        create_single_choice_ballot(b.voter_id, b.choice) for b in req.ballots
    ]
    result = resolve_plurality(
        candidates, ballots, tiebreak=deterministic_tiebreak
    )
    return asdict(result)


@router.post("/approval/resolve")
def resolve_approval_endpoint(req: ApprovalRequest):
    candidates = _to_candidates(req.candidates)
    ballots = [
        create_approval_ballot(b.voter_id, b.approvals if b.approvals else None)
        for b in req.ballots
    ]
    result = resolve_approval(
        candidates, ballots, tiebreak=deterministic_tiebreak
    )
    return asdict(result)


@router.post("/irv/resolve")
def resolve_irv_endpoint(req: RankedRequest):
    candidates = _to_candidates(req.candidates)
    cids = [c.id for c in candidates]
    ballots = [
        create_ranked_choice_ballot(
            b.voter_id, b.ranking if b.ranking else None, cids
        )
        for b in req.ballots
    ]
    result = resolve_irv(candidates, ballots, tiebreak=deterministic_tiebreak)
    return asdict(result)


@router.post("/borda/resolve")
def resolve_borda_endpoint(req: RankedRequest):
    candidates = _to_candidates(req.candidates)
    cids = [c.id for c in candidates]
    ballots = [
        create_ranked_choice_ballot(
            b.voter_id, b.ranking if b.ranking else None, cids
        )
        for b in req.ballots
    ]
    result = resolve_borda(candidates, ballots, tiebreak=deterministic_tiebreak)
    return asdict(result)


@router.post("/ranked_pairs/resolve")
def resolve_ranked_pairs_endpoint(req: RankedRequest):
    candidates = _to_candidates(req.candidates)
    cids = [c.id for c in candidates]
    ballots = [
        create_ranked_choice_ballot(
            b.voter_id, b.ranking if b.ranking else None, cids
        )
        for b in req.ballots
    ]
    result = resolve_ranked_pairs(
        candidates, ballots, tiebreak=deterministic_tiebreak
    )
    return asdict(result)


@router.post("/score/resolve")
def resolve_score_endpoint(req: ScoreRequest):
    candidates = _to_candidates(req.candidates)
    ballots = [
        create_score_ballot(b.voter_id, b.scores if b.scores else None)
        for b in req.ballots
    ]
    result = resolve_score(candidates, ballots, tiebreak=deterministic_tiebreak)
    return asdict(result)


@router.post("/quadratic/resolve")
def resolve_quadratic_endpoint(req: QuadraticRequest):
    candidates = _to_candidates(req.candidates)
    ballots = [
        create_quadratic_ballot(
            b.voter_id,
            b.allocations if b.allocations else None,
            credit_budget=b.credit_budget,
        )
        for b in req.ballots
    ]
    result = resolve_quadratic(
        candidates, ballots, tiebreak=deterministic_tiebreak
    )
    return asdict(result)


# -----------------------------------------------------------------------
# Scenario endpoints
# -----------------------------------------------------------------------


@router.get("/scenarios")
def list_scenarios():
    """Return all curated election scenarios."""
    return get_scenarios()


@router.get("/scenarios/{method}")
def get_scenario_by_method(method: str):
    """Return a single scenario by method name."""
    scenario = get_scenario(method)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Unknown method: {method}")
    return scenario


@router.get("/demo-scenarios")
def list_interactive_demo_scenarios():
    """Return curated interactive electorate scenarios for the methods lab."""
    return list_demo_scenarios()


@router.post("/demo-scenarios/{scenario_id}/resolve")
def resolve_interactive_demo_scenario(
    scenario_id: str,
    req: DemoScenarioResolveRequest,
):
    """Resolve every supported voting method for a scenario/control state."""
    result = resolve_demo_scenario(scenario_id, req.controls)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")
    return result
