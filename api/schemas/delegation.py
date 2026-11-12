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
    name: str = Field(description="A made-up display name; names can repeat.")
    username: str = Field(description="Unique across the network.")
    home: str | None = Field(
        description="The district the person lives in; null outside the city."
    )
    residences: list[str] = Field(description="Jurisdiction ids; empty for outsiders.")
    behaviour: str | None = Field(
        description="How this simulated person delegates; null for the viewer."
    )
    well_known_for: list[str] = Field(
        description="Ids of categories this person is well known for."
    )
    location: list[float] | None = Field(
        description="Where the person lives, as x and y in the unit square; "
        "null outside the city."
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


BallotTypeLiteral = Literal["single_choice", "ranked", "approval"]
MethodLiteral = Literal["plurality", "irv", "approval"]

# One vote: a single option, every option in order, or the approved options
Choice = Annotated[list[Annotated[str, StringConstraints(max_length=80)]], Field(max_length=12)]


class OptionSchema(BaseModel):
    id: str
    name: str
    note: str | None = Field(
        default=None, description="A line about the option, where the measure has one."
    )


class QuestionSchema(BaseModel):
    id: str
    label: str = Field(description="Its name on the ballot paper, such as Measure C.")
    kind: str = Field(description="What sort of measure it is, such as Bond.")
    title: str
    summary: str = Field(
        description="With the title and option names, what the decision model is shown."
    )
    ballot_type: BallotTypeLiteral
    method: MethodLiteral = Field(description="How the ballots are counted.")
    wording: str = Field(description="The official wording put to voters.")
    fiscal: str
    placed_by: str
    argument_for: str = Field(description="Empty for a choice among several options.")
    argument_against: str
    site: list[float] | None = Field(
        description="Where it would be built, when it has one place."
    )
    options: list[OptionSchema]


StatusLiteral = Literal["open", "closed"]


class BallotPaperSchema(BaseModel):
    id: str
    title: str
    jurisdiction: str
    closes_in_days: int = Field(
        description="Days from today until the paper closes; negative once it has."
    )
    opens_in_days: int = Field(
        description="Days from today until the paper opened; negative once it has."
    )
    status: StatusLiteral
    eligible_voters: int
    questions: list[QuestionSchema]


class ViewerChangeSchema(BaseModel):
    day: int = Field(description="Days from today; negative, as it is in the past.")
    category: str = Field(description="Category text.")
    before: str | None = Field(description="Who held it before; null when newly made.")
    after: str | None = Field(description="Who holds it after; null when withdrawn.")


class ScenarioResponse(BaseModel):
    scenario: str
    city: str = Field(description="The invented city's name.")
    provisional: list[str] = Field(
        description="Ids of questions routed on judgments recorded for earlier wording, "
        "until their own are collected."
    )
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
    viewer_delegations: list[ViewerDelegationSchema] = Field(
        description="The delegations the viewer's account starts with, in list order. "
        "Closed ballot papers were resolved with these."
    )
    viewer_changes: list[ViewerChangeSchema] = Field(
        description="The dated changes that led to the viewer's starting delegations, "
        "most recent first."
    )
    ballot_papers: list[BallotPaperSchema] = Field(description="Oldest first.")


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
    scores: list[QuestionScoreSchema] = Field(
        description="One per question on an open ballot paper."
    )
    limited: bool = Field(
        description="Whether the day's allowance of newly judged categories was used up, "
        "so the decision model was not asked."
    )
    failures: list[str] = Field(
        description="One message per failed request to the decision model."
    )


# ---------------------------------------------------------------------------
# POST /resolve
# ---------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    ballot_paper: str = Field(description="Id of a curated ballot paper.")
    viewer_delegations: ViewerDelegations
    viewer_votes: dict[str, Choice] = Field(
        default_factory=dict,
        description="Question id to the viewer's choice: one option id, every option in "
        "order for a ranked question, or the approved options. A vote the viewer casts "
        "themself overrides their delegations for that question, and is the ballot used "
        "for anyone they answer for.",
    )
    threshold: float = Field(default=DEFAULT_THRESHOLD, ge=0, le=1)
    tiebreak_seed: int = Field(default=DEFAULT_TIEBREAK_SEED, ge=0, le=2**31 - 1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ballot_paper": "city-advisory-2",
                    "viewer_delegations": _EXAMPLE_DELEGATIONS,
                    "viewer_votes": {"q68": ["yes"]},
                    "threshold": 0.7,
                    "tiebreak_seed": 0,
                }
            ]
        }
    }


class RoundSchema(BaseModel):
    round: int
    counts: dict[str, int]
    eliminated: list[str]
    exhausted: int


class TallySchema(BaseModel):
    method: MethodLiteral
    winners: list[str]
    counts: dict[str, int] = Field(
        description="Votes per option: first choices under instant-runoff voting, "
        "approvals under approval voting."
    )
    rounds: list[RoundSchema] = Field(
        description="Each round of an instant-runoff count; empty for other methods."
    )
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
    choice: list[str] | None = Field(
        description="The choice cast for the viewer; null when nothing has been cast."
    )
    resolver_votes_in_days: int | None = Field(
        description="On an open paper, when someone else holds the decision and has not "
        "voted yet: days from today until they are due to. Null otherwise."
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
    ballot_type: BallotTypeLiteral
    cast_so_far: int = Field(
        description="People who have cast their own ballot on the question, in or out "
        "of the jurisdiction."
    )
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
    status: StatusLiteral = Field(
        description="A closed paper is resolved with the delegations and votes the viewer "
        "had when it closed; the request's are not used."
    )
    closes_in_days: int
    viewer_eligible: bool
    threshold: float
    tiebreak_seed: int
    unjudged_categories: list[str] = Field(
        description="Texts of the viewer's categories with no recorded judgment for some question. "
        "The viewer keeps those questions."
    )
    questions: list[QuestionResultSchema]


# ---------------------------------------------------------------------------
# GET /people/{person_id}
# ---------------------------------------------------------------------------

HowLiteral = Literal["voted", "delegated", "abstained"]


class ProfileStatsSchema(BaseModel):
    votes_issued: int = Field(description="Closed questions issued to this person.")
    voted_personally: int
    delegated: int = Field(description="Of those, decided by someone else.")
    abstained: int = Field(description="Held by this person and not voted on.")
    delegation_rate: float | None = Field(
        description="Share of issued votes decided by someone else; null with none issued."
    )
    categories_handed_over: int
    delegators: int = Field(
        description="People who have handed this person at least one category."
    )
    categories_received: int = Field(description="Delegations made to this person.")
    votes_decided_for_others: int = Field(
        description="Other people's votes this person decided, over every closed question."
    )
    most_votes_held: int = Field(
        description="The most other people's votes this person held on one question."
    )
    largest_share: float = Field(
        description="The largest share of one question's votes this person decided, their own included."
    )


class ProfileDelegationSchema(BaseModel):
    category: str = Field(description="Category text.")
    delegate: str


class ProfileReceivedSchema(BaseModel):
    delegator: str
    category: str = Field(description="Category text.")


class HistoryEntrySchema(BaseModel):
    ballot_paper: str
    paper_title: str
    jurisdiction: str
    closed_days_ago: int
    question_id: str
    label: str
    title: str
    summary: str
    ballot_type: BallotTypeLiteral
    issued: bool = Field(
        description="Whether this person was issued the question. When false they appear "
        "only because other people's votes reached them."
    )
    how: HowLiteral = Field(
        description="Whether this person voted themself, their vote was decided by a delegate, "
        "or they held the decision and did not vote."
    )
    category: str | None = Field(
        description="Text of the category the vote was sent under, when delegated."
    )
    chain: list[str] = Field(description="From this person to whoever decided.")
    resolver: str
    choice: list[str] | None = Field(
        description="The choice on this person's ballot; null is an abstention."
    )
    votes_for_others: int = Field(
        description="Other people's votes this person decided on the question."
    )
    share: float = Field(
        description="The share of the question's votes this person decided, their own included."
    )
    winners: list[str] = Field(description="The result with delegation.")


class DelegationChangeSchema(BaseModel):
    day: int = Field(description="Days from today; negative, as it is in the past.")
    delegator: str
    category: str = Field(description="Category text.")
    before: str | None = Field(description="Who held it before; null when newly made.")
    after: str | None = Field(description="Who holds it after; null when withdrawn.")


class ProfileResponse(BaseModel):
    person: PersonSchema
    stats: ProfileStatsSchema
    delegations: list[ProfileDelegationSchema] = Field(
        description="What this person has handed over. For the viewer, the delegations "
        "their account started with."
    )
    received: list[ProfileReceivedSchema]
    history: list[HistoryEntrySchema] = Field(description="Most recent first.")
    changes: list[DelegationChangeSchema] = Field(
        description="Dated changes to delegations this person made, and to delegations "
        "made to or taken from them, most recent first."
    )


# ---------------------------------------------------------------------------
# GET /city
# ---------------------------------------------------------------------------


class CityQuestionSchema(BaseModel):
    ballot_paper: str
    paper_title: str
    jurisdiction: str
    closed_days_ago: int
    question_id: str
    label: str
    kind: str
    title: str
    ballot_type: BallotTypeLiteral
    voters: int = Field(description="People the question was issued to.")
    cast_delegated: int = Field(
        description="Ballots that counted with delegation: voters whose resolver voted."
    )
    cast_direct: int = Field(description="Voters who cast their own ballot.")
    delegated_share: float = Field(
        description="Share of votes resolved by someone other than the voter."
    )
    largest_share: float
    largest_resolver: str | None
    gini: float
    winners: list[str] = Field(description="The result with delegation.")
    direct_winners: list[str] = Field(description="The result without it.")
    winner_changed: bool
    support: float | None = Field(
        description="For a yes/no question, the yes share of the ballots that counted "
        "with delegation; null otherwise or when none counted."
    )


class CityPaperSchema(BaseModel):
    id: str
    title: str
    jurisdiction: str
    closed_days_ago: int
    questions: int
    turnout_delegated: float = Field(
        description="Ballots that counted with delegation over ballots issued, across the paper."
    )
    turnout_direct: float = Field(
        description="Ballots people cast themselves over ballots issued, across the paper."
    )
    delegated_share: float
    largest_share: float = Field(description="The largest on any of its questions.")
    changed: int = Field(description="Questions whose result delegation changed.")


class CityDeciderSchema(BaseModel):
    person: str
    votes_decided: int = Field(
        description="Other people's votes this person decided, over every closed question."
    )
    questions: int = Field(description="Closed questions on which they held someone's vote.")
    largest_share: float = Field(
        description="The largest share of one question's votes they decided, their own included."
    )


class CityTotalsSchema(BaseModel):
    questions: int
    changed: int
    turnout_delegated: float
    turnout_direct: float
    delegated_share: float
    largest_share: float
    largest_resolver: str | None


class CityResponse(BaseModel):
    scenario: str
    totals: CityTotalsSchema
    papers: list[CityPaperSchema] = Field(description="Closed papers, oldest first.")
    questions: list[CityQuestionSchema] = Field(
        description="Closed questions, most recent paper first."
    )
    deciders: list[CityDeciderSchema] = Field(
        description="The people who decided the most votes for others, most first."
    )
