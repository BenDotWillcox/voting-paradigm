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
  - A sincere yes/no ballot for everyone but the viewer, from a
    one-dimensional spatial model: each person has a position, each question
    a direction and a cutpoint, and a little noise decides close calls.

Every delegation goes through graph.add_delegation, so the network has no
loop within an identical category. Loops that depend on the question can
still occur and are left for resolution.

Limits: this is a toy population. The behaviours, their shares and the
spatial model are assumptions chosen to exercise the machinery, and say
nothing about how real voters would delegate or vote.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from voting.ballots.single_choice import SingleChoiceBallot, create_single_choice_ballot
from voting.types import CandidateId

from .graph import DelegationLoopError, add_delegation
from .nesting import NestingPair, with_nesting
from .types import (
    Category,
    CategoryId,
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
    # People who delegate one category to the viewer, per district, when
    # viewer_inbound does not spell them out
    viewer_delegators_per_district: int = 2
    # Authored delegations to the viewer, as (district number, category
    # text). One resident of that district hands the viewer that category.
    viewer_inbound: tuple[tuple[int, str], ...] = ()
    # Standard deviation of the noise in a sincere vote
    vote_noise: float = 0.35


@dataclass(frozen=True)
class Simulation:
    """A synthetic network and what is needed to cast its sincere ballots."""

    config: SimulationConfig
    network: Network
    # Each person's position on the one dimension votes depend on
    positions: Mapping[PersonId, float]
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
) -> Simulation:
    """
    Build the seeded synthetic network.

    Args:
        categories: The pool people draw their categories from
        config: The population's parameters
        nesting: Which pool categories sit inside which

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
    positions = {person: rng.uniform(-1.0, 1.0) for person in everyone}

    rng = _stream(config, "experts")
    well_known = rng.sample(everyone, min(config.experts, len(everyone)))
    experts = {
        category.id: tuple(
            rng.sample(well_known, min(config.experts_per_category, len(well_known)))
        )
        for category in categories
    }

    nesting = frozenset(nesting)
    narrow = {inner for inner, _ in nesting}
    network = create_network(persons, categories)

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
                delegate(person, category, rng.choice(options))

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
                if member != VIEWER and network.delegate_for(member, named.id) is None
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

    return Simulation(
        config=config,
        network=with_nesting(network, nesting),
        positions=positions,
        behaviours=behaviours,
        experts=experts,
        names=names,
        usernames=usernames,
    )


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


def _lean(config: SimulationConfig, question: Question) -> tuple[int, float]:
    """Which side of the dimension a question's first option sits on, and where it divides."""
    rng = _stream(config, f"question:{question.id}")
    return rng.choice((-1, 1)), rng.uniform(-0.4, 0.4)


def sincere_choice(
    simulation: Simulation, person: PersonId, question: Question
) -> CandidateId:
    """
    The option a person would choose themself on a two-option question.

    Raises:
        ValueError: If the question does not have exactly two options, or
            the person has no position (the viewer does not)
    """
    if person not in simulation.positions:
        raise ValueError(f"{person!r} has no simulated position")
    return choice_at(simulation.config, simulation.positions[person], person, question)


def choice_at(
    config: SimulationConfig, position: float, person: PersonId, question: Question
) -> CandidateId:
    """
    The option someone at this position would choose on a two-option question.

    The viewer has no simulated position; a scenario that needs past votes
    for the viewer supplies one here.

    Raises:
        ValueError: If the question does not have exactly two options
    """
    if len(question.options) != 2:
        raise ValueError("Sincere ballots are defined for two-option questions")
    direction, cutpoint = _lean(config, question)
    noise = _stream(config, f"vote:{person}:{question.id}").gauss(
        0.0, config.vote_noise
    )
    favours_first = direction * (position - cutpoint) + noise > 0
    return question.options[0 if favours_first else 1].id


def sincere_ballots(
    simulation: Simulation, question: Question
) -> dict[PersonId, SingleChoiceBallot]:
    """Everyone's own ballot on a question, except the viewer, who has none."""
    return {
        person: create_single_choice_ballot(
            person, sincere_choice(simulation, person, question)
        )
        for person in simulation.positions
    }
