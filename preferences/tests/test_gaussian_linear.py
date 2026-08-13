"""Tests for the Gaussian linear utility model."""

import numpy as np
import pytest

from preferences.model.common import flat_to_sigma, sigma_to_flat
from preferences.model.gaussian_linear import GaussianLinearUtilityModel
from preferences.types import (
    Evidence,
    EvidenceSource,
    PreferenceState,
    UnsupportedEvidenceError,
)


ITEMS = ["freedom", "security", "equality", "tradition", "innovation"]


def make_model() -> GaussianLinearUtilityModel:
    return GaussianLinearUtilityModel(
        prior_variance=1.0, base_noise_variance=0.25
    )


def make_state(model: GaussianLinearUtilityModel) -> PreferenceState:
    return model.initialize(user_id="u1", session_id="s1", item_ids=ITEMS)


def pairwise(item_a: str, item_b: str, value: float, **kwargs) -> Evidence:
    return Evidence(
        source=EvidenceSource.PAIRWISE,
        item_a=item_a,
        item_b=item_b,
        value=value,
        **kwargs,
    )


class TestInitialization:
    def test_prior_mean_is_zero(self):
        state = make_state(make_model())
        assert all(m == 0.0 for m in state.mu)

    def test_prior_variance_matches_identity(self):
        model = GaussianLinearUtilityModel(prior_variance=2.5)
        state = make_state(model)
        sigma = flat_to_sigma(state.sigma_flat, len(ITEMS))
        assert np.allclose(sigma, 2.5 * np.eye(len(ITEMS)))

    def test_state_preserves_item_ids(self):
        state = make_state(make_model())
        assert state.item_ids == ITEMS

    def test_initial_n_questions_is_zero(self):
        state = make_state(make_model())
        assert state.n_questions_asked == 0
        assert state.evidence == []

    def test_model_version(self):
        state = make_state(make_model())
        assert state.model_version == "gaussian_linear_v1"


class TestSigmaPacking:
    def test_sigma_roundtrip(self):
        n = 5
        rng = np.random.default_rng(42)
        a = rng.standard_normal((n, n))
        sigma = a @ a.T  # symmetric positive semidefinite
        flat = sigma_to_flat(sigma)
        sigma2 = flat_to_sigma(flat, n)
        assert np.allclose(sigma, sigma2)

    def test_flat_length(self):
        n = 5
        flat = sigma_to_flat(np.eye(n))
        assert len(flat) == n * (n + 1) // 2


class TestUpdate:
    def test_preferring_a_increases_mu_a(self):
        model = make_model()
        state = make_state(model)
        # User strongly prefers freedom over security
        new_state = model.update(state, pairwise("freedom", "security", 10.0))
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        assert new_state.mu[idx["freedom"]] > 0
        assert new_state.mu[idx["security"]] < 0
        assert new_state.mu[idx["freedom"]] > new_state.mu[idx["security"]]

    def test_negative_value_prefers_b(self):
        model = make_model()
        state = make_state(model)
        new_state = model.update(state, pairwise("freedom", "security", -10.0))
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        assert new_state.mu[idx["security"]] > new_state.mu[idx["freedom"]]

    def test_slider_source_shares_likelihood(self):
        model = make_model()
        state = make_state(model)
        ev_pair = pairwise("freedom", "security", 6.0)
        ev_slider = Evidence(
            source=EvidenceSource.SLIDER,
            item_a="freedom",
            item_b="security",
            value=6.0,
        )
        s1 = model.update(state, ev_pair)
        s2 = model.update(state, ev_slider)
        assert np.allclose(s1.mu, s2.mu)
        assert np.allclose(s1.sigma_flat, s2.sigma_flat)

    def test_update_reduces_uncertainty(self):
        model = make_model()
        state = make_state(model)
        pre_std = model.get_uncertainty(state, "freedom", "security")
        new_state = model.update(state, pairwise("freedom", "security", 8.0))
        post_std = model.get_uncertainty(new_state, "freedom", "security")
        assert post_std < pre_std

    def test_unrelated_items_barely_move(self):
        model = make_model()
        state = make_state(model)
        new_state = model.update(state, pairwise("freedom", "security", 10.0))
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        # Items not in the evidence should have mu still at zero
        assert abs(new_state.mu[idx["equality"]]) < 1e-10
        assert abs(new_state.mu[idx["tradition"]]) < 1e-10

    def test_multiple_consistent_updates_converge(self):
        """If the user always prefers freedom over security, the posterior gap
        should widen monotonically toward the observed gap."""
        model = make_model()
        state = make_state(model)
        gaps = []
        for i in range(10):
            state = model.update(
                state, pairwise("freedom", "security", 10.0, prompt_id=f"q{i}")
            )
            idx = {iid: i2 for i2, iid in enumerate(state.item_ids)}
            gaps.append(state.mu[idx["freedom"]] - state.mu[idx["security"]])
        # Monotone non-decreasing (Bayesian updates with consistent evidence)
        assert all(gaps[i + 1] >= gaps[i] - 1e-9 for i in range(len(gaps) - 1))
        # Eventually close to the observed gap (y = 1.0 per update)
        assert gaps[-1] > 0.5

    def test_strength_weight_affects_magnitude(self):
        """Higher |value| should produce a larger update."""
        model = make_model()
        state = make_state(model)
        state_strong = model.update(state, pairwise("freedom", "security", 10.0))
        state_weak = model.update(state, pairwise("freedom", "security", 2.0))
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        strong_gap = (
            state_strong.mu[idx["freedom"]] - state_strong.mu[idx["security"]]
        )
        weak_gap = state_weak.mu[idx["freedom"]] - state_weak.mu[idx["security"]]
        assert strong_gap > weak_gap
        assert weak_gap > 0  # still in the right direction

    def test_low_confidence_shrinks_update(self):
        model = make_model()
        state = make_state(model)
        full = model.update(state, pairwise("freedom", "security", 8.0))
        tentative = model.update(
            state, pairwise("freedom", "security", 8.0, confidence=0.2)
        )
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        assert (
            tentative.mu[idx["freedom"]] < full.mu[idx["freedom"]]
        )

    def test_increments_counter_and_trail(self):
        model = make_model()
        state = make_state(model)
        state2 = model.update(
            state, pairwise("freedom", "security", 5.0, prompt_id="q1")
        )
        assert state2.n_questions_asked == 1
        assert len(state2.evidence) == 1
        assert state2.asked_question_ids == ["q1"]

    def test_raises_on_unknown_item(self):
        model = make_model()
        state = make_state(model)
        with pytest.raises(ValueError, match="not found"):
            model.update(state, pairwise("freedom", "unknown_item", 5.0))

    def test_raises_on_out_of_range_value(self):
        model = make_model()
        state = make_state(model)
        with pytest.raises(ValueError, match="outside"):
            model.update(state, pairwise("freedom", "security", 11.0))

    def test_raises_on_non_training_source(self):
        model = make_model()
        state = make_state(model)
        ev = Evidence(
            source=EvidenceSource.OVERRIDE,
            item_a="freedom",
            item_b="security",
            value=5.0,
        )
        with pytest.raises(UnsupportedEvidenceError):
            model.update(state, ev)

    def test_raises_on_unconfirmed_extracted_source(self):
        model = make_model()
        state = make_state(model)
        ev = Evidence(
            source=EvidenceSource.FREE_TEXT_EXTRACTION,
            item_a="freedom",
            item_b="security",
            value=5.0,
        )
        with pytest.raises(UnsupportedEvidenceError, match="confirmed Phase 4C"):
            model.update(state, ev)

    def test_metadata_cannot_self_assert_confirmation(self):
        model = make_model()
        state = make_state(model)
        ev = Evidence(
            source=EvidenceSource.FREE_TEXT_EXTRACTION,
            item_a="freedom",
            item_b="security",
            value=5.0,
            event_id="evidence_forged",
            metadata={"phase4_participant_confirmed": True},
        )
        with pytest.raises(UnsupportedEvidenceError, match="confirmed Phase 4C"):
            model.update(state, ev)


class TestPrediction:
    def test_prior_predicts_50_50(self):
        model = make_model()
        state = make_state(model)
        p = model.predict_preference(state, "freedom", "security")
        assert abs(p - 0.5) < 1e-9

    def test_after_pro_a_update_predicts_a_wins(self):
        model = make_model()
        state = make_state(model)
        new_state = model.update(state, pairwise("freedom", "security", 10.0))
        p = model.predict_preference(new_state, "freedom", "security")
        assert p > 0.5

    def test_prediction_symmetry(self):
        model = make_model()
        state = make_state(model)
        new_state = model.update(state, pairwise("freedom", "security", 7.0))
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
