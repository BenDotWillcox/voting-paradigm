"""Tests for the ElicitationEngine."""

import pytest

from preferences.engine import ElicitationEngine, EngineConfig
from preferences.model.bradley_terry import BradleyTerryLaplaceModel
from preferences.model.gaussian_linear import GaussianLinearUtilityModel
from preferences.questions.bank import Item, QuestionBank
from preferences.types import Evidence, EvidenceSource


def small_bank() -> QuestionBank:
    return QuestionBank(
        items=[
            Item(id="a", text="Alpha", description="a", domain="d"),
            Item(id="b", text="Beta", description="b", domain="d"),
            Item(id="c", text="Gamma", description="c", domain="d"),
            Item(id="d", text="Delta", description="d", domain="d"),
        ]
    )


def make_engine(target: int = 3, policy: str = "max_variance") -> ElicitationEngine:
    return ElicitationEngine(
        model=GaussianLinearUtilityModel(),
        question_bank=small_bank(),
        config=EngineConfig(
            target_questions=target, seed=42, selection_policy=policy
        ),
    )


def evidence_for(question, value: float = 8.0) -> Evidence:
    opt_ids = [o.item_id for o in question.options]
    return Evidence(
        source=EvidenceSource.PAIRWISE,
        item_a=opt_ids[0],
        item_b=opt_ids[1],
        value=value,
        prompt_id=question.id,
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


class TestSubmitEvidence:
    def test_first_evidence_updates_state(self):
        engine = make_engine()
        state, q = engine.start_session("u1", "s1")
        new_state, next_q = engine.submit_evidence(state, evidence_for(q))
        assert new_state.n_questions_asked == 1
        assert next_q is not None

    def test_session_ends_at_target(self):
        engine = make_engine(target=3)
        state, q = engine.start_session("u1", "s1")
        for _ in range(3):
            state, q = engine.submit_evidence(state, evidence_for(q, 5.0))
        assert state.n_questions_asked == 3
        assert q is None  # No more questions

    def test_adds_timestamp(self):
        engine = make_engine()
        state, q = engine.start_session("u1", "s1")
        new_state, _ = engine.submit_evidence(state, evidence_for(q))
        assert new_state.evidence[-1].timestamp is not None

    def test_rejects_state_from_other_model_family(self):
        engine = make_engine()
        bt_state = BradleyTerryLaplaceModel().initialize(
            "u1", "s1", small_bank().item_ids()
        )
        ev = Evidence(
            source=EvidenceSource.PAIRWISE, item_a="a", item_b="b", value=5.0
        )
        with pytest.raises(ValueError, match="engine is running"):
            engine.submit_evidence(bt_state, ev)


class TestQuestionSelection:
    @pytest.mark.parametrize("policy", ["random", "max_variance"])
    def test_does_not_repeat_pairs(self, policy):
        engine = make_engine(target=6, policy=policy)  # 4 items => 6 pairs
        state, q = engine.start_session("u1", "s1")
        seen = set()
        for _ in range(6):
            pair = frozenset(o.item_id for o in q.options)
            assert pair not in seen
            seen.add(pair)
            state, q = engine.submit_evidence(state, evidence_for(q, 5.0))

    def test_max_variance_is_deterministic(self):
        """Same answers => same question sequence, regardless of RNG."""
        sequences = []
        for run_seed in (1, 2):
            engine = ElicitationEngine(
                model=GaussianLinearUtilityModel(),
                question_bank=small_bank(),
                config=EngineConfig(
                    target_questions=4,
                    seed=run_seed,
                    selection_policy="max_variance",
                ),
            )
            state, q = engine.start_session("u1", "s1")
            seq = [q.id]
            for _ in range(3):
                state, q = engine.submit_evidence(state, evidence_for(q, 6.0))
                seq.append(q.id if q else None)
            sequences.append(seq)
        assert sequences[0] == sequences[1]


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
            if "a" in opt_ids:
                value = 10.0 if opt_ids[0] == "a" else -10.0
            else:
                value = 5.0
            ev = Evidence(
                source=EvidenceSource.PAIRWISE,
                item_a=opt_ids[0],
                item_b=opt_ids[1],
                value=value,
                prompt_id=q.id,
            )
            state, q = engine.submit_evidence(state, ev)
        summary = engine.get_summary(state)
        # "a" should have the highest rank (rank 0)
        top = summary["values"][0]
        assert top["item_id"] == "a"
        assert summary["progress"]["is_complete"]
