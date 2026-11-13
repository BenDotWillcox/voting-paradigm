"""
Which categories are two wordings of the same thing.

Voters write their own categories, so "all things taxes" and "tax policy"
are different texts and, for routing, different categories. Routing stays
that way: a vote moves only under the text its voter wrote. Grouping is for
reading the network, not for moving votes: what a person is trusted with,
and which wordings other people already use.

It needs no judgments of its own. The nesting question (nesting.py) asks
whether every decision about A is also a decision about B. A yes one way is
nesting. A yes both ways is two wordings of one thing, and that is a group.

Yes-both-ways does not chain reliably: A can match B and B match C while A
and C do not. So a wording joins a group only when it matches every wording
already in it, and pairs are taken from the most certain down. The groups
are therefore sets in which every pair matches, and the same judgments
always give the same groups.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .nesting import DEFAULT_NESTING_THRESHOLD, NestingPair
from .types import CategoryId, validate_probability

# One group: the ids of its wordings, in the order they were given
Group = tuple[CategoryId, ...]


def same_thing(
    probabilities: Mapping[NestingPair, float],
    first: CategoryId,
    second: CategoryId,
    threshold: float = DEFAULT_NESTING_THRESHOLD,
) -> bool:
    """Whether two categories were judged to sit inside each other."""
    forward = probabilities.get((first, second))
    backward = probabilities.get((second, first))
    return (
        forward is not None
        and backward is not None
        and forward >= threshold
        and backward >= threshold
    )


def derive_groups(
    categories: Iterable[CategoryId],
    probabilities: Mapping[NestingPair, float],
    threshold: float = DEFAULT_NESTING_THRESHOLD,
) -> tuple[Group, ...]:
    """
    Put categories that are wordings of the same thing into groups.

    Every category is in exactly one group, alone when it matches nothing.
    Two groups merge only when every wording in one matches every wording in
    the other, strongest pairs first, so no group is held together by a chain.
    A pair with a judgment missing either way does not match.

    Args:
        categories: The category ids, in the order groups should list them
        probabilities: For each ordered pair, the probability that the first
            sits inside the second
        threshold: How sure the model must be, both ways

    Returns:
        The groups, each in the given order, sorted by their first member's
        place in that order

    Raises:
        InvalidJudgmentError: If the threshold is not a probability
    """
    validate_probability(threshold, "Grouping threshold")
    order = {category: index for index, category in enumerate(dict.fromkeys(categories))}
    group_of: dict[CategoryId, set[CategoryId]] = {
        category: {category} for category in order
    }

    matches = sorted(
        (
            -min(probabilities[(first, second)], probabilities[(second, first)]),
            order[first],
            order[second],
            first,
            second,
        )
        for first in order
        for second in order
        if order[first] < order[second]
        and same_thing(probabilities, first, second, threshold)
    )
    for _, _, _, first, second in matches:
        ours, theirs = group_of[first], group_of[second]
        if ours is theirs:
            continue
        if all(
            same_thing(probabilities, one, other, threshold)
            for one in ours
            for other in theirs
        ):
            ours |= theirs
            for member in theirs:
                group_of[member] = ours

    groups: dict[int, Group] = {}
    for members in group_of.values():
        listed = tuple(sorted(members, key=order.__getitem__))
        groups[order[listed[0]]] = listed
    return tuple(groups[index] for index in sorted(groups))
