"""Tests for the per-voter routing rule."""

from __future__ import annotations

import pytest

from delegation import (
    DEFAULT_THRESHOLD,
    InvalidJudgmentError,
    InvalidNetworkError,
    RouteOutcome,
    route,
)

from .helpers import QUESTION, cid, network_of, scores

# One voter with a broad category, a narrow one, and an unrelated one.
VOTER_NETWORK = network_of(
    ["voter", "lee", "sam", "dana"],
    [
        ("voter", "the environment", "lee"),
        ("voter", "tree frogs in the Amazon", "sam"),
        ("voter", "all things taxes", "dana"),
    ],
)


class TestHighestScoreWins:
    def test_highest_scoring_category_gets_the_decision(self) -> None:
        decision = route(
            VOTER_NETWORK,
            "voter",
            QUESTION,
            scores(
                the_environment=0.93,
                tree_frogs_in_the_Amazon=0.45,
                all_things_taxes=0.05,
            ),
        )
        assert decision.outcome is RouteOutcome.DELEGATED
        assert decision.category == cid("the environment")
        assert decision.delegate == "lee"
        assert not decision.kept

    def test_every_category_is_scored_not_just_the_first_to_pass(self) -> None:
        # The first category in the list clears the threshold, but a later
        # one scores higher and wins.
        decision = route(
            VOTER_NETWORK,
            "voter",
            QUESTION,
            scores(
                the_environment=0.75,
                tree_frogs_in_the_Amazon=0.10,
                all_things_taxes=0.99,
            ),
        )
        assert decision.delegate == "dana"
        assert [score.probability for score in decision.scores] == [0.75, 0.10, 0.99]

    def test_with_no_nesting_recorded_the_higher_score_wins(self) -> None:
        # This network records no nesting, so the broad category wins on
        # score. test_nesting.py covers the rule once nesting is known.
        decision = route(
            VOTER_NETWORK,
            "voter",
            QUESTION,
            scores(
                the_environment=0.95,
                tree_frogs_in_the_Amazon=0.90,
                all_things_taxes=0.03,
            ),
        )
        assert decision.delegate == "lee"

    def test_exact_tie_goes_to_the_first_category_in_the_list(self) -> None:
        tied = scores(
            the_environment=0.9, tree_frogs_in_the_Amazon=0.9, all_things_taxes=0.9
        )
        assert route(VOTER_NETWORK, "voter", QUESTION, tied).delegate == "lee"

        reordered = network_of(
            ["voter", "lee", "sam", "dana"],
            [
                ("voter", "all things taxes", "dana"),
                ("voter", "the environment", "lee"),
                ("voter", "tree frogs in the Amazon", "sam"),
            ],
        )
        assert route(reordered, "voter", QUESTION, tied).delegate == "dana"


class TestThresholdIsAFloor:
    def test_best_category_below_threshold_stays_with_the_voter(self) -> None:
        decision = route(
            VOTER_NETWORK,
            "voter",
            QUESTION,
            scores(
                the_environment=0.04,
                tree_frogs_in_the_Amazon=0.02,
                all_things_taxes=0.30,
            ),
        )
        assert decision.outcome is RouteOutcome.NONE_AVAILABLE
        assert decision.kept
        assert decision.delegate is None
        assert decision.category is None
        assert len(decision.scores) == 3

    def test_threshold_is_inclusive(self) -> None:
        judgments = scores(
            the_environment=DEFAULT_THRESHOLD,
            tree_frogs_in_the_Amazon=0.0,
            all_things_taxes=0.0,
        )
        assert route(VOTER_NETWORK, "voter", QUESTION, judgments).delegate == "lee"

    def test_threshold_can_be_changed(self) -> None:
        judgments = scores(
            the_environment=0.6, tree_frogs_in_the_Amazon=0.0, all_things_taxes=0.0
        )
        assert route(VOTER_NETWORK, "voter", QUESTION, judgments).kept
        lowered = route(VOTER_NETWORK, "voter", QUESTION, judgments, threshold=0.5)
        assert lowered.delegate == "lee"
        assert lowered.threshold == 0.5


class TestKeeping:
    def test_direct_vote_overrides_every_delegation(self) -> None:
        decision = route(
            VOTER_NETWORK,
            "voter",
            QUESTION,
            scores(
                the_environment=1.0, tree_frogs_in_the_Amazon=1.0, all_things_taxes=1.0
            ),
            direct_vote=True,
        )
        assert decision.outcome is RouteOutcome.DIRECT_VOTE
        assert decision.kept
        assert decision.scores == ()

    def test_person_without_delegations_keeps_the_decision(self) -> None:
        decision = route(VOTER_NETWORK, "lee", QUESTION, {})
        assert decision.outcome is RouteOutcome.NO_DELEGATIONS
        assert decision.kept

    def test_missing_judgment_fails_closed(self) -> None:
        # One category has a judgment that would win on its own. The rule
        # still does not run, because it cannot compare all categories.
        decision = route(VOTER_NETWORK, "voter", QUESTION, scores(the_environment=0.99))
        assert decision.outcome is RouteOutcome.ROUTER_UNAVAILABLE
        assert decision.kept
        assert [score.category for score in decision.scores] == [cid("the environment")]

    def test_judgments_for_another_question_are_not_used(self) -> None:
        other = {("other question", cid("the environment")): 0.99}
        decision = route(VOTER_NETWORK, "voter", QUESTION, other)
        assert decision.outcome is RouteOutcome.ROUTER_UNAVAILABLE


class TestInvalidInput:
    def test_unknown_person_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            route(VOTER_NETWORK, "ghost", QUESTION, {})

    @pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan")])
    def test_threshold_must_be_a_probability(self, threshold: float) -> None:
        with pytest.raises(InvalidJudgmentError):
            route(VOTER_NETWORK, "voter", QUESTION, {}, threshold=threshold)

    @pytest.mark.parametrize("probability", [-0.01, 1.01, float("inf"), float("nan")])
    def test_judgment_must_be_a_probability(self, probability: float) -> None:
        judgments = scores(
            the_environment=probability,
            tree_frogs_in_the_Amazon=0.5,
            all_things_taxes=0.5,
        )
        with pytest.raises(InvalidJudgmentError):
            route(VOTER_NETWORK, "voter", QUESTION, judgments)
