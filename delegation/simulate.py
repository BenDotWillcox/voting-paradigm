"""
A seeded synthetic network and its sincere ballots.

The demo needs people to delegate to, people who delegate, and ballots to
count. This module makes them up, reproducibly:

  - One city split into districts, plus some people who live outside it.
    Outsiders originate no votes on city ballots but can be delegates.
  - Three delegation behaviours. Some people keep every decision. Some hand
    a few categories to a well-known person for that category, which is
    what concentrates votes. Some hand a few categories to someone in their
    own district.
  - One viewer, a resident with no delegations of their own, and a handful
    of people who delegate to the viewer, including from another district.
  - A made-up name and a unique username for everyone, so the demo can show
    people the way an account would.
  - A home inside their district for every resident, as a point in the
    unit square, so a measure with a site can matter more to people nearby.
  - A past: some delegations were made, or moved to someone else, on a day
    before today. network_on gives the network as it stood on any day.
  - A sincere ballot for everyone but the viewer, from a small spatial
    model: each person has a position on a few issue dimensions, each option
    an appeal and a lean along them, and a little noise decides close calls.
    The same utilities give a single choice, a ranking or a set of approvals.
  - Turnout. Not everyone votes on everything: each person has a chance of
    casting their own ballot, high for people others delegate to.

Every delegation goes through graph.add_delegation, so the network has no
loop within an identical category, today or on any earlier day. Loops that
depend on the question can still occur and are left for resolution.

Limits: this is a toy population. The behaviours, their shares, the spatial
model and the turnout are assumptions chosen to exercise the machinery, and
say nothing about how real voters would delegate or vote.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from voting.ballots.single_choice import SingleChoiceBallot, create_single_choice_ballot
from voting.types import CandidateId

from .graph import DelegationLoopError, add_delegation
from .nesting import NestingPair, with_nesting
from .types import (
    Category,
    CategoryId,
    Delegation,
    InvalidNetworkError,
    JurisdictionId,
    Network,
    Person,
    PersonId,
    Question,
    create_network,
    normalize_category_text,
)

VIEWER: PersonId = "you"
CITY: JurisdictionId = "city"

DIRECT = "keeps every decision"
TRUSTS_EXPERTS = "trusts well-known people"
TRUSTS_NEIGHBOURS = "trusts neighbours"
BEHAVIOURS = (DIRECT, TRUSTS_EXPERTS, TRUSTS_NEIGHBOURS)

VIEWER_NAME = "You"
VIEWER_USERNAME = "you"

# Invented names. Any resemblance to a real person is a coincidence.
FIRST_NAMES = (
    "Amara",
    "Ben",
    "Carmen",
    "Dmitri",
    "Elena",
    "Farid",
    "Grace",
    "Hiro",
    "Imani",
    "Jonas",
    "Keiko",
    "Luis",
    "Maya",
    "Nikhil",
    "Olga",
    "Pablo",
    "Quinn",
    "Rosa",
    "Samir",
    "Tessa",
    "Uma",
    "Viktor",
    "Wanjiru",
    "Xavier",
    "Yara",
    "Zane",
    "Aiden",
    "Bianca",
    "Chidi",
    "Daria",
    "Emeka",
    "Fiona",
    "Gustavo",
    "Hana",
    "Ivan",
    "Jia",
    "Kofi",
    "Leila",
    "Marco",
    "Nadia",
    "Omar",
    "Priya",
    "Rafael",
    "Sofia",
    "Tariq",
    "Ula",
    "Vera",
    "Wei",
)
LAST_NAMES = (
    "Abara",
    "Bergstrom",
    "Castillo",
    "Dang",
    "Eze",
    "Fontaine",
    "Guerrero",
    "Haddad",
    "Ito",
    "Jovanovic",
    "Kowalski",
    "Lindqvist",
    "Mbeki",
    "Nakamura",
    "Okafor",
    "Petrov",
    "Quispe",
    "Rahman",
    "Santos",
    "Tanaka",
    "Uribe",
    "Vasquez",
    "Whitfield",
    "Xu",
    "Yilmaz",
    "Zielinski",
    "Alvarez",
    "Banerjee",
    "Cohen",
    "Diallo",
    "Eriksen",
    "Farouk",
    "Greene",
    "Hosseini",
    "Iyer",
    "Jensen",
    "Kimura",
    "Laurent",
    "Moreau",
    "Novak",
    "Osei",
    "Park",
    "Romero",
    "Silva",
    "Thackeray",
    "Underhill",
    "Volkov",
    "Wright",
)


@dataclass(frozen=True)
class SimulationConfig:
    """The synthetic population's fixed parameters."""

    seed: int = 20261111
    districts: int = 3
    residents_per_district: int = 80
    outsiders: int = 20
    # Well-known people, and how many of them each category has
    experts: int = 8
    experts_per_category: int = 2
    # Shares of people who keep every decision and who trust well-known
    # people; the rest trust neighbours
    share_direct: float = 0.30
    share_trusting_experts: float = 0.45
    # How many categories a delegating person hands over
    min_categories: int = 3
    max_categories: int = 7
    # How much likelier a person is to pick a broad category than a narrow one
    broad_weight: float = 3.0
    # The chance that a person writes a category in one of its other
    # wordings, when the pool has any for it
    share_reworded: float = 0.4
    # People who delegate one category to the viewer, per district, when
    # viewer_inbound does not spell them out
    viewer_delegators_per_district: int = 2
    # Authored delegations to the viewer, as (district number, category
    # text). One resident of that district hands the viewer that category.
    viewer_inbound: tuple[tuple[int, str], ...] = ()
    # Standard deviation of the noise in a sincere vote
    vote_noise: float = 0.35
    # Issue dimensions a person's position has
    dimensions: int = 3
    # Where each district's residents sit on those dimensions on average, by
    # district number from 1; a missing district, and everyone outside the
    # city, averages zero
    district_leans: tuple[tuple[float, ...], ...] = ()
    # Standard deviation of a person's position around their district's
    position_spread: float = 0.5
    # Each district's part of the unit square, as (x0, y0, x1, y1), by
    # district number from 1. Left empty, the districts are equal strips.
    district_areas: tuple[tuple[float, float, float, float], ...] = ()
    # How far a site's pull reaches: it falls to about a third at this distance
    site_reach: float = 0.25
    # The chance that an ordinary person casts their own ballot on a question
    # of ordinary salience, drawn per person from this range
    min_turnout: float = 0.25
    max_turnout: float = 0.75
    # The same chance for well-known people and for anyone at least
    # trusted_by other people delegate to
    delegate_turnout: float = 0.96
    trusted_by: int = 3
    # The share of delegations that were made or moved after the earliest
    # day, and the range of days, counted from today, on which they were
    share_changed: float = 0.18
    earliest_change: int = -335
    latest_change: int = -8


@dataclass(frozen=True)
class DelegationChange:
    """
    One dated change to who a person hands a category to.

    Days count from today, so a change in the past has a negative day. A
    delegation made on that day has no `before`; one that moved has both; one
    that was withdrawn has no `after`.
    """

    day: int
    delegator: PersonId
    category: CategoryId
    before: PersonId | None
    after: PersonId | None


@dataclass(frozen=True)
class OptionSupport:
    """What draws people to one option of a measure."""

    # Its pull on everyone alike
    appeal: float = 0.0
    # Its pull along each issue dimension; missing dimensions count as zero
    lean: tuple[float, ...] = ()
    # Where it would be built, if anywhere, and its pull on people living
    # next to it (negative when neighbours tend to object)
    site: tuple[float, float] | None = None
    local: float = 0.0


@dataclass(frozen=True)
class Support:
    """How a measure divides people: one entry per option, by option id."""

    options: Mapping[CandidateId, OptionSupport] = field(default_factory=dict)
    # Scales everyone's chance of voting on it themself
    salience: float = 1.0


@dataclass(frozen=True)
class Simulation:
    """A synthetic network and what is needed to cast its sincere ballots."""

    config: SimulationConfig
    network: Network
    # Each person's position on the issue dimensions votes depend on
    positions: Mapping[PersonId, tuple[float, ...]]
    # Each resident's home in the unit square, the viewer's included
    homes: Mapping[PersonId, tuple[float, float]]
    # Each person's chance of casting their own ballot
    turnout: Mapping[PersonId, float]
    # Dated changes that led to today's network, most recent first
    changes: tuple[DelegationChange, ...]
    behaviours: Mapping[PersonId, str]
    # The well-known people for each category
    experts: Mapping[CategoryId, tuple[PersonId, ...]]
    # Everyone's display name and unique username, the viewer's included
    names: Mapping[PersonId, str]
    usernames: Mapping[PersonId, str]


def district_id(number: int) -> JurisdictionId:
    """The jurisdiction id of a district, numbered from 1."""
    return f"district-{number}"


def jurisdictions(config: SimulationConfig) -> tuple[JurisdictionId, ...]:
    """The city and its districts."""
    return (CITY,) + tuple(district_id(n) for n in range(1, config.districts + 1))


def _stream(config: SimulationConfig, purpose: str) -> random.Random:
    """An independent random stream, so one part can change without moving the others."""
    return random.Random(f"{config.seed}:{purpose}")


def simulate_network(
    categories: Sequence[Category],
    config: SimulationConfig = SimulationConfig(),
    nesting: Iterable[NestingPair] = (),
    wordings: Mapping[CategoryId, Sequence[Category]] | None = None,
) -> Simulation:
    """
    Build the seeded synthetic network.

    Args:
        categories: The pool people draw their categories from
        config: The population's parameters
        nesting: Which categories sit inside which, other wordings included
        wordings: Other ways people write a pool category, by its id.
            Each is a category of its own: a person who would hand over
            the pool category sometimes writes one of these instead.

    Raises:
        ValueError: If there are no categories or the shares exceed one
    """
    if not categories:
        raise ValueError("The simulation needs at least one category")
    if config.share_direct + config.share_trusting_experts > 1:
        raise ValueError("The behaviour shares add up to more than one")

    residents: dict[JurisdictionId, list[PersonId]] = {}
    persons: list[Person] = []
    for number in range(1, config.districts + 1):
        district = district_id(number)
        members = [
            f"d{number}-{index:03d}" for index in range(config.residents_per_district)
        ]
        if number == 1:
            members.append(VIEWER)
        residents[district] = members
        persons += [Person(member, frozenset({CITY, district})) for member in members]
    outsiders = [f"out-{index:02d}" for index in range(config.outsiders)]
    persons += [Person(outsider) for outsider in outsiders]

    everyone = [person.id for person in persons if person.id != VIEWER]
    home = {
        member: district
        for district, members in residents.items()
        for member in members
    }

    rng = _stream(config, "positions")
    positions = {
        person: tuple(
            max(-1.0, min(1.0, rng.gauss(mean, config.position_spread)))
            for mean in _district_lean(config, home.get(person))
        )
        for person in everyone
    }

    rng = _stream(config, "homes")
    homes: dict[PersonId, tuple[float, float]] = {}
    for district, members in residents.items():
        x0, y0, x1, y1 = _district_area(config, district)
        for member in members:
            homes[member] = (
                round(rng.uniform(x0, x1), 4),
                round(rng.uniform(y0, y1), 4),
            )

    rng = _stream(config, "experts")
    well_known = rng.sample(everyone, min(config.experts, len(everyone)))
    experts = {
        category.id: tuple(
            rng.sample(well_known, min(config.experts_per_category, len(well_known)))
        )
        for category in categories
    }
    wordings = wordings or {}
    other_wordings = [
        wording for category in categories for wording in wordings.get(category.id, ())
    ]
    # Whoever is well known for a category is well known for it however
    # it is written
    for category in categories:
        for wording in wordings.get(category.id, ()):
            experts[wording.id] = experts[category.id]

    def worded(person: PersonId, category: Category) -> Category:
        """The wording this person uses for a pool category."""
        options = wordings.get(category.id, ())
        if not options:
            return category
        # Drawn per person and category, so it moves no other draw
        draw = random.Random(f"{config.seed}:wording:{person}:{category.id}")
        if draw.random() >= config.share_reworded:
            return category
        return draw.choice(list(options))

    nesting = frozenset(nesting)
    # Narrow within the pool: another wording that happens to be broader does
    # not make a pool category less likely to be picked
    in_pool = {category.id for category in categories}
    narrow = {
        inner for inner, outer in nesting if inner in in_pool and outer in in_pool
    }
    network = create_network(persons, [*categories, *other_wordings])

    def delegate(delegator: PersonId, category: Category, chosen: PersonId) -> None:
        nonlocal network
        try:
            network = add_delegation(network, delegator, category, chosen)
        except DelegationLoopError:
            pass  # the creation check refused it; the person keeps that category
        except InvalidNetworkError:
            pass  # they already delegate this category

    rng = _stream(config, "behaviours")
    behaviours: dict[PersonId, str] = {}
    for person in everyone:
        draw = rng.random()
        if draw < config.share_direct:
            behaviours[person] = DIRECT
            continue
        trusts_experts = draw < config.share_direct + config.share_trusting_experts
        behaviours[person] = TRUSTS_EXPERTS if trusts_experts else TRUSTS_NEIGHBOURS
        for category in _pick_categories(rng, categories, narrow, config):
            if trusts_experts:
                options = [
                    expert for expert in experts[category.id] if expert != person
                ]
            else:
                around = residents[home[person]] if person in home else outsiders
                options = [other for other in around if other not in (person, VIEWER)]
            if options:
                delegate(person, worded(person, category), rng.choice(options))

    # A few people hand one category to the viewer, so the viewer answers for
    # others, including on ballots issued to districts the viewer is not in.
    rng = _stream(config, "viewer")
    if config.viewer_inbound:
        by_text = {normalize_category_text(c.text): c for c in categories}
        for number, text in config.viewer_inbound:
            named = by_text.get(normalize_category_text(text))
            if named is None:
                continue  # not a pool category; nothing to hand over
            free = [
                member
                for member in residents.get(district_id(number), [])
                if member != VIEWER
                # Nobody hands over the same thing twice in two wordings
                and all(
                    network.delegate_for(member, written.id) is None
                    for written in (named, *wordings.get(named.id, ()))
                )
            ]
            if free:
                delegate(rng.choice(free), named, VIEWER)
    else:
        for members in residents.values():
            candidates = [member for member in members if member != VIEWER]
            count = min(config.viewer_delegators_per_district, len(candidates))
            for person in rng.sample(candidates, count):
                unheld = [
                    category
                    for category in categories
                    if network.delegate_for(person, category.id) is None
                ]
                if unheld:
                    delegate(person, rng.choice(unheld), VIEWER)

    names, usernames = _personas(config, everyone)

    delegators: dict[PersonId, set[PersonId]] = {}
    for delegation in network.delegations:
        delegators.setdefault(delegation.delegate, set()).add(delegation.delegator)
    trusted = {
        person
        for person, others in delegators.items()
        if len(others) >= config.trusted_by
    }
    rng = _stream(config, "turnout")
    turnout = {
        person: (
            config.delegate_turnout
            if person in trusted or person in well_known
            else rng.uniform(config.min_turnout, config.max_turnout)
        )
        for person in everyone
    }

    def alternatives(delegation: Delegation) -> list[PersonId]:
        """Who else this person might have handed the category to before."""
        person = delegation.delegator
        if behaviours[person] == TRUSTS_EXPERTS:
            pool = list(experts[delegation.category])
        else:
            pool = residents[home[person]] if person in home else outsiders
        return [
            other
            for other in pool
            if other not in (person, VIEWER, delegation.delegate)
        ]

    network = with_nesting(network, nesting)
    return Simulation(
        config=config,
        network=network,
        positions=positions,
        homes=homes,
        turnout=turnout,
        changes=_changes(config, network, alternatives),
        behaviours=behaviours,
        experts=experts,
        names=names,
        usernames=usernames,
    )


def _district_lean(
    config: SimulationConfig, district: JurisdictionId | None
) -> tuple[float, ...]:
    """The average position of a district's residents, zero where none is given."""
    lean: tuple[float, ...] = ()
    if district is not None:
        number = int(district.rsplit("-", 1)[1])
        if number <= len(config.district_leans):
            lean = config.district_leans[number - 1]
    return tuple(
        lean[index] if index < len(lean) else 0.0 for index in range(config.dimensions)
    )


def district_area(
    config: SimulationConfig, district: JurisdictionId
) -> tuple[float, float, float, float]:
    """A district's part of the unit square, as (x0, y0, x1, y1)."""
    return _district_area(config, district)


def _district_area(
    config: SimulationConfig, district: JurisdictionId
) -> tuple[float, float, float, float]:
    """A district's part of the unit square: as configured, or an equal strip."""
    number = int(district.rsplit("-", 1)[1])
    if number <= len(config.district_areas):
        return config.district_areas[number - 1]
    width = 1.0 / config.districts
    return ((number - 1) * width, 0.0, number * width, 1.0)


def _replaced(
    network: Network,
    delegator: PersonId,
    category: CategoryId,
    delegate: PersonId | None,
) -> Network:
    """
    The network with one person's category handed to someone else, or to
    nobody, keeping its place in their category list.

    Raises:
        DelegationLoopError: If the other delegate would close a loop
    """
    kept = tuple(
        d
        for d in network.delegations
        if (d.delegator, d.category) != (delegator, category)
    )
    without = create_network(
        network.persons.values(), network.categories.values(), kept, network.nesting
    )
    if delegate is None:
        return without
    # The loop check only; the delegation then goes back where it was.
    add_delegation(without, delegator, network.categories[category], delegate)
    placed = tuple(
        (
            Delegation(delegator, category, delegate)
            if (d.delegator, d.category) == (delegator, category)
            else d
        )
        for d in network.delegations
    )
    if len(placed) == len(kept):
        placed = kept + (Delegation(delegator, category, delegate),)
    return create_network(
        network.persons.values(), network.categories.values(), placed, network.nesting
    )


def _latest_first(changes: Iterable[DelegationChange]) -> list[DelegationChange]:
    return sorted(
        changes, key=lambda change: (-change.day, change.delegator, change.category)
    )


def _changes(
    config: SimulationConfig,
    network: Network,
    alternatives: Callable[[Delegation], list[PersonId]],
) -> tuple[DelegationChange, ...]:
    """
    The dated changes behind today's network, most recent first.

    Some delegations were made after the earliest day, and some were moved
    from another person. A move is kept only if the network before it had no
    loop within the category, so every day's network obeys the creation rule.
    """
    rng = _stream(config, "changes")
    drafted: list[DelegationChange] = []
    for delegation in network.delegations:
        if rng.random() >= config.share_changed:
            continue
        day = rng.randint(config.earliest_change, config.latest_change)
        options = alternatives(delegation)
        before = rng.choice(options) if options and rng.random() < 0.45 else None
        drafted.append(
            DelegationChange(
                day,
                delegation.delegator,
                delegation.category,
                before,
                delegation.delegate,
            )
        )

    kept: list[DelegationChange] = []
    earlier = network
    for change in _latest_first(drafted):
        try:
            earlier = _replaced(
                earlier, change.delegator, change.category, change.before
            )
        except DelegationLoopError:
            continue  # that earlier delegate would have closed a loop
        kept.append(change)
    return tuple(kept)


def network_on(
    network: Network, changes: Iterable[DelegationChange], day: int
) -> Network:
    """
    The network as it stood at the end of a day.

    Args:
        network: Today's network
        changes: The dated changes that led to it
        day: Days from today; changes made after this day are undone

    Raises:
        DelegationLoopError: If undoing a change closes a loop within a
            category, which a set of changes built by this module never does
    """
    earlier = network
    for change in _latest_first(changes):
        if change.day > day:
            earlier = _replaced(
                earlier, change.delegator, change.category, change.before
            )
    return earlier


def _personas(
    config: SimulationConfig, everyone: Sequence[PersonId]
) -> tuple[dict[PersonId, str], dict[PersonId, str]]:
    """
    A name and a unique username for each person, and the viewer's.

    Names may repeat, as they do among real people; usernames may not. A
    username is the name in lower case, with a number added when taken.
    """
    rng = _stream(config, "personas")
    names: dict[PersonId, str] = {VIEWER: VIEWER_NAME}
    usernames: dict[PersonId, str] = {VIEWER: VIEWER_USERNAME}
    taken = {VIEWER_USERNAME}
    for person in everyone:
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        names[person] = f"{first} {last}"
        base = f"{first}.{last}".lower()
        username, number = base, 1
        while username in taken:
            number += 1
            username = f"{base}{number}"
        taken.add(username)
        usernames[person] = username
    return names, usernames


def _pick_categories(
    rng: random.Random,
    categories: Sequence[Category],
    narrow: set[CategoryId],
    config: SimulationConfig,
) -> list[Category]:
    """
    The categories one delegating person hands over.

    Drawn without repeats, with broad categories likelier than the narrow
    ones that sit inside another category.
    """
    count = rng.randint(
        min(config.min_categories, len(categories)),
        min(config.max_categories, len(categories)),
    )
    remaining = list(categories)
    picked: list[Category] = []
    while remaining and len(picked) < count:
        weights = [
            1.0 if category.id in narrow else config.broad_weight
            for category in remaining
        ]
        choice = rng.choices(range(len(remaining)), weights=weights)[0]
        picked.append(remaining.pop(choice))
    return picked


def default_support(config: SimulationConfig, question: Question) -> Support:
    """
    A seeded stand-in for a question nobody authored support for.

    The first option leans one way along the first dimension, from a seeded
    starting point; the others are neutral.
    """
    rng = _stream(config, f"question:{question.id}")
    direction, cutpoint = rng.choice((-1, 1)), rng.uniform(-0.4, 0.4)
    first = OptionSupport(appeal=-direction * cutpoint, lean=(float(direction),))
    return Support({question.options[0].id: first})


def option_utilities(
    config: SimulationConfig,
    position: Sequence[float],
    home: tuple[float, float] | None,
    person: PersonId,
    question: Question,
    support: Support | None = None,
) -> dict[CandidateId, float]:
    """
    How much someone at this position and home wants each option.

    An option's utility is its appeal, plus its lean along the person's
    position, plus its pull on people who live near its site, plus noise
    drawn once per person, question and option.
    """
    support = support if support is not None else default_support(config, question)
    utilities: dict[CandidateId, float] = {}
    for option in question.options:
        drawn = support.options.get(option.id, OptionSupport())
        value = drawn.appeal + sum(
            weight * coordinate for weight, coordinate in zip(drawn.lean, position)
        )
        if drawn.site is not None and home is not None and drawn.local:
            distance = math.dist(home, drawn.site)
            value += drawn.local * math.exp(-distance / config.site_reach)
        noise = _stream(config, f"vote:{person}:{question.id}:{option.id}").gauss(
            0.0, config.vote_noise
        )
        utilities[option.id] = value + noise
    return utilities


def person_utilities(
    simulation: Simulation,
    person: PersonId,
    question: Question,
    support: Support | None = None,
) -> dict[CandidateId, float]:
    """
    How much a simulated person wants each option.

    Raises:
        ValueError: If the person has no position (the viewer does not)
    """
    if person not in simulation.positions:
        raise ValueError(f"{person!r} has no simulated position")
    return option_utilities(
        simulation.config,
        simulation.positions[person],
        simulation.homes.get(person),
        person,
        question,
        support,
    )


def favourite(
    utilities: Mapping[CandidateId, float], question: Question
) -> CandidateId:
    """The option with the highest utility; the earlier option wins a tie."""
    return max(question.options, key=lambda option: utilities[option.id]).id


def sincere_choice(
    simulation: Simulation,
    person: PersonId,
    question: Question,
    support: Support | None = None,
) -> CandidateId:
    """
    The option a person would choose themself.

    Raises:
        ValueError: If the person has no position (the viewer does not)
    """
    return favourite(person_utilities(simulation, person, question, support), question)


def sincere_ballots(
    simulation: Simulation, question: Question, support: Support | None = None
) -> dict[PersonId, SingleChoiceBallot]:
    """Everyone's own single-choice ballot, except the viewer, who has none."""
    return {
        person: create_single_choice_ballot(
            person, sincere_choice(simulation, person, question, support)
        )
        for person in simulation.positions
    }


def casts(
    simulation: Simulation, person: PersonId, question: Question, salience: float = 1.0
) -> bool:
    """
    Whether a person casts their own ballot on a question.

    One seeded draw per person and question, against the person's turnout
    scaled by how salient the question is. The viewer has no turnout and
    never casts here; their votes are supplied from outside.
    """
    chance = simulation.turnout.get(person)
    if chance is None:
        return False
    draw = _stream(simulation.config, f"turnout:{person}:{question.id}").random()
    return draw < min(1.0, chance * salience)


def cast_day(
    simulation: Simulation, person: PersonId, paper_id: str, opens: int, closes: int
) -> int:
    """
    The day a person fills in a ballot paper, between its opening and closing
    days, both counted from today. People fill in a whole paper at once.
    """
    rng = _stream(simulation.config, f"cast-day:{person}:{paper_id}")
    return rng.randint(min(opens, closes), closes)
