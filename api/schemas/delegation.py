"""
Pydantic request/response models for the liquid democracy routes.

The API is stateless. The synthetic network and the curated ballot papers
are rebuilt from a seed on the server, so a request carries only what the
viewer changed: the categories they have handed to someone, in their list
order, and any votes they have cast themself.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from delegation import DEFAULT_THRESHOLD, MAX_CATEGORY_LENGTH
from voting.types import DEFAULT_TIEBREAK_SEED

MAX_VIEWER_DELEGATIONS = 12

CategoryText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_CATEGORY_LENGTH
    ),
]
PersonRef = Annotated[str, StringConstraints(min_length=1, max_length=40)]

OutcomeLiteral = Literal[
    "direct_vote", "no_delegations", "router_unavailable", "none_available", "delegated"
]
KeptLiteral = Literal[
    "direct_vote", "no_delegations", "router_unavailable", "none_available", "loop"
]


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# What the viewer sends
# ---------------------------------------------------------------------------


class ViewerDelegationSchema(BaseModel):
    category: CategoryText = Field(
        description="The category in the viewer's own words, at any granularity."
    )
    delegate: PersonRef = Field(description="The id of a person in the network.")


ViewerDelegations = Annotated[
    list[ViewerDelegationSchema],
    Field(
        default_factory=list,
        max_length=MAX_VIEWER_DELEGATIONS,
        description="The viewer's delegations, in their category list order.",
    ),
]

_EXAMPLE_DELEGATIONS: list[Any] = [
    {"category": "all things taxes", "delegate": "d2-007"},
    {"category": "the well-being of tree frogs in the Amazon", "delegate": "out-16"},
]


# ---------------------------------------------------------------------------
# GET /scenario
# ---------------------------------------------------------------------------


class JurisdictionSchema(BaseModel):
    id: str
    name: str


class PersonSchema(BaseModel):
    id: str
    label: str
    residences: list[str] = Field(description="Jurisdiction ids; empty for outsiders.")
    behaviour: str | None = Field(
        description="How this simulated person delegates; null for the viewer."
    )
    well_known_for: list[str] = Field(
        description="Ids of categories this person is well known for."
    )


class CategorySchema(BaseModel):
    id: str
    text: str
    in_pool: bool = Field(
        description="Whether the category has recorded judgments for every curated question."
    )
    inside: list[str] = Field(
        default_factory=list,
        description="Ids of broader categories this one sits inside.",
    )


class DelegationSchema(BaseModel):
    delegator: str
    category: str = Field(description="Category id.")
    delegate: str


class OptionSchema(BaseModel):
    id: str
    name: str


class QuestionSchema(BaseModel):
    id: str
    title: str
    summary: str
    options: list[OptionSchema]


class BallotPaperSchema(BaseModel):
    id: str
    title: str
    jurisdiction: str
    eligible_voters: int
    questions: list[QuestionSchema]


class ScenarioResponse(BaseModel):
    scenario: str
    model: str = Field(
        description="The pinned decision model the recorded judgments came from."
    )
    seed: int = Field(description="Seed of the synthetic network.")
    threshold: float = Field(description="Default routing threshold.")
    viewer: str
    live_judgments: bool = Field(
        description="Whether the server will ask the decision model about a category it has no record of."
    )
    jurisdictions: list[JurisdictionSchema]
    persons: list[PersonSchema]
    categories: list[CategorySchema]
    delegations: list[DelegationSchema] = Field(
        description="The simulated network's delegations."
    )
    ballot_papers: list[BallotPaperSchema]


# ---------------------------------------------------------------------------
# POST /delegations/validate
# ---------------------------------------------------------------------------


class ValidateRequest(BaseModel):
    viewer_delegations: ViewerDelegations
    proposed: ViewerDelegationSchema
    threshold: float = Field(default=DEFAULT_THRESHOLD, ge=0, le=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "viewer_delegations": _EXAMPLE_DELEGATIONS[:1],
                    "proposed": {
                        "category": "bike lanes and cycling safety",
                        "delegate": "d2-061",
                    },
                }
            ]
        }
    }


class LoopWarningSchema(BaseModel):
    ballot_paper: str
    question_id: str
    title: str


class ValidateResponse(BaseModel):
    accepted: bool
    reason: str | None = Field(description="Why the delegation was rejected.")
    chain: list[str] | None = Field(
        description="When rejected for a loop: the chain from the viewer back to the viewer."
    )
    category: CategorySchema
    judged: bool = Field(
        description="Whether every curated question has a recorded judgment for this category. "
        "Without them the routing rule keeps the viewer's votes."
    )
    warnings: list[LoopWarningSchema] = Field(
        description="Curated questions on which this delegation would come back to the viewer. "
        "The delegation is still allowed; on those questions the viewer keeps the decision."
    )


# ---------------------------------------------------------------------------
# POST /judgments
# ---------------------------------------------------------------------------


class JudgmentsRequest(BaseModel):
    category: CategoryText
    held: list[CategoryText] = Field(
        default_factory=list,
        max_length=MAX_VIEWER_DELEGATIONS,
        description="The viewer's other categories, so nesting between them can be judged.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "category": "protecting urban wildlife",
                    "held": ["the environment and conservation"],
                }
            ]
        }
    }


class JudgmentCountsSchema(BaseModel):
    recorded: int = Field(description="Already on record.")
    fetched: int = Field(
        description="Asked of the decision model just now, and recorded."
    )
    missing: int = Field(description="Still without a judgment.")


class QuestionScoreSchema(BaseModel):
    ballot_paper: str
    question_id: str
    title: str
    probability: float | None = Field(description="Null when there is no judgment.")


class JudgmentsResponse(BaseModel):
    category: CategorySchema
    model: str
    live: bool = Field(
        description="Whether the decision model was available for this request."
    )
    judgments: JudgmentCountsSchema
    nesting: JudgmentCountsSchema
    inside: list[str] = Field(
        description="Held categories this one sits inside, by text."
    )
    contains: list[str] = Field(
        description="Held categories that sit inside this one, by text."
    )
    scores: list[QuestionScoreSchema]
    failures: list[str] = Field(
        description="One message per failed request to the decision model."
    )


# ---------------------------------------------------------------------------
# POST /resolve
# ---------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    ballot_paper: str = Field(description="Id of a curated ballot paper.")
    viewer_delegations: ViewerDelegations
    viewer_votes: dict[str, str] = Field(
        default_factory=dict,
        description="Question id to option id. A vote the viewer casts themself overrides "
        "their delegations for that question, and is the ballot used for anyone they answer for.",
    )
    threshold: float = Field(default=DEFAULT_THRESHOLD, ge=0, le=1)
    tiebreak_seed: int = Field(default=DEFAULT_TIEBREAK_SEED, ge=0, le=2**31 - 1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ballot_paper": "city-general",
                    "viewer_delegations": _EXAMPLE_DELEGATIONS,
                    "viewer_votes": {"q66": "yes"},
                    "threshold": 0.7,
                    "tiebreak_seed": 0,
                }
            ]
        }
    }


class TallySchema(BaseModel):
    winners: list[str]
    counts: dict[str, int]
    abstentions: int
    total_ballots: int
    tiebreak_applied: bool


class ChainLengthSchema(BaseModel):
    hops: int
    votes: int


class MetricsSchema(BaseModel):
    voters: int
    delegated_share: float = Field(
        description="Share of votes resolved by someone other than the voter."
    )
    largest_share: float = Field(
        description="Share of all votes held by the heaviest resolver."
    )
    largest_resolver: str | None
    gini: float = Field(description="Gini coefficient of effective voting weight.")
    chain_lengths: list[ChainLengthSchema]
    loops: list[list[str]] = Field(
        description="Each loop found; everyone on it kept the decision."
    )


class CategoryScoreSchema(BaseModel):
    category: str = Field(description="Category id.")
    text: str
    probability: float


class ReceiptSchema(BaseModel):
    outcome: OutcomeLiteral = Field(
        description="What the routing rule decided for the viewer."
    )
    threshold: float
    scores: list[CategoryScoreSchema] = Field(
        description="The viewer's categories, in list order."
    )
    category: str | None = Field(
        description="Text of the winning category, when delegated."
    )
    set_aside: list[str] = Field(
        description="Texts of categories that cleared the threshold but gave way to a narrower one."
    )
    chain: list[str] = Field(description="From the viewer to the resolver.")
    resolver: str
    kept_because: KeptLiteral = Field(
        description="Why the resolver holds the decision."
    )
    loop: list[str] | None
    choice: str | None = Field(
        description="The option cast for the viewer; null is an abstention."
    )


class HeldVoteSchema(BaseModel):
    voter: str
    home: str | None = Field(description="The voter's district.")


class InboxSchema(BaseModel):
    votes_for_others: int = Field(
        description="Votes the viewer resolves for other people."
    )
    held: list[HeldVoteSchema]
    answered: bool = Field(
        description="Whether the viewer has voted. Until they do, the votes they hold are abstentions."
    )


class QuestionResultSchema(BaseModel):
    question_id: str
    title: str
    delegated: TallySchema
    direct: TallySchema = Field(
        description="The same question with everyone voting for themself."
    )
    winner_changed: bool
    metrics: MetricsSchema
    receipt: ReceiptSchema | None = Field(
        description="Null when the viewer is not issued this ballot paper."
    )
    inbox: InboxSchema


class ResolveResponse(BaseModel):
    scenario: str
    model: str
    ballot_paper: str
    jurisdiction: str
    viewer_eligible: bool
    threshold: float
    tiebreak_seed: int
    unjudged_categories: list[str] = Field(
        description="Texts of the viewer's categories with no recorded judgment for some question. "
        "The viewer keeps those questions."
    )
    questions: list[QuestionResultSchema]
