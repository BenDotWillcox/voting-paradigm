"""Tests for the creation checks and per-question resolution."""

from __future__ import annotations

import pytest

from delegation import (
    DelegationLoopError,
    InvalidNetworkError,
    KeepReason,
    RouteOutcome,
    add_delegation,
    closing_chain,
    create_category,
    create_network,
    loop_warnings,
    remove_delegation,
    resolve_question,
)
from delegation import Person

from .helpers import CITY, QUESTION, cid, network_of, scores

TAXES = create_category("taxes")
HOUSING = create_category("housing and land use")
TRANSIT = create_category("transportation and infrastructure")


def residents(*ids: str) -> list[Person]:
    return [Person(person, frozenset({CITY})) for person in ids]


class TestCreationChecks:
    def test_swapping_the_same_category_is_rejected(self) -> None:
        # Voter 1 delegates a category to voter 2, who then tries to
        # delegate the same category back.
        network = create_network(residents("v1", "v2"))
        network = add_delegation(network, "v1", TAXES, "v2")

        with pytest.raises(DelegationLoopError) as rejected:
            add_delegation(network, "v2", TAXES, "v1")

        assert rejected.value.chain == ("v2", "v1", "v2")
        assert rejected.value.category == TAXES.id

    def test_longer_loop_in_one_category_is_rejected_with_its_chain(self) -> None:
        network = create_network(residents("a", "b", "c", "d"))
        network = add_delegation(network, "a", TAXES, "b")
        network = add_delegation(network, "b", TAXES, "c")
        network = add_delegation(network, "c", TAXES, "d")

        assert closing_chain(network, "d", TAXES.id, "a") == ("d", "a", "b", "c", "d")
        with pytest.raises(DelegationLoopError):
            add_delegation(network, "d", TAXES, "a")

    def test_identity_ignores_case_and_whitespace(self) -> None:
        network = create_network(residents("a", "b"))
        network = add_delegation(network, "a", create_category("All things taxes"), "b")
        with pytest.raises(DelegationLoopError):
            add_delegation(network, "b", create_category("all  things TAXES"), "a")

    def test_differently_worded_categories_are_allowed(self) -> None:
        # Whether these two loop depends on the question, so the delegation
        # is accepted and left to loop_warnings and the resolution rule.
        network = create_network(residents("a", "b"))
        network = add_delegation(network, "a", HOUSING, "b")
        network = add_delegation(network, "b", TRANSIT, "a")
        assert len(network.delegations) == 2

    def test_new_category_is_registered_and_appended_to_the_list(self) -> None:
        network = create_network(residents("a", "b", "c"))
        network = add_delegation(network, "a", HOUSING, "b")
        network = add_delegation(network, "a", TAXES, "c")
        assert set(network.categories) == {HOUSING.id, TAXES.id}
        assert [d.category for d in network.delegations_of("a")] == [
            HOUSING.id,
            TAXES.id,
        ]

    def test_self_delegation_is_rejected(self) -> None:
        network = create_network(residents("a"))
        with pytest.raises(InvalidNetworkError) as rejected:
            add_delegation(network, "a", TAXES, "a")
        assert not isinstance(rejected.value, DelegationLoopError)

    def test_unknown_person_is_rejected(self) -> None:
        network = create_network(residents("a"))
        with pytest.raises(InvalidNetworkError):
            add_delegation(network, "a", TAXES, "ghost")
        with pytest.raises(InvalidNetworkError):
            add_delegation(network, "ghost", TAXES, "a")

    def test_delegating_a_category_twice_is_rejected(self) -> None:
        network = create_network(residents("a", "b", "c"))
        network = add_delegation(network, "a", TAXES, "b")
        with pytest.raises(InvalidNetworkError):
            add_delegation(network, "a", TAXES, "c")

    def test_existing_loop_elsewhere_does_not_block_or_hang(self) -> None:
        # b and c already loop on taxes (built without the checks). A new
        # delegation into that loop does not itself close a loop.
        network = network_of(
            ["a", "b", "c"], [("b", "taxes", "c"), ("c", "taxes", "b")]
        )
        assert closing_chain(network, "a", TAXES.id, "b") is None
        network = add_delegation(network, "a", TAXES, "b")
        assert network.delegate_for("a", TAXES.id) == "b"

    def test_removing_a_delegation_lifts_the_rejection(self) -> None:
        network = create_network(residents("a", "b"))
        network = add_delegation(network, "a", TAXES, "b")
        network = remove_delegation(network, "a", TAXES.id)
        assert network.delegations == ()
        network = add_delegation(network, "b", TAXES, "a")
        assert network.delegate_for("b", TAXES.id) == "a"

    def test_removing_a_missing_delegation_is_rejected(self) -> None:
        network = create_network(residents("a", "b"))
        with pytest.raises(InvalidNetworkError):
            remove_delegation(network, "a", TAXES.id)


class TestLoopWarnings:
    # A delegates housing to B; B delegates transportation to A.
    NETWORK = network_of(
        ["a", "b"],
        [
            ("a", "housing and land use", "b"),
            ("b", "transportation and infrastructure", "a"),
        ],
    )
    JUDGMENTS = {
        ("transit zoning", HOUSING.id): 0.80,
        ("transit zoning", TRANSIT.id): 0.85,
        ("rent control", HOUSING.id): 0.95,
        ("rent control", TRANSIT.id): 0.05,
        ("bus lanes", HOUSING.id): 0.05,
        ("bus lanes", TRANSIT.id): 0.95,
    }
    QUESTIONS = ["transit zoning", "rent control", "bus lanes"]

    def test_warns_only_on_questions_that_come_back(self) -> None:
        warned = loop_warnings(
            self.NETWORK, "b", TRANSIT.id, self.QUESTIONS, self.JUDGMENTS
        )
        assert warned == ("transit zoning",)

    def test_both_ends_of_the_loop_are_warned(self) -> None:
        warned = loop_warnings(
            self.NETWORK, "a", HOUSING.id, self.QUESTIONS, self.JUDGMENTS
        )
        assert warned == ("transit zoning",)

    def test_no_warning_when_the_loop_runs_through_another_category(self) -> None:
        # A also delegates taxes to B. The loop on "transit zoning" runs
        # through A's housing delegation, not the taxes one.
        network = add_delegation(self.NETWORK, "a", TAXES, "b")
        judgments = {**self.JUDGMENTS, ("transit zoning", TAXES.id): 0.01}
        assert (
            loop_warnings(network, "a", TAXES.id, ["transit zoning"], judgments) == ()
        )

    def test_no_warning_when_only_upstream_of_a_loop(self) -> None:
        network = network_of(
            ["a", "b", "c"],
            [
                ("a", "housing and land use", "b"),
                ("b", "transportation and infrastructure", "a"),
                ("c", "housing and land use", "a"),
            ],
        )
        warned = loop_warnings(
            network, "c", HOUSING.id, ["transit zoning"], self.JUDGMENTS
        )
        assert warned == ()

    def test_delegation_must_exist(self) -> None:
        with pytest.raises(InvalidNetworkError):
            loop_warnings(self.NETWORK, "a", TRANSIT.id, self.QUESTIONS, self.JUDGMENTS)


class TestResolution:
    def test_without_delegations_everyone_resolves_for_themself(self) -> None:
        network = network_of(["a", "b"])
        resolution = resolve_question(network, QUESTION, ["a", "b"], {})

        assert resolution.weights() == {"a": 1, "b": 1}
        assert resolution.loops == ()
        trace = resolution.traces["a"]
        assert trace.chain == ("a",)
        assert trace.hops == 0
        assert not trace.delegated
        assert trace.kept_because is KeepReason.NO_DELEGATIONS

    def test_chain_is_followed_to_its_end(self) -> None:
        network = network_of(
            ["a", "b", "c"], [("a", "taxes", "b"), ("b", "taxes", "c")]
        )
        resolution = resolve_question(
            network, QUESTION, ["a", "b", "c"], scores(taxes=0.9)
        )

        assert resolution.traces["a"].chain == ("a", "b", "c")
        assert resolution.traces["a"].hops == 2
        assert resolution.resolver_of("b") == "c"
        assert resolution.weights() == {"c": 3}

    def test_each_holder_applies_their_own_categories(self) -> None:
        # B receives A's tax question but has only delegated schools.
        network = network_of(
            ["a", "b", "c"], [("a", "taxes", "b"), ("b", "schools", "c")]
        )
        resolution = resolve_question(
            network, QUESTION, ["a"], scores(taxes=0.9, schools=0.1)
        )

        trace = resolution.traces["a"]
        assert trace.chain == ("a", "b")
        assert trace.kept_because is KeepReason.NONE_AVAILABLE
        assert resolution.decisions["b"].outcome is RouteOutcome.NONE_AVAILABLE

    def test_direct_vote_stops_the_chain(self) -> None:
        network = network_of(
            ["a", "b", "c"], [("a", "taxes", "b"), ("b", "taxes", "c")]
        )
        resolution = resolve_question(
            network, QUESTION, ["a", "b", "c"], scores(taxes=0.9), direct_voters={"b"}
        )

        assert resolution.resolver_of("a") == "b"
        assert resolution.traces["a"].kept_because is KeepReason.DIRECT_VOTE
        assert resolution.weights() == {"b": 2, "c": 1}

    def test_missing_judgment_keeps_the_vote_with_its_holder(self) -> None:
        network = network_of(["a", "b"], [("a", "taxes", "b")])
        resolution = resolve_question(network, QUESTION, ["a"], {})
        assert resolution.resolver_of("a") == "a"
        assert resolution.traces["a"].kept_because is KeepReason.ROUTER_UNAVAILABLE

    def test_person_outside_the_voters_can_resolve(self) -> None:
        network = network_of(["a"], [("a", "taxes", "expert")], outsiders=["expert"])
        resolution = resolve_question(network, QUESTION, ["a"], scores(taxes=0.9))

        assert resolution.voters == ("a",)
        assert resolution.weights() == {"expert": 1}

    def test_question_dependent_loop_everyone_keeps_the_decision(self) -> None:
        # The example from the design doc: neither delegation closes a loop
        # when it is created, but this question matches both categories.
        network = network_of(
            ["a", "b"],
            [
                ("a", "housing and land use", "b"),
                ("b", "transportation and infrastructure", "a"),
            ],
        )
        judgments = {(QUESTION, HOUSING.id): 0.80, (QUESTION, TRANSIT.id): 0.85}
        resolution = resolve_question(network, QUESTION, ["a", "b"], judgments)

        assert resolution.loops == (("a", "b"),)
        for voter in ("a", "b"):
            trace = resolution.traces[voter]
            assert trace.resolver == voter
            assert trace.chain == (voter,)
            assert trace.kept_because is KeepReason.LOOP
            assert trace.loop == ("a", "b")

    def test_the_same_network_does_not_loop_on_another_question(self) -> None:
        network = network_of(
            ["a", "b"],
            [
                ("a", "housing and land use", "b"),
                ("b", "transportation and infrastructure", "a"),
            ],
        )
        judgments = {(QUESTION, HOUSING.id): 0.95, (QUESTION, TRANSIT.id): 0.05}
        resolution = resolve_question(network, QUESTION, ["a", "b"], judgments)

        assert resolution.loops == ()
        assert resolution.weights() == {"b": 2}

    def test_three_person_loop_is_reported_once_from_its_smallest_id(self) -> None:
        network = network_of(
            ["a", "b", "c"],
            [("b", "taxes", "c"), ("c", "taxes", "a"), ("a", "taxes", "b")],
        )
        resolution = resolve_question(
            network, QUESTION, ["c", "a", "b"], scores(taxes=0.9)
        )

        assert resolution.loops == (("a", "b", "c"),)
        assert resolution.weights() == {"a": 1, "b": 1, "c": 1}

    def test_voters_upstream_of_a_loop_reach_the_member_they_lead_to(self) -> None:
        network = network_of(
            ["a", "b", "c", "d", "e"],
            [
                ("a", "taxes", "b"),
                ("b", "taxes", "c"),
                ("c", "taxes", "a"),
                ("d", "taxes", "b"),
                ("e", "taxes", "d"),
            ],
        )
        resolution = resolve_question(
            network, QUESTION, ["a", "b", "c", "d", "e"], scores(taxes=0.9)
        )

        assert resolution.traces["d"].chain == ("d", "b")
        assert resolution.traces["e"].chain == ("e", "d", "b")
        assert resolution.traces["e"].kept_because is KeepReason.LOOP
        assert resolution.traces["e"].loop == ("a", "b", "c")
        assert resolution.weights() == {"a": 1, "b": 3, "c": 1}

    def test_direct_vote_on_a_loop_breaks_it(self) -> None:
        network = network_of(["a", "b"], [("a", "taxes", "b"), ("b", "taxes", "a")])
        resolution = resolve_question(
            network, QUESTION, ["a", "b"], scores(taxes=0.9), direct_voters={"b"}
        )

        assert resolution.loops == ()
        assert resolution.weights() == {"b": 2}

    def test_repeated_voters_originate_one_vote_each(self) -> None:
        network = network_of(["a", "b"])
        resolution = resolve_question(network, QUESTION, ["b", "a", "b"], {})
        assert resolution.voters == ("a", "b")

    def test_unknown_voter_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            resolve_question(network_of(["a"]), QUESTION, ["ghost"], {})

    def test_decisions_cover_everyone_consulted(self) -> None:
        network = network_of(
            ["a", "b"], [("a", "taxes", "expert")], outsiders=["expert", "bystander"]
        )
        resolution = resolve_question(network, QUESTION, ["a", "b"], scores(taxes=0.9))
        assert set(resolution.decisions) == {"a", "b", "expert"}
        assert resolution.decisions["a"].category == cid("taxes")
