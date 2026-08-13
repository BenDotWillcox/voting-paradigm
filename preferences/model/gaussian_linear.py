"""
Gaussian linear utility model with exact conjugate posterior updates.

Model:
    Each item i has a latent utility u_i for this user.
    Prior: u ~ N(0, prior_variance * I)
    Likelihood: evidence about a pair (a, b) with signed value v in [-10, 10]
        is treated as a noisy continuous observation of the utility gap:
        (u_a - u_b) ~ N(v / 10, sigma_obs^2 / weight)

Because both prior and likelihood are Gaussian with a linear observation
model, the posterior is exactly Gaussian and each update is a closed-form
rank-1 (Kalman-style) update — no approximation is involved.

Naming note: this class was previously called ``ThurstonePairwiseModel``.
That name was wrong. Thurstone's Case V models a *binary* choice via a probit
link, P(a > b) = Phi((u_a - u_b) / sigma). This model instead consumes the
slider's *continuous* signed strength directly as a Gaussian observation of
the gap — a Gaussian linear (Bayesian linear-regression-style) model. The
probit-flavored baseline in this package is ``BradleyTerryLaplaceModel``
(logistic rather than probit link).

The evidence weight provides noise scaling: |value| near 10 with confidence
1.0 => high-information observation (low noise); |value| near 0 or low
evidence confidence => high noise.
"""

import numpy as np

from ..types import Evidence, ItemId, PreferenceState
from .common import (
    flat_to_sigma,
    normalize_pairwise_evidence,
    posterior_diff_stats,
    sigma_to_flat,
)


class GaussianLinearUtilityModel:
    """Gaussian linear utility model over a fixed item bank.

    Attributes:
        prior_variance: variance of the N(0, sigma_p^2) prior on each u_i.
        base_noise_variance: observation noise when weight = 1 (|value| = 10,
            confidence = 1). For lower weight, noise scales inversely:
            sigma_obs^2 / weight.
        min_strength_weight: floor on the observation weight so that a
            zero-strength (indifference) response still carries a weak
            pull of the gap toward zero instead of infinite noise.
    """

    model_version = "gaussian_linear_v1"

    def __init__(
        self,
        prior_variance: float = 1.0,
        base_noise_variance: float = 0.25,
        min_strength_weight: float = 0.05,
    ):
        self.prior_variance = prior_variance
        self.base_noise_variance = base_noise_variance
        self.min_strength_weight = min_strength_weight

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def initialize(
        self,
        user_id: str,
        session_id: str,
        item_ids: list[ItemId],
    ) -> PreferenceState:
        n = len(item_ids)
        mu = np.zeros(n)
        sigma = self.prior_variance * np.eye(n)
        return PreferenceState(
            user_id=user_id,
            session_id=session_id,
            item_ids=list(item_ids),
            mu=mu.tolist(),
            sigma_flat=sigma_to_flat(sigma),
            evidence=[],
            n_questions_asked=0,
            asked_question_ids=[],
            model_version=self.model_version,
        )

    def update(
        self,
        state: PreferenceState,
        evidence: Evidence,
    ) -> PreferenceState:
        """Exact conjugate update for one piece of pairwise/slider evidence.

        Observation model: (u_a - u_b) ~ N(y, sigma_obs^2) with
        y = evidence.value / 10 and sigma_obs^2 = base_noise_variance / weight.

        One-dimensional Gaussian update via Kalman-style formulas:
            h = e_a - e_b  (the observation direction)
            K = Sigma @ h / (h.T @ Sigma @ h + sigma_obs^2)
            mu_new = mu + K * (y - h.T @ mu)
            Sigma_new = Sigma - K @ (h.T @ Sigma)
        """
        n = len(state.item_ids)
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        i_a, i_b, y, weight = normalize_pairwise_evidence(
            evidence, idx, self.min_strength_weight
        )

        mu = np.array(state.mu)
        sigma = flat_to_sigma(state.sigma_flat, n)
        sigma_obs2 = self.base_noise_variance / weight

        h = np.zeros(n)
        h[i_a] = 1.0
        h[i_b] = -1.0

        sigma_h = sigma @ h  # shape (n,)
        denom = float(h @ sigma_h) + sigma_obs2
        k = sigma_h / denom  # Kalman gain, shape (n,)

        innovation = y - float(h @ mu)
        new_mu = mu + k * innovation
        new_sigma = sigma - np.outer(k, sigma_h)
        # Symmetrize to counter tiny numerical drift
        new_sigma = 0.5 * (new_sigma + new_sigma.T)

        new_asked = list(state.asked_question_ids)
        if evidence.prompt_id is not None:
            new_asked.append(evidence.prompt_id)

        return PreferenceState(
            user_id=state.user_id,
            session_id=state.session_id,
            item_ids=state.item_ids,
            mu=new_mu.tolist(),
            sigma_flat=sigma_to_flat(new_sigma),
            evidence=list(state.evidence) + [evidence],
            n_questions_asked=state.n_questions_asked + 1,
            asked_question_ids=new_asked,
            model_version=self.model_version,
        )

    def predict_preference(
        self,
        state: PreferenceState,
        item_a: ItemId,
        item_b: ItemId,
    ) -> float:
        """Return P(u_a > u_b) under the current Gaussian posterior."""
        from scipy.stats import norm

        mean_diff, std_diff = self._diff_stats(state, item_a, item_b)
        if std_diff == 0:
            return 1.0 if mean_diff > 0 else (0.0 if mean_diff < 0 else 0.5)
        return float(norm.cdf(mean_diff / std_diff))

    def get_uncertainty(
        self,
        state: PreferenceState,
        item_a: ItemId,
        item_b: ItemId,
    ) -> float:
        """Return posterior std of (u_a - u_b)."""
        _, std_diff = self._diff_stats(state, item_a, item_b)
        return std_diff

    def get_utility_estimates(
        self,
        state: PreferenceState,
    ) -> dict[ItemId, tuple[float, float]]:
        n = len(state.item_ids)
        sigma = flat_to_sigma(state.sigma_flat, n)
        result: dict[ItemId, tuple[float, float]] = {}
        for i, iid in enumerate(state.item_ids):
            result[iid] = (float(state.mu[i]), float(np.sqrt(max(sigma[i, i], 0.0))))
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _diff_stats(
        self,
        state: PreferenceState,
        item_a: ItemId,
        item_b: ItemId,
    ) -> tuple[float, float]:
        return posterior_diff_stats(state, item_a, item_b)
