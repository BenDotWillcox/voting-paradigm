"""Tests for the Bradley-Terry + Laplace preference model."""

import numpy as np
import pytest

from preferences.model.bradley_terry import BradleyTerryLaplaceModel
from preferences.model.common import flat_to_sigma
from preferences.types import (
    Evidence,
    EvidenceSource,
    PreferenceState,
    UnsupportedEvidenceError,
)

ITEMS = ["freedom", "security", "equality", "tradition", "innovation"]


def make_model() -> BradleyTerryLaplaceModel:
    return BradleyTerryLaplaceModel(prior_variance=1.0)


def make_state(model: BradleyTerryLaplaceModel) -> PreferenceState:
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
    def test_prior_is_zero_mean_identity_cov(self):
        model = BradleyTerryLaplaceModel(prior_variance=2.0)
        state = make_state(model)
        assert all(m == 0.0 for m in state.mu)
        sigma = flat_to_sigma(state.sigma_flat, len(ITEMS))
        assert np.allclose(sigma, 2.0 * np.eye(len(ITEMS)))

    def test_model_version(self):
        state = make_state(make_model())
        assert state.model_version == "bradley_terry_laplace_v1"


class TestUpdate:
    def test_preferring_a_increases_mu_a(self):
        model = make_model()
        state = make_state(model)
        new_state = model.update(state, pairwise("freedom", "security", 10.0))
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        assert new_state.mu[idx["freedom"]] > 0
        assert new_state.mu[idx["security"]] < 0

    def test_negative_value_prefers_b(self):
        model = make_model()
        state = make_state(model)
        new_state = model.update(state, pairwise("freedom", "security", -8.0))
        idx = {iid: i for i, iid in enumerate(new_state.item_ids)}
        assert new_state.mu[idx["security"]] > new_state.mu[idx["freedom"]]

    def test_update_reduces_uncertainty(self):
        model = make_model()
        state = make_state(model)
        pre_std = model.get_uncertainty(state, "freedom", "security")
        new_state = model.update(state, pairwise("freedom", "security", 8.0))
        post_std = model.get_uncertainty(new_state, "freedom", "security")
        assert post_std < pre_std

    def test_strength_only_weights_the_direction(self):
        """Stronger slider = larger weight = bigger MAP gap."""
        model = make_model()
        state = make_state(model)
        strong = model.update(state, pairwise("freedom", "security", 10.0))
        weak = model.update(state, pairwise("freedom", "security", 2.0))
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        strong_gap = strong.mu[idx["freedom"]] - strong.mu[idx["security"]]
        weak_gap = weak.mu[idx["freedom"]] - weak.mu[idx["security"]]
        assert strong_gap > weak_gap > 0

    def test_indifference_pulls_items_together(self):
        """value = 0 is a symmetric observation shrinking the gap."""
        model = make_model()
        state = make_state(model)
        # Build up a gap first, then observe indifference repeatedly.
        state = model.update(state, pairwise("freedom", "security", 10.0))
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        gap_before = state.mu[idx["freedom"]] - state.mu[idx["security"]]
        for _ in range(20):
            state = model.update(state, pairwise("freedom", "security", 0.0))
        gap_after = state.mu[idx["freedom"]] - state.mu[idx["security"]]
        assert abs(gap_after) < abs(gap_before)

    def test_order_independence(self):
        """Refit-from-history inference: evidence order must not matter."""
        model = make_model()
        state = make_state(model)
        evs = [
            pairwise("freedom", "security", 8.0),
            pairwise("equality", "tradition", -5.0),
            pairwise("freedom", "equality", 3.0),
        ]
        s_fwd = state
        for ev in evs:
            s_fwd = model.update(s_fwd, ev)
        s_rev = state
        for ev in reversed(evs):
            s_rev = model.update(s_rev, ev)
        assert np.allclose(s_fwd.mu, s_rev.mu, atol=1e-6)
        assert np.allclose(s_fwd.sigma_flat, s_rev.sigma_flat, atol=1e-6)

    def test_consistent_updates_grow_gap(self):
        model = make_model()
        state = make_state(model)
        gaps = []
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        for i in range(8):
            state = model.update(
                state, pairwise("freedom", "security", 10.0, prompt_id=f"q{i}")
            )
            gaps.append(state.mu[idx["freedom"]] - state.mu[idx["security"]])
        assert all(gaps[i + 1] >= gaps[i] - 1e-9 for i in range(len(gaps) - 1))
        assert gaps[-1] > 0.5

    def test_raises_on_unknown_item(self):
        model = make_model()
        state = make_state(model)
        with pytest.raises(ValueError, match="not found"):
            model.update(state, pairwise("freedom", "nope", 5.0))

    def test_raises_on_unimplemented_source(self):
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

    def test_posterior_uncertainty_moderates_prediction(self):
        """Same MAP gap with more uncertainty => prediction closer to 0.5."""
        model = make_model()
        state = make_state(model)
        s1 = model.update(state, pairwise("freedom", "security", 10.0))
        # Manually inflate the posterior variance and re-predict.
        n = len(ITEMS)
        inflated = PreferenceState(
            user_id=s1.user_id,
            session_id=s1.session_id,
            item_ids=s1.item_ids,
            mu=s1.mu,
            sigma_flat=[4.0 * v for v in s1.sigma_flat],
            evidence=s1.evidence,
            n_questions_asked=s1.n_questions_asked,
            asked_question_ids=s1.asked_question_ids,
            model_version=s1.model_version,
        )
        p_tight = model.predict_preference(s1, "freedom", "security")
        p_loose = model.predict_preference(inflated, "freedom", "security")
        assert 0.5 < p_loose < p_tight


class TestUtilityEstimates:
    def test_returns_all_items(self):
        model = make_model()
        state = make_state(model)
        est = model.get_utility_estimates(state)
        assert set(est.keys()) == set(ITEMS)
