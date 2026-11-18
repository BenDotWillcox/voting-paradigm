"""
The arrangements: whose ballot counts for a voter on a question.

  Full turnout    the reference corner: everyone votes on every question
                  (fidelity 1, overhead 1)
  Direct          the voter's own ballot, on every question, cast at their
                  turnout rate
  Representative  the district's representative, elected by plurality, on
                  every question
  Personal proxy  one person the voter chose by overall agreement, on every
                  question (the step that separates dilution from bundling)
  Liquid          per category, a person the voter chose by agreement on
                  that category; the voter's own ballot on what they keep

Every arrangement is scored on the evaluation period and uses the same
turnout draws, so they differ only in whose ballot counts. A voter whose
counted ballot is empty (their resolver did not vote) abstains.

The proxy and liquid arrangements run on the package's own machinery: the
chosen delegations form a Network, each question is routed with exact
judgments (a question is about its own dimension with probability 1 and
about every other with 0), and graph.resolve_question follows the chains,
so transitive delegation and the loop rule apply exactly as in the account
app. Router error is a separate condition, not modelled here.

Representatives are honest: their platform is their true position, voters
pick the closest platform, and the elected representative casts their
sincere vote. Anyone deciding for others, representative or delegate, votes
at a floor rate set by a TurnoutPolicy (amendment A1): symmetric by default.
Deliberation, agenda-setting and compromise are not modelled.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from dataclasses import dataclass, replace

import numpy as np

from voting.ballots.single_choice import SingleChoiceBallot, create_single_choice_ballot
from voting.methods.plurality import resolve_plurality
from voting.types import Candidate, CandidateId, random_tiebreak

from ..graph import resolve_question
from ..types import (
    Category,
    CategoryId,
    Delegation,
    Network,
    Person,
    QuestionId,
    create_category,
    create_network,
)
from .choice import (
    KEEP,
    Agreement,
    Choice,
    ChoicePolicy,
    agreement,
    choose,
    pooled_agreements,
    tie_key,
    top_candidates,
)
from .population import (
    CANDIDATE_STREAM,
    ELECTION_STREAM,
    NO,
    NOT_CAST,
    YES,
    BoolArray,
    FloatArray,
    IntArray,
    Population,
    QuestionSet,
    VoteArray,
    stream,
)

YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))
_CHOICE_ID: Mapping[int, CandidateId | None] = {YES: "yes", NO: "no", NOT_CAST: None}

FULL_TURNOUT = "full_turnout"
DIRECT = "direct"
REPRESENTATIVE = "representative"
REPRESENTATIVE_BY_RECORD = "representative_by_record"
DISTRICT_CHOICE_VOTERS = "district_choice_voters"
DISTRICT_CHOICE = "district_choice"
PROXY = "proxy"
LIQUID = "liquid"


@dataclass(frozen=True, eq=False)
class Outcome:
    """
    What one arrangement did on the evaluation period.

    Arrays are indexed [voter, question].
    """

    arrangement: str
    # The ballot counted for each voter: YES, NO or NOT_CAST
    counted: VoteArray
    # The index of the person whose ballot counted
    resolver: IntArray
    # Whether the voter decided the question themself
    kept: BoolArray
    # [person, question]: whether the person actually cast a ballot: they
    # decide the question (for themself or for anyone holding through
    # them) and voted. Someone whose own vote and every follower's vote are
    # resolved elsewhere casts nothing. A resolver's attendance is read
    # from this, not from their own counted ballot, which someone else may
    # supply (third review; masked to deciders in the fourth, 2026-11-18)
    cast: BoolArray
    # The winning option of each question
    winners: tuple[CandidateId, ...]
    # How many delegations each voter maintains
    delegations: IntArray
    # Whether the voter delegated but decides for themself because their
    # chain loops back through them (the loop rule); all False where
    # nobody delegates onward
    looped: BoolArray
    # How many distinct loops each question's delegation graph has
    loops: IntArray


def _no_loops(people: int, questions: int) -> tuple[BoolArray, IntArray]:
    return np.zeros((people, questions), dtype=np.bool_), np.zeros(questions, dtype=np.int64)


def _seed(*parts: object) -> int:
    """A stable integer seed from labelled parts."""
    return zlib.crc32(":".join(str(part) for part in parts).encode())


def _winners(population: Population, counted: VoteArray) -> tuple[CandidateId, ...]:
    """Plurality over the counted ballots of each question, abstentions aside."""
    winners: list[CandidateId] = []
    for q, question in enumerate(population.evaluation.ids):
        ballots: list[SingleChoiceBallot] = [
            create_single_choice_ballot(voter, _CHOICE_ID[int(counted[v, q])])
            for v, voter in enumerate(population.ids)
        ]
        # One tiebreak seed per question, shared by every arrangement
        result = resolve_plurality(
            list(YES_NO),
            ballots,
            random_tiebreak(_seed(population.config.seed, "tally", question)),
        )
        winners.append(result.winners[0])
    return tuple(winners)


@dataclass(frozen=True)
class TurnoutPolicy:
    """
    How often people who decide for others vote (amendment A1).

    A person who resolves at least one other voter's vote on a question
    casts their ballot when their turnout draw for that question falls
    below the larger of their own turnout rate and a floor: `office_rate`
    for an elected representative, `resolver_turnout` for anyone holding
    delegated votes. Everyone else votes at their own rate. Draws are
    shared, so raising a floor only ever adds ballots.

    The primary condition is symmetric: both floors are the office-holder
    rate, 0.96, the share of roll calls on which members of the 118th House
    cast a yea or nay while serving (Voteview; scripts/voteview_house_rates.py).
    The 117th House reached 0.98 under its pandemic proxy-voting rule, itself
    a form of delegation, so it is not used. Setting `resolver_turnout` to 0
    gives the co-reported condition, delegates at ordinary turnout;
    `office_rate` 1 with `resolver_turnout` 0 reproduces the pilot.
    """

    office_rate: float = 0.96
    resolver_turnout: float = 0.96

    def __post_init__(self) -> None:
        for name in ("office_rate", "resolver_turnout"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


PRIMARY_TURNOUT = TurnoutPolicy()
ORDINARY_RESOLVER_TURNOUT = TurnoutPolicy(resolver_turnout=0.0)
PILOT_TURNOUT = TurnoutPolicy(office_rate=1.0, resolver_turnout=0.0)


def _counted_from(
    population: Population, resolver: IntArray, floor: float
) -> tuple[VoteArray, BoolArray]:
    """
    Each voter's counted ballot: their resolver's sincere ballot, if the
    resolver votes. A resolver holding anyone else's vote on a question
    votes at the larger of their own rate and `floor`. Also whether each
    person actually cast a ballot: only people who decide a question (they
    resolve their own vote or hold someone else's) can.
    """
    questions = population.evaluation
    people, count = questions.sincere.shape
    columns = np.arange(count)[None, :]
    voters = np.arange(people)[:, None]
    # Whether each person resolves at least one other voter's vote
    holds = np.zeros((people, count), dtype=np.bool_)
    others = resolver != voters
    holds[resolver[others], np.broadcast_to(columns, resolver.shape)[others]] = True
    rate = np.where(holds, np.maximum(population.turnout[:, None], floor), population.turnout[:, None])
    would_cast = questions.turnout_draw < rate
    own = np.where(would_cast, questions.sincere, NOT_CAST)
    decides = holds | (resolver == voters)
    casts = np.asarray(would_cast & decides, dtype=np.bool_)
    return np.asarray(own[resolver, columns], dtype=np.int8), casts


def full_turnout(population: Population) -> Outcome:
    """
    The reference corner: everyone decides and votes on every question.

    Fidelity is 1 and overhead is 1 by definition. Its winners are what the
    whole city would choose, which is the reference for outcome agreement.
    Real turnout falls short of this; the shortfall is direct voting's
    overhead showing up as abstention.
    """
    people, questions = population.evaluation.sincere.shape
    resolver = np.repeat(np.arange(people, dtype=np.int64)[:, None], questions, axis=1)
    counted = np.asarray(population.evaluation.sincere, dtype=np.int8)
    return Outcome(
        arrangement=FULL_TURNOUT,
        counted=counted,
        resolver=resolver,
        kept=np.ones((people, questions), dtype=np.bool_),
        cast=np.ones((people, questions), dtype=np.bool_),
        winners=_winners(population, counted),
        delegations=np.zeros(people, dtype=np.int64),
        looped=_no_loops(people, questions)[0],
        loops=_no_loops(people, questions)[1],
    )


def direct(population: Population) -> Outcome:
    """
    Everyone decides every question and votes with their turnout rate; a
    non-voter abstains and matches nothing.
    """
    people, questions = population.evaluation.sincere.shape
    resolver = np.repeat(np.arange(people, dtype=np.int64)[:, None], questions, axis=1)
    counted = population.evaluation.own_votes
    return Outcome(
        arrangement=DIRECT,
        counted=counted,
        resolver=resolver,
        kept=np.ones((people, questions), dtype=np.bool_),
        cast=np.asarray(population.evaluation.casts, dtype=np.bool_),
        winners=_winners(population, counted),
        delegations=np.zeros(people, dtype=np.int64),
        looped=_no_loops(people, questions)[0],
        loops=_no_loops(people, questions)[1],
    )


@dataclass(frozen=True, eq=False)
class Election:
    """One plurality election per district."""

    # Candidate indices per district, in the order drawn
    candidates: tuple[IntArray, ...]
    # The elected representative of each district
    elected: IntArray


def elect_representatives(population: Population) -> Election:
    """
    Elect each district's representative by plurality.

    Candidates are residents drawn at random; their platform is their true
    position. Each resident who turns out (a seeded draw against their
    turnout rate) votes for the closest platform by unweighted distance
    across every dimension. Ties are broken by a seeded tiebreak per
    district.
    """
    config = population.config
    pick = stream(config.seed, CANDIDATE_STREAM)
    turn_out = stream(config.seed, ELECTION_STREAM).random(population.size)
    candidates: list[IntArray] = []
    elected: list[int] = []
    for district in range(config.districts):
        residents = population.residents_of(district)
        drawn = np.asarray(
            pick.choice(residents, size=config.candidates_per_district, replace=False),
            dtype=np.int64,
        )
        candidates.append(drawn)
        platforms = population.positions[drawn]
        ballots: list[SingleChoiceBallot] = []
        for voter in residents:
            if turn_out[voter] >= population.turnout[voter]:
                continue
            distance = np.linalg.norm(platforms - population.positions[voter], axis=1)
            closest = drawn[int(np.argmin(distance))]
            ballots.append(
                create_single_choice_ballot(
                    population.ids[voter], population.ids[closest]
                )
            )
        result = resolve_plurality(
            [Candidate(population.ids[c], population.ids[c]) for c in drawn],
            ballots,
            random_tiebreak(_seed(config.seed, "election", district)),
        )
        elected.append(population.index_of(result.winners[0]))
    return Election(candidates=tuple(candidates), elected=np.asarray(elected, dtype=np.int64))


def representative(
    population: Population,
    election: Election | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
) -> Outcome:
    """
    Each voter's district representative decides every question, voting at
    the office-holder rate.

    Districts are the same size, so the winner over voters' counted ballots
    is the council majority.
    """
    election = election or elect_representatives(population)
    people, questions = population.evaluation.sincere.shape
    rep = election.elected[population.district]
    resolver = np.repeat(rep[:, None], questions, axis=1)
    counted, cast = _counted_from(population, resolver, turnout.office_rate)
    voters = np.arange(people, dtype=np.int64)[:, None]
    return Outcome(
        arrangement=REPRESENTATIVE,
        counted=counted,
        resolver=resolver,
        cast=cast,
        # The elected resident decides every question themself; everyone
        # else decides none (the same accounting as the delegated arms)
        kept=np.asarray(resolver == voters, dtype=np.bool_),
        winners=_winners(population, counted),
        delegations=np.zeros(people, dtype=np.int64),
        looped=_no_loops(people, questions)[0],
        loops=_no_loops(people, questions)[1],
    )


def population_tie_key(population: Population) -> FloatArray:
    """The seeded tie key every record-based choice in a city uses."""
    return tie_key(population.config.seed, population.size)


def record_preferences(population: Population, election: Election) -> IntArray:
    """
    Each resident's preferred candidate among their own district's
    candidates, judged the way delegates are: agreement over the whole
    history record, ranked by the lower bound of its credible interval, then
    the posterior mean, then the city's seeded tie key. A candidate prefers
    themself.
    """
    whole = agreement(population.history.own_votes)
    ties = population_tie_key(population)
    preferred = np.empty(population.size, dtype=np.int64)
    for district, drawn in enumerate(election.candidates):
        for voter in population.residents_of(district):
            if voter in drawn:
                preferred[voter] = voter
                continue
            order = np.lexsort(
                (drawn, ties[voter, drawn], -whole.mean[voter, drawn], -whole.lower[voter, drawn])
            )
            preferred[voter] = drawn[order[0]]
    return preferred


def _matched_outcome(
    population: Population,
    arrangement: str,
    resolver_of_voter: IntArray,
    floor: float,
    assigned: BoolArray,
) -> Outcome:
    """
    `assigned` marks the residents who maintain a personal assignment of
    their ballot; residents represented by an election winner maintain none.
    """
    people, questions = population.evaluation.sincere.shape
    resolver = np.repeat(resolver_of_voter[:, None], questions, axis=1)
    counted, cast = _counted_from(population, resolver, floor)
    voters = np.arange(people, dtype=np.int64)[:, None]
    looped, loops = _no_loops(people, questions)
    return Outcome(
        arrangement=arrangement,
        counted=counted,
        resolver=resolver,
        cast=cast,
        kept=np.asarray(resolver == voters, dtype=np.bool_),
        winners=_winners(population, counted),
        delegations=(assigned & (resolver_of_voter != np.arange(people))).astype(np.int64),
        looped=looped,
        loops=loops,
    )


def _record_election(
    population: Population, election: Election, preferred: IntArray
) -> tuple[IntArray, BoolArray]:
    """
    Plurality over record-based preferences among the residents who turn
    out (the election's turnout draws): each district's winner, and whether
    each resident voted.
    """
    config = population.config
    turn_out = stream(config.seed, ELECTION_STREAM).random(population.size)
    voted = np.asarray(turn_out < population.turnout, dtype=np.bool_)
    winner_of = np.empty(config.districts, dtype=np.int64)
    for district, drawn in enumerate(election.candidates):
        ballots = [
            create_single_choice_ballot(population.ids[v], population.ids[preferred[v]])
            for v in population.residents_of(district)
            if voted[v]
        ]
        result = resolve_plurality(
            [Candidate(population.ids[c], population.ids[c]) for c in drawn],
            ballots,
            # The same tie-break draw as the platform election, so the
            # paired "platform against record" contrast cannot differ only
            # because identical ballots met different tie-breaks
            random_tiebreak(_seed(config.seed, "election", district)),
        )
        winner_of[district] = population.index_of(result.winners[0])
    return winner_of, voted


def representative_by_record(
    population: Population,
    election: Election | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
) -> Outcome:
    """
    The matched representative (pre-freeze review): the same three
    candidates per district as the representative arm, but residents rank
    them by public record, as delegates are chosen, and plurality among
    those who turn out (the election's turnout draws) elects one, who
    decides for the whole district at the office-holder rate.

    Paired with `district_choice_voters`, which differs only in that the
    same voters need not share: the gap between the two is the cost of
    sharing one representative under matched candidates, records, turnout
    and participation. Constituents cast an election ballot and maintain no
    assignment, so delegations maintained are zero.
    """
    election = election or elect_representatives(population)
    preferred = record_preferences(population, election)
    winner_of, _ = _record_election(population, election, preferred)
    nobody = np.zeros(population.size, dtype=np.bool_)
    return _matched_outcome(
        population,
        REPRESENTATIVE_BY_RECORD,
        winner_of[population.district],
        turnout.office_rate,
        nobody,
    )


def district_choice_voters(
    population: Population,
    election: Election | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
) -> Outcome:
    """
    The residents who voted in the record election each assign their ballot
    to their own preferred one of the district's three candidates; those
    who did not vote are represented by that election's winner, as in
    `representative_by_record` (second review, 2026-11-18). Against
    `representative_by_record` only sharing changes; against
    `district_choice` only whether non-voters choose too.
    """
    election = election or elect_representatives(population)
    preferred = record_preferences(population, election)
    winner_of, voted = _record_election(population, election, preferred)
    resolver_of = np.where(voted, preferred, winner_of[population.district]).astype(np.int64)
    return _matched_outcome(
        population, DISTRICT_CHOICE_VOTERS, resolver_of, turnout.office_rate, voted
    )


def district_choice(
    population: Population,
    election: Election | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
) -> Outcome:
    """
    Every resident assigns their ballot to their own preferred one of their
    district's three candidates (by public record), who decide at the
    office-holder rate and do not delegate onward. Like the proxy and
    liquid, everyone chooses, whether or not they would vote in an election.
    """
    election = election or elect_representatives(population)
    preferred = record_preferences(population, election)
    everyone = np.ones(population.size, dtype=np.bool_)
    return _matched_outcome(population, DISTRICT_CHOICE, preferred, turnout.office_rate, everyone)


def _people(population: Population) -> list[Person]:
    return [
        Person(person, frozenset({population.district_names[population.district[i]]}))
        for i, person in enumerate(population.ids)
    ]


def delegation_network(
    population: Population, choice: Choice, categories: list[Category]
) -> Network:
    """The Network formed by a choice, one category per column."""
    if len(categories) != choice.categories:
        raise ValueError("one category per column of the choice is needed")
    delegations = [
        Delegation(population.ids[v], categories[k].id, population.ids[int(d)])
        for v in range(population.size)
        for k in range(choice.categories)
        if (d := choice.delegate[v, k]) != KEEP
    ]
    return create_network(_people(population), categories, delegations)


def _resolve(
    population: Population,
    network: Network,
    judgments: Mapping[tuple[QuestionId, CategoryId], float],
    questions: QuestionSet | None = None,
) -> IntArray:
    """The resolver of every voter on every question of a period (evaluation by default)."""
    questions = questions or population.evaluation
    people, count = questions.sincere.shape
    resolver = np.empty((people, count), dtype=np.int64)
    voters = population.ids
    for q, question in enumerate(questions.ids):
        # A voter who keeps the question decides it; whether they cast a
        # ballot is the shared turnout draw, read when ballots are counted.
        resolution = resolve_question(network, question, voters, judgments)
        for v, voter in enumerate(voters):
            resolver[v, q] = population.index_of(resolution.resolver_of(voter))
    return resolver


def resolve_functional(delegate_of: IntArray) -> IntArray:
    """The resolver of every person under the loop rule (see `resolve_with_loops`)."""
    return resolve_with_loops(delegate_of)[0]


def resolve_with_loops(delegate_of: IntArray) -> tuple[IntArray, BoolArray, int]:
    """
    The resolver of every person when each has at most one next hop
    (`delegate_of[p]`, KEEP for none), under the package's loop rule:
    everyone on a loop decides for themself, and anyone upstream of a loop
    resolves to the loop member their chain reaches first.

    With exact routing every question of one category has exactly this
    structure, so this gives the same resolvers as graph.resolve_question
    run on each question (tested against it), in a fraction of the time.

    Returns the resolvers, whether each person is on a loop (they delegated
    but decide for themself, which a voluntary keep looks like from the
    resolvers alone), and how many distinct loops there are.
    """
    people = delegate_of.shape[0]
    resolver = np.full(people, KEEP, dtype=np.int64)
    on_loop = np.zeros(people, dtype=np.bool_)
    loops = 0
    for start in range(people):
        if resolver[start] != KEEP:
            continue
        path: list[int] = []
        position: dict[int, int] = {}
        current = start
        while True:
            if resolver[current] != KEEP:
                end = int(resolver[current])
                for p in path:
                    resolver[p] = end
                break
            if current in position:
                entry = position[current]
                loops += 1
                for p in path[entry:]:
                    resolver[p] = p
                    on_loop[p] = True
                for p in path[:entry]:
                    resolver[p] = current
                break
            nxt = int(delegate_of[current])
            if nxt == KEEP:
                resolver[current] = current
                for p in path:
                    resolver[p] = current
                break
            position[current] = len(path)
            path.append(current)
            current = nxt
    return resolver, on_loop, loops


def _resolve_by_category(
    choice: Choice, category_of_question: IntArray
) -> tuple[IntArray, BoolArray, IntArray]:
    """
    Resolvers of every voter on every question under exact routing: one
    resolution per category, shared by all its questions. Also loop
    membership per voter and question, and the number of loops per question.
    """
    resolved = [resolve_with_loops(choice.delegate[:, k]) for k in range(choice.categories)]
    resolver = np.stack([r for r, _, _ in resolved], axis=1)
    on_loop = np.stack([m for _, m, _ in resolved], axis=1)
    loops = np.array([n for _, _, n in resolved], dtype=np.int64)
    return (
        np.asarray(resolver[:, category_of_question], dtype=np.int64),
        np.asarray(on_loop[:, category_of_question], dtype=np.bool_),
        np.asarray(loops[category_of_question], dtype=np.int64),
    )


def reference_resolvers(
    population: Population, choice: Choice, questions: QuestionSet, single_category: bool
) -> IntArray:
    """
    The same resolvers through the package's general machinery: the chosen
    delegations as a Network, routed with exact judgments and resolved
    question by question by graph.resolve_question. Slow; used to verify
    the fast path.
    """
    categories = [EVERYTHING] if single_category else population_categories(population)
    network = delegation_network(population, choice, categories)
    if single_category:
        judgments = {(q, EVERYTHING.id): 1.0 for q in questions.ids}
    else:
        judgments = _exact_judgments(questions, categories)
    people, count = questions.sincere.shape
    resolver = np.empty((people, count), dtype=np.int64)
    for q, question in enumerate(questions.ids):
        resolution = resolve_question(network, question, population.ids, judgments)
        for v, voter in enumerate(population.ids):
            resolver[v, q] = population.index_of(resolution.resolver_of(voter))
    return resolver


def _delegated_outcome(
    population: Population,
    arrangement: str,
    choice: Choice,
    category_of_question: IntArray,
    floor: float,
) -> Outcome:
    resolver, looped, loops = _resolve_by_category(choice, category_of_question)
    counted, cast = _counted_from(population, resolver, floor)
    voters = np.arange(population.size, dtype=np.int64)[:, None]
    return Outcome(
        arrangement=arrangement,
        counted=counted,
        resolver=resolver,
        cast=cast,
        kept=np.asarray(resolver == voters, dtype=np.bool_),
        winners=_winners(population, counted),
        delegations=np.asarray(choice.held().sum(axis=1), dtype=np.int64),
        looped=looped,
        loops=loops,
    )


EVERYTHING = create_category("every question")


def population_categories(population: Population) -> list[Category]:
    """The delegation categories of a population, in index order."""
    return [create_category(name) for name in population.categories]


def _proxy_agreements(population: Population, policy: ChoicePolicy) -> list[Agreement]:
    return [agreement(population.history.own_votes, policy.credible_mass)]


def _liquid_agreements(population: Population, policy: ChoicePolicy) -> list[Agreement]:
    votes = population.history.own_votes
    if policy.borrow_strength:
        return list(
            pooled_agreements(
                votes,
                population.history.dimension,
                len(population.categories),
                policy.credible_mass,
            ).agreements
        )
    return [
        agreement(votes[:, population.history.on_dimension(d)], policy.credible_mass)
        for d in range(len(population.categories))
    ]


def choose_proxies(population: Population, policy: ChoicePolicy) -> Choice:
    """Each voter's proxy, chosen by agreement over every history question."""
    return choose(_proxy_agreements(population, policy), policy, population_tie_key(population))


def choose_liquid(population: Population, policy: ChoicePolicy) -> Choice:
    """
    Each voter's delegate per category, by agreement on that category. With
    `policy.borrow_strength` (the default, amendment A3) each category's
    agreement borrows strength from the rest of the record.
    """
    return choose(_liquid_agreements(population, policy), policy, population_tie_key(population))


def proxy(
    population: Population,
    policy: ChoicePolicy | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
) -> Outcome:
    """
    Each voter's proxy decides every question; a voter with no acceptable
    proxy keeps everything. Proxies follow their own proxies.
    """
    policy = policy or ChoicePolicy()
    choice = choose_proxies(population, policy)
    everything = np.zeros(len(population.evaluation), dtype=np.int64)
    return _delegated_outcome(population, PROXY, choice, everything, turnout.resolver_turnout)


def liquid(
    population: Population,
    policy: ChoicePolicy | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
) -> Outcome:
    """
    Each voter's delegate for a question's category decides it; the voter
    decides the categories they keep. Delegates apply their own delegations.
    """
    policy = policy or ChoicePolicy()
    choice = choose_liquid(population, policy)
    return _delegated_outcome(
        population, LIQUID, choice, population.evaluation.dimension, turnout.resolver_turnout
    )


def _exact_judgments(
    questions: QuestionSet, categories: list[Category]
) -> dict[tuple[QuestionId, CategoryId], float]:
    """Exact routing: a question is about its own category and no other."""
    return {
        (question, category.id): 1.0 if questions.dimension[q] == d else 0.0
        for q, question in enumerate(questions.ids)
        for d, category in enumerate(categories)
    }


def history_overhead(population: Population, policy: ChoicePolicy) -> float:
    """
    Liquid's overhead on the history questions: the share of (voter,
    question) pairs a voter would decide themself if the delegations chosen
    under `policy` had applied to the history period. Uses no evaluation
    question.
    """
    choice = choose_liquid(population, policy)
    resolver, _, _ = _resolve_by_category(choice, population.history.dimension)
    voters = np.arange(population.size, dtype=np.int64)[:, None]
    return float((resolver == voters).mean())


@dataclass(frozen=True)
class AcceptanceChoice:
    """The acceptance level fixed by the overhead rule, and how it was found."""

    acceptance: float
    history_overhead: float
    max_overhead: float
    # False when no acceptance level reaches the bound; the level with the
    # lowest overhead is then used (research protocol, infeasible cities)
    feasible: bool
    # How many distinct acceptance levels were checked (all of them)
    levels_checked: int


def _overhead_rule(
    top: IntArray,
    best: FloatArray,
    shares: FloatArray,
    max_overhead: float,
) -> AcceptanceChoice:
    """
    Exhaustive search for the highest acceptance level whose overhead is at
    most `max_overhead`.

    A voter delegates category k exactly when their best lower bound there,
    best[v, k], reaches the acceptance level, so the delegations in k change
    only at the distinct values of best[:, k]. Every one of them is
    resolved, every candidate level in their union is scored as the
    share-weighted sum of each category's self-resolution rate, and the
    highest qualifying level is taken. Overhead need not fall steadily as
    acceptance falls: a stricter level can break a mutual pair that the
    loop rule would otherwise leave both deciding for themselves, so no
    early exit or bisection is used.
    """
    people, categories = best.shape
    voters = np.arange(people)
    steps: list[FloatArray] = []
    rates: list[FloatArray] = []
    for k in range(categories):
        values = np.unique(np.clip(best[np.isfinite(best[:, k]), k], 0.0, 1.0))
        rate = np.empty(values.size)
        for i, level in enumerate(values):
            delegate_of = np.where(best[:, k] >= level, top[:, k], KEEP)
            rate[i] = float((resolve_functional(delegate_of) == voters).mean())
        steps.append(values)
        rates.append(rate)
    # 0 and 1 are both admissible levels; 1 keeps everything (no lower
    # bound reaches it), the highest possible threshold
    levels = np.unique(np.concatenate([[0.0, 1.0], *steps]))

    def overhead_at(level: float) -> float:
        total = 0.0
        for k in range(categories):
            i = int(np.searchsorted(steps[k], level, side="left"))
            total += shares[k] * (rates[k][i] if i < steps[k].size else 1.0)
        return total

    overhead = np.array([overhead_at(float(level)) for level in levels])
    ok = np.flatnonzero(overhead <= max_overhead + 1e-12)
    if ok.size:
        i = int(ok[-1])
        return AcceptanceChoice(float(levels[i]), float(overhead[i]), max_overhead, True, levels.size)
    lowest = float(overhead.min())
    i = int(np.flatnonzero(overhead == lowest)[-1])
    return AcceptanceChoice(float(levels[i]), lowest, max_overhead, False, levels.size)


def acceptance_for_overhead(
    population: Population,
    base: ChoicePolicy | None = None,
    max_overhead: float = 0.10,
    arrangement: str = LIQUID,
) -> AcceptanceChoice:
    """
    The highest acceptance level whose overhead on the history questions is
    at most `max_overhead` (research protocol, "Fixing the liquid
    configuration without evaluation data"), for liquid or the proxy.
    Infeasible cities get the level with the lowest history overhead and
    are flagged.
    """
    base = base or ChoicePolicy()
    if base.max_categories is not None:
        raise ValueError("the overhead rule assumes no limit on categories")
    if not 0.0 <= max_overhead <= 1.0:
        raise ValueError("max_overhead must be in [0, 1]")
    if arrangement == LIQUID:
        agreements = _liquid_agreements(population, base)
        counts = np.bincount(population.history.dimension, minlength=len(population.categories))
    elif arrangement == PROXY:
        agreements = _proxy_agreements(population, base)
        counts = np.array([len(population.history)])
    else:
        raise ValueError("the overhead rule applies to liquid or the proxy")
    top, best = top_candidates(agreements, population_tie_key(population))
    shares = (counts / counts.sum()).astype(np.float64)
    return _overhead_rule(top, best, shares, max_overhead)


def liquid_at_overhead(
    population: Population,
    base: ChoicePolicy | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
    max_overhead: float = 0.10,
) -> tuple[Outcome, AcceptanceChoice]:
    """Liquid under the protocol's comparison condition: acceptance fixed by the overhead rule."""
    base = base or ChoicePolicy()
    fixed = acceptance_for_overhead(population, base, max_overhead, LIQUID)
    return liquid(population, replace(base, acceptance=fixed.acceptance), turnout), fixed


def proxy_at_overhead(
    population: Population,
    base: ChoicePolicy | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
    max_overhead: float = 0.10,
) -> tuple[Outcome, AcceptanceChoice]:
    """The proxy under the same overhead rule, so it is compared with liquid at matched overhead."""
    base = base or ChoicePolicy()
    fixed = acceptance_for_overhead(population, base, max_overhead, PROXY)
    return proxy(population, replace(base, acceptance=fixed.acceptance), turnout), fixed
