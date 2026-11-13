"""Map comparison contracts to the isolated expressive domain evaluator."""

from dataclasses import asdict

from api.schemas.expressive_comparison import (
    ScalarComparisonRequest,
    ScalarComparisonResponse,
)
from expressive.comparison import CANDIDATE_STEP, PROPOSAL, STATUS_QUO, compare_ballots, curve_vote
from expressive.scalar import ScalarBallot


def compare_scalar_ballots(request: ScalarComparisonRequest) -> ScalarComparisonResponse:
    ballot = ScalarBallot(
        ideal=request.ballot.ideal,
        lower_half_width=request.ballot.lower_half_width,
        upper_half_width=request.ballot.upper_half_width,
        approval_min=request.ballot.approval_min,
        approval_max=request.ballot.approval_max,
    )
    result = compare_ballots(ballot, request.binary_vote, request.scenario)
    return ScalarComparisonResponse.model_validate({
        "model": "scalar-comparison-v4",
        "scenario": request.scenario,
        "status_quo": STATUS_QUO,
        "proposal": PROPOSAL,
        "electorate_size": 100,
        "candidate_step": CANDIDATE_STEP,
        "score_tie_tolerance": 1e-12,
        "user_binary_vote": request.binary_vote,
        "user_curve_vote": curve_vote(ballot),
        **asdict(result),
    })
