"""Tests for the probit item response model (delegation.comparison.irt)."""

from __future__ import annotations

import numpy as np
import pytest

from delegation.comparison.irt import (
    ItemParameters,
    PositionConfig,
    _truncated_normal,
    estimate_items,
    fit_factors,
    holdout_log_scores,
    holdout_mask,
    implied_correlation,
    sample_positions,
    simulate_answers,
    split_rhat,
    support_rates,
    tetrachoric_pair,
    thresholds,
    to_items,
)

FAST = PositionConfig(iterations=300, burn_in=100, thin=4, seed=1)


@pytest.fixture(scope="module")
def truth() -> ItemParameters:
    rng = np.random.default_rng(1)
    return ItemParameters(rng.normal(0, 0.8, (12, 2)), rng.normal(0, 0.7, 12))


@pytest.fixture(scope="module")
def answers(truth):
    return simulate_answers(truth, 6000, seed=3, missing_share=0.02)


def test_truncated_normal_respects_sides_and_tails():
    rng = np.random.default_rng(0)
    mean = np.array([-9.0, -2.0, 0.0, 2.0, 9.0] * 2000)
    positive = np.repeat([True, False], 5000)
    z = _truncated_normal(rng, mean, positive)
    assert np.isfinite(z).all()
    assert (z[positive] > 0).all() and (z[~positive] < 0).all()
    # Truncating N(0, 1) to z > 0 gives mean sqrt(2 / pi)
    centre = z[:5000][mean[:5000] == 0.0]
    assert centre.mean() == pytest.approx(np.sqrt(2 / np.pi), abs=0.05)


def test_tetrachoric_recovers_a_known_correlation():
    rng = np.random.default_rng(4)
    latent = rng.multivariate_normal([0, 0], [[1, 0.6], [0.6, 1]], size=20000)
    x = (latent[:, 0] < 0.3).astype(float)
    z = (latent[:, 1] < -0.5).astype(float)
    assert tetrachoric_pair(x, z) == pytest.approx(0.6, abs=0.03)


def test_thresholds_match_support_rates(answers):
    y, _ = answers
    rate = np.nanmean(y, axis=0)
    from scipy.stats import norm

    assert np.allclose(norm.cdf(thresholds(y)), rate)


def test_validation_rejects_bad_answers():
    with pytest.raises(ValueError):
        thresholds(np.array([[0.0, 2.0]]))


def test_items_are_recovered(truth, answers):
    y, _ = answers
    items, factors, _ = estimate_items(y, 2)
    upper = np.triu_indices(12, 1)
    corr_error = np.abs(
        implied_correlation(items.loadings) - implied_correlation(truth.loadings)
    )[upper]
    assert corr_error.max() < 0.06
    rate_error = support_rates(items.loadings, items.intercepts) - support_rates(
        truth.loadings, truth.intercepts
    )
    assert np.abs(rate_error).max() < 0.02
    assert factors.capped == ()


def test_conversion_round_trips(truth):
    # Standardise the true loadings, convert back, and recover (a, b)
    norm = np.sqrt(1 + (truth.loadings**2).sum(axis=1))
    lam = truth.loadings / norm[:, None]
    tau = truth.intercepts / norm
    from delegation.comparison.irt import FactorFit

    back = to_items(FactorFit(lam, 0.0, ()), tau)
    assert np.allclose(back.loadings, truth.loadings)
    assert np.allclose(back.intercepts, truth.intercepts)


def test_factor_fit_keeps_communality_below_one():
    corr = np.full((4, 4), 0.999)
    np.fill_diagonal(corr, 1.0)
    fit = fit_factors(corr, 1)
    communality = (fit.loadings**2).sum(axis=1)
    # The ridge keeps a near-Heywood solution finite instead of clipping it
    assert (communality < 1.0).all() and (communality > 0.95).all()


def test_factor_fit_residual_never_rises_with_k(truth, answers):
    y, _ = answers
    from delegation.comparison.irt import tetrachoric_matrix

    corr = tetrachoric_matrix(y)
    rmsr = [fit_factors(corr, k).rmsr for k in (1, 2, 3, 4)]
    assert all(later <= earlier + 1e-6 for earlier, later in zip(rmsr, rmsr[1:]))


def test_positions_track_the_truth(truth, answers):
    y, theta = answers
    draws = sample_positions(y, truth, FAST)
    estimate = draws.mean(axis=0)
    for d in range(2):
        assert np.corrcoef(estimate[:, d], theta[:, d])[0, 1] > 0.7
    # Posterior draws keep the population's spread (plausible values)
    assert draws[-1].std(axis=0) == pytest.approx([1.0, 1.0], abs=0.1)


def test_positions_are_deterministic(truth, answers):
    y, _ = answers
    a = sample_positions(y[:200], truth, FAST)
    b = sample_positions(y[:200], truth, FAST)
    assert np.array_equal(a, b)


def test_split_rhat_flags_disagreeing_chains():
    rng = np.random.default_rng(0)
    same = rng.standard_normal((2, 200, 3))
    assert split_rhat(same).max() < 1.05
    apart = same + np.array([0.0, 3.0])[:, None, None]
    assert split_rhat(apart).min() > 1.5


def test_holdout_prefers_the_true_dimension(truth, answers):
    y, _ = answers
    mask = holdout_mask(y, 0.1, seed=5)
    assert not (mask & np.isnan(y)).any()
    hidden = y.copy()
    hidden[mask] = np.nan
    scores = {}
    for k in (1, 2):
        items, _, _ = estimate_items(hidden, k)
        scores[k] = holdout_log_scores(y, mask, items, sample_positions(hidden, items, FAST)).mean()
    assert scores[2] > scores[1]
