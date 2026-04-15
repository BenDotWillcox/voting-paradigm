"""Tests for the QuestionBank."""

import random

import pytest

from preferences.questions.bank import QuestionBank, Item
from preferences.types import QuestionType


def make_bank() -> QuestionBank:
    return QuestionBank(
        items=[
            Item(id="a", text="Alpha", description="alpha desc", domain="d1"),
            Item(id="b", text="Beta", description="beta desc", domain="d1"),
            Item(id="c", text="Gamma", description="gamma desc", domain="d2"),
        ]
    )


class TestBankConstruction:
    def test_requires_at_least_2_items(self):
        with pytest.raises(ValueError):
            QuestionBank(items=[Item(id="only", text="Only")])

    def test_item_ids(self):
        bank = make_bank()
        assert set(bank.item_ids()) == {"a", "b", "c"}

    def test_domains(self):
        bank = make_bank()
        assert bank.domains() == ["d1", "d2"]

    def test_get_item(self):
        bank = make_bank()
        assert bank.get("a").text == "Alpha"


class TestDefaultLoad:
    def test_default_loads(self):
        bank = QuestionBank.load_default()
        assert len(bank.items) >= 20
        # Check a known item exists
        assert "economic_freedom" in bank.item_ids()

    def test_default_has_multiple_domains(self):
        bank = QuestionBank.load_default()
        assert len(bank.domains()) >= 3


class TestBuildPairwise:
    def test_basic_pair(self):
        bank = make_bank()
        q = bank.build_pairwise_question("a", "b")
        assert q.question_type == QuestionType.PAIRWISE
        assert len(q.options) == 2
        assert q.options[0].item_id == "a"
        assert q.options[1].item_id == "b"
        assert "Alpha" in q.prompt and "Beta" in q.prompt

    def test_same_domain_marked(self):
        bank = make_bank()
        q = bank.build_pairwise_question("a", "b")
        assert q.domain == "d1"

    def test_cross_domain_marked(self):
        bank = make_bank()
        q = bank.build_pairwise_question("a", "c")
        assert q.domain == "cross_domain"

    def test_source_is_bank(self):
        bank = make_bank()
        q = bank.build_pairwise_question("a", "b")
        assert q.source == "bank"


class TestRandomPair:
    def test_returns_distinct_items(self):
        bank = make_bank()
        rng = random.Random(42)
        a, b = bank.random_pair(rng=rng)
        assert a != b
        assert a in bank.item_ids()
        assert b in bank.item_ids()

    def test_excludes_seen_pairs(self):
        bank = make_bank()
        rng = random.Random(42)
        seen = {frozenset(("a", "b"))}
        for _ in range(10):
            a, b = bank.random_pair(exclude_pairs=seen, rng=rng)
            assert frozenset((a, b)) != frozenset(("a", "b"))

    def test_exhausts_gracefully(self):
        bank = make_bank()
        # 3 items => 3 possible pairs. Exhaust them all.
        seen = {
            frozenset(("a", "b")),
            frozenset(("a", "c")),
            frozenset(("b", "c")),
        }
        with pytest.raises(RuntimeError):
            bank.random_pair(exclude_pairs=seen)
