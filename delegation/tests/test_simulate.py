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
from delegation.graph import DelegationLoopError
from delegation.simulate import (
    BEHAVIOURS,
    CITY,
    DIRECT,
    VIEWER,
    OptionSupport,
    SimulationConfig,
    Support,
    cast_day,
    casts,
    district_id,
    jurisdictions,
    network_on,
    option_utilities,
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
        ordered = sorted(SIMULATION.positions, key=lambda p: SIMULATION.positions[p][0])
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

    def test_a_question_can_have_any_number_of_options(self) -> None:
        three = Question("q3", "T", "S", YES_NO + (Candidate("maybe", "Maybe"),))
        assert sincere_choice(SIMULATION, "d1-000", three) in {"yes", "no", "maybe"}

    def test_authored_support_moves_the_result(self) -> None:
        popular = Support({"yes": OptionSupport(appeal=2.0)})
        unpopular = Support({"yes": OptionSupport(appeal=-2.0)})
        for support, winner in ((popular, "yes"), (unpopular, "no")):
            ballots = sincere_ballots(SIMULATION, MEASURE, support)
            share = sum(b.choice == winner for b in ballots.values()) / len(ballots)
            assert share > 0.95

    def test_a_lean_splits_people_by_position(self) -> None:
        support = Support({"yes": OptionSupport(lean=(0.0, 2.0, 0.0))})
        for person, position in SIMULATION.positions.items():
            if abs(position[1]) > 0.6:
                wants_yes = sincere_choice(SIMULATION, person, MEASURE, support) == "yes"
                assert wants_yes == (position[1] > 0)

    def test_a_site_pulls_on_people_who_live_near_it(self) -> None:
        config = SIMULATION.config
        support = Support({"yes": OptionSupport(site=(0.5, 0.5), local=1.0)})
        near = option_utilities(config, (0, 0, 0), (0.5, 0.5), "p", MEASURE, support)
        far = option_utilities(config, (0, 0, 0), (0.0, 0.0), "p", MEASURE, support)
        nowhere = option_utilities(config, (0, 0, 0), None, "p", MEASURE, support)
        # The same person and question, so the same noise: only the pull differs.
        assert near["yes"] == pytest.approx(nowhere["yes"] + 1.0)
        assert nowhere["yes"] < far["yes"] < near["yes"]
        assert near["no"] == far["no"] == nowhere["no"]


class TestHomes:
    def test_every_resident_lives_inside_their_district(self) -> None:
        config = SimulationConfig(
            district_areas=((0.0, 0.5, 1.0, 1.0), (0.0, 0.0, 0.5, 0.5))
        )
        simulation = simulate_network(POOL, config)
        for person, (x, y) in simulation.homes.items():
            home = next(
                r for r in simulation.network.persons[person].residences if r != CITY
            )
            if home == district_id(1):
                assert 0.0 <= x <= 1.0 and 0.5 <= y <= 1.0
            elif home == district_id(2):
                assert 0.0 <= x <= 0.5 and 0.0 <= y <= 0.5
            else:  # no area given: the third of three equal strips
                assert 2 / 3 <= x <= 1.0 and 0.0 <= y <= 1.0

    def test_outsiders_have_no_home_and_the_viewer_has_one(self) -> None:
        assert VIEWER in SIMULATION.homes
        assert not any(person.startswith("out-") for person in SIMULATION.homes)

    def test_district_leans_shift_positions(self) -> None:
        config = SimulationConfig(district_leans=((0.6, 0.0, 0.0), (-0.6, 0.0, 0.0)))
        simulation = simulate_network(POOL, config)

        def mean(prefix: str) -> float:
            values = [
                position[0]
                for person, position in simulation.positions.items()
                if person.startswith(prefix)
            ]
            return sum(values) / len(values)

        assert mean("d1-") > 0.3 and mean("d2-") < -0.3
        assert abs(mean("d3-")) < 0.2 and abs(mean("out-")) < 0.3


class TestTurnout:
    def test_people_others_rely_on_nearly_always_vote(self) -> None:
        config = SIMULATION.config
        well_known = {p for people in SIMULATION.experts.values() for p in people}
        assert well_known
        for person in well_known:
            assert SIMULATION.turnout[person] == config.delegate_turnout
        ordinary = [
            chance
            for chance in SIMULATION.turnout.values()
            if chance != config.delegate_turnout
        ]
        assert ordinary
        assert all(config.min_turnout <= c <= config.max_turnout for c in ordinary)

    def test_casting_is_seeded_and_follows_turnout_and_salience(self) -> None:
        questions = [Question(f"t{n}", "T", "S", YES_NO) for n in range(300)]
        person = min(SIMULATION.turnout, key=SIMULATION.turnout.__getitem__)
        chance = SIMULATION.turnout[person]

        def share(salience: float) -> float:
            return sum(casts(SIMULATION, person, q, salience) for q in questions) / 300

        assert share(1.0) == share(1.0)
        assert abs(share(1.0) - chance) < 0.1
        assert share(0.2) < share(1.0) < share(10.0) == 1.0

    def test_the_viewer_never_casts_here(self) -> None:
        assert not casts(SIMULATION, VIEWER, MEASURE)

    def test_a_cast_day_falls_while_the_paper_is_open(self) -> None:
        days = {cast_day(SIMULATION, p, "paper", -18, 3) for p in SIMULATION.positions}
        assert min(days) >= -18 and max(days) <= 3
        assert len(days) > 10
        assert cast_day(SIMULATION, "d1-000", "paper", -18, 3) == cast_day(
            SIMULATION, "d1-000", "paper", -18, 3
        )


class TestChanges:
    def test_some_delegations_were_made_or_moved_in_the_past(self) -> None:
        config = SIMULATION.config
        changes = SIMULATION.changes
        assert 0.05 < len(changes) / len(NETWORK.delegations) < 0.3
        assert any(change.before is None for change in changes)
        assert any(change.before is not None for change in changes)
        for change in changes:
            assert config.earliest_change <= change.day <= config.latest_change
            assert NETWORK.delegate_for(change.delegator, change.category) == change.after
            assert change.before not in (change.after, change.delegator, VIEWER)
        assert [c.day for c in changes] == sorted((c.day for c in changes), reverse=True)

    def test_the_network_on_an_earlier_day_undoes_later_changes(self) -> None:
        changes = SIMULATION.changes
        assert network_on(NETWORK, changes, 0) == NETWORK
        earliest = network_on(NETWORK, changes, SIMULATION.config.earliest_change - 1)
        for change in changes:
            assert earliest.delegate_for(change.delegator, change.category) == change.before
        made = sum(change.before is None for change in changes)
        assert len(earliest.delegations) == len(NETWORK.delegations) - made

        middle = sorted(change.day for change in changes)[len(changes) // 2]
        halfway = network_on(NETWORK, changes, middle)
        for change in changes:
            expected = change.after if change.day <= middle else change.before
            assert halfway.delegate_for(change.delegator, change.category) == expected

    def test_a_moved_delegation_keeps_its_place_in_the_category_list(self) -> None:
        change = next(c for c in SIMULATION.changes if c.before is not None)
        before = network_on(NETWORK, SIMULATION.changes, change.day - 1)
        assert [d.category for d in before.delegations_of(change.delegator)] == [
            d.category
            for d in NETWORK.delegations_of(change.delegator)
            if before.delegate_for(change.delegator, d.category) is not None
        ]

    def test_no_day_has_a_loop_within_one_category(self) -> None:
        days = sorted({change.day for change in SIMULATION.changes})
        for day in days[:: max(1, len(days) // 8)]:
            earlier = network_on(NETWORK, SIMULATION.changes, day - 1)
            for category in POOL:
                judgments = {("q", c.id): float(c.id == category.id) for c in POOL}
                assert resolve_question(earlier, "q", earlier.persons, judgments).loops == ()

    def test_undoing_into_a_loop_is_refused(self) -> None:
        from delegation.simulate import DelegationChange

        first = next(d for d in NETWORK.delegations if d.delegate != VIEWER)
        # Pretend the delegate used to hand the same category back.
        closing = DelegationChange(-1, first.delegate, first.category, first.delegator, None)
        if NETWORK.delegate_for(first.delegate, first.category) is None:
            with pytest.raises(DelegationLoopError):
                network_on(NETWORK, [closing], -5)
