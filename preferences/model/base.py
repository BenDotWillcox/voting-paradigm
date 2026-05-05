"""
Abstract protocol for preference models.

Any model implementing this protocol can be plugged into the ElicitationEngine.
"""

from typing import Protocol

from ..types import ItemId, PreferenceState, Response


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
        response: Response,
        question_options: list[ItemId],
    ) -> PreferenceState:
        """Return a new state with posterior updated by the response.

        `question_options` is the ordered list of item ids the question compared
        (length 2 for pairwise). The response's `chosen_option_id` and `strength`
        determine the observed preference direction.
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
