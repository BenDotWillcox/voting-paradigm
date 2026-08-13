"""
Shared numerics for Gaussian-posterior preference models.

Both fixed-bank models (Gaussian linear, Bradley-Terry + Laplace) represent
their posterior as N(mu, Sigma) over item utilities and consume the same
pairwise/slider evidence. This module holds the covariance packing helpers
and the evidence -> observation normalization they share.
"""

import numpy as np

from ..types import (
    IMPLEMENTED_EVIDENCE_SOURCES,
    Evidence,
    EvidenceSource,
    ItemId,
    PreferenceState,
    UnsupportedEvidenceError,
)


def sigma_to_flat(sigma: np.ndarray) -> list[float]:
    """Pack the lower triangle (including diagonal) row-major."""
    n = sigma.shape[0]
    i_low, j_low = np.tril_indices(n)
    return sigma[i_low, j_low].astype(float).tolist()


def flat_to_sigma(flat: list[float], n: int) -> np.ndarray:
    """Unpack a flat lower triangle back to a symmetric matrix."""
    sigma = np.zeros((n, n))
    i_low, j_low = np.tril_indices(n)
    values = np.asarray(flat, dtype=float)
    sigma[i_low, j_low] = values
    sigma[j_low, i_low] = values
    return sigma


def posterior_diff_stats(
    state: PreferenceState,
    item_a: ItemId,
    item_b: ItemId,
) -> tuple[float, float]:
    """Return (mean, std) of u_a - u_b under the state's Gaussian posterior."""
    n = len(state.item_ids)
    idx = {iid: i for i, iid in enumerate(state.item_ids)}
    if item_a not in idx or item_b not in idx:
        raise ValueError(f"Items {item_a}, {item_b} not in state")
    i_a, i_b = idx[item_a], idx[item_b]
    sigma = flat_to_sigma(state.sigma_flat, n)
    mean_diff = float(state.mu[i_a] - state.mu[i_b])
    var_diff = float(sigma[i_a, i_a] + sigma[i_b, i_b] - 2 * sigma[i_a, i_b])
    std_diff = float(np.sqrt(max(var_diff, 0.0)))
    return mean_diff, std_diff


def normalize_pairwise_evidence(
    evidence: Evidence,
    item_index: dict[ItemId, int],
    min_weight: float,
) -> tuple[int, int, float, float]:
    """Validate evidence and return (idx_a, idx_b, signed_gap, weight).

    signed_gap = value / 10 in [-1, 1] is the observed utility gap u_a - u_b.
    weight in [min_weight, 1] scales observation informativeness: it grows
    with |value| (a confident slider position) and with the evidence
    confidence (1.0 for direct and currently confirmed input; lower only under
    an explicitly evaluated weighting policy).
    """
    if evidence.source not in IMPLEMENTED_EVIDENCE_SOURCES:
        raise UnsupportedEvidenceError(
            f"No likelihood implemented for evidence source "
            f"'{evidence.source.value}'. Supported: "
            f"{sorted(s.value for s in IMPLEMENTED_EVIDENCE_SOURCES)}"
        )
    if evidence.source in {
        EvidenceSource.FREE_TEXT_EXTRACTION,
        EvidenceSource.CORRECTION,
    } and (
        evidence.event_id is None
        or not evidence.confirmed_by_participant
    ):
        raise UnsupportedEvidenceError(
            f"evidence source '{evidence.source.value}' requires a confirmed "
            "Phase 4C evidence event"
        )
    if evidence.item_a not in item_index or evidence.item_b not in item_index:
        raise ValueError(
            f"Evidence items ({evidence.item_a}, {evidence.item_b}) "
            f"not found in state items"
        )
    if evidence.item_a == evidence.item_b:
        raise ValueError(f"Evidence compares item {evidence.item_a} to itself")
    if not -10.0 <= evidence.value <= 10.0:
        raise ValueError(f"Evidence value {evidence.value} outside [-10, 10]")
    if not 0.0 < evidence.confidence <= 1.0:
        raise ValueError(
            f"Evidence confidence {evidence.confidence} outside (0, 1]"
        )

    signed_gap = evidence.value / 10.0
    weight = max(abs(signed_gap) * evidence.confidence, min_weight)
    return (
        item_index[evidence.item_a],
        item_index[evidence.item_b],
        signed_gap,
        weight,
    )
