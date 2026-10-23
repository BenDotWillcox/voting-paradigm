"""
Pydantic request/response models for the voting router.

A request carries a profile tagged with its type:
- "ranked": voters' complete rankings. Resolved by the four ranked methods.
- "utility": voter types with utilities. A ballot model turns each type into
  every ballot format, so all seven methods resolve it.
Partial rankings, rated ballots and weights can join as further tags without
breaking existing requests.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from voting.types import DEFAULT_TIEBREAK_SEED

# Bounds for the instrument: a profile is edited by hand, and every method
# resolves one ballot object per voter.
MIN_CANDIDATES = 2
MAX_CANDIDATES = 5
MAX_VOTERS = 10_000

MethodLiteral = Literal[
    "plurality", "irv", "borda", "ranked_pairs", "approval", "score", "quadratic"
]

CandidateIdStr = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,32}$")
]


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class RankedRowSchema(BaseModel):
    """How many voters cast one complete ranking, most preferred first."""

    count: int = Field(ge=0, le=MAX_VOTERS)
    ranking: list[CandidateIdStr] = Field(min_length=1, max_length=MAX_CANDIDATES)


class RankedProfileSchema(BaseModel):
    """An anonymous profile of complete rankings."""

    ballot_type: Literal["ranked"]
    candidates: list[CandidateIdStr] = Field(
        min_length=MIN_CANDIDATES, max_length=MAX_CANDIDATES
    )
    rows: list[RankedRowSchema]

    @model_validator(mode="after")
    def _voters_in_range(self) -> Self:
        total = sum(row.count for row in self.rows)
        if not 1 <= total <= MAX_VOTERS:
            raise ValueError(f"A profile needs 1 to {MAX_VOTERS} voters, got {total}")
        return self


class UtilityRowSchema(BaseModel):
    """How many voters share one set of utilities (0 worst, 100 best)."""

    count: int = Field(ge=0, le=MAX_VOTERS)
    utilities: dict[CandidateIdStr, int] = Field(
        description="One utility per candidate, 0 to 100."
    )


class UtilityProfileSchema(BaseModel):
    """Voter types with utilities. Rows keep their order and are not merged."""

    ballot_type: Literal["utility"]
    candidates: list[CandidateIdStr] = Field(
        min_length=MIN_CANDIDATES, max_length=MAX_CANDIDATES
    )
    rows: list[UtilityRowSchema]

    @model_validator(mode="after")
    def _voters_in_range(self) -> Self:
        total = sum(row.count for row in self.rows)
        if not 1 <= total <= MAX_VOTERS:
            raise ValueError(f"A profile needs 1 to {MAX_VOTERS} voters, got {total}")
        return self


ProfileSchema = Annotated[
    RankedProfileSchema | UtilityProfileSchema, Field(discriminator="ballot_type")
]


class ProfileResolveRequest(BaseModel):
    profile: ProfileSchema
    tiebreak_seed: int = Field(
        default=DEFAULT_TIEBREAK_SEED,
        ge=0,
        le=2**31 - 1,
        description=(
            "Seed for the random tiebreak. Each method gets its own tiebreaker "
            "built from this seed, so a result never depends on which other "
            "methods were resolved."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "profile": {
                        "ballot_type": "utility",
                        "candidates": ["A", "B", "C"],
                        "rows": [
                            {"count": 35, "utilities": {"A": 100, "B": 0, "C": 60}},
                            {"count": 33, "utilities": {"A": 0, "B": 100, "C": 60}},
                            {"count": 32, "utilities": {"A": 0, "B": 40, "C": 100}},
                        ],
                    },
                    "tiebreak_seed": 0,
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class TiebreakEventSchema(BaseModel):
    """One call to the tiebreak: the candidates it chose among, and its pick."""

    tied: list[str] = Field(description="Tied candidates, sorted.")
    chose: str


class PluralityTraceSchema(BaseModel):
    kind: Literal["plurality"] = "plurality"
    first_choices: dict[str, int]


class IRVRoundSchema(BaseModel):
    round_number: int
    counts: dict[str, int]
    exhausted_ballots: int
    eliminated: list[str]
    elimination_was_tiebreak: bool


class IRVTraceSchema(BaseModel):
    kind: Literal["irv"] = "irv"
    rounds: list[IRVRoundSchema]
    winning_round: int


class BordaTraceSchema(BaseModel):
    kind: Literal["borda"] = "borda"
    points: dict[str, int]
    max_points_per_ballot: int


class VictorySchema(BaseModel):
    winner: str
    loser: str
    margin: int


class RankedPairsTraceSchema(BaseModel):
    kind: Literal["ranked_pairs"] = "ranked_pairs"
    had_condorcet_winner: bool
    locked: list[VictorySchema] = Field(description="Victories locked, in order.")
    skipped: list[VictorySchema] = Field(description="Victories skipped to avoid cycles.")
    tiebreak_priority: list[str] = Field(
        description="Candidate priority that ordered equal-strength victories; empty if unused."
    )


class ApprovalTraceSchema(BaseModel):
    kind: Literal["approval"] = "approval"
    approvals: dict[str, int]
    abstentions: int


class ScoreTraceSchema(BaseModel):
    kind: Literal["score"] = "score"
    totals: dict[str, int]
    max_score: int


class QuadraticTraceSchema(BaseModel):
    kind: Literal["quadratic"] = "quadratic"
    net_votes: dict[str, int] = Field(description="Votes for minus votes against.")
    credits_spent: int
    credits_available: int


TraceSchema = Annotated[
    PluralityTraceSchema
    | IRVTraceSchema
    | BordaTraceSchema
    | RankedPairsTraceSchema
    | ApprovalTraceSchema
    | ScoreTraceSchema
    | QuadraticTraceSchema,
    Field(discriminator="kind"),
]


class VoterBallotsSchema(BaseModel):
    """The ballots one voter type casts in every format, under the ballot model."""

    row: int = Field(description="Index of the voter type in the request's rows.")
    count: int
    choice: str
    ranking: list[str]
    approvals: list[str]
    scores: dict[str, int]
    allocations: dict[str, int] = Field(description="Quadratic votes; nonzero only.")
    credits_used: int
    credit_budget: int


class MethodResultSchema(BaseModel):
    method: MethodLiteral
    winner: str
    decisive: bool = Field(
        description=(
            "True when the ballots alone decided the winner: no tiebreak was "
            "applied and, for IRV, no round eliminated several candidates tied "
            "for last at once."
        )
    )
    tiebreaks: list[TiebreakEventSchema] = Field(
        description="Every tie the tiebreak settled, in the order it settled them."
    )
    trace: TraceSchema


class SingleProfileCriteriaSchema(BaseModel):
    """The candidates single-profile criteria single out, if any."""

    majority_winner: str | None = Field(
        description="Ranked first by more than half the voters."
    )
    condorcet_winner: str | None = Field(description="Beats every other head to head.")
    condorcet_loser: str | None = Field(description="Loses to every other head to head.")


class ProfileResolveResponse(BaseModel):
    profile: ProfileSchema = Field(
        description=(
            "The request's profile. A ranked profile comes back canonical (one "
            "row per distinct ranking, zero rows dropped, rows in candidate "
            "order); a utility profile comes back as given."
        )
    )
    rankings: RankedProfileSchema = Field(
        description=(
            "The ranked ballots, canonical. Ranked methods, the head-to-head "
            "matrix and the criteria read these."
        )
    )
    ballot_model: str | None = Field(
        description="The model that turned utilities into ballots; null for ranked input."
    )
    voter_ballots: list[VoterBallotsSchema] = Field(
        description="Each voter type's ballots, in request row order; empty for ranked input."
    )
    total_voters: int
    tiebreak_seed: int
    pairwise: dict[str, dict[str, int]] = Field(
        description="pairwise[a][b] = voters ranking a above b."
    )
    criteria: SingleProfileCriteriaSchema
    results: list[MethodResultSchema] = Field(
        description=(
            "Plurality, IRV, Borda and Ranked Pairs; for utility input also "
            "approval, score and quadratic voting."
        )
    )


class ErrorResponse(BaseModel):
    detail: str
