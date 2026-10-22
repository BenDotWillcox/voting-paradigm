"""
Pydantic request/response models for the voting router.

A request carries an anonymous profile tagged with its ballot type. Only
"ranked" exists today; partial rankings, rated ballots and weights will
arrive as further ballot types (the `profile` field then becomes a union
discriminated on `ballot_type`), so existing requests keep working.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from voting.types import DEFAULT_TIEBREAK_SEED

# Bounds for the instrument: a profile is edited by hand, and every method
# resolves one ballot object per voter.
MIN_CANDIDATES = 2
MAX_CANDIDATES = 5
MAX_VOTERS = 10_000

RankedMethodLiteral = Literal["plurality", "irv", "borda", "ranked_pairs"]

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


class ProfileResolveRequest(BaseModel):
    profile: RankedProfileSchema
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
                        "ballot_type": "ranked",
                        "candidates": ["A", "B", "C"],
                        "rows": [
                            {"count": 6, "ranking": ["A", "B", "C"]},
                            {"count": 4, "ranking": ["B", "C", "A"]},
                            {"count": 2, "ranking": ["C", "A", "B"]},
                            {"count": 3, "ranking": ["C", "B", "A"]},
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


TraceSchema = Annotated[
    PluralityTraceSchema | IRVTraceSchema | BordaTraceSchema | RankedPairsTraceSchema,
    Field(discriminator="kind"),
]


class MethodResultSchema(BaseModel):
    method: RankedMethodLiteral
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
    profile: RankedProfileSchema = Field(
        description=(
            "The profile in canonical form: one row per distinct ranking, zero "
            "rows dropped, rows sorted in candidate order. Equal electorates "
            "always echo identically, so clients can cache by it."
        )
    )
    total_voters: int
    tiebreak_seed: int
    pairwise: dict[str, dict[str, int]] = Field(
        description="pairwise[a][b] = voters ranking a above b."
    )
    criteria: SingleProfileCriteriaSchema
    results: list[MethodResultSchema] = Field(
        description="One result per ranked method: plurality, IRV, Borda, Ranked Pairs."
    )


class ErrorResponse(BaseModel):
    detail: str
