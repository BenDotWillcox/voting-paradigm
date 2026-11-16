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
from dataclasses import dataclass

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
from .choice import KEEP, Choice, ChoicePolicy, agreement, choose, pooled_agreements
from .population import (
    CANDIDATE_STREAM,
    ELECTION_STREAM,
    NO,
    NOT_CAST,
    YES,
    BoolArray,
    IntArray,
    Population,
    VoteArray,
    stream,
)

YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))
_CHOICE_ID: Mapping[int, CandidateId | None] = {YES: "yes", NO: "no", NOT_CAST: None}

FULL_TURNOUT = "full_turnout"
DIRECT = "direct"
REPRESENTATIVE = "representative"
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
    # The winning option of each question
    winners: tuple[CandidateId, ...]
    # How many delegations each voter maintains
    delegations: IntArray


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


def _counted_from(population: Population, resolver: IntArray, floor: float) -> VoteArray:
    """
    Each voter's counted ballot: their resolver's sincere ballot, if the
    resolver votes. A resolver holding anyone else's vote on a question
    votes at the larger of their own rate and `floor`.
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
    casts = questions.turnout_draw < rate
    own = np.where(casts, questions.sincere, NOT_CAST)
    return np.asarray(own[resolver, columns], dtype=np.int8)


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
        winners=_winners(population, counted),
        delegations=np.zeros(people, dtype=np.int64),
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
        winners=_winners(population, counted),
        delegations=np.zeros(people, dtype=np.int64),
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
    counted = _counted_from(population, resolver, turnout.office_rate)
    return Outcome(
        arrangement=REPRESENTATIVE,
        counted=counted,
        resolver=resolver,
        kept=np.zeros((people, questions), dtype=np.bool_),
        winners=_winners(population, counted),
        delegations=np.zeros(people, dtype=np.int64),
    )


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
) -> IntArray:
    """The resolver of every voter on every evaluation question."""
    people, questions = population.evaluation.sincere.shape
    resolver = np.empty((people, questions), dtype=np.int64)
    voters = population.ids
    for q, question in enumerate(population.evaluation.ids):
        # A voter who keeps the question decides it; whether they cast a
        # ballot is the shared turnout draw, read when ballots are counted.
        resolution = resolve_question(network, question, voters, judgments)
        for v, voter in enumerate(voters):
            resolver[v, q] = population.index_of(resolution.resolver_of(voter))
    return resolver


def _delegated_outcome(
    population: Population,
    arrangement: str,
    network: Network,
    judgments: Mapping[tuple[QuestionId, CategoryId], float],
    choice: Choice,
    turnout: TurnoutPolicy,
) -> Outcome:
    resolver = _resolve(population, network, judgments)
    counted = _counted_from(population, resolver, turnout.resolver_turnout)
    voters = np.arange(population.size, dtype=np.int64)[:, None]
    return Outcome(
        arrangement=arrangement,
        counted=counted,
        resolver=resolver,
        kept=np.asarray(resolver == voters, dtype=np.bool_),
        winners=_winners(population, counted),
        delegations=np.asarray(choice.held().sum(axis=1), dtype=np.int64),
    )


EVERYTHING = create_category("every question")


def population_categories(population: Population) -> list[Category]:
    """The delegation categories of a population, in index order."""
    return [create_category(name) for name in population.categories]


def choose_proxies(population: Population, policy: ChoicePolicy) -> Choice:
    """Each voter's proxy, chosen by agreement over every history question."""
    votes = population.history.own_votes
    return choose([agreement(votes, policy.credible_mass)], policy)


def choose_liquid(population: Population, policy: ChoicePolicy) -> Choice:
    """
    Each voter's delegate per category, by agreement on that category. With
    `policy.borrow_strength` (the default, amendment A3) each category's
    agreement borrows strength from the rest of the record.
    """
    votes = population.history.own_votes
    if policy.borrow_strength:
        pooled = pooled_agreements(
            votes,
            population.history.dimension,
            len(population.categories),
            policy.credible_mass,
        )
        return choose(pooled.agreements, policy)
    agreements = [
        agreement(votes[:, population.history.on_dimension(d)], policy.credible_mass)
        for d in range(len(population.categories))
    ]
    return choose(agreements, policy)


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
    network = delegation_network(population, choice, [EVERYTHING])
    judgments = {(q, EVERYTHING.id): 1.0 for q in population.evaluation.ids}
    return _delegated_outcome(population, PROXY, network, judgments, choice, turnout)


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
    categories = population_categories(population)
    network = delegation_network(population, choice, categories)
    judgments = {
        (question, category.id): 1.0 if population.evaluation.dimension[q] == d else 0.0
        for q, question in enumerate(population.evaluation.ids)
        for d, category in enumerate(categories)
    }
    return _delegated_outcome(population, LIQUID, network, judgments, choice, turnout)
