"""Tests for grouping categories that are wordings of the same thing."""

from __future__ import annotations

import pytest

from delegation import InvalidJudgmentError
from delegation.grouping import derive_groups, same_thing

A, B, C, D = "cat_a", "cat_b", "cat_c", "cat_d"


def both_ways(*pairs: tuple[str, str, float, float]) -> dict[tuple[str, str], float]:
    """Containment probabilities from (first, second, forward, backward) rows."""
    probabilities: dict[tuple[str, str], float] = {}
    for first, second, forward, backward in pairs:
        probabilities[(first, second)] = forward
        probabilities[(second, first)] = backward
    return probabilities


class TestSameThing:
    def test_needs_a_yes_both_ways(self) -> None:
        judged = both_ways((A, B, 0.9, 0.8), (A, C, 0.9, 0.3))
        assert same_thing(judged, A, B) and same_thing(judged, B, A)
        assert not same_thing(judged, A, C)  # nested, not the same

    def test_a_missing_direction_is_not_a_match(self) -> None:
        assert not same_thing({(A, B): 0.99}, A, B)
        assert not same_thing({}, A, B)

    def test_the_threshold_is_inclusive(self) -> None:
        judged = both_ways((A, B, 0.7, 0.7))
        assert same_thing(judged, A, B, 0.7)
        assert not same_thing(judged, A, B, 0.71)


class TestDeriveGroups:
    def test_every_category_is_in_exactly_one_group(self) -> None:
        groups = derive_groups([A, B, C, D], both_ways((A, C, 0.9, 0.9)))
        assert groups == ((A, C), (B,), (D,))
        assert sorted(member for group in groups for member in group) == [A, B, C, D]

    def test_with_no_judgments_everything_stands_alone(self) -> None:
        assert derive_groups([B, A], {}) == ((B,), (A,))

    def test_nesting_is_not_grouping(self) -> None:
        assert derive_groups([A, B], both_ways((A, B, 0.95, 0.2))) == ((A,), (B,))

    def test_a_chain_does_not_hold_a_group_together(self) -> None:
        # A matches B and B matches C, but A and C do not match. B joins the
        # stronger of its two matches and the third stays out.
        judged = both_ways((A, B, 0.9, 0.9), (B, C, 0.8, 0.8), (A, C, 0.2, 0.2))
        assert derive_groups([A, B, C], judged) == ((A, B), (C,))
        stronger_other_way = both_ways(
            (A, B, 0.8, 0.8), (B, C, 0.9, 0.9), (A, C, 0.2, 0.2)
        )
        assert derive_groups([A, B, C], stronger_other_way) == ((A,), (B, C))

    def test_three_that_all_match_are_one_group(self) -> None:
        judged = both_ways((A, B, 0.9, 0.9), (B, C, 0.8, 0.8), (A, C, 0.75, 0.9))
        assert derive_groups([C, A, B], judged) == ((C, A, B),)

    def test_groups_follow_the_given_order_not_the_judgment_order(self) -> None:
        judged = both_ways((D, B, 0.9, 0.9))
        assert derive_groups([A, B, C, D], judged) == ((A,), (B, D), (C,))
        assert derive_groups([D, C, B, A], judged) == ((D, B), (C,), (A,))

    def test_a_higher_threshold_splits_a_group(self) -> None:
        judged = both_ways((A, B, 0.75, 0.9))
        assert derive_groups([A, B], judged, 0.7) == ((A, B),)
        assert derive_groups([A, B], judged, 0.8) == ((A,), (B,))

    def test_repeated_ids_are_listed_once(self) -> None:
        assert derive_groups([A, A, B], {}) == ((A,), (B,))

    def test_the_threshold_must_be_a_probability(self) -> None:
        with pytest.raises(InvalidJudgmentError):
            derive_groups([A], {}, 1.5)
