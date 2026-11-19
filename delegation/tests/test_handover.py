"""Tests for liquid's handover curve (an exploratory analysis after the freeze)."""

from __future__ import annotations

import numpy as np
import pytest

from delegation.comparison import runner
from delegation.comparison.arrangements import DIAL_TURNOUT, direct, full_turnout, liquid
from delegation.comparison.beliefs import BeliefCityConfig
from delegation.comparison.choice import KEEP, ChoicePolicy
from delegation.comparison.handover import depths, handover_level, handover_policy
from delegation.comparison.measures import measure
from delegation.comparison.population import Population


@pytest.fixture(scope="module")
def city() -> Population:
    # A small fitted city on a development seed, outside the primary namespace
    return runner._population(
        BeliefCityConfig(
            seed=3_000_101,
            districts=2,
            residents_per_district=40,
            history_questions_per_topic=6,
            evaluation_questions_per_topic=4,
            turnout_mean=0.45,
        )
    )


def test_depth_zero_is_direct_voting(city: Population) -> None:
    handed = liquid(city, handover_policy(0), DIAL_TURNOUT)
    plain = direct(city)
    assert np.array_equal(handed.counted, plain.counted)
    reference = full_turnout(city)
    first, second = measure(city, handed, reference), measure(city, plain, reference)
    for name in ("fidelity", "contrary_share", "none_share", "overhead", "outcome_agreement"):
        assert getattr(first, name) == getattr(second, name), name


def test_the_deepest_handover_is_liquid_without_an_acceptance_level(city: Population) -> None:
    deepest = max(depths(city))
    assert deepest == len(city.categories)
    handed = liquid(city, handover_policy(deepest), DIAL_TURNOUT)
    unlimited = liquid(city, ChoicePolicy(), DIAL_TURNOUT)
    assert np.array_equal(handed.resolver, unlimited.resolver)
    assert np.array_equal(handed.counted, unlimited.counted)


def test_each_voter_hands_over_their_best_categories_first(city: Population) -> None:
    from delegation.comparison.arrangements import _liquid_agreements, population_tie_key
    from delegation.comparison.choice import choose, top_candidates

    agreements = _liquid_agreements(city, ChoicePolicy())
    top, best = top_candidates(agreements, population_tie_key(city))
    available = np.isfinite(best).sum(axis=1)
    previous = np.zeros(best.shape, dtype=bool)
    for depth in depths(city):
        held = choose(agreements, handover_policy(depth), population_tie_key(city)).delegate != KEEP
        # Each depth hands over as many categories as it can, and keeps
        # everything handed over at the depth before
        assert np.array_equal(held.sum(axis=1), np.minimum(depth, available))
        assert not (previous & ~held).any()
        # What is held ranks at least as high as anything kept
        for voter in range(best.shape[0]):
            if held[voter].any() and (~held[voter] & np.isfinite(best[voter])).any():
                assert best[voter, held[voter]].min() >= best[voter, ~held[voter]].max()
        previous = held


def test_a_level_records_every_depth_and_direct_voting(city: Population) -> None:
    record = handover_level(city)
    assert list(record["depths"]) == [str(d) for d in depths(city)]
    assert record["pairs"] == city.evaluation.sincere.size
    assert record["depths"]["0"]["matches"] == record["direct_matches"]
    delegations = [record["depths"][str(d)]["measures"]["delegations_per_voter"] for d in depths(city)]
    assert delegations == sorted(delegations)
