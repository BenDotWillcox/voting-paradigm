"""Tests for the Thurstone pairwise preference model."""

import numpy as np
import pytest

from preferences.model.thurstone import ThurstonePairwiseModel
from preferences.types import PreferenceState, Response


ITEMS = ["freedom", "security", "equality", "tradition", "innovation"]


def make_model() -> ThurstonePairwiseModel:
    return ThurstonePairwiseModel(prior_variance=1.0, base_noise_variance=0.25)


def make_state(model: ThurstonePairwiseModel) -> PreferenceState:
    return model.initialize(user_id="u1", session_id="s1", item_ids=ITEMS)


class TestInitialization:
    def test_prior_mean_is_zero(self):
        state = make_state(make_model())
        assert all(m == 0.0 for m in state.mu)

    def test_prior_variance_matches_identity(self):
        model = ThurstonePairwiseModel(prior_variance=2.5)
        state = make_state(model)
        sigma = model._flat_to_sigma(state.sigma_flat, len(ITEMS))
        assert np.allclose(sigma, 2.5 * np.eye(len(ITEMS)))

    def test_state_preserves_item_ids(self):
        state = make_state(make_model())
        assert state.item_ids == ITEMS

    def test_initial_n_questions_is_zero(self):
        state = make_state(make_model())
        assert state.n_questions_asked == 0
        assert state.responses == []


class TestSerialization:
    def test_sigma_roundtrip(self):
        model = make_model()
        n = 5
        rng = np.random.default_rng(42)
        a = rng.standard_normal((n, n))
        sigma = a @ a.T  # symmetric positive semidefinite
        flat = model._sigma_to_flat(sigma)
        sigma2 = model._flat_to_sigma(flat, n)
        assert np.allclose(sigma, sigma2)

    def test_flat_length(self):
        model = make_model()
        n = 5
        sigma = np.eye(n)
        flat = model._sigma_to_flat(sigma)
        assert len(flat) == n * (n + 1) // 2


class TestUpdate:
    def test_preferring_a_increases_mu_a(self):
        model = make_model()
        state = make_state(model)
        # User strongly prefers freedom over security
        resp = Response(
            question_id="q1",
            chosen_option_id="freedom",
            strength=10.0,
        )
        new_state = model.update(state, resp, ["freedom", "security"])
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        assert new_state.mu[idx["freedom"]] > 0
        assert new_state.mu[idx["security"]] < 0
        assert new_state.mu[idx["freedom"]] > new_state.mu[idx["security"]]

    def test_preferring_b_decreases_mu_a(self):
        model = make_model()
        state = make_state(model)
        resp = Response(
            question_id="q1",
            chosen_option_id="security",
            strength=10.0,
        )
        new_state = model.update(state, resp, ["freedom", "security"])
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        assert new_state.mu[idx["security"]] > new_state.mu[idx["freedom"]]

    def test_update_reduces_uncertainty(self):
        model = make_model()
        state = make_state(model)
        pre_std = model.get_uncertainty(state, "freedom", "security")
        resp = Response(
            question_id="q1",
            chosen_option_id="freedom",
            strength=8.0,
        )
        new_state = model.update(state, resp, ["freedom", "security"])
        post_std = model.get_uncertainty(new_state, "freedom", "security")
        assert post_std < pre_std

    def test_unrelated_items_barely_move(self):
        model = make_model()
        state = make_state(model)
        resp = Response(
            question_id="q1",
            chosen_option_id="freedom",
            strength=10.0,
        )
        new_state = model.update(state, resp, ["freedom", "security"])
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        # Items not in the question should have mu still at zero
        assert abs(new_state.mu[idx["equality"]]) < 1e-10
        assert abs(new_state.mu[idx["tradition"]]) < 1e-10

    def test_multiple_consistent_updates_converge(self):
        """If the user always prefers freedom over security, mu_freedom should
        grow with each update and the gap should widen."""
        model = make_model()
        state = make_state(model)
        gaps = []
        for i in range(10):
            resp = Response(
                question_id=f"q{i}",
                chosen_option_id="freedom",
                strength=10.0,
            )
            state = model.update(state, resp, ["freedom", "security"])
            idx = {iid: i2 for i2, iid in enumerate(state.item_ids)}
            gaps.append(state.mu[idx["freedom"]] - state.mu[idx["security"]])
        # Monotone non-decreasing (Bayesian updates with consistent evidence)
        assert all(gaps[i + 1] >= gaps[i] - 1e-9 for i in range(len(gaps) - 1))
        # Eventually close to the observed gap (y = 1.0 per update)
        assert gaps[-1] > 0.5

    def test_strength_weight_affects_magnitude(self):
        """Higher strength should produce a larger update."""
        model = make_model()
        state = make_state(model)
        resp_strong = Response(
            question_id="q1", chosen_option_id="freedom", strength=10.0
        )
        resp_weak = Response(
            question_id="q1", chosen_option_id="freedom", strength=2.0
        )
        state_strong = model.update(state, resp_strong, ["freedom", "security"])
        state_weak = model.update(state, resp_weak, ["freedom", "security"])
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        strong_gap = (
            state_strong.mu[idx["freedom"]] - state_strong.mu[idx["security"]]
        )
        weak_gap = state_weak.mu[idx["freedom"]] - state_weak.mu[idx["security"]]
        assert strong_gap > weak_gap
        assert weak_gap > 0  # still in the right direction

    def test_increments_counter(self):
        model = make_model()
        state = make_state(model)
        resp = Response(
            question_id="q1", chosen_option_id="freedom", strength=5.0
        )
        state2 = model.update(state, resp, ["freedom", "security"])
        assert state2.n_questions_asked == 1
        assert len(state2.responses) == 1
        assert state2.asked_question_ids == ["q1"]

    def test_raises_on_unknown_item(self):
        model = make_model()
        state = make_state(model)
        resp = Response(
            question_id="q1", chosen_option_id="freedom", strength=5.0
        )
        with pytest.raises(ValueError, match="not found"):
            model.update(state, resp, ["freedom", "unknown_item"])

    def test_raises_on_bad_chosen_id(self):
        model = make_model()
        state = make_state(model)
        resp = Response(
            question_id="q1", chosen_option_id="tradition", strength=5.0
        )
        with pytest.raises(ValueError, match="not in options"):
            model.update(state, resp, ["freedom", "security"])


class TestPrediction:
    def test_prior_predicts_50_50(self):
        model = make_model()
        state = make_state(model)
        p = model.predict_preference(state, "freedom", "security")
        assert abs(p - 0.5) < 1e-9

    def test_after_pro_a_update_predicts_a_wins(self):
        model = make_model()
        state = make_state(model)
        resp = Response(
            question_id="q1", chosen_option_id="freedom", strength=10.0
        )
        new_state = model.update(state, resp, ["freedom", "security"])
        p = model.predict_preference(new_state, "freedom", "security")
        assert p > 0.5

    def test_prediction_symmetry(self):
        model = make_model()
        state = make_state(model)
        resp = Response(
            question_id="q1", chosen_option_id="freedom", strength=7.0
        )
        new_state = model.update(state, resp, ["freedom", "security"])
        p_ab = model.predict_preference(new_state, "freedom", "security")
        p_ba = model.predict_preference(new_state, "security", "freedom")
        assert abs((p_ab + p_ba) - 1.0) < 1e-6


class TestUtilityEstimates:
    def test_returns_all_items(self):
        model = make_model()
        state = make_state(model)
        est = model.get_utility_estimates(state)
        assert set(est.keys()) == set(ITEMS)
        for _iid, (mean, std) in est.items():
            assert mean == 0.0
            assert std == pytest.approx(1.0)  # sqrt(prior_variance)
