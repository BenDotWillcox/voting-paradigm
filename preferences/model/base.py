"""
Abstract protocol for preference models.

Any model implementing this protocol can be plugged into the ElicitationEngine.
Models consume typed `Evidence` (never raw LLM output or UI payloads) and are
the ONLY code allowed to move the posterior — the evidence contract is the
boundary between elicitation frontends (UI, LLM interviewer) and inference.
"""

from typing import Protocol

from ..types import Evidence, ItemId, PreferenceState


class PreferenceModel(Protocol):
    """Protocol for Bayesian preference models over item utilities."""

    model_version: str

    def initialize(
        self,
        user_id: str,
        session_id: str,
        item_ids: list[ItemId],
    ) -> PreferenceState:
        """Return a fresh state with prior beliefs over the given items."""
        ...

    def update(
        self,
        state: PreferenceState,
        evidence: Evidence,
    ) -> PreferenceState:
        """Return a new state with posterior updated by one piece of evidence.

        Must raise `UnsupportedEvidenceError` for evidence sources the model
        has no likelihood for, and ValueError for malformed evidence — never
        silently skip.
        """
        ...

    def predict_preference(
        self,
        state: PreferenceState,
        item_a: ItemId,
        item_b: ItemId,
    ) -> float:
        """Return P(user prefers item_a over item_b) in [0, 1]."""
        ...

    def get_uncertainty(
        self,
        state: PreferenceState,
        item_a: ItemId,
        item_b: ItemId,
    ) -> float:
        """Return the posterior std of (u_a - u_b). Higher = more uncertain."""
        ...

    def get_utility_estimates(
        self,
        state: PreferenceState,
    ) -> dict[ItemId, tuple[float, float]]:
        """Return {item_id: (mean, std)} for all items."""
        ...
