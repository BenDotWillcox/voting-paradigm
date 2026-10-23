"""Tests for transformations between profiles."""

import pytest

from voting import (
    InvalidProfileError,
    InvalidRankingError,
    add_voters,
    are_clones,
    combine,
    create_ranked_profile,
    raise_candidate,
    remove_candidate,
)

ABC = ["a", "b", "c"]


def profile(*rows: tuple[int, str], candidates: list[str] = ABC):
    return create_ranked_profile(candidates, [(count, list(r)) for count, r in rows])


class TestRaiseCandidate:
    def test_moves_some_voters_and_keeps_rival_order(self):
        before = profile((3, "bca"), (2, "cab"))

        after = raise_candidate(before, ("b", "c", "a"), "a", 0, 2)

        assert after == profile((2, "abc"), (1, "bca"), (2, "cab"))

    def test_raise_one_place(self):
        after = raise_candidate(profile((1, "bca")), ("b", "c", "a"), "a", 1, 1)

        assert after == profile((1, "bac"))

    def test_input_unchanged(self):
        before = profile((3, "bca"))

        raise_candidate(before, ("b", "c", "a"), "a", 0, 1)

        assert before == profile((3, "bca"))

    def test_more_voters_than_cast_the_ranking(self):
        with pytest.raises(InvalidProfileError):
            raise_candidate(profile((1, "bca")), ("b", "c", "a"), "a", 0, 2)

    def test_ranking_not_in_profile(self):
        with pytest.raises(InvalidProfileError):
            raise_candidate(profile((1, "bca")), ("c", "b", "a"), "a", 0, 1)

    def test_must_move_up(self):
        with pytest.raises(InvalidProfileError):
            raise_candidate(profile((1, "abc")), ("a", "b", "c"), "b", 1, 1)


class TestAddVoters:
    def test_adds_to_existing_row(self):
        assert add_voters(profile((1, "abc")), ("a", "b", "c"), 2) == profile((3, "abc"))

    def test_adds_new_row(self):
        assert add_voters(profile((1, "abc")), ("c", "a", "b"), 1) == profile(
            (1, "abc"), (1, "cab")
        )

    def test_needs_a_positive_count(self):
        with pytest.raises(InvalidProfileError):
            add_voters(profile((1, "abc")), ("a", "b", "c"), 0)

    def test_validates_the_ranking(self):
        with pytest.raises(InvalidRankingError):
            add_voters(profile((1, "abc")), ("a", "b"), 1)


class TestCombine:
    def test_pools_counts(self):
        combined = combine(profile((2, "abc"), (1, "cab")), profile((1, "abc"), (4, "bca")))

        assert combined == profile((3, "abc"), (4, "bca"), (1, "cab"))

    def test_candidates_must_match(self):
        with pytest.raises(InvalidProfileError):
            combine(profile((1, "abc")), profile((1, "ab"), candidates=["a", "b"]))


class TestRemoveCandidate:
    def test_drops_candidate_and_merges_rows(self):
        reduced = remove_candidate(profile((2, "abc"), (1, "acb"), (3, "cba")), "c")

        assert reduced.candidates == ("a", "b")
        assert reduced.rows == ((3, ("a", "b")), (3, ("b", "a")))

    def test_unknown_candidate(self):
        with pytest.raises(InvalidProfileError):
            remove_candidate(profile((1, "abc")), "z")

    def test_only_candidate(self):
        single = create_ranked_profile(["a"], [(2, ["a"])])

        with pytest.raises(InvalidProfileError):
            remove_candidate(single, "a")


class TestAreClones:
    def test_adjacent_in_every_ranking(self):
        assert are_clones(profile((2, "abc"), (1, "cba"), (1, "bca")), "b", "c")

    def test_separated_by_one_voter(self):
        assert not are_clones(profile((2, "abc"), (1, "bac")), "b", "c")

    def test_empty_profile(self):
        assert are_clones(profile(), "a", "c")
