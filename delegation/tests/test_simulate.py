"""Tests for the seeded synthetic network and its sincere ballots."""

from __future__ import annotations

from collections import Counter

import pytest

from delegation import (
    Question,
    create_category,
    delegated_share,
    largest_share,
    resolve_question,
)
from delegation.simulate import (
    BEHAVIOURS,
    CITY,
    DIRECT,
    VIEWER,
    SimulationConfig,
    district_id,
    jurisdictions,
    simulate_network,
    sincere_ballots,
    sincere_choice,
)
from voting import Candidate

POOL = [create_category(f"topic {index}") for index in range(8)]
NESTING = [(POOL[6].id, POOL[0].id), (POOL[7].id, POOL[1].id)]
YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))
MEASURE = Question("q", "A measure", "A yes or no question.", YES_NO)
SIMULATION = simulate_network(POOL, nesting=NESTING)
NETWORK = SIMULATION.network


class TestPopulation:
    def test_sizes(self) -> None:
        config = SIMULATION.config
        residents = config.districts * config.residents_per_district
        assert len(NETWORK.persons) == residents + config.outsiders + 1
        assert jurisdictions(config) == (CITY, "district-1", "district-2", "district-3")

    def test_residents_live_in_the_city_and_one_district(self) -> None:
        for person in NETWORK.persons.values():
            if person.id.startswith("out-"):
                assert person.residences == frozenset()
            else:
                assert CITY in person.residences
                assert len(person.residences) == 2

    def test_the_viewer_is_a_district_one_resident_with_no_delegations(self) -> None:
        assert NETWORK.persons[VIEWER].residences == frozenset({CITY, district_id(1)})
        assert NETWORK.delegations_of(VIEWER) == ()
        assert VIEWER not in SIMULATION.positions
        assert VIEWER not in SIMULATION.behaviours

    def test_every_behaviour_occurs_in_roughly_its_share(self) -> None:
        counts = Counter(SIMULATION.behaviours.values())
        assert set(counts) == set(BEHAVIOURS)
        total = sum(counts.values())
        assert 0.2 < counts[DIRECT] / total < 0.4

    def test_people_who_keep_every_decision_delegate_nothing(self) -> None:
        for person, behaviour in SIMULATION.behaviours.items():
            if behaviour == DIRECT and not self.hands_to_viewer(person):
                assert NETWORK.delegations_of(person) == ()

    @staticmethod
    def hands_to_viewer(person: str) -> bool:
        return any(d.delegate == VIEWER for d in NETWORK.delegations_of(person))

    def test_delegators_hand_over_a_bounded_number_of_categories(self) -> None:
        config = SIMULATION.config
        for person in NETWORK.persons:
            # One more is possible for someone who also hands a category to the viewer.
            assert len(NETWORK.delegations_of(person)) <= config.max_categories + 1

    def test_outsiders_can_be_delegates(self) -> None:
        delegates = {delegation.delegate for delegation in NETWORK.delegations}
        assert any(delegate.startswith("out-") for delegate in delegates)

    def test_people_from_every_district_delegate_to_the_viewer(self) -> None:
        homes = {
            next(r for r in NETWORK.persons[d.delegator].residences if r != CITY)
            for d in NETWORK.delegations
            if d.delegate == VIEWER
        }
        assert homes == {district_id(1), district_id(2), district_id(3)}

    def test_nesting_is_carried_onto_the_network(self) -> None:
        assert NETWORK.nesting == frozenset(NESTING)

    def test_broad_categories_are_picked_more_often_than_narrow_ones(self) -> None:
        narrow = {POOL[6].id, POOL[7].id}
        counts = Counter(delegation.category for delegation in NETWORK.delegations)
        broad_mean = sum(counts[c.id] for c in POOL if c.id not in narrow) / 6
        narrow_mean = sum(counts[c] for c in narrow) / 2
        assert broad_mean > narrow_mean


class TestAuthoredViewerDelegations:
    CONFIG = SimulationConfig(
        viewer_inbound=((2, "Topic 3"), (3, "topic 5"), (1, "not in the pool"))
    )

    def test_named_categories_come_from_named_districts(self) -> None:
        network = simulate_network(POOL, self.CONFIG).network
        inbound = {
            (
                next(r for r in network.persons[d.delegator].residences if r != CITY),
                d.category,
            )
            for d in network.delegations
            if d.delegate == VIEWER
        }
        assert inbound == {(district_id(2), POOL[3].id), (district_id(3), POOL[5].id)}


class TestReproducibility:
    def test_same_seed_same_network(self) -> None:
        again = simulate_network(POOL, nesting=NESTING)
        assert again.network == NETWORK
        assert again.positions == SIMULATION.positions
        assert again.experts == SIMULATION.experts

    def test_another_seed_another_network(self) -> None:
        other = simulate_network(POOL, SimulationConfig(seed=1), NESTING)
        assert other.network.delegations != NETWORK.delegations

    def test_invalid_configurations_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            simulate_network([])
        with pytest.raises(ValueError):
            simulate_network(
                POOL, SimulationConfig(share_direct=0.7, share_trusting_experts=0.5)
            )


class TestDelegationShape:
    def everything_matches(self, category_id: str) -> dict[tuple[str, str], float]:
        return {("q", c.id): 1.0 if c.id == category_id else 0.0 for c in POOL}

    def test_no_loop_within_one_category(self) -> None:
        # Every delegation went through the creation check.
        for category in POOL:
            resolution = resolve_question(
                NETWORK, "q", NETWORK.persons, self.everything_matches(category.id)
            )
            assert resolution.loops == ()

    def test_well_known_people_concentrate_votes(self) -> None:
        shares = []
        for category in POOL:
            resolution = resolve_question(
                NETWORK, "q", NETWORK.persons, self.everything_matches(category.id)
            )
            shares.append(largest_share(resolution))
            assert 0 < delegated_share(resolution) < 1
        assert max(shares) > 0.05


class TestSincereBallots:
    def test_everyone_but_the_viewer_has_a_ballot(self) -> None:
        ballots = sincere_ballots(SIMULATION, MEASURE)
        assert set(ballots) == set(NETWORK.persons) - {VIEWER}
        assert all(ballot.voter_id == person for person, ballot in ballots.items())

    def test_ballots_are_reproducible_and_split(self) -> None:
        first = sincere_ballots(SIMULATION, MEASURE)
        assert first == sincere_ballots(SIMULATION, MEASURE)
        choices = Counter(ballot.choice for ballot in first.values())
        assert set(choices) == {"yes", "no"}
        assert min(choices.values()) > 20

    def test_votes_follow_position(self) -> None:
        # Across many questions, people at opposite ends disagree far more
        # often than close neighbours do.
        ordered = sorted(SIMULATION.positions, key=SIMULATION.positions.__getitem__)
        low, near_low, high = ordered[0], ordered[1], ordered[-1]
        questions = [Question(f"q{n}", "T", "S", YES_NO) for n in range(200)]

        def disagreements(first: str, second: str) -> int:
            return sum(
                sincere_choice(SIMULATION, first, q)
                != sincere_choice(SIMULATION, second, q)
                for q in questions
            )

        assert disagreements(low, high) > 2 * disagreements(low, near_low)

    def test_different_questions_lean_differently(self) -> None:
        shares = set()
        for number in range(12):
            question = Question(f"lean-{number}", "T", "S", YES_NO)
            ballots = sincere_ballots(SIMULATION, question)
            shares.add(
                round(
                    sum(b.choice == "yes" for b in ballots.values()) / len(ballots), 2
                )
            )
        assert len(shares) > 6

    def test_the_viewer_has_no_sincere_choice(self) -> None:
        with pytest.raises(ValueError):
            sincere_choice(SIMULATION, VIEWER, MEASURE)

    def test_only_two_option_questions_are_supported(self) -> None:
        three = Question("q3", "T", "S", YES_NO + (Candidate("maybe", "Maybe"),))
        with pytest.raises(ValueError):
            sincere_choice(SIMULATION, "d1-000", three)
