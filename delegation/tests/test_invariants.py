"""
The resolution invariants from prompts/demo-5-liquid-democracy.md, checked
over seeded random networks.

The networks are built without the creation checks unless a test says
otherwise, so loops of every kind occur. The last test in this module
confirms the seeds really do exercise loops, long chains, outside resolvers
and every reason for keeping a vote.
"""

from __future__ import annotations

import random

import pytest

from delegation import (
    Delegation,
    KeepReason,
    Person,
    PersonId,
    QuestionResolution,
    create_network,
    resolve_question,
)

from .helpers import QUESTION, Scenario, random_scenario

SEEDS = range(300)


def resolve(scenario: Scenario) -> QuestionResolution:
    return resolve_question(
        scenario.network,
        QUESTION,
        scenario.voters,
        scenario.judgments,
        direct_voters=scenario.direct_voters,
    )


def raw_reach(resolution: QuestionResolution, start: PersonId) -> set[PersonId]:
    """Everyone a vote would visit following routing decisions alone."""
    reached: set[PersonId] = set()
    current: PersonId | None = start
    while current is not None and current not in reached:
        reached.add(current)
        current = resolution.decisions[current].delegate
    return reached


@pytest.mark.parametrize("seed", SEEDS)
def test_every_voter_has_exactly_one_resolver(seed: int) -> None:
    scenario = random_scenario(seed)
    resolution = resolve(scenario)

    assert set(resolution.traces) == set(scenario.voters)
    for voter, trace in resolution.traces.items():
        assert trace.voter == voter
        assert trace.resolver in scenario.network.persons


@pytest.mark.parametrize("seed", SEEDS)
def test_a_resolver_keeps_the_decision(seed: int) -> None:
    resolution = resolve(random_scenario(seed))
    on_a_loop = {member for loop in resolution.loops for member in loop}

    for resolver in set(resolution.weights()):
        assert resolution.decisions[resolver].kept or resolver in on_a_loop
        if resolver in resolution.traces:
            assert resolution.resolver_of(resolver) == resolver


@pytest.mark.parametrize("seed", SEEDS)
def test_weight_is_conserved(seed: int) -> None:
    scenario = random_scenario(seed)
    resolution = resolve(scenario)
    assert sum(resolution.weights().values()) == len(scenario.voters)


@pytest.mark.parametrize("seed", SEEDS)
def test_chains_are_simple_paths_along_routing_decisions(seed: int) -> None:
    scenario = random_scenario(seed)
    resolution = resolve(scenario)

    for voter, trace in resolution.traces.items():
        assert trace.chain[0] == voter
        assert trace.chain[-1] == trace.resolver
        assert len(set(trace.chain)) == len(trace.chain)
        assert len(trace.chain) <= len(scenario.network.persons)
        for holder, receiver in zip(trace.chain, trace.chain[1:]):
            assert resolution.decisions[holder].delegate == receiver


@pytest.mark.parametrize("seed", SEEDS)
def test_voter_order_does_not_matter(seed: int) -> None:
    scenario = random_scenario(seed)
    shuffled = list(scenario.voters)
    random.Random(seed).shuffle(shuffled)

    reordered = resolve_question(
        scenario.network,
        QUESTION,
        shuffled,
        scenario.judgments,
        direct_voters=scenario.direct_voters,
    )
    assert reordered == resolve(scenario)


@pytest.mark.parametrize("seed", SEEDS)
def test_relabelling_persons_does_not_matter(seed: int) -> None:
    scenario = random_scenario(seed)
    resolution = resolve(scenario)

    ids = list(scenario.network.persons)
    renamed = ids[:]
    random.Random(seed).shuffle(renamed)
    new_id = {old: f"x{renamed.index(old):02d}" for old in ids}

    network = create_network(
        [
            Person(new_id[person.id], person.residences)
            for person in scenario.network.persons.values()
        ],
        scenario.categories,
        [
            Delegation(new_id[d.delegator], d.category, new_id[d.delegate])
            for d in scenario.network.delegations
        ],
    )
    relabelled = resolve_question(
        network,
        QUESTION,
        [new_id[voter] for voter in scenario.voters],
        scenario.judgments,
        direct_voters={new_id[person] for person in scenario.direct_voters},
    )

    for voter in scenario.voters:
        assert (
            relabelled.resolver_of(new_id[voter])
            == new_id[resolution.resolver_of(voter)]
        )
    assert {frozenset(new_id[m] for m in loop) for loop in resolution.loops} == {
        frozenset(loop) for loop in relabelled.loops
    }


@pytest.mark.parametrize("seed", SEEDS)
def test_everyone_on_a_loop_keeps_the_decision(seed: int) -> None:
    resolution = resolve(random_scenario(seed))

    for loop in resolution.loops:
        assert loop[0] == min(loop)
        for index, member in enumerate(loop):
            # The loop is a real cycle of routing decisions.
            assert (
                resolution.decisions[member].delegate == loop[(index + 1) % len(loop)]
            )
            if member in resolution.traces:
                trace = resolution.traces[member]
                assert trace.resolver == member
                assert trace.kept_because is KeepReason.LOOP
                assert trace.loop == loop


@pytest.mark.parametrize("seed", SEEDS)
def test_a_direct_vote_changes_only_those_upstream(seed: int) -> None:
    scenario = random_scenario(seed)
    resolution = resolve(scenario)
    newcomer = random.Random(seed).choice(sorted(scenario.network.persons))

    after = resolve_question(
        scenario.network,
        QUESTION,
        scenario.voters,
        scenario.judgments,
        direct_voters=scenario.direct_voters | {newcomer},
    )

    if newcomer in after.traces:
        assert after.resolver_of(newcomer) == newcomer
    for voter in scenario.voters:
        if newcomer not in raw_reach(resolution, voter):
            assert after.traces[voter] == resolution.traces[voter]


@pytest.mark.parametrize("seed", SEEDS)
def test_checked_networks_never_loop_within_one_category(seed: int) -> None:
    scenario = random_scenario(seed, guarded=True)

    for category in scenario.categories:
        # Only this category clears the threshold, so every hop uses it.
        judgments = {
            (QUESTION, other.id): 1.0 if other.id == category.id else 0.0
            for other in scenario.categories
        }
        resolution = resolve_question(
            scenario.network, QUESTION, scenario.network.persons, judgments
        )
        assert resolution.loops == ()


def test_the_seeds_exercise_the_interesting_cases() -> None:
    loops = 0
    long_chains = 0
    outside_resolvers = 0
    upstream_of_a_loop = 0
    reasons: set[KeepReason] = set()

    for seed in SEEDS:
        scenario = random_scenario(seed)
        resolution = resolve(scenario)
        loops += len(resolution.loops)
        voters = set(scenario.voters)
        for trace in resolution.traces.values():
            reasons.add(trace.kept_because)
            long_chains += trace.hops >= 2
            outside_resolvers += trace.resolver not in voters
            upstream_of_a_loop += trace.loop is not None and trace.delegated

    assert loops >= 100
    assert long_chains >= 100
    assert outside_resolvers >= 100
    assert upstream_of_a_loop >= 100
    assert reasons == set(KeepReason)
