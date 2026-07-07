"""Tests for acquisition (pair selection) policies."""

import random

import pytest

from preferences.acquisition import (
    MaxVariancePairSelector,
    RandomPairSelector,
    create_selector,
)
from preferences.model.gaussian_linear import GaussianLinearUtilityModel
from preferences.questions.bank import Item, QuestionBank
from preferences.types import Evidence, EvidenceSource


def small_bank() -> QuestionBank:
    return QuestionBank(
        items=[
            Item(id="a", text="Alpha"),
            Item(id="b", text="Beta"),
            Item(id="c", text="Gamma"),
            Item(id="d", text="Delta"),
        ]
    )


def pairwise(a: str, b: str, value: float) -> Evidence:
    return Evidence(
        source=EvidenceSource.PAIRWISE, item_a=a, item_b=b, value=value
    )


class TestRandomSelector:
    def test_respects_exclusions(self):
        bank = small_bank()
        model = GaussianLinearUtilityModel()
        state = model.initialize("u", "s", bank.item_ids())
        selector = RandomPairSelector()
        rng = random.Random(0)
        exclude = {frozenset(("a", "b")), frozenset(("c", "d"))}
        for _ in range(50):
            pair = selector.select_pair(state, model, bank, exclude, rng)
            assert frozenset(pair) not in exclude

    def test_exhaustion_returns_none(self):
        bank = small_bank()
        model = GaussianLinearUtilityModel()
        state = model.initialize("u", "s", bank.item_ids())
        selector = RandomPairSelector()
        all_pairs = {
            frozenset((x, y))
            for i, x in enumerate(bank.item_ids())
            for y in bank.item_ids()[i + 1 :]
        }
        assert (
            selector.select_pair(state, model, bank, all_pairs, random.Random(0))
            is None
        )

    def test_seeded_determinism(self):
        bank = small_bank()
        model = GaussianLinearUtilityModel()
        state = model.initialize("u", "s", bank.item_ids())
        selector = RandomPairSelector()
        p1 = selector.select_pair(state, model, bank, set(), random.Random(7))
        p2 = selector.select_pair(state, model, bank, set(), random.Random(7))
        assert p1 == p2


class TestMaxVarianceSelector:
    def test_picks_highest_variance_pair(self):
        """After observing (a, b), that pair's gap variance drops, so the
        selector must pick an unobserved combination."""
        bank = small_bank()
        model = GaussianLinearUtilityModel()
        state = model.initialize("u", "s", bank.item_ids())
        state = model.update(state, pairwise("a", "b", 8.0))
        selector = MaxVariancePairSelector()
        pair = selector.select_pair(state, model, bank, set(), random.Random(0))
        # (a, b) has the least remaining uncertainty; anything else beats it.
        assert frozenset(pair) != frozenset(("a", "b"))
        # And the chosen pair must actually maximize the uncertainty.
        best = model.get_uncertainty(state, pair[0], pair[1])
        ids = bank.item_ids()
        for i, x in enumerate(ids):
            for y in ids[i + 1 :]:
                assert best >= model.get_uncertainty(state, x, y) - 1e-12

    def test_deterministic_under_ties(self):
        """At the prior all pairs tie; the canonical first pair must win."""
        bank = small_bank()
        model = GaussianLinearUtilityModel()
        state = model.initialize("u", "s", bank.item_ids())
        selector = MaxVariancePairSelector()
        pairs = {
            selector.select_pair(state, model, bank, set(), random.Random(i))
            for i in range(5)
        }
        assert pairs == {("a", "b")}

    def test_respects_exclusions(self):
        bank = small_bank()
        model = GaussianLinearUtilityModel()
        state = model.initialize("u", "s", bank.item_ids())
        selector = MaxVariancePairSelector()
        exclude = {frozenset(("a", "b"))}
        pair = selector.select_pair(state, model, bank, exclude, random.Random(0))
        assert frozenset(pair) not in exclude


class TestRegistry:
    def test_create_by_name(self):
        assert isinstance(create_selector("random"), RandomPairSelector)
        assert isinstance(create_selector("max_variance"), MaxVariancePairSelector)

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown selection policy"):
            create_selector("thompson")
