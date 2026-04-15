"""
Thurstone pairwise preference model with Laplace-approximated Gaussian posterior.

Model:
    Each item i has a latent utility u_i for this user.
    Prior: u ~ N(0, prior_variance * I)
    Likelihood (pairwise): if user prefers A over B with strength s,
        we observe a noisy signal that (u_A - u_B) ~ N(s, sigma_obs^2 / weight)

Because both prior and observation are Gaussian with a linear observation model,
the posterior is exactly Gaussian (no Laplace approximation needed for the
Gaussian-observation version). We use strength/10 as a continuous observation
rather than a binary probit, since the PreferenceSlider gives us fine-grained
preference intensity directly.

This is faster, simpler, and the equations are cleaner than probit. The strength
field provides the noise weighting: |strength| close to 10 => high confidence
observation (low noise); |strength| close to 0 => low confidence (high noise).
"""

import numpy as np

from ..types import ItemId, PreferenceState, Response


class ThurstonePairwiseModel:
    """Gaussian-observation Thurstone model.

    Attributes:
        prior_variance: variance of the N(0, sigma_p^2) prior on each u_i.
        base_noise_variance: observation noise when strength = +/-10 (certain).
            For lower |strength|, noise scales inversely: sigma_obs^2 / (|s|/10 + eps).
    """

    model_version = "thurstone_v1"

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
    # Serialization helpers (Sigma <-> flat lower triangle)
    # ------------------------------------------------------------------

    @staticmethod
    def _sigma_to_flat(sigma: np.ndarray) -> list[float]:
        """Pack lower-triangle (including diagonal) row-major."""
        n = sigma.shape[0]
        flat: list[float] = []
        for i in range(n):
            for j in range(i + 1):
                flat.append(float(sigma[i, j]))
        return flat

    @staticmethod
    def _flat_to_sigma(flat: list[float], n: int) -> np.ndarray:
        """Unpack flat lower-triangle back to a symmetric matrix."""
        sigma = np.zeros((n, n))
        idx = 0
        for i in range(n):
            for j in range(i + 1):
                sigma[i, j] = flat[idx]
                if i != j:
                    sigma[j, i] = flat[idx]
                idx += 1
        return sigma

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
            sigma_flat=self._sigma_to_flat(sigma),
            responses=[],
            n_questions_asked=0,
            asked_question_ids=[],
            model_version=self.model_version,
        )

    def update(
        self,
        state: PreferenceState,
        response: Response,
        question_options: list[ItemId],
    ) -> PreferenceState:
        """Bayesian update for a pairwise comparison.

        Observation model: (u_a - u_b) ~ N(y, sigma_obs^2)
        where (a, b) = (chosen, not_chosen) and y = |strength| / 10 * scale.

        We use a one-dimensional Gaussian update via Kalman-style formulas:
            h = e_a - e_b  (the observation direction)
            K = Sigma @ h / (h.T @ Sigma @ h + sigma_obs^2)
            mu_new = mu + K * (y - h.T @ mu)
            Sigma_new = Sigma - K @ (h.T @ Sigma)
        """
        if len(question_options) != 2:
            raise ValueError(
                f"Pairwise update requires 2 options, got {len(question_options)}"
            )

        n = len(state.item_ids)
        mu = np.array(state.mu)
        sigma = self._flat_to_sigma(state.sigma_flat, n)
        idx = {iid: i for i, iid in enumerate(state.item_ids)}

        opt_a_id, opt_b_id = question_options
        if opt_a_id not in idx or opt_b_id not in idx:
            raise ValueError(
                f"Question options {question_options} not found in state items"
            )
        i_a, i_b = idx[opt_a_id], idx[opt_b_id]

        # Determine signed observation: positive if chose A over B, negative otherwise.
        # Strength magnitude gives the observed utility gap magnitude.
        strength = response.strength if response.strength is not None else 5.0
        abs_strength = abs(strength)
        if response.chosen_option_id == opt_a_id:
            y = abs_strength / 10.0  # observed u_a - u_b ≈ +y
        elif response.chosen_option_id == opt_b_id:
            y = -abs_strength / 10.0  # observed u_a - u_b ≈ -y (i.e., B preferred)
        else:
            raise ValueError(
                f"chosen_option_id {response.chosen_option_id} is not in options "
                f"{question_options}"
            )

        # Noise scales inversely with strength — lower strength = noisier observation.
        strength_weight = max(abs_strength / 10.0, self.min_strength_weight)
        sigma_obs2 = self.base_noise_variance / strength_weight

        # Observation vector h: h[i_a]=+1, h[i_b]=-1, else 0.
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

        new_responses = list(state.responses) + [response]
        new_asked = list(state.asked_question_ids) + [response.question_id]

        return PreferenceState(
            user_id=state.user_id,
            session_id=state.session_id,
            item_ids=state.item_ids,
            mu=new_mu.tolist(),
            sigma_flat=self._sigma_to_flat(new_sigma),
            responses=new_responses,
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
        sigma = self._flat_to_sigma(state.sigma_flat, n)
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
        """Return (mean, std) of u_a - u_b under the posterior."""
        n = len(state.item_ids)
        idx = {iid: i for i, iid in enumerate(state.item_ids)}
        if item_a not in idx or item_b not in idx:
            raise ValueError(f"Items {item_a}, {item_b} not in state")
        i_a, i_b = idx[item_a], idx[item_b]
        sigma = self._flat_to_sigma(state.sigma_flat, n)
        mean_diff = float(state.mu[i_a] - state.mu[i_b])
        var_diff = float(sigma[i_a, i_a] + sigma[i_b, i_b] - 2 * sigma[i_a, i_b])
        std_diff = float(np.sqrt(max(var_diff, 0.0)))
        return mean_diff, std_diff
