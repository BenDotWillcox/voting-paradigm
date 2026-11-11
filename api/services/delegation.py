"""
Liquid democracy: the scenario, the creation checks, judgments and resolution.

Orchestration only. The delegation package does the routing, loop handling,
resolution and vote copying; voting/ does the counting.

Stateless and reproducible. The synthetic network and the curated ballot
papers are rebuilt from the scenario file and a seed, the viewer's changes
arrive with each request, and resolution reads only recorded judgments. The
same request therefore gives the same response.

There is one exception, and it is opt-in. A category the viewer writes has
no recorded judgments. POST /judgments will ask hosted Jev about it and
record the answers, but only when the server has an API key and
DELEGATION_LIVE_JUDGMENTS is switched on. Otherwise nothing is asked, the
category stays unjudged, and the routing rule keeps the viewer's votes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from delegation import (
    Category,
    CategoryId,
    DelegationLoopError,
    InvalidCategoryError,
    InvalidNetworkError,
    Judgments,
    JudgmentSource,
    JudgmentStore,
    NestingSource,
    NestingStore,
    Network,
    Question,
    QuestionResolution,
    add_delegation,
    chain_length_counts,
    create_category,
    delegated_ballots,
    delegated_share,
    direct_ballots,
    eligible_voters,
    gather_judgments,
    gather_nesting,
    largest_share,
    loop_warnings,
    resolve_question,
    weight_gini,
    winners_differ,
    with_nesting,
)
from delegation.scenario import (
    SCENARIO_SCHEMA,
    SCENARIO_SIMULATION,
    Scenario,
    load_scenario,
)
from delegation.simulate import (
    CITY,
    VIEWER,
    Simulation,
    jurisdictions,
    simulate_network,
    sincere_ballots,
)
from voting import (
    ElectionResult,
    SingleChoiceBallot,
    create_single_choice_ballot,
    random_tiebreak,
    resolve_plurality,
)

from ..schemas.delegation import (
    BallotPaperSchema,
    CategorySchema,
    CategoryScoreSchema,
    ChainLengthSchema,
    DelegationSchema,
    HeldVoteSchema,
    InboxSchema,
    JudgmentCountsSchema,
    JudgmentsRequest,
    JudgmentsResponse,
    JurisdictionSchema,
    LoopWarningSchema,
    MetricsSchema,
    OptionSchema,
    PersonSchema,
    QuestionResultSchema,
    QuestionSchema,
    QuestionScoreSchema,
    ReceiptSchema,
    ResolveRequest,
    ResolveResponse,
    ScenarioResponse,
    TallySchema,
    ValidateRequest,
    ValidateResponse,
    ViewerDelegationSchema,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env.local"
CACHE_DIR_VARIABLE = "DELEGATION_CACHE_DIR"
LIVE_VARIABLE = "DELEGATION_LIVE_JUDGMENTS"


class DelegationRequestError(ValueError):
    """Raised when a request cannot be honoured as sent; maps to HTTP 422."""


class LiveSource(JudgmentSource, NestingSource, Protocol):
    """A decision model that can judge both questions and nesting."""


@dataclass(frozen=True)
class RuntimeStores:
    """Where judgments for viewer-written categories are recorded."""

    judgments: JudgmentStore
    nesting: NestingStore


# ---------------------------------------------------------------------------
# Process-wide defaults (the router's dependencies)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _scenario() -> Scenario:
    return load_scenario()


@lru_cache(maxsize=1)
def _simulation() -> Simulation:
    scenario = _scenario()
    return simulate_network(scenario.categories, SCENARIO_SIMULATION, scenario.nesting)


@lru_cache(maxsize=1)
def default_stores() -> RuntimeStores:
    """Recorded judgments for viewer-written categories, under the git-ignored cache."""
    from delegation.jev import read_setting

    configured = read_setting(CACHE_DIR_VARIABLE, ENV_FILE)
    directory = Path(configured) if configured else REPO_ROOT / ".cache" / "delegation"
    return RuntimeStores(
        judgments=JudgmentStore(directory / "judgments.jsonl"),
        nesting=NestingStore(directory / "nesting.jsonl"),
    )


@lru_cache(maxsize=1)
def default_source() -> LiveSource | None:
    """
    Hosted Jev, when the server is set up to ask it.

    Live judgments cost money, so they need both an API key and an explicit
    switch. With either missing this returns None and nothing is asked.
    """
    from delegation.jev import JevSource, read_api_key, read_setting

    switch = (read_setting(LIVE_VARIABLE, ENV_FILE) or "").lower()
    if switch not in {"1", "true", "yes", "on"}:
        return None
    key = read_api_key(ENV_FILE)
    return JevSource(key) if key else None


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------


def _pool_ids(scenario: Scenario) -> set[CategoryId]:
    return {category.id for category in scenario.categories}


def _category(text: str, stores: RuntimeStores) -> Category:
    """
    The category for some text, in the wording it is already known by.

    A category's identity ignores case and whitespace, but a judgment
    records the exact wording the model was asked about. Reusing the pool's
    wording, or the wording a written category was first judged under, lets
    every spelling of a category share its judgments.
    """
    try:
        category = create_category(text)
    except InvalidCategoryError as error:
        raise DelegationRequestError(str(error)) from error
    known = _scenario().category(category.id)
    if known is not None:
        return known
    wording = stores.judgments.wording(category.id)
    return Category(category.id, wording) if wording is not None else category


def _viewer_network(
    delegations: list[ViewerDelegationSchema], stores: RuntimeStores
) -> Network:
    """
    The simulated network with the viewer's delegations applied.

    Raises:
        DelegationRequestError: If a delegation is invalid or would close a
            loop within one category
    """
    network = _simulation().network
    for item in delegations:
        try:
            network = add_delegation(
                network, VIEWER, _category(item.category, stores), item.delegate
            )
        except InvalidNetworkError as error:
            raise DelegationRequestError(str(error)) from error
    return _with_recorded_nesting(network, stores)


def _viewer_categories(network: Network) -> list[Category]:
    return [network.categories[d.category] for d in network.delegations_of(VIEWER)]


def _with_recorded_nesting(network: Network, stores: RuntimeStores) -> Network:
    """Add any recorded nesting that involves a category the viewer wrote."""
    scenario = _scenario()
    pool = _pool_ids(scenario)
    held = _viewer_categories(network)
    pairs = [
        (first, second)
        for first in held
        for second in held
        if first.id != second.id and not (first.id in pool and second.id in pool)
    ]
    if not pairs:
        return network
    found = gather_nesting(
        pairs,
        stores.nesting,
        model=scenario.model,
        threshold=scenario.nesting_threshold,
    ).nesting
    for pair in sorted(found):
        try:
            network = with_nesting(network, network.nesting | {pair})
        except InvalidNetworkError:
            continue  # it would make the nesting loop; leave it out
    return network


def _judgments(
    network: Network, questions: list[Question], stores: RuntimeStores
) -> tuple[Judgments, list[Category]]:
    """
    Every recorded judgment the network can use, and the viewer's categories
    that are missing some.
    """
    scenario = _scenario()
    pool = _pool_ids(scenario)
    written = [
        category for category in _viewer_categories(network) if category.id not in pool
    ]
    judgments = dict(scenario.judgments)
    unjudged: list[Category] = []
    if written:
        report = gather_judgments(
            questions, written, stores.judgments, model=scenario.model
        )
        judgments.update(report.judgments)
        missing = {category_id for _, category_id in report.missing}
        unjudged = [category for category in written if category.id in missing]
    return judgments, unjudged


def _category_schema(
    category: Category, network: Network | None = None
) -> CategorySchema:
    scenario = _scenario()
    nesting = network.nesting if network is not None else scenario.nesting
    return CategorySchema(
        id=category.id,
        text=category.text,
        in_pool=category.id in _pool_ids(scenario),
        inside=sorted(broad for narrow, broad in nesting if narrow == category.id),
    )


def _label(person: str) -> str:
    if person == VIEWER:
        return "You"
    prefix, _, number = person.partition("-")
    if prefix == "out":
        return f"Outside resident {int(number)}"
    return f"District {prefix[1:]} resident {int(number)}"


def _home(network: Network, person: str) -> str | None:
    """The district a person lives in, if they live in the city."""
    return next(
        (r for r in sorted(network.persons[person].residences) if r != CITY), None
    )


# ---------------------------------------------------------------------------
# GET /scenario
# ---------------------------------------------------------------------------


def scenario_response(live: bool) -> ScenarioResponse:
    """The simulated network and the curated ballot papers."""
    scenario = _scenario()
    simulation = _simulation()
    network = simulation.network

    well_known: dict[str, list[str]] = {}
    for category_id, people in simulation.experts.items():
        for person in people:
            well_known.setdefault(person, []).append(category_id)

    return ScenarioResponse(
        scenario=SCENARIO_SCHEMA,
        model=scenario.model,
        seed=simulation.config.seed,
        threshold=scenario.threshold,
        viewer=VIEWER,
        live_judgments=live,
        jurisdictions=[
            JurisdictionSchema(
                id=jurisdiction,
                name=(
                    "The city"
                    if jurisdiction == CITY
                    else f"District {jurisdiction[-1]}"
                ),
            )
            for jurisdiction in jurisdictions(simulation.config)
        ],
        persons=[
            PersonSchema(
                id=person.id,
                label=_label(person.id),
                residences=sorted(person.residences),
                behaviour=simulation.behaviours.get(person.id),
                well_known_for=sorted(well_known.get(person.id, [])),
            )
            for person in network.persons.values()
        ],
        categories=[_category_schema(category) for category in scenario.categories],
        delegations=[
            DelegationSchema(
                delegator=d.delegator, category=d.category, delegate=d.delegate
            )
            for d in network.delegations
        ],
        ballot_papers=[
            BallotPaperSchema(
                id=entry.id,
                title=entry.title,
                jurisdiction=entry.paper.jurisdiction,
                eligible_voters=len(eligible_voters(network, entry.paper.jurisdiction)),
                questions=[
                    QuestionSchema(
                        id=question.id,
                        title=question.title,
                        summary=question.summary,
                        options=[
                            OptionSchema(id=o.id, name=o.name) for o in question.options
                        ],
                    )
                    for question in entry.paper.questions
                ],
            )
            for entry in scenario.papers
        ],
    )


# ---------------------------------------------------------------------------
# POST /delegations/validate
# ---------------------------------------------------------------------------


def validate_response(
    request: ValidateRequest, stores: RuntimeStores
) -> ValidateResponse:
    """
    Run the creation checks on one proposed delegation.

    Raises:
        DelegationRequestError: If the viewer's existing delegations or the
            proposed category text are invalid
    """
    scenario = _scenario()
    network = _viewer_network(request.viewer_delegations, stores)
    category = _category(request.proposed.category, stores)

    def rejected(reason: str, chain: list[str] | None = None) -> ValidateResponse:
        return ValidateResponse(
            accepted=False,
            reason=reason,
            chain=chain,
            category=_category_schema(category, network),
            judged=category.id in _pool_ids(scenario),
            warnings=[],
        )

    try:
        proposed = add_delegation(network, VIEWER, category, request.proposed.delegate)
    except DelegationLoopError as error:
        return rejected(
            "This would close a loop: the same category comes back to you.",
            list(error.chain),
        )
    except InvalidNetworkError as error:
        return rejected(str(error))

    proposed = _with_recorded_nesting(proposed, stores)
    questions = list(scenario.questions)
    judgments, unjudged = _judgments(proposed, questions, stores)
    warned = set(
        loop_warnings(
            proposed,
            VIEWER,
            category.id,
            [question.id for question in questions],
            judgments,
            threshold=request.threshold,
        )
    )
    return ValidateResponse(
        accepted=True,
        reason=None,
        chain=None,
        category=_category_schema(category, proposed),
        judged=category not in unjudged,
        warnings=[
            LoopWarningSchema(
                ballot_paper=entry.id, question_id=question.id, title=question.title
            )
            for entry in scenario.papers
            for question in entry.paper.questions
            if question.id in warned
        ],
    )


# ---------------------------------------------------------------------------
# POST /judgments
# ---------------------------------------------------------------------------


def judgments_response(
    request: JudgmentsRequest, stores: RuntimeStores, source: LiveSource | None
) -> JudgmentsResponse:
    """
    Make sure a category has judgments for every curated question.

    A pool category already has them. For a category the viewer wrote,
    recorded judgments are used first and the rest are asked of the decision
    model when one is available. Nesting against the viewer's other
    categories is judged the same way.

    Raises:
        DelegationRequestError: If a category text is invalid
    """
    scenario = _scenario()
    pool = _pool_ids(scenario)
    category = _category(request.category, stores)
    held = [
        other
        for other in (_category(text, stores) for text in request.held)
        if other.id != category.id
    ]
    questions = list(scenario.questions)

    judgments = dict(scenario.judgments)
    counts = JudgmentCountsSchema(recorded=len(questions), fetched=0, missing=0)
    failures: list[str] = []
    if category.id not in pool:
        report = gather_judgments(
            questions, [category], stores.judgments, model=scenario.model, source=source
        )
        judgments.update(report.judgments)
        counts = JudgmentCountsSchema(
            recorded=report.recorded,
            fetched=report.fetched,
            missing=len(report.missing),
        )
        failures += report.failures

    pairs = [
        pair
        for other in held
        if not (category.id in pool and other.id in pool)
        for pair in ((category, other), (other, category))
    ]
    nested = gather_nesting(
        pairs,
        stores.nesting,
        model=scenario.model,
        source=source,
        threshold=scenario.nesting_threshold,
    )
    failures += nested.failures
    nesting = scenario.nesting | nested.nesting

    return JudgmentsResponse(
        category=_category_schema(category),
        model=scenario.model,
        live=source is not None,
        judgments=counts,
        nesting=JudgmentCountsSchema(
            recorded=nested.recorded,
            fetched=nested.fetched,
            missing=len(nested.missing),
        ),
        inside=[other.text for other in held if (category.id, other.id) in nesting],
        contains=[other.text for other in held if (other.id, category.id) in nesting],
        scores=[
            QuestionScoreSchema(
                ballot_paper=entry.id,
                question_id=question.id,
                title=question.title,
                probability=judgments.get((question.id, category.id)),
            )
            for entry in scenario.papers
            for question in entry.paper.questions
        ],
        failures=failures,
    )


# ---------------------------------------------------------------------------
# POST /resolve
# ---------------------------------------------------------------------------


def _abstain(voter: str) -> SingleChoiceBallot:
    return create_single_choice_ballot(voter, None)


def _tally(result: ElectionResult) -> TallySchema:
    return TallySchema(
        winners=result.winners,
        counts=result.vote_counts,
        abstentions=result.abstentions,
        total_ballots=result.total_ballots,
        tiebreak_applied=result.tiebreak_applied,
    )


def _metrics(resolution: QuestionResolution) -> MetricsSchema:
    weights = resolution.weights()
    heaviest: str | None = None
    if weights:
        top = max(weights.values())
        # Ties go to the smallest id, so the answer never depends on order.
        heaviest = min(person for person, weight in weights.items() if weight == top)
    return MetricsSchema(
        voters=len(resolution.voters),
        delegated_share=round(delegated_share(resolution), 4),
        largest_share=round(largest_share(resolution), 4),
        largest_resolver=heaviest,
        gini=round(weight_gini(resolution), 4),
        chain_lengths=[
            ChainLengthSchema(hops=hops, votes=votes)
            for hops, votes in chain_length_counts(resolution).items()
        ],
        loops=[list(loop) for loop in resolution.loops],
    )


def _receipt(
    network: Network,
    resolution: QuestionResolution,
    cast: dict[str, SingleChoiceBallot],
) -> ReceiptSchema | None:
    trace = resolution.traces.get(VIEWER)
    if trace is None:
        return None  # the viewer is not issued this ballot paper
    decision = resolution.decisions[VIEWER]
    used = cast.get(trace.resolver)
    return ReceiptSchema(
        outcome=decision.outcome.value,
        threshold=decision.threshold,
        scores=[
            CategoryScoreSchema(
                category=score.category,
                text=network.categories[score.category].text,
                probability=score.probability,
            )
            for score in decision.scores
        ],
        category=(
            network.categories[decision.category].text if decision.category else None
        ),
        set_aside=[
            network.categories[category].text for category in decision.set_aside
        ],
        chain=list(trace.chain),
        resolver=trace.resolver,
        kept_because=trace.kept_because.value,
        loop=list(trace.loop) if trace.loop is not None else None,
        choice=used.choice if used is not None else None,
    )


def resolve_response(request: ResolveRequest, stores: RuntimeStores) -> ResolveResponse:
    """
    Process one curated ballot paper for the network with the viewer's changes.

    Raises:
        DelegationRequestError: If the ballot paper is unknown, a delegation
            is invalid, or a vote names an unknown question or option
    """
    scenario = _scenario()
    simulation = _simulation()
    try:
        entry = scenario.paper(request.ballot_paper)
    except KeyError:
        raise DelegationRequestError(
            f"Unknown ballot paper {request.ballot_paper!r}"
        ) from None

    paper = entry.paper
    on_paper = {question.id: question for question in paper.questions}
    for question_id, option in request.viewer_votes.items():
        question = on_paper.get(question_id)
        if question is None:
            raise DelegationRequestError(
                f"Question {question_id!r} is not on this ballot paper"
            )
        if option not in {candidate.id for candidate in question.options}:
            raise DelegationRequestError(
                f"{option!r} is not an option on question {question_id!r}"
            )

    network = _viewer_network(request.viewer_delegations, stores)
    judgments, unjudged = _judgments(network, list(paper.questions), stores)
    voters = eligible_voters(network, paper.jurisdiction)

    results: list[QuestionResultSchema] = []
    for question in paper.questions:
        viewer_choice = request.viewer_votes.get(question.id)
        resolution = resolve_question(
            network,
            question.id,
            voters,
            judgments,
            threshold=request.threshold,
            direct_voters={VIEWER} if viewer_choice is not None else frozenset(),
        )
        cast = sincere_ballots(simulation, question)
        if viewer_choice is not None:
            cast[VIEWER] = create_single_choice_ballot(VIEWER, viewer_choice)

        candidates = list(question.options)
        # A fresh tiebreak for each count, so neither depends on the other.
        delegated = resolve_plurality(
            candidates,
            delegated_ballots(resolution, cast, _abstain),
            random_tiebreak(request.tiebreak_seed),
        )
        direct = resolve_plurality(
            candidates,
            direct_ballots(voters, cast, _abstain),
            random_tiebreak(request.tiebreak_seed),
        )
        held = [
            voter
            for voter, trace in resolution.traces.items()
            if trace.resolver == VIEWER and voter != VIEWER
        ]
        results.append(
            QuestionResultSchema(
                question_id=question.id,
                title=question.title,
                delegated=_tally(delegated),
                direct=_tally(direct),
                winner_changed=winners_differ(direct, delegated),
                metrics=_metrics(resolution),
                receipt=_receipt(network, resolution, cast),
                inbox=InboxSchema(
                    votes_for_others=len(held),
                    held=[
                        HeldVoteSchema(voter=voter, home=_home(network, voter))
                        for voter in held
                    ],
                    answered=viewer_choice is not None,
                ),
            )
        )

    return ResolveResponse(
        scenario=SCENARIO_SCHEMA,
        model=scenario.model,
        ballot_paper=entry.id,
        jurisdiction=paper.jurisdiction,
        viewer_eligible=VIEWER in voters,
        threshold=request.threshold,
        tiebreak_seed=request.tiebreak_seed,
        unjudged_categories=[category.text for category in unjudged],
        questions=results,
    )
