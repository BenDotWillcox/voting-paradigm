"""
A multidimensional probit item response model, estimated in two stages.

    Respondent i has a latent position theta_i in K dimensions, N(0, I).
    Item j has loadings a_j and an intercept b_j.
    Respondent i supports item j when a_j . theta_i + b_j + e_ij > 0,
    with e_ij ~ N(0, 1).

This is the simulation's own vote rule, so a fit is directly a generative
model for synthetic voters and questions. The model is exploratory: no
dimension is labelled or required, and correlation between items comes only
from loadings the data supports.

Estimation:

  1. Items, by limited information. Each item's threshold comes from its
     support rate, each pair's tetrachoric correlation from their 2x2
     table, and the loadings from an unweighted least squares factor fit to
     the tetrachoric matrix. Under the model the latent utilities have
     correlation a_j . a_k / sqrt((1 + |a_j|^2)(1 + |a_k|^2)), so a factor
     loading lambda_j converts to a_j = lambda_j / sqrt(1 - |lambda_j|^2).
     This is consistent, fast, and with tens of thousands of respondents
     the item parameters are estimated far more precisely than anything
     downstream needs.
  2. Respondents, by Gibbs sampling with the items fixed: alternate the
     latent utilities (normals truncated to the side the answer fell on,
     untruncated where the answer is missing or held out) and theta (a
     normal with the shared covariance (I + A'A)^-1). With the items fixed
     each respondent's chain is short and mixes quickly.

A fully joint Gibbs sampler over items and respondents (Albert and Chib
1992; Béguin and Glas 2001) was tried first. It recovered known parameters
but mixed too slowly at this sample size: on a 15,000-respondent CES
subsample with K = 3, 2,000 iterations left split R-hat at 1.15 on the
implied item correlations. That is the known weakness of data augmentation
when the latent variables carry most of the uncertainty.

The loadings are identified only up to rotation. Nothing downstream needs
the rotation fixed, because the simulation uses only a_j . theta_i + b_j and
theta's N(0, I) prior is rotation-invariant.

Pure and seeded. Missing answers are NaN in the response matrix.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize, minimize_scalar
from scipy.special import log_ndtr, ndtr, ndtri
from scipy.stats import multivariate_normal

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

_EPS = 1e-300
# An item whose communality ends above this is reported as capped (a near
# Heywood case: almost no unique variance)
_MAX_COMMUNALITY = 0.98
# Ridge on the item response loadings in the factor fit. On the CES 2024
# items it leaves the residual RMSR unchanged to four decimals at every K
# from 1 to 6, and stops one extreme item ("make abortion illegal in all
# circumstances", 10.5% support) running to a Heywood case at K >= 5, which
# a ridge of 1e-6 allowed (communality 0.993)
RIDGE = 1e-4


# ---------------------------------------------------------------------------
# Stage 1: items
# ---------------------------------------------------------------------------


def _validate(y: FloatArray) -> BoolArray:
    if y.ndim != 2:
        raise ValueError("y must be a [respondent, item] matrix")
    observed = ~np.isnan(y)
    if not np.isin(y[observed], (0.0, 1.0)).all():
        raise ValueError("answers must be 0, 1 or NaN")
    return np.asarray(observed)


def thresholds(y: FloatArray) -> FloatArray:
    """Each item's standardised threshold, Phi^-1 of its support rate."""
    observed = _validate(y)
    rate = np.nansum(y, axis=0) / observed.sum(axis=0)
    return np.asarray(ndtri(np.clip(rate, 1e-6, 1 - 1e-6)))


def _bivariate_upper(t1: float, t2: float, rho: float) -> float:
    """P(u1 < t1, u2 < t2) for standard normals with correlation rho."""
    cov = np.array([[1.0, rho], [rho, 1.0]])
    return float(multivariate_normal.cdf([t1, t2], mean=[0.0, 0.0], cov=cov))


def tetrachoric_pair(x: FloatArray, z: FloatArray) -> float:
    """
    The maximum likelihood tetrachoric correlation of two binary items,
    over respondents who answered both. Each item's threshold is taken from
    those same respondents.
    """
    both = ~np.isnan(x) & ~np.isnan(z)
    x, z = x[both], z[both]
    n11 = float(np.sum((x == 1) & (z == 1)))
    n10 = float(np.sum((x == 1) & (z == 0)))
    n01 = float(np.sum((x == 0) & (z == 1)))
    n00 = float(np.sum((x == 0) & (z == 0)))
    n = n11 + n10 + n01 + n00
    # Support is u < t with P = Phi(t)
    t1 = float(ndtri(np.clip((n11 + n10) / n, 1e-6, 1 - 1e-6)))
    t2 = float(ndtri(np.clip((n11 + n01) / n, 1e-6, 1 - 1e-6)))
    p1, p2 = float(ndtr(t1)), float(ndtr(t2))

    def negative_log_likelihood(rho: float) -> float:
        p11 = _bivariate_upper(t1, t2, rho)
        p10 = p1 - p11
        p01 = p2 - p11
        p00 = 1.0 - p1 - p2 + p11
        cells = np.maximum([p11, p10, p01, p00], 1e-12)
        return -float(np.dot([n11, n10, n01, n00], np.log(cells)))

    result = minimize_scalar(
        negative_log_likelihood, bounds=(-0.999, 0.999), method="bounded",
        options={"xatol": 1e-5},
    )
    return float(result.x)


def tetrachoric_matrix(y: FloatArray) -> FloatArray:
    """Pairwise tetrachoric correlations of every item pair."""
    _validate(y)
    j = y.shape[1]
    r = np.eye(j)
    for a in range(j):
        for b in range(a + 1, j):
            r[a, b] = r[b, a] = tetrachoric_pair(y[:, a], y[:, b])
    return r


@dataclass(frozen=True)
class FactorFit:
    """A least squares factor fit to a correlation matrix."""

    # [item, dimension] standardised loadings
    loadings: FloatArray
    # Root mean square of the off-diagonal residuals
    rmsr: float
    # Items whose communality hit the cap
    capped: tuple[int, ...]


def fit_factors(correlation: FloatArray, dimensions: int, seed: int = 0) -> FactorFit:
    """
    Unweighted least squares factor analysis: minimise the squared
    off-diagonal difference between the correlations and Lambda Lambda'.

    The search runs on the item response scale, lambda_j = a_j /
    sqrt(1 + |a_j|^2), so every communality stays below 1 by construction
    and no solution has to be clipped afterwards (clipping a finished
    solution distorted fits at higher K). A ridge of RIDGE |a|^2 keeps a
    finite when an item would otherwise run to a communality of 1; items
    that end above _MAX_COMMUNALITY are reported as capped.
    """
    j = correlation.shape[0]
    if not 1 <= dimensions < j:
        raise ValueError("dimensions must be in [1, items)")
    off = ~np.eye(j, dtype=bool)
    values, vectors = np.linalg.eigh(correlation)
    order = np.argsort(values)[::-1][:dimensions]
    lam0 = vectors[:, order] * np.sqrt(np.maximum(values[order], 1e-6))
    lam0 = lam0 * min(1.0, 0.9 / max(np.sqrt((lam0**2).sum(axis=1)).max(), 1e-12))
    # Invert lambda = a / sqrt(1 + |a|^2) for the start
    start = lam0 / np.sqrt(1.0 - (lam0**2).sum(axis=1, keepdims=True))
    rng = np.random.default_rng(seed)
    start = start + 1e-3 * rng.standard_normal(start.shape)

    def objective(flat: FloatArray) -> tuple[float, FloatArray]:
        a = flat.reshape(j, dimensions)
        s = np.sqrt(1.0 + (a**2).sum(axis=1, keepdims=True))
        lam = a / s
        residual = np.where(off, correlation - lam @ lam.T, 0.0)
        g = -4.0 * residual @ lam  # d f / d lambda
        # d lambda_j / d a_j = I / s_j - a_j a_j' / s_j^3 (symmetric)
        grad = g / s - a * ((a * g).sum(axis=1, keepdims=True) / s**3)
        value = float((residual**2).sum()) + RIDGE * float((a**2).sum())
        return value, (grad + 2.0 * RIDGE * a).ravel()

    result = minimize(objective, start.ravel(), jac=True, method="L-BFGS-B",
                      options={"maxiter": 20000, "gtol": 1e-10})
    a = result.x.reshape(j, dimensions)
    lam = a / np.sqrt(1.0 + (a**2).sum(axis=1, keepdims=True))
    communality = (lam**2).sum(axis=1)
    capped = tuple(int(i) for i in np.flatnonzero(communality > _MAX_COMMUNALITY))
    residual = (correlation - lam @ lam.T)[off]
    return FactorFit(lam, float(np.sqrt((residual**2).mean())), capped)


@dataclass(frozen=True, eq=False)
class ItemParameters:
    """Probit item parameters on the model's own scale."""

    loadings: FloatArray  # [item, dimension]
    intercepts: FloatArray  # [item]

    @property
    def dimensions(self) -> int:
        return int(self.loadings.shape[1])


def to_items(factors: FactorFit, item_thresholds: FloatArray) -> ItemParameters:
    """
    Convert standardised loadings and thresholds to (a, b):
    a_j = lambda_j / sqrt(psi_j), b_j = tau_j / sqrt(psi_j), with the unique
    variance psi_j = 1 - |lambda_j|^2.
    """
    psi = 1.0 - (factors.loadings**2).sum(axis=1)
    scale = 1.0 / np.sqrt(psi)
    return ItemParameters(factors.loadings * scale[:, None], item_thresholds * scale)


def estimate_items(y: FloatArray, dimensions: int) -> tuple[ItemParameters, FactorFit, FloatArray]:
    """Stage 1 end to end: thresholds, tetrachorics, factor fit, conversion."""
    corr = tetrachoric_matrix(y)
    factors = fit_factors(corr, dimensions)
    return to_items(factors, thresholds(y)), factors, corr


# ---------------------------------------------------------------------------
# Rotation-free summaries
# ---------------------------------------------------------------------------


def implied_correlation(loadings: FloatArray) -> FloatArray:
    """
    Correlations between items' latent utilities implied by loadings:
    a_j . a_k / sqrt((1 + |a_j|^2)(1 + |a_k|^2)). Rotation-free.
    """
    gram = loadings @ loadings.T
    scale = np.sqrt(1.0 + np.diag(gram))
    corr = gram / np.outer(scale, scale)
    np.fill_diagonal(corr, 1.0)
    return np.asarray(corr)


def support_rates(loadings: FloatArray, intercepts: FloatArray) -> FloatArray:
    """
    Each item's population support rate under theta ~ N(0, I):
    Phi(b_j / sqrt(1 + |a_j|^2)). Rotation-free.
    """
    return np.asarray(ndtr(intercepts / np.sqrt(1.0 + (loadings**2).sum(axis=1))))


# ---------------------------------------------------------------------------
# Stage 2: respondents
# ---------------------------------------------------------------------------


def _truncated_normal(
    rng: np.random.Generator, mean: FloatArray, positive: BoolArray
) -> FloatArray:
    """
    Draw z ~ N(mean, 1) truncated to z > 0 where `positive`, else z < 0.

    Uses the tail-stable inverse CDF: for z > 0 the excess over the mean is
    -ndtri(u * ndtr(mean)), which stays accurate when the truncation point
    is far in either tail.
    """
    u = rng.random(mean.shape)
    mass = np.where(positive, ndtr(mean), ndtr(-mean))
    v = np.clip(u * mass, _EPS, 1.0 - 1e-16)
    offset = ndtri(v)
    return np.asarray(np.where(positive, mean - offset, mean + offset))


@dataclass(frozen=True)
class PositionConfig:
    """
    Settings of the respondent sampler. The defaults keep 200 draws; on
    simulated data with 20 items they gave split R-hat at most 1.07 (99th
    percentile 1.03) over 1,000 position coordinates, where 300 iterations
    kept every other draw left the worst at 1.23.
    """

    iterations: int = 1200
    burn_in: int = 200
    thin: int = 5
    seed: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.burn_in < self.iterations:
            raise ValueError("burn_in must be in [0, iterations)")
        if self.thin < 1:
            raise ValueError("thin must be at least 1")


def sample_positions(
    y: FloatArray, items: ItemParameters, config: PositionConfig
) -> npt.NDArray[np.float32]:
    """
    Posterior draws of every respondent's theta, with items fixed.

    Returns:
        [draw, respondent, dimension], float32 to keep large runs small
    """
    observed = _validate(y)
    n, j = y.shape
    if items.loadings.shape[0] != j:
        raise ValueError("one set of item parameters per column is needed")
    k = items.dimensions
    a, b = items.loadings, items.intercepts
    rng = np.random.default_rng(np.random.SeedSequence([config.seed, k, 2]))
    support = np.where(observed, y == 1.0, False)
    missing = ~observed
    cov = np.linalg.inv(np.eye(k) + a.T @ a)
    chol = np.linalg.cholesky(cov)
    projection = a @ cov  # [item, k]
    theta = np.zeros((n, k))
    kept = range(config.burn_in, config.iterations, config.thin)
    out = np.empty((len(kept), n, k), dtype=np.float32)
    slot = 0
    for step in range(config.iterations):
        mean = theta @ a.T + b
        z = _truncated_normal(rng, mean, support)
        if missing.any():
            z[missing] = mean[missing] + rng.standard_normal(int(missing.sum()))
        theta = (z - b) @ projection + rng.standard_normal((n, k)) @ chol.T
        if step >= config.burn_in and (step - config.burn_in) % config.thin == 0:
            out[slot] = theta
            slot += 1
    return out


@dataclass(frozen=True, eq=False)
class GroupedDraws:
    """Posterior draws of the hierarchical position model."""

    # [draw, respondent, dimension]
    positions: npt.NDArray[np.float32]
    # [draw, group, dimension]
    group_means: FloatArray
    # [draw, dimension, dimension]
    within_cov: FloatArray
    between_cov: FloatArray


# Weak inverse-Wishart priors for the hierarchical position model: degrees
# of freedom K + 2 and scale (K + 2) times a guess, so the prior mean of
# each covariance is near its guess but carries the weight of only a few
# observations
_WITHIN_GUESS = 0.9
_BETWEEN_GUESS = 0.1


def sample_grouped_positions(
    y: FloatArray,
    items: ItemParameters,
    group: npt.NDArray[np.int64],
    config: PositionConfig,
) -> GroupedDraws:
    """
    Posterior draws of positions conditioned on group membership.

        theta_i ~ N(mu_g(i), W),  mu_g ~ N(0, T)

    with W (within-group) and T (between-group) covariances sampled in the
    same Gibbs run, items fixed. Conditioning on the group is what keeps
    group differences intact: draws under one common N(0, I) prior shrink
    every respondent toward the overall mean and so understate how much
    groups differ, the known bias of unconditioned plausible values.

    Args:
        y: [respondent, item] answers, 1.0, 0.0 or NaN
        items: Fixed item parameters
        group: Each respondent's group index, 0..G-1
        config: Iterations, burn-in, thinning and seed
    """
    from scipy.stats import invwishart

    observed = _validate(y)
    n, j = y.shape
    if group.shape != (n,) or group.min() < 0:
        raise ValueError("one non-negative group index per respondent is needed")
    groups = int(group.max()) + 1
    counts = np.bincount(group, minlength=groups).astype(np.float64)
    k = items.dimensions
    a, b = items.loadings, items.intercepts
    rng = np.random.default_rng(np.random.SeedSequence([config.seed, k, 3]))
    support = np.where(observed, y == 1.0, False)
    missing = ~observed
    df0 = k + 2.0
    within = np.eye(k) * _WITHIN_GUESS
    between = np.eye(k) * _BETWEEN_GUESS
    mu = np.zeros((groups, k))
    theta = np.zeros((n, k))
    ata = a.T @ a
    kept = range(config.burn_in, config.iterations, config.thin)
    out_t = np.empty((len(kept), n, k), dtype=np.float32)
    out_mu = np.empty((len(kept), groups, k))
    out_w = np.empty((len(kept), k, k))
    out_b = np.empty((len(kept), k, k))
    slot = 0
    for step in range(config.iterations):
        # 1. Latent utilities
        mean = theta @ a.T + b
        z = _truncated_normal(rng, mean, support)
        if missing.any():
            z[missing] = mean[missing] + rng.standard_normal(int(missing.sum()))
        # 2. Positions around their group's mean
        w_inv = np.linalg.inv(within)
        cov = np.linalg.inv(w_inv + ata)
        chol = np.linalg.cholesky(cov)
        means = (mu[group] @ w_inv + (z - b) @ a) @ cov
        theta = means + rng.standard_normal((n, k)) @ chol.T
        # 3. Group means: precision n_g W^-1 + T^-1
        t_inv = np.linalg.inv(between)
        sums = np.zeros((groups, k))
        np.add.at(sums, group, theta)
        precision = counts[:, None, None] * w_inv[None] + t_inv[None]
        g_cov = np.linalg.inv(precision)
        g_mean = np.einsum("gij,gj->gi", g_cov, sums @ w_inv)
        g_chol = np.linalg.cholesky(g_cov)
        mu = g_mean + np.einsum("gij,gj->gi", g_chol, rng.standard_normal((groups, k)))
        # 4. Within- and between-group covariances
        resid = theta - mu[group]
        within = invwishart.rvs(
            df=df0 + n, scale=np.eye(k) * df0 * _WITHIN_GUESS + resid.T @ resid,
            random_state=rng,
        ).reshape(k, k)
        between = invwishart.rvs(
            df=df0 + groups, scale=np.eye(k) * df0 * _BETWEEN_GUESS + mu.T @ mu,
            random_state=rng,
        ).reshape(k, k)
        if step >= config.burn_in and (step - config.burn_in) % config.thin == 0:
            out_t[slot] = theta
            out_mu[slot] = mu
            out_w[slot] = within
            out_b[slot] = between
            slot += 1
    return GroupedDraws(out_t, out_mu, out_w, out_b)


def split_rhat(draws: FloatArray) -> FloatArray:
    """
    Split R-hat (Gelman et al.) for each scalar in [chain, draw, ...].
    Each chain is split in half, so a chain that drifts is caught even when
    there is only one.
    """
    half = draws.shape[1] // 2
    if half < 2:
        raise ValueError("need at least four draws per chain")
    split = np.concatenate([draws[:, :half], draws[:, half : 2 * half]], axis=0)
    within = split.var(axis=1, ddof=1).mean(axis=0)
    between = half * split.mean(axis=1).var(axis=0, ddof=1)
    var_plus = (half - 1) / half * within + between / half
    return np.asarray(np.sqrt(var_plus / np.maximum(within, 1e-300)))


# ---------------------------------------------------------------------------
# Held-out scoring
# ---------------------------------------------------------------------------


def holdout_mask(y: FloatArray, share: float, seed: int) -> BoolArray:
    """A seeded random share of the answered cells, to hide from the fit."""
    if not 0.0 < share < 1.0:
        raise ValueError("share must be in (0, 1)")
    rng = np.random.default_rng(np.random.SeedSequence([seed, 7919]))
    observed = _validate(y)
    return np.asarray(observed & (rng.random(y.shape) < share))


def holdout_log_scores(
    y: FloatArray,
    mask: BoolArray,
    items: ItemParameters,
    positions: npt.NDArray[np.float32],
) -> FloatArray:
    """
    The posterior predictive log score of every held-out cell, in mask
    order: the log of the probability of the observed answer, averaged over
    position draws (the probability, not its log, is averaged).
    """
    rows, cols = np.nonzero(mask)
    answers = y[rows, cols] == 1.0
    a, b = items.loadings, items.intercepts
    total = np.zeros(rows.size)
    for theta in positions:
        eta = (theta[rows].astype(np.float64) * a[cols]).sum(axis=1) + b[cols]
        total += np.exp(np.where(answers, log_ndtr(eta), log_ndtr(-eta)))
    return np.asarray(np.log(np.maximum(total / positions.shape[0], _EPS)))


def simulate_answers(
    items: ItemParameters,
    respondents: int,
    seed: int,
    missing_share: float = 0.0,
) -> tuple[FloatArray, FloatArray]:
    """
    Answers drawn from the model itself, for testing.

    Returns:
        (answers with NaN where missing, the true positions)
    """
    rng = np.random.default_rng(np.random.SeedSequence([seed, 31]))
    theta = rng.standard_normal((respondents, items.dimensions))
    eta = theta @ items.loadings.T + items.intercepts
    y = (eta + rng.standard_normal(eta.shape) > 0).astype(np.float64)
    if missing_share:
        y[rng.random(y.shape) < missing_share] = np.nan
    return y, theta
