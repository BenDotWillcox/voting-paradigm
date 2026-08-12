"""
Acquisition policies: which pair of items to ask about next.

Stage 1 of the active-learning roadmap. Three policies ship today:

- ``fixed_sequence``: the canonical first unseen pair. This is the
  questionnaire baseline: its sequence depends only on the versioned bank and
  exclusions, never on answers, posterior state, or a random seed.

- ``random``: uniform over unseen pairs (the baseline the eval harness
  scores active selection against).
- ``max_variance``: pick the unseen pair (a, b) with the highest posterior
  std of (u_a - u_b). Greedy uncertainty sampling — under a Gaussian
  posterior this is the pair whose answer is currently least predictable.

Stage 2 (expected information gain / BALD) plugs in as another selector
behind the same protocol.

Determinism: ``fixed_sequence`` and ``max_variance`` break ties
lexicographically on the sorted pair, so the same inputs always yield the same
question. ``random`` takes an injected ``random.Random`` seeded by the engine.
"""

import random
from typing import Optional, Protocol

from .model.base import PreferenceModel
from .questions.bank import QuestionBank
from .types import ItemId, PreferenceState

Pair = tuple[ItemId, ItemId]


class PairSelector(Protocol):
    """Protocol for pair-acquisition policies."""

    name: str

    def select_pair(
        self,
        state: PreferenceState,
        model: PreferenceModel,
        bank: QuestionBank,
        exclude_pairs: set[frozenset[ItemId]],
        rng: random.Random,
    ) -> Optional[Pair]:
        """Return the next pair to ask about, or None if exhausted."""
        ...


def _unseen_pairs(
    bank: QuestionBank,
    exclude_pairs: set[frozenset[ItemId]],
) -> list[Pair]:
    """All unordered item pairs not yet excluded, in canonical sorted order."""
    ids = sorted(bank.item_ids())
    return [
        (ids[i], ids[j])
        for i in range(len(ids))
        for j in range(i + 1, len(ids))
        if frozenset((ids[i], ids[j])) not in exclude_pairs
    ]


class RandomPairSelector:
    """Uniform selection over unseen pairs (baseline policy)."""

    name = "random"

    def select_pair(
        self,
        state: PreferenceState,
        model: PreferenceModel,
        bank: QuestionBank,
        exclude_pairs: set[frozenset[ItemId]],
        rng: random.Random,
    ) -> Optional[Pair]:
        candidates = _unseen_pairs(bank, exclude_pairs)
        if not candidates:
            return None
        return rng.choice(candidates)


class FixedSequencePairSelector:
    """Canonical non-adaptive questionnaire baseline.

    The selector deliberately ignores posterior state and RNG. Holding the
    question bank and exclusions fixed therefore produces the same question
    sequence for every participant, which is the Phase 4 fixed-acquisition
    control.
    """

    name = "fixed_sequence"

    def select_pair(
        self,
        state: PreferenceState,
        model: PreferenceModel,
        bank: QuestionBank,
        exclude_pairs: set[frozenset[ItemId]],
        rng: random.Random,
    ) -> Optional[Pair]:
        candidates = _unseen_pairs(bank, exclude_pairs)
        return candidates[0] if candidates else None


class MaxVariancePairSelector:
    """Greedy uncertainty sampling: highest posterior std of (u_a - u_b)."""

    name = "max_variance"

    def select_pair(
        self,
        state: PreferenceState,
        model: PreferenceModel,
        bank: QuestionBank,
        exclude_pairs: set[frozenset[ItemId]],
        rng: random.Random,
    ) -> Optional[Pair]:
        candidates = _unseen_pairs(bank, exclude_pairs)
        if not candidates:
            return None
        # Candidates are in canonical order, so on exact variance ties the
        # lexicographically first pair wins — deterministic given the state.
        return max(
            candidates,
            key=lambda pair: model.get_uncertainty(state, pair[0], pair[1]),
        )


SELECTOR_REGISTRY: dict[str, type] = {
    FixedSequencePairSelector.name: FixedSequencePairSelector,
    RandomPairSelector.name: RandomPairSelector,
    MaxVariancePairSelector.name: MaxVariancePairSelector,
}

DEFAULT_SELECTOR_NAME = MaxVariancePairSelector.name


def create_selector(name: str = DEFAULT_SELECTOR_NAME) -> PairSelector:
    """Instantiate a registered acquisition policy by name."""
    try:
        return SELECTOR_REGISTRY[name]()  # type: ignore[no-any-return]
    except KeyError:
        raise ValueError(
            f"Unknown selection policy '{name}'. "
            f"Available: {sorted(SELECTOR_REGISTRY)}"
        ) from None
