"""
Liquid democracy: the scenario, the creation checks, judgments and resolution.

Orchestration only. The delegation package does the routing, loop handling,
resolution and vote copying; voting/ does the counting.

Stateless and reproducible. The synthetic network and the curated ballot
papers are rebuilt from the scenario file and a seed, the viewer's changes
arrive with each request, and resolution reads only recorded judgments. The
same request therefore gives the same response.

Closed ballot papers are history. Each was resolved with the network as it
stood on the day it closed, the viewer's delegations of that day included,
so they do not change when the viewer edits their delegations, and
everyone's profile is read from them. Open ballot papers are resolved with
whatever the request carries, and count only the ballots cast so far: some
people have yet to fill theirs in.

Not everyone votes. A simulated person casts their own ballot on a question
with their own seeded chance, so a vote that ends with someone who did not
vote is an abstention, and the direct count is of the people who turned out.

There is one exception to "recorded only", and it is opt-in. A category the
viewer writes has no recorded judgments. POST /judgments will ask hosted Jev
about it, for the questions that are still open, and record the answers, but
only when the server has an API key and DELEGATION_LIVE_JUDGMENTS is
switched on, and only until the day's allowance of new categories is used
up. Otherwise nothing is asked, the category stays unjudged, and the routing
rule keeps the viewer's votes.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

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
from delegation.ballots import (
    METHODS,
    BallotType,
    InvalidChoiceError,
    ballot_for,
    choice_on,
    count,
    sincere_choice_for,
)
from delegation.scenario import (
    SCENARIO_SCHEMA,
    SCENARIO_SIMULATION,
    Measure,
    Scenario,
    ScenarioPaper,
    load_scenario,
)
from delegation.simulate import (
    CITY,
    VIEWER,
    Simulation,
    cast_day,
    casts,
    jurisdictions,
    network_on,
    option_utilities,
    person_utilities,
    simulate_network,
)
from voting import DEFAULT_TIEBREAK_SEED, ElectionResult, IRVResult, random_tiebreak
from voting.types import Ballot

from ..schemas.delegation import (
    BallotPaperSchema,
    CategorySchema,
    CategoryScoreSchema,
    ChainLengthSchema,
    CityDeciderSchema,
    CityPaperSchema,
    CityQuestionSchema,
    CityResponse,
    CityTotalsSchema,
    DelegationChangeSchema,
    DelegationSchema,
    HeldVoteSchema,
    HistoryEntrySchema,
    InboxSchema,
    JudgmentCountsSchema,
    JudgmentsRequest,
    JudgmentsResponse,
    JurisdictionSchema,
    LoopWarningSchema,
    MetricsSchema,
    OptionSchema,
    PersonSchema,
    ProfileDelegationSchema,
    ProfileReceivedSchema,
    ProfileResponse,
    ProfileStatsSchema,
    QuestionResultSchema,
    QuestionSchema,
    QuestionScoreSchema,
    ReceiptSchema,
    ResolveRequest,
    ResolveResponse,
    RoundSchema,
    ScenarioResponse,
    TallySchema,
    ValidateRequest,
    ValidateResponse,
    ViewerChangeSchema,
    ViewerDelegationSchema,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env.local"
CACHE_DIR_VARIABLE = "DELEGATION_CACHE_DIR"
LIVE_VARIABLE = "DELEGATION_LIVE_JUDGMENTS"
DAILY_CAP_VARIABLE = "DELEGATION_LIVE_DAILY_CATEGORIES"
# New categories the decision model may be asked about in one day (UTC)
DEFAULT_DAILY_CAP = 200


class DelegationRequestError(ValueError):
    """Raised when a request cannot be honoured as sent; maps to HTTP 422."""


class LiveSource(JudgmentSource, NestingSource, Protocol):
    """A decision model that can judge both questions and nesting."""


@dataclass(frozen=True)
class RuntimeStores:
    """Where judgments for viewer-written categories are recorded."""

    judgments: JudgmentStore
    nesting: NestingStore
    # Where the day's count of newly judged categories is kept; None keeps
    # no count and applies no limit
    usage: Path | None = None
    daily_cap: int = DEFAULT_DAILY_CAP


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
    cap = read_setting(DAILY_CAP_VARIABLE, ENV_FILE)
    return RuntimeStores(
        judgments=JudgmentStore(directory / "judgments.jsonl"),
        nesting=NestingStore(directory / "nesting.jsonl"),
        usage=directory / "usage.json",
        daily_cap=int(cap) if cap and cap.isdigit() else DEFAULT_DAILY_CAP,
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


def _home(network: Network, person: str) -> str | None:
    """The district a person lives in, if they live in the city."""
    return next(
        (r for r in sorted(network.persons[person].residences) if r != CITY), None
    )


@lru_cache(maxsize=1)
def _well_known() -> dict[str, list[str]]:
    """The categories each well-known person is known for."""
    known: dict[str, list[str]] = {}
    for category_id, people in _simulation().experts.items():
        for person in people:
            known.setdefault(person, []).append(category_id)
    return known


def _person_schema(person: str) -> PersonSchema:
    simulation = _simulation()
    network = simulation.network
    return PersonSchema(
        id=person,
        name=simulation.names[person],
        username=simulation.usernames[person],
        home=_home(network, person),
        residences=sorted(network.persons[person].residences),
        behaviour=simulation.behaviours.get(person),
        well_known_for=sorted(_well_known().get(person, [])),
        location=(
            list(simulation.homes[person]) if person in simulation.homes else None
        ),
    )


def _open_questions(scenario: Scenario) -> list[Question]:
    """The questions still open: the only ones a new delegation can affect."""
    return [
        question for entry in scenario.open_papers for question in entry.paper.questions
    ]


def _question_schema(measure: Measure) -> QuestionSchema:
    question = measure.question
    site = measure.site
    return QuestionSchema(
        id=question.id,
        label=measure.label,
        kind=measure.kind,
        title=question.title,
        summary=question.summary,
        ballot_type=measure.ballot_type,
        method=_method(measure.ballot_type),
        wording=measure.wording,
        fiscal=measure.fiscal,
        placed_by=measure.placed_by,
        argument_for=measure.argument_for,
        argument_against=measure.argument_against,
        site=list(site) if site is not None else None,
        options=[
            OptionSchema(id=o.id, name=o.name, note=measure.option_notes.get(o.id))
            for o in question.options
        ],
    )


def _paper_schema(entry: ScenarioPaper, network: Network) -> BallotPaperSchema:
    return BallotPaperSchema(
        id=entry.id,
        title=entry.title,
        jurisdiction=entry.paper.jurisdiction,
        closes_in_days=entry.closes_in_days,
        opens_in_days=entry.opens_in_days,
        status="open" if entry.is_open else "closed",
        eligible_voters=len(eligible_voters(network, entry.paper.jurisdiction)),
        questions=[_question_schema(measure) for measure in entry.measures],
    )


# ---------------------------------------------------------------------------
# The day's allowance of newly judged categories
# ---------------------------------------------------------------------------


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _used_today(stores: RuntimeStores) -> int:
    if stores.usage is None or not stores.usage.exists():
        return 0
    try:
        record = json.loads(stores.usage.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(record, dict) or record.get("day") != _today():
        return 0
    used = record.get("categories", 0)
    return used if isinstance(used, int) else 0


def _allowance_left(stores: RuntimeStores) -> bool:
    return stores.usage is None or _used_today(stores) < stores.daily_cap


def _count_new_category(stores: RuntimeStores) -> None:
    if stores.usage is None:
        return
    stores.usage.parent.mkdir(parents=True, exist_ok=True)
    stores.usage.write_text(
        json.dumps({"day": _today(), "categories": _used_today(stores) + 1}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# GET /scenario
# ---------------------------------------------------------------------------


def scenario_response(live: bool) -> ScenarioResponse:
    """The simulated network, the ballot papers, and the viewer's starting account."""
    scenario = _scenario()
    simulation = _simulation()
    network = simulation.network

    return ScenarioResponse(
        scenario=SCENARIO_SCHEMA,
        city=scenario.city,
        provisional=sorted(scenario.provisional),
        model=scenario.model,
        seed=simulation.config.seed,
        threshold=scenario.threshold,
        viewer=VIEWER,
        live_judgments=live,
        jurisdictions=[
            JurisdictionSchema(
                id=jurisdiction,
                name=(
                    scenario.city
                    if jurisdiction == CITY
                    else scenario.districts.get(
                        jurisdiction, f"District {jurisdiction[-1]}"
                    )
                ),
            )
            for jurisdiction in jurisdictions(simulation.config)
        ],
        persons=[_person_schema(person) for person in network.persons],
        categories=[_category_schema(category) for category in scenario.categories],
        delegations=[
            DelegationSchema(
                delegator=d.delegator, category=d.category, delegate=d.delegate
            )
            for d in network.delegations
        ],
        viewer_delegations=[
            ViewerDelegationSchema(category=category, delegate=delegate)
            for category, delegate in scenario.viewer.delegations
        ],
        viewer_changes=[
            ViewerChangeSchema(day=day, category=text, before=before, after=after)
            for day, text, before, after in sorted(
                scenario.viewer.changes, key=lambda change: -change[0]
            )
        ],
        ballot_papers=[_paper_schema(entry, network) for entry in scenario.papers],
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
    questions = _open_questions(scenario)
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
            for entry in scenario.open_papers
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
    Make sure a category has judgments for every open question.

    A pool category already has them. For a category the viewer wrote,
    recorded judgments are used first and the rest are asked of the decision
    model when one is available and the day's allowance of new categories
    is not used up. Nesting against the viewer's other categories is judged
    the same way. Closed questions are never asked about: they were resolved
    before the category existed.

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
    questions = _open_questions(scenario)

    judgments = dict(scenario.judgments)
    counts = JudgmentCountsSchema(recorded=len(questions), fetched=0, missing=0)
    failures: list[str] = []
    limited = False
    if category.id not in pool:
        on_record = gather_judgments(
            questions, [category], stores.judgments, model=scenario.model
        )
        if on_record.missing and source is not None and not _allowance_left(stores):
            # Over the day's allowance: ask nothing, for this category or its nesting.
            limited = True
            source = None
        report = gather_judgments(
            questions, [category], stores.judgments, model=scenario.model, source=source
        )
        if report.fetched:
            _count_new_category(stores)
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
        live=source is not None or limited,
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
            for entry in scenario.open_papers
            for question in entry.paper.questions
        ],
        limited=limited,
        failures=failures,
    )


# ---------------------------------------------------------------------------
# POST /resolve
# ---------------------------------------------------------------------------


def _method(ballot_type: BallotType) -> Literal["plurality", "irv", "approval"]:
    method = METHODS[ballot_type]
    assert method in ("plurality", "irv", "approval")
    return method  # type: ignore[return-value]


def _tally(result: ElectionResult, ballot_type: BallotType) -> TallySchema:
    rounds = (
        [
            RoundSchema(
                round=entry.round_number,
                counts=entry.vote_counts,
                eliminated=entry.eliminated,
                exhausted=entry.exhausted_ballots,
            )
            for entry in result.rounds
        ]
        if isinstance(result, IRVResult)
        else []
    )
    return TallySchema(
        method=_method(ballot_type),
        winners=result.winners,
        counts=rounds[0].counts if rounds else result.vote_counts,
        rounds=rounds,
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


@dataclass(frozen=True)
class _Resolved:
    """One question, resolved and counted both ways."""

    measure: Measure
    voters: frozenset[str]
    resolution: QuestionResolution
    # The ballots cast so far: everyone's own, the viewer's only if they voted
    cast: Mapping[str, Ballot]
    # People who have not filled in an open paper yet, and the day they will
    pending: Mapping[str, int]
    delegated: ElectionResult
    direct: ElectionResult

    @property
    def question(self) -> Question:
        return self.measure.question

    def choice_of(self, person: str) -> list[str] | None:
        """What a person's own ballot says; None when they cast nothing."""
        ballot = self.cast.get(person)
        return choice_on(ballot, self.question) if ballot is not None else None


def _receipt(network: Network, resolved: _Resolved) -> ReceiptSchema | None:
    resolution = resolved.resolution
    trace = resolution.traces.get(VIEWER)
    if trace is None:
        return None  # the viewer is not issued this ballot paper
    decision = resolution.decisions[VIEWER]
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
        choice=resolved.choice_of(trace.resolver),
        resolver_votes_in_days=(
            resolved.pending.get(trace.resolver) if trace.resolver != VIEWER else None
        ),
    )


def _abstention(measure: Measure) -> Callable[[str], Ballot]:
    return lambda voter: ballot_for(measure.ballot_type, voter, None, measure.question)


def _resolve_paper(
    entry: ScenarioPaper,
    network: Network,
    judgments: Judgments,
    viewer_votes: Mapping[str, Sequence[str]],
    viewer_direct: frozenset[str],
    threshold: float,
    tiebreak_seed: int,
) -> list[_Resolved]:
    """
    Resolve and count every question on a ballot paper.

    Args:
        viewer_votes: The viewer's own choice per question, where they have one
        viewer_direct: Questions on which the viewer's vote overrides their
            delegations

    Raises:
        InvalidChoiceError: If one of the viewer's votes does not fit its question
    """
    simulation = _simulation()
    voters = frozenset(eligible_voters(network, entry.paper.jurisdiction))

    resolved: list[_Resolved] = []
    for measure in entry.measures:
        question = measure.question
        resolution = resolve_question(
            network,
            question.id,
            voters,
            judgments,
            threshold=threshold,
            direct_voters={VIEWER} if question.id in viewer_direct else frozenset(),
        )

        cast: dict[str, Ballot] = {}
        pending: dict[str, int] = {}
        for person in simulation.positions:
            if not casts(simulation, person, question, measure.support.salience):
                continue  # this person sits the question out
            if entry.is_open:
                day = cast_day(
                    simulation,
                    person,
                    entry.id,
                    entry.opens_in_days,
                    entry.closes_in_days,
                )
                if day > 0:
                    pending[person] = day
                    continue
            utilities = person_utilities(simulation, person, question, measure.support)
            cast[person] = ballot_for(
                measure.ballot_type,
                person,
                sincere_choice_for(measure.ballot_type, utilities, question),
                question,
            )
        if question.id in viewer_votes:
            cast[VIEWER] = ballot_for(
                measure.ballot_type, VIEWER, viewer_votes[question.id], question
            )

        abstain = _abstention(measure)
        # A fresh tiebreak for each count, so neither depends on the other.
        delegated = count(
            measure.ballot_type,
            question.options,
            delegated_ballots(resolution, cast, abstain),
            random_tiebreak(tiebreak_seed),
        )
        direct = count(
            measure.ballot_type,
            question.options,
            direct_ballots(voters, cast, abstain),
            random_tiebreak(tiebreak_seed),
        )
        resolved.append(
            _Resolved(measure, voters, resolution, cast, pending, delegated, direct)
        )
    return resolved


@lru_cache(maxsize=64)
def _network_on(day: int) -> Network:
    """
    The network as it stood at the end of a day, with the delegations the
    viewer's account had then. Day 0 is today, with the account the viewer
    starts the demo with.
    """
    scenario = _scenario()
    simulation = _simulation()
    network = network_on(simulation.network, simulation.changes, day)
    by_text = {category.text: category for category in scenario.categories}
    for text, delegate in scenario.viewer.delegations_on(day):
        network = add_delegation(network, VIEWER, by_text[text], delegate)
    return network


def _viewer_past_choice(measure: Measure) -> list[str]:
    """What the viewer chose on a closed question, from their authored position."""
    simulation = _simulation()
    utilities = option_utilities(
        simulation.config,
        _scenario().viewer.position,
        simulation.homes.get(VIEWER),
        VIEWER,
        measure.question,
        measure.support,
    )
    return sincere_choice_for(measure.ballot_type, utilities, measure.question)


@lru_cache(maxsize=1)
def _history() -> dict[str, list[_Resolved]]:
    """
    Every closed ballot paper, resolved once, with the network of its day.

    The viewer's past votes come from the scenario: a choice from their
    authored position on every closed question except the ones they missed,
    and an override of their delegations where the scenario says they voted
    themself.
    """
    scenario = _scenario()
    viewer = scenario.viewer
    history: dict[str, list[_Resolved]] = {}
    for entry in scenario.closed_papers:
        votes = {
            measure.question.id: _viewer_past_choice(measure)
            for measure in entry.measures
            if measure.question.id not in viewer.missed
        }
        history[entry.id] = _resolve_paper(
            entry,
            _network_on(entry.closes_in_days),
            scenario.judgments,
            votes,
            viewer.voted_directly,
            scenario.threshold,
            DEFAULT_TIEBREAK_SEED,
        )
    return history


def _held_by(resolved: _Resolved, person: str) -> list[str]:
    """The other voters whose vote this person decided."""
    return [
        voter
        for voter, trace in resolved.resolution.traces.items()
        if trace.resolver == person and voter != person
    ]


def _question_result(network: Network, resolved: _Resolved) -> QuestionResultSchema:
    held = _held_by(resolved, VIEWER)
    return QuestionResultSchema(
        question_id=resolved.question.id,
        title=resolved.question.title,
        ballot_type=resolved.measure.ballot_type,
        cast_so_far=len(resolved.cast),
        delegated=_tally(resolved.delegated, resolved.measure.ballot_type),
        direct=_tally(resolved.direct, resolved.measure.ballot_type),
        winner_changed=winners_differ(resolved.direct, resolved.delegated),
        metrics=_metrics(resolved.resolution),
        receipt=_receipt(network, resolved),
        inbox=InboxSchema(
            votes_for_others=len(held),
            held=[
                HeldVoteSchema(voter=voter, home=_home(network, voter))
                for voter in held
            ],
            answered=VIEWER in resolved.cast,
        ),
    )


def resolve_response(request: ResolveRequest, stores: RuntimeStores) -> ResolveResponse:
    """
    Process one ballot paper.

    An open paper is resolved for the network with the viewer's changes,
    counting the ballots cast so far. A closed paper is history: it is
    returned as it was resolved, with the network of the day it closed, and
    the request's delegations, votes, threshold and tiebreak seed are not
    used.

    Raises:
        DelegationRequestError: If the ballot paper is unknown, a delegation
            is invalid, or a vote names an unknown question or option
    """
    scenario = _scenario()
    try:
        entry = scenario.paper(request.ballot_paper)
    except KeyError:
        raise DelegationRequestError(
            f"Unknown ballot paper {request.ballot_paper!r}"
        ) from None
    paper = entry.paper

    unjudged: list[Category] = []
    if entry.is_open:
        on_paper = {question.id for question in paper.questions}
        for question_id in request.viewer_votes:
            if question_id not in on_paper:
                raise DelegationRequestError(
                    f"Question {question_id!r} is not on this ballot paper"
                )
        network = _viewer_network(request.viewer_delegations, stores)
        judgments, unjudged = _judgments(network, list(paper.questions), stores)
        threshold, tiebreak_seed = request.threshold, request.tiebreak_seed
        try:
            resolved = _resolve_paper(
                entry,
                network,
                judgments,
                request.viewer_votes,
                frozenset(request.viewer_votes),
                threshold,
                tiebreak_seed,
            )
        except InvalidChoiceError as error:
            raise DelegationRequestError(str(error)) from error
    else:
        network = _network_on(entry.closes_in_days)
        threshold, tiebreak_seed = scenario.threshold, DEFAULT_TIEBREAK_SEED
        resolved = _history()[entry.id]

    return ResolveResponse(
        scenario=SCENARIO_SCHEMA,
        model=scenario.model,
        ballot_paper=entry.id,
        jurisdiction=paper.jurisdiction,
        status="open" if entry.is_open else "closed",
        closes_in_days=entry.closes_in_days,
        viewer_eligible=VIEWER in eligible_voters(network, paper.jurisdiction),
        threshold=threshold,
        tiebreak_seed=tiebreak_seed,
        unjudged_categories=[category.text for category in unjudged],
        questions=[_question_result(network, item) for item in resolved],
    )


# ---------------------------------------------------------------------------
# GET /people/{person_id}
# ---------------------------------------------------------------------------


def profile_response(person: str) -> ProfileResponse:
    """
    One person's profile: who they are, what they have handed over and been
    handed, and how each closed question went for them.

    Read from the closed ballot papers only, so it is the same on every
    request. The delegations listed are today's; for the viewer, the ones
    their account starts the demo with.

    Raises:
        DelegationRequestError: If there is no such person
    """
    scenario = _scenario()
    network = _network_on(0)
    if person not in network.persons:
        raise DelegationRequestError(f"Unknown person {person!r}")

    entries: list[HistoryEntrySchema] = []
    most_held = 0
    largest = 0.0
    for paper in reversed(scenario.closed_papers):
        for resolved in _history()[paper.id]:
            resolution = resolved.resolution
            trace = resolution.traces.get(person)
            held = len(_held_by(resolved, person))
            if trace is None and held == 0:
                continue  # neither issued to them nor decided by them

            most_held = max(most_held, held)
            share = resolution.weights().get(person, 0) / len(resolved.voters)
            largest = max(largest, share)

            resolver = trace.resolver if trace is not None else person
            how: Literal["voted", "delegated", "abstained"]
            if resolver != person:
                how = "delegated"
            elif resolved.choice_of(person) is not None:
                how = "voted"
            else:
                how = "abstained"
            decision = resolution.decisions.get(person)
            then = _network_on(paper.closes_in_days)
            sent_under = (
                then.categories[decision.category].text
                if how == "delegated" and decision is not None and decision.category
                else None
            )
            entries.append(
                HistoryEntrySchema(
                    ballot_paper=paper.id,
                    paper_title=paper.title,
                    jurisdiction=paper.paper.jurisdiction,
                    closed_days_ago=-paper.closes_in_days,
                    question_id=resolved.question.id,
                    label=resolved.measure.label,
                    title=resolved.question.title,
                    summary=resolved.question.summary,
                    ballot_type=resolved.measure.ballot_type,
                    issued=trace is not None,
                    how=how,
                    category=sent_under,
                    chain=list(trace.chain) if trace is not None else [person],
                    resolver=resolver,
                    choice=resolved.choice_of(resolver),
                    votes_for_others=held,
                    share=round(share, 4),
                    winners=resolved.delegated.winners,
                )
            )

    issued = [entry for entry in entries if entry.issued]
    delegated = sum(1 for entry in issued if entry.how == "delegated")
    received = [d for d in network.delegations if d.delegate == person]
    return ProfileResponse(
        person=_person_schema(person),
        stats=ProfileStatsSchema(
            votes_issued=len(issued),
            voted_personally=sum(1 for entry in issued if entry.how == "voted"),
            delegated=delegated,
            abstained=sum(1 for entry in issued if entry.how == "abstained"),
            delegation_rate=round(delegated / len(issued), 4) if issued else None,
            categories_handed_over=len(network.delegations_of(person)),
            delegators=len({d.delegator for d in received}),
            categories_received=len(received),
            votes_decided_for_others=sum(entry.votes_for_others for entry in entries),
            most_votes_held=most_held,
            largest_share=round(largest, 4),
        ),
        delegations=[
            ProfileDelegationSchema(
                category=network.categories[d.category].text, delegate=d.delegate
            )
            for d in network.delegations_of(person)
        ],
        received=[
            ProfileReceivedSchema(
                delegator=d.delegator, category=network.categories[d.category].text
            )
            for d in received
        ],
        history=entries,
        changes=_changes_for(person),
    )


def _changes_for(person: str) -> list[DelegationChangeSchema]:
    """
    The dated delegation changes a person made or was party to, most recent
    first: their own, and those that handed them a category or took one away.
    """
    scenario = _scenario()
    simulation = _simulation()
    categories = _network_on(0).categories
    everything = [*simulation.changes, *scenario.viewer_changes(VIEWER)]
    involved = [
        change
        for change in everything
        if person in (change.delegator, change.before, change.after)
    ]
    involved.sort(key=lambda change: (-change.day, change.delegator, change.category))
    return [
        DelegationChangeSchema(
            day=change.day,
            delegator=change.delegator,
            category=categories[change.category].text,
            before=change.before,
            after=change.after,
        )
        for change in involved
    ]


# ---------------------------------------------------------------------------
# GET /city
# ---------------------------------------------------------------------------

CITY_DECIDERS = 12


@lru_cache(maxsize=1)
def city_response() -> CityResponse:
    """
    Every closed question at a glance: turnout with and without delegation,
    how much of the vote was delegated and to how few, and whether the
    result changed. Read from the closed ballot papers only, so it never
    changes.
    """
    scenario = _scenario()
    questions: list[CityQuestionSchema] = []
    papers: list[CityPaperSchema] = []
    decided: dict[str, int] = {}
    held_on: dict[str, int] = {}
    share_of: dict[str, float] = {}

    for paper in scenario.closed_papers:
        rows: list[CityQuestionSchema] = []
        for resolved in _history()[paper.id]:
            resolution = resolved.resolution
            voters = len(resolved.voters)
            delegated, direct = resolved.delegated, resolved.direct
            cast = delegated.total_ballots - delegated.abstentions
            weights = resolution.weights()
            for person, weight in weights.items():
                others = weight - (1 if person in resolved.voters else 0)
                if others > 0:
                    decided[person] = decided.get(person, 0) + others
                    held_on[person] = held_on.get(person, 0) + 1
                    share_of[person] = max(share_of.get(person, 0.0), weight / voters)
            metrics = _metrics(resolution)
            yes = (
                delegated.vote_counts.get("yes", 0) / cast
                if resolved.measure.ballot_type == "single_choice" and cast
                else None
            )
            rows.append(
                CityQuestionSchema(
                    ballot_paper=paper.id,
                    paper_title=paper.title,
                    jurisdiction=paper.paper.jurisdiction,
                    closed_days_ago=-paper.closes_in_days,
                    question_id=resolved.question.id,
                    label=resolved.measure.label,
                    kind=resolved.measure.kind,
                    title=resolved.question.title,
                    ballot_type=resolved.measure.ballot_type,
                    voters=voters,
                    cast_delegated=cast,
                    cast_direct=direct.total_ballots - direct.abstentions,
                    delegated_share=metrics.delegated_share,
                    largest_share=metrics.largest_share,
                    largest_resolver=metrics.largest_resolver,
                    gini=metrics.gini,
                    winners=delegated.winners,
                    direct_winners=direct.winners,
                    winner_changed=winners_differ(direct, delegated),
                    support=round(yes, 4) if yes is not None else None,
                )
            )
        issued = sum(row.voters for row in rows)
        papers.append(
            CityPaperSchema(
                id=paper.id,
                title=paper.title,
                jurisdiction=paper.paper.jurisdiction,
                closed_days_ago=-paper.closes_in_days,
                questions=len(rows),
                turnout_delegated=round(sum(r.cast_delegated for r in rows) / issued, 4),
                turnout_direct=round(sum(r.cast_direct for r in rows) / issued, 4),
                delegated_share=round(
                    sum(r.delegated_share * r.voters for r in rows) / issued, 4
                ),
                largest_share=max(row.largest_share for row in rows),
                changed=sum(row.winner_changed for row in rows),
            )
        )
        questions = rows + questions  # most recent paper first

    issued = sum(row.voters for row in questions)
    heaviest = max(questions, key=lambda row: (row.largest_share, row.question_id))
    ranked = sorted(decided, key=lambda person: (-decided[person], person))
    return CityResponse(
        scenario=SCENARIO_SCHEMA,
        totals=CityTotalsSchema(
            questions=len(questions),
            changed=sum(row.winner_changed for row in questions),
            turnout_delegated=round(
                sum(row.cast_delegated for row in questions) / issued, 4
            ),
            turnout_direct=round(sum(row.cast_direct for row in questions) / issued, 4),
            delegated_share=round(
                sum(row.delegated_share * row.voters for row in questions) / issued, 4
            ),
            largest_share=heaviest.largest_share,
            largest_resolver=heaviest.largest_resolver,
        ),
        papers=papers,
        questions=questions,
        deciders=[
            CityDeciderSchema(
                person=person,
                votes_decided=decided[person],
                questions=held_on[person],
                largest_share=round(share_of[person], 4),
            )
            for person in ranked[:CITY_DECIDERS]
        ],
    )
