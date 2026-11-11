"""
Which categories sit inside which.

The routing rule lets a narrower category overrule the broader one it sits
inside (routing.py). This module finds those pairs. Voters write their own
categories and declare nothing, so the decision model is asked: for two
categories A and B, is every decision about A also a decision about B?

A pair counts as nested only when the answer is yes one way and no the
other. Yes both ways means two wordings of the same thing, which is not
nesting, and the pair is left to highest-score-wins.

Containment is a fact about two category texts, not about a voter, so
judgments are recorded and shared exactly like question judgments: hashed by
model and wording, first response wins, and the routing rule reads only what
is recorded. When a judgment is missing the pair is simply not nested, and
routing falls back to highest-score-wins for it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .judgments import JudgmentUnavailable, RecordStore, SourceAnswer, _utc_now
from .types import Category, CategoryId, Network, validate_probability

# What the model is told the two topics are. Part of every judgment's key.
NESTING_STATE = (
    "Two topics that voters wrote to describe the kinds of civic decisions "
    "they hand to someone else."
)
NESTING_INSTRUCTION = (
    "Is every decision about topic A also a decision about topic B? "
    "Topic A: {narrow}. Topic B: {broad}."
)
# How sure the model must be that A sits inside B, and unsure of the reverse
DEFAULT_NESTING_THRESHOLD = 0.7

# (narrow, broad): the first category sits inside the second
NestingPair = tuple[CategoryId, CategoryId]


def nesting_instruction(narrow: Category, broad: Category) -> str:
    """The yes/no question asking whether one category sits inside another."""
    return NESTING_INSTRUCTION.format(narrow=narrow.text, broad=broad.text)


def nesting_key(model: str, narrow: Category, broad: Category) -> str:
    """The identity of one containment judgment: the model and what it was asked."""
    asked = {
        "model": model,
        "type": "noul",
        "state": NESTING_STATE,
        "instructions": nesting_instruction(narrow, broad),
    }
    canonical = json.dumps(asked, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class NestingSource(Protocol):
    """Anything that can judge whether categories sit inside one another."""

    @property
    def model(self) -> str:
        """The pinned model id this source asks."""
        ...

    def judge_nesting(
        self, pairs: Sequence[tuple[Category, Category]]
    ) -> Mapping[NestingPair, SourceAnswer]:
        """
        Judge, for each (narrow, broad) pair, whether narrow sits inside broad.

        Raises:
            JudgmentUnavailable: If the request failed or its answer could
                not be trusted
        """
        ...


@dataclass(frozen=True)
class NestingRecord:
    """A stored containment judgment."""

    key: str
    model: str
    answered_by: str
    narrow: CategoryId
    broad: CategoryId
    narrow_text: str
    broad_text: str
    # The probability that every decision about narrow is also about broad
    probability: float
    recorded_at: str


class NestingStore(RecordStore[NestingRecord]):
    """The recorded containment judgments, one per ordered pair of categories."""

    def __init__(self, path: Path | None = None) -> None:
        super().__init__(NestingRecord, path)


def co_held_pairs(network: Network) -> tuple[tuple[Category, Category], ...]:
    """
    Every ordered pair of distinct categories that one person holds together.

    These are the only pairs the routing rule can ever compare, so they are
    the only ones worth asking about. Each pair appears in both orders.
    """
    pairs: dict[NestingPair, tuple[Category, Category]] = {}
    held_by: dict[str, list[CategoryId]] = {}
    for delegation in network.delegations:
        held_by.setdefault(delegation.delegator, []).append(delegation.category)
    for held in held_by.values():
        for first in held:
            for second in held:
                if first != second:
                    pairs.setdefault(
                        (first, second),
                        (network.categories[first], network.categories[second]),
                    )
    return tuple(pairs[key] for key in sorted(pairs))


def derive_nesting(
    probabilities: Mapping[NestingPair, float],
    threshold: float = DEFAULT_NESTING_THRESHOLD,
) -> frozenset[NestingPair]:
    """
    Turn containment probabilities into a nesting relation.

    A pair (narrow, broad) is nested when the model is at least `threshold`
    sure that narrow sits inside broad and less than `threshold` sure of the
    reverse. Both directions must have been judged. Pairs are taken from the
    most certain down, and a pair that would make the relation loop is left
    out, so the result is always a valid nesting for a Network.

    Raises:
        InvalidJudgmentError: If the threshold is not a probability
    """
    validate_probability(threshold, "Nesting threshold")
    candidates = sorted(
        (
            (-probability, narrow, broad)
            for (narrow, broad), probability in probabilities.items()
            if probability >= threshold
            and (broad, narrow) in probabilities
            and probabilities[(broad, narrow)] < threshold
        )
    )
    broader: dict[CategoryId, set[CategoryId]] = {}

    def reaches(start: CategoryId, target: CategoryId) -> bool:
        seen: set[CategoryId] = set()
        frontier = [start]
        while frontier:
            current = frontier.pop()
            if current == target:
                return True
            if current not in seen:
                seen.add(current)
                frontier.extend(broader.get(current, ()))
        return False

    accepted: set[NestingPair] = set()
    for _, narrow, broad in candidates:
        if reaches(broad, narrow):
            continue  # the broad one already sits inside the narrow one
        broader.setdefault(narrow, set()).add(broad)
        accepted.add((narrow, broad))
    return frozenset(accepted)


@dataclass(frozen=True)
class NestingReport:
    """The containment judgments available for some pairs, and what they imply."""

    # The probability that the first category sits inside the second
    probabilities: dict[NestingPair, float]
    # The nesting relation derived from them
    nesting: frozenset[NestingPair]
    # Pairs served from the store, and pairs newly judged and stored
    recorded: int
    fetched: int
    # Pairs with no judgment, because there was no source or it failed
    missing: tuple[NestingPair, ...]
    # One message per failed request
    failures: tuple[str, ...]


def gather_nesting(
    pairs: Iterable[tuple[Category, Category]],
    store: NestingStore,
    *,
    model: str,
    source: NestingSource | None = None,
    threshold: float = DEFAULT_NESTING_THRESHOLD,
    batch_size: int = 60,
    clock: Callable[[], str] = _utc_now,
) -> NestingReport:
    """
    Collect containment judgments for ordered (narrow, broad) pairs.

    Stored judgments are used first. Pairs without one are sent to the
    source in batches, and each new answer is stored before it is used. A
    failed request leaves its pairs without a judgment, which means they are
    not treated as nested.

    Args:
        pairs: Ordered (narrow, broad) pairs. Pass both orders of a pair so
            that nesting can be told apart from two wordings of one thing.
        store: Where containment judgments are recorded
        model: The pinned model id the judgments belong to
        source: Where missing judgments come from. With no source only
            stored judgments are used.
        threshold: The nesting threshold (see derive_nesting)
        batch_size: The most pairs sent in one request
        clock: Supplies the recording time

    Raises:
        ValueError: If the source asks a different model, or batch_size is
            not positive
    """
    if source is not None and source.model != model:
        raise ValueError(
            f"The source asks {source.model!r} but judgments were requested "
            f"for {model!r}"
        )
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    distinct: dict[NestingPair, tuple[Category, Category]] = {}
    for narrow, broad in pairs:
        if narrow.id != broad.id:
            distinct.setdefault((narrow.id, broad.id), (narrow, broad))

    probabilities: dict[NestingPair, float] = {}
    wanted: list[tuple[Category, Category]] = []
    recorded = 0
    for key, (narrow, broad) in distinct.items():
        stored = store.get(nesting_key(model, narrow, broad))
        if stored is None:
            wanted.append((narrow, broad))
        else:
            probabilities[key] = stored.probability
            recorded += 1

    missing: list[NestingPair] = []
    failures: list[str] = []
    fetched = 0
    for start in range(0, len(wanted), batch_size):
        batch = wanted[start : start + batch_size]
        answers: Mapping[NestingPair, SourceAnswer] = {}
        if source is not None:
            try:
                answers = source.judge_nesting(batch)
            except JudgmentUnavailable as error:
                failures.append(str(error))
        for narrow, broad in batch:
            answer = answers.get((narrow.id, broad.id))
            if answer is None or answer.answered_by != model:
                missing.append((narrow.id, broad.id))
                continue
            kept = store.record(
                NestingRecord(
                    key=nesting_key(model, narrow, broad),
                    model=model,
                    answered_by=answer.answered_by,
                    narrow=narrow.id,
                    broad=broad.id,
                    narrow_text=narrow.text,
                    broad_text=broad.text,
                    probability=answer.probability,
                    recorded_at=clock(),
                )
            )
            probabilities[(narrow.id, broad.id)] = kept.probability
            fetched += 1

    return NestingReport(
        probabilities=probabilities,
        nesting=derive_nesting(probabilities, threshold),
        recorded=recorded,
        fetched=fetched,
        missing=tuple(missing),
        failures=tuple(failures),
    )


def with_nesting(network: Network, nesting: Iterable[NestingPair]) -> Network:
    """
    Return the network with its nesting replaced.

    Pairs naming a category the network does not have are dropped, so a
    relation gathered for a larger pool can be applied to any network.

    Raises:
        InvalidNetworkError: If the nesting loops
    """
    return Network(
        persons=network.persons,
        categories=network.categories,
        delegations=network.delegations,
        nesting=frozenset(
            (narrow, broad)
            for narrow, broad in nesting
            if narrow in network.categories and broad in network.categories
        ),
    )
