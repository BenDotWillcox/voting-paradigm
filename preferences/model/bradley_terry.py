"""
Bradley-Terry preference model with a Laplace-approximated Gaussian posterior.

Model:
    Each item i has a latent utility u_i for this user.
    Prior: u ~ N(0, prior_variance * I)
    Likelihood (per evidence about pair (a, b) with signed value v):
        the *direction* of v is a Bernoulli choice under the logistic link,
            P(a chosen over b) = sigmoid(u_a - u_b)
        and |v| / 10 (scaled by evidence confidence) is the per-observation
        weight — a strong slider position counts as a more informative
        observation, a hesitant one counts less.

This is the canonical classical pairwise-ranking baseline. Unlike the
Gaussian linear model (which consumes the slider value as a continuous
observation of the utility gap), Bradley-Terry only uses the sign of the
response plus a weight, so it makes weaker assumptions about what the slider
magnitude means. Stated indifference (v = 0) is handled as a symmetric
half-weight observation in each direction, which pulls u_a - u_b toward 0.

Inference:
    The weighted log-posterior is strictly concave, so the MAP is found by a
    few Newton iterations refit from the full evidence history on every
    update (the fixed bank is small; this is exact-history, order-independent
    inference rather than an approximate online filter). The posterior is
    approximated as Gaussian around the MAP with covariance equal to the
    inverse Hessian of the negative log-posterior (Laplace approximation).
"""

import numpy as np
from scipy.special import expit, log_expit

from ..types import Evidence, ItemId, PreferenceState
from .common import (
    flat_to_sigma,
    normalize_pairwise_evidence,
    posterior_diff_stats,
    sigma_to_flat,
)


class BradleyTerryLaplaceModel:
    """Bradley-Terry model over a fixed item bank, Laplace posterior.

    Attributes:
        prior_variance: variance of the N(0, sigma_p^2) prior on each u_i.
        min_strength_weight: floor on the observation weight (see
            ``normalize_pairwise_evidence``).
        max_newton_iters / newton_tol: MAP optimizer controls. The objective
            is strictly concave, so Newton converges in a handful of steps.
    """

    model_version = "bradley_terry_laplace_v1"

    def __init__(
        self,
        prior_variance: float = 1.0,
        min_strength_weight: float = 0.05,
        max_newton_iters: int = 50,
        newton_tol: float = 1e-8,
    ):
        self.prior_variance = prior_variance
        self.min_strength_weight = min_strength_weight
        self.max_newton_iters = max_newton_iters
        self.newton_tol = newton_tol

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
        """Refit the MAP + Laplace posterior from the full evidence history.

        The new evidence is validated against the state's item universe first
        so a bad observation fails loudly instead of poisoning the refit.
        """
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        # Validate eagerly (raises on unsupported source / unknown items).
        normalize_pairwise_evidence(evidence, idx, self.min_strength_weight)

        all_evidence = list(state.evidence) + [evidence]
        mu, sigma = self._fit(state.item_ids, all_evidence)

        new_asked = list(state.asked_question_ids)
        if evidence.prompt_id is not None:
            new_asked.append(evidence.prompt_id)

        return PreferenceState(
            user_id=state.user_id,
            session_id=state.session_id,
            item_ids=state.item_ids,
            mu=mu.tolist(),
            sigma_flat=sigma_to_flat(sigma),
            evidence=all_evidence,
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
        """Return P(user prefers item_a over item_b).

        Approximates the posterior-predictive integral of the logistic link
        over the Gaussian posterior with the standard probit-matching
        correction: E[sigmoid(d)] ~= sigmoid(mu_d / sqrt(1 + pi * var_d / 8)).
        """
        mean_diff, std_diff = posterior_diff_stats(state, item_a, item_b)
        kappa = 1.0 / np.sqrt(1.0 + np.pi * std_diff**2 / 8.0)
        return float(expit(kappa * mean_diff))

    def get_uncertainty(
        self,
        state: PreferenceState,
        item_a: ItemId,
        item_b: ItemId,
    ) -> float:
        """Return posterior std of (u_a - u_b) under the Laplace posterior."""
        _, std_diff = posterior_diff_stats(state, item_a, item_b)
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
    # Internal: MAP fit + Laplace covariance
    # ------------------------------------------------------------------

    def _fit(
        self,
        item_ids: list[ItemId],
        evidence_list: list[Evidence],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Newton MAP fit over the whole history, then Laplace covariance."""
        n = len(item_ids)
        idx = {iid: i for i, iid in enumerate(item_ids)}
        prior_precision = 1.0 / self.prior_variance

        # Normalize each evidence into (i_a, i_b, soft_label, weight):
        # soft_label p = 1 (a preferred), 0 (b preferred), 0.5 (indifferent).
        # The weighted cross-entropy w * [p*log(sig(d)) + (1-p)*log(1-sig(d))]
        # covers all three cases with one concave objective.
        obs: list[tuple[int, int, float, float]] = []
        for ev in evidence_list:
            i_a, i_b, signed_gap, weight = normalize_pairwise_evidence(
                ev, idx, self.min_strength_weight
            )
            if signed_gap > 0:
                p = 1.0
            elif signed_gap < 0:
                p = 0.0
            else:
                p = 0.5
            obs.append((i_a, i_b, p, weight))

        u = np.zeros(n)
        if not obs:
            return u, self.prior_variance * np.eye(n)

        a_idx = np.array([o[0] for o in obs])
        b_idx = np.array([o[1] for o in obs])
        labels = np.array([o[2] for o in obs])
        weights = np.array([o[3] for o in obs])

        hessian = np.eye(n)  # placeholder; set inside the loop
        for _ in range(self.max_newton_iters):
            d = u[a_idx] - u[b_idx]
            s = expit(d)

            # Gradient of the log-posterior.
            resid = weights * (labels - s)  # per-observation d(loglik)/dd
            grad = -prior_precision * u
            np.add.at(grad, a_idx, resid)
            np.add.at(grad, b_idx, -resid)

            # Hessian of the negative log-posterior (positive definite).
            lam = weights * s * (1.0 - s)  # per-observation curvature
            hessian = prior_precision * np.eye(n)
            np.add.at(hessian, (a_idx, a_idx), lam)
            np.add.at(hessian, (b_idx, b_idx), lam)
            np.add.at(hessian, (a_idx, b_idx), -lam)
            np.add.at(hessian, (b_idx, a_idx), -lam)

            step = np.linalg.solve(hessian, grad)
            u = u + step
            if float(np.max(np.abs(step))) < self.newton_tol:
                break

        # Recompute the Hessian at the converged MAP for the Laplace cov.
        d = u[a_idx] - u[b_idx]
        s = expit(d)
        lam = weights * s * (1.0 - s)
        hessian = prior_precision * np.eye(n)
        np.add.at(hessian, (a_idx, a_idx), lam)
        np.add.at(hessian, (b_idx, b_idx), lam)
        np.add.at(hessian, (a_idx, b_idx), -lam)
        np.add.at(hessian, (b_idx, a_idx), -lam)

        sigma = np.linalg.inv(hessian)
        sigma = 0.5 * (sigma + sigma.T)  # symmetrize numerical drift
        return u, sigma

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def log_likelihood(
        self,
        state: PreferenceState,
        evidence_list: list[Evidence],
    ) -> float:
        """Weighted log-likelihood of held-out evidence at the MAP estimate.

        Diagnostic helper for the eval harness; not part of the model
        protocol.
        """
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        mu = np.array(state.mu)
        total = 0.0
        for ev in evidence_list:
            i_a, i_b, signed_gap, weight = normalize_pairwise_evidence(
                ev, idx, self.min_strength_weight
            )
            d = mu[i_a] - mu[i_b]
            if signed_gap > 0:
                total += weight * float(log_expit(d))
            elif signed_gap < 0:
                total += weight * float(log_expit(-d))
            else:
                total += weight * 0.5 * float(log_expit(d) + log_expit(-d))
        return total
