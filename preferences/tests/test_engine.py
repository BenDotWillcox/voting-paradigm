"""Tests for the ElicitationEngine."""

import pytest

from preferences.engine import ElicitationEngine, EngineConfig
from preferences.model.thurstone import ThurstonePairwiseModel
from preferences.questions.bank import Item, QuestionBank
from preferences.types import Response


def small_bank() -> QuestionBank:
    return QuestionBank(
        items=[
            Item(id="a", text="Alpha", description="a", domain="d"),
            Item(id="b", text="Beta", description="b", domain="d"),
            Item(id="c", text="Gamma", description="c", domain="d"),
            Item(id="d", text="Delta", description="d", domain="d"),
        ]
    )


def make_engine(target: int = 3) -> ElicitationEngine:
    return ElicitationEngine(
        model=ThurstonePairwiseModel(),
        question_bank=small_bank(),
        config=EngineConfig(target_questions=target, seed=42),
    )


class TestStart:
    def test_returns_state_and_question(self):
        engine = make_engine()
        state, question = engine.start_session(user_id="u1", session_id="s1")
        assert state.user_id == "u1"
        assert state.session_id == "s1"
        assert state.n_questions_asked == 0
        assert question is not None
        assert len(question.options) == 2

    def test_state_includes_all_bank_items(self):
        engine = make_engine()
        state, _ = engine.start_session("u1", "s1")
        assert set(state.item_ids) == {"a", "b", "c", "d"}


class TestSubmitResponse:
    def test_first_response_updates_state(self):
        engine = make_engine()
        state, q = engine.start_session("u1", "s1")
        opt_ids = [o.item_id for o in q.options]
        response = Response(
            question_id=q.id,
            chosen_option_id=opt_ids[0],
            strength=8.0,
        )
        new_state, next_q = engine.submit_response(state, response, opt_ids)
        assert new_state.n_questions_asked == 1
        assert next_q is not None

    def test_session_ends_at_target(self):
        engine = make_engine(target=3)
        state, q = engine.start_session("u1", "s1")
        for i in range(3):
            opt_ids = [o.item_id for o in q.options]
            response = Response(
                question_id=q.id,
                chosen_option_id=opt_ids[0],
                strength=5.0,
            )
            state, q = engine.submit_response(state, response, opt_ids)
        assert state.n_questions_asked == 3
        assert q is None  # No more questions

    def test_adds_timestamp(self):
        engine = make_engine()
        state, q = engine.start_session("u1", "s1")
        opt_ids = [o.item_id for o in q.options]
        response = Response(
            question_id=q.id, chosen_option_id=opt_ids[0], strength=5.0
        )
        new_state, _ = engine.submit_response(state, response, opt_ids)
        assert new_state.responses[-1].timestamp is not None


class TestQuestionSelection:
    def test_does_not_repeat_pairs(self):
        engine = make_engine(target=6)  # 4 items => 6 possible pairs
        state, q = engine.start_session("u1", "s1")
        seen = set()
        for i in range(6):
            opt_ids = [o.item_id for o in q.options]
            pair = frozenset(opt_ids)
            assert pair not in seen
            seen.add(pair)
            response = Response(
                question_id=q.id, chosen_option_id=opt_ids[0], strength=5.0
            )
            state, q = engine.submit_response(state, response, opt_ids)


class TestSummary:
    def test_progress_reports_correctly(self):
        engine = make_engine(target=3)
        state, q = engine.start_session("u1", "s1")
        progress = engine.get_progress(state)
        assert progress.n_answered == 0
        assert progress.target_questions == 3
        assert not progress.is_complete

    def test_ranking_after_consistent_answers(self):
        engine = make_engine(target=5)
        state, q = engine.start_session("u1", "s1")
        # Always prefer "a" when it appears
        for _ in range(5):
            opt_ids = [o.item_id for o in q.options]
            chosen = "a" if "a" in opt_ids else opt_ids[0]
            response = Response(
                question_id=q.id, chosen_option_id=chosen, strength=10.0
            )
            state, q = engine.submit_response(state, response, opt_ids)
        summary = engine.get_summary(state)
        # "a" should have the highest rank (rank 0)
        top = summary["values"][0]
        assert top["item_id"] == "a"
        assert summary["progress"]["is_complete"]
