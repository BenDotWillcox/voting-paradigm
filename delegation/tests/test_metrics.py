"""Tests for the concentration and reach measures."""

from __future__ import annotations

import pytest

from delegation import (
    chain_length_counts,
    delegated_share,
    largest_share,
    resolve_question,
    weight_gini,
    winners_differ,
)
from voting import ElectionResult

from .helpers import QUESTION, network_of, scores


def result(*winners: str) -> ElectionResult:
    return ElectionResult(
        winners=list(winners),
        vote_counts={},
        total_ballots=0,
        abstentions=0,
        tiebreak_applied=False,
    )


class TestDirectVoting:
    RESOLUTION = resolve_question(
        network_of(["a", "b", "c", "d"]), QUESTION, ["a", "b", "c", "d"], {}
    )

    def test_nothing_is_delegated_or_concentrated(self) -> None:
        assert delegated_share(self.RESOLUTION) == 0.0
        assert largest_share(self.RESOLUTION) == 0.25
        assert weight_gini(self.RESOLUTION) == 0.0
        assert chain_length_counts(self.RESOLUTION) == {0: 4}


class TestOneResolverHoldsEverything:
    # b, c and d all hand the question to a; c goes through b.
    RESOLUTION = resolve_question(
        network_of(
            ["a", "b", "c", "d"],
            [("b", "taxes", "a"), ("c", "taxes", "b"), ("d", "taxes", "a")],
        ),
        QUESTION,
        ["a", "b", "c", "d"],
        scores(taxes=0.9),
    )

    def test_shares(self) -> None:
        assert delegated_share(self.RESOLUTION) == 0.75
        assert largest_share(self.RESOLUTION) == 1.0

    def test_gini_is_the_maximum_for_the_population(self) -> None:
        # Weights 0, 0, 0, 4: the maximum Gini for four people is 3/4.
        assert weight_gini(self.RESOLUTION) == pytest.approx(0.75)

    def test_chain_lengths(self) -> None:
        assert chain_length_counts(self.RESOLUTION) == {0: 1, 1: 2, 2: 1}


class TestOutsideResolver:
    def test_population_includes_resolvers_who_are_not_voters(self) -> None:
        resolution = resolve_question(
            network_of(["a", "b"], [("a", "taxes", "expert")], outsiders=["expert"]),
            QUESTION,
            ["a", "b"],
            scores(taxes=0.9),
        )
        # Weights: a 0, b 1, expert 1.
        assert weight_gini(resolution) == pytest.approx(1 / 3)
        assert largest_share(resolution) == 0.5
        assert delegated_share(resolution) == 0.5


class TestEmpty:
    def test_no_voters_gives_zeros(self) -> None:
        resolution = resolve_question(network_of(["a"]), QUESTION, [], {})
        assert delegated_share(resolution) == 0.0
        assert largest_share(resolution) == 0.0
        assert weight_gini(resolution) == 0.0
        assert chain_length_counts(resolution) == {}


class TestWinnersDiffer:
    def test_same_winner(self) -> None:
        assert not winners_differ(result("yes"), result("yes"))

    def test_different_winner(self) -> None:
        assert winners_differ(result("yes"), result("no"))

    def test_order_of_co_winners_does_not_matter(self) -> None:
        assert not winners_differ(result("a", "b"), result("b", "a"))
