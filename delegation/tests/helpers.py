"""Shared builders for the delegation tests."""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass

from delegation import (
    Category,
    CategoryId,
    Delegation,
    DelegationLoopError,
    Network,
    Person,
    PersonId,
    add_delegation,
    create_category,
    create_network,
)

CITY = "city"
QUESTION = "q"


def cid(text: str) -> CategoryId:
    """The id of the category with this text."""
    return create_category(text).id


def network_of(
    residents: Iterable[PersonId],
    delegations: Iterable[tuple[PersonId, str, PersonId]] = (),
    *,
    outsiders: Iterable[PersonId] = (),
) -> Network:
    """
    Build a network from (delegator, category text, delegate) triples.

    Residents live in CITY; outsiders live nowhere. The creation checks are
    skipped, so loops of every kind can be built.
    """
    persons = [Person(person, frozenset({CITY})) for person in residents]
    persons += [Person(person) for person in outsiders]
    triples = list(delegations)
    categories = [create_category(text) for _, text, _ in triples]
    return create_network(
        persons,
        categories,
        [
            Delegation(delegator, create_category(text).id, delegate)
            for delegator, text, delegate in triples
        ],
    )


def scores(**by_text: float) -> dict[tuple[str, CategoryId], float]:
    """Judgments for QUESTION, keyed by category text with underscores."""
    return {
        (QUESTION, cid(text.replace("_", " "))): probability
        for text, probability in by_text.items()
    }


@dataclass(frozen=True)
class Scenario:
    """A seeded random network with one question's judgments."""

    network: Network
    categories: tuple[Category, ...]
    voters: tuple[PersonId, ...]
    judgments: dict[tuple[str, CategoryId], float]
    direct_voters: frozenset[PersonId]


# Scores that produce exact ties and sit exactly on the default threshold.
_COARSE_SCORES = (0.0, 0.2, 0.5, 0.7, 0.9, 1.0)


def random_scenario(seed: int, *, guarded: bool = False) -> Scenario:
    """
    Build a seeded random scenario.

    With `guarded=False` delegations are placed without the creation checks,
    so loops can occur. With `guarded=True` every delegation goes through
    add_delegation and the rejected ones are skipped.

    About two in five scenarios are dense: everyone delegates something,
    every category matches the question and nobody votes directly. Every
    chain in a dense scenario ends in a loop, which is what exercises the
    loop rule. The rest are sparse and mix every reason for keeping a vote.
    """
    rng = random.Random(seed)
    dense = rng.random() < 0.4
    count = rng.randint(2, 30)
    ids = [f"p{index:02d}" for index in range(count)]
    categories = tuple(
        create_category(f"topic {index}") for index in range(rng.randint(1, 6))
    )
    persons = [
        Person(person, frozenset({CITY}) if rng.random() < 0.8 else frozenset())
        for person in ids
    ]

    proposed: list[tuple[PersonId, Category, PersonId]] = []
    for person in ids:
        fewest = 1 if dense else 0
        held = rng.sample(categories, rng.randint(fewest, min(3, len(categories))))
        for category in held:
            delegate = rng.choice([other for other in ids if other != person])
            proposed.append((person, category, delegate))

    if guarded:
        network = create_network(persons, categories)
        for delegator, category, delegate in proposed:
            try:
                network = add_delegation(network, delegator, category, delegate)
            except DelegationLoopError:
                continue
    else:
        network = create_network(
            persons,
            categories,
            [
                Delegation(delegator, category.id, delegate)
                for delegator, category, delegate in proposed
            ],
        )

    judgments: dict[tuple[str, CategoryId], float] = {}
    for category in categories:
        if dense:
            judgments[(QUESTION, category.id)] = rng.uniform(0.7, 1.0)
            continue
        if rng.random() < 0.1:
            continue  # the router has no judgment for this category
        coarse = rng.random() < 0.5
        judgments[(QUESTION, category.id)] = (
            rng.choice(_COARSE_SCORES) if coarse else rng.random()
        )

    return Scenario(
        network=network,
        categories=categories,
        voters=tuple(person.id for person in persons if CITY in person.residences),
        judgments=judgments,
        direct_voters=frozenset(
            person for person in ids if not dense and rng.random() < 0.1
        ),
    )
