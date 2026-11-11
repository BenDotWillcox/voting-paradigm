"""Explicit HTTP contracts for one electorate viewed through two ballot formats."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from api.schemas.expressive import Score, StrictSchema
from api.schemas.expressive_scalar import HalfWidth, PolicyValue, ScalarPreviewRequest

Count = Annotated[int, Field(ge=0, strict=True)]
BinaryVote = Literal["yes", "no", "abstain"]


class ScalarComparisonRequest(StrictSchema):
    ballot: ScalarPreviewRequest
    binary_vote: Literal["yes", "no"]

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "ballot": {"ideal": 4.55, "lower_half_width": 2, "upper_half_width": 2,
                   "approval_min": 0, "approval_max": 100, "probe": 4.55},
        "binary_vote": "no",
    }]})


class ComparisonBallotSchema(StrictSchema):
    ideal: PolicyValue
    lower_half_width: HalfWidth
    upper_half_width: HalfWidth
    approval_min: PolicyValue
    approval_max: PolicyValue


class ComparisonVoterSchema(StrictSchema):
    id: str
    label: str
    ballot: ComparisonBallotSchema
    binary_vote: BinaryVote
    curve_vote: BinaryVote
    status_quo_score: Score
    proposal_score: Score


class ComparisonElectorateSchema(StrictSchema):
    id: str
    label: str
    description: str
    seed: Count
    voters: Annotated[list[ComparisonVoterSchema], Field(min_length=100, max_length=100)]


class ComparisonBinarySchema(StrictSchema):
    yes: Count
    no: Count
    abstain: Count
    passed: bool
    outcome_rate: PolicyValue


class ComparisonPairSchema(StrictSchema):
    status_quo_mean: Score
    proposal_mean: Score
    winner_rates: list[PolicyValue]


class ComparisonPointSchema(StrictSchema):
    rate: PolicyValue
    mean_score: Score
    approval_count: Count
    user_score: Score
    user_approved: bool
    prefer_this: Count
    prefer_binary: Count
    indifferent: Count


class ScalarComparisonResponse(StrictSchema):
    model: Literal["scalar-comparison-v4"]
    status_quo: Literal[4.55]
    proposal: Literal[4.4]
    electorate_size: Literal[100]
    candidate_step: Literal[0.05]
    score_tie_tolerance: Literal[1e-12]
    user_binary_vote: Literal["yes", "no"]
    user_curve_vote: BinaryVote
    electorate: ComparisonElectorateSchema
    binary: ComparisonBinarySchema
    pair: ComparisonPairSchema
    winner_rates: list[PolicyValue]
    max_mean_score: Score
    points: Annotated[list[ComparisonPointSchema], Field(min_length=2001, max_length=2001)]
