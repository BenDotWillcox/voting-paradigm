"""Tests for anonymous ranked profiles."""

import pytest

from voting import (
    InvalidProfileError,
    InvalidRankingError,
    create_ranked_profile,
    profile_ballots,
    resolve_ranked_pairs,
    Candidate,
)

ABC = ["a", "b", "c"]


class TestCanonicalForm:
    def test_rows_sorted_in_candidate_order(self):
        profile = create_ranked_profile(
            ABC, [(2, ["c", "b", "a"]), (3, ["a", "c", "b"]), (1, ["a", "b", "c"])]
        )

        assert profile.rows == (
            (1, ("a", "b", "c")),
            (3, ("a", "c", "b")),
            (2, ("c", "b", "a")),
        )

    def test_duplicate_rankings_merge(self):
        profile = create_ranked_profile(ABC, [(2, ["b", "a", "c"]), (3, ["b", "a", "c"])])

        assert profile.rows == ((5, ("b", "a", "c")),)

    def test_zero_counts_dropped(self):
        profile = create_ranked_profile(ABC, [(0, ["a", "b", "c"]), (1, ["c", "a", "b"])])

        assert profile.rows == ((1, ("c", "a", "b")),)

    def test_equal_electorates_compare_and_hash_equal(self):
        first = create_ranked_profile(ABC, [(1, ["a", "b", "c"]), (2, ["b", "c", "a"])])
        second = create_ranked_profile(
            ABC, [(2, ["b", "c", "a"]), (1, ["a", "b", "c"])]
        )

        assert first == second
        assert hash(first) == hash(second)

    def test_total_voters(self):
        profile = create_ranked_profile(ABC, [(4, ["a", "b", "c"]), (6, ["c", "b", "a"])])

        assert profile.total_voters == 10

    def test_empty_profile_has_no_voters(self):
        profile = create_ranked_profile(ABC, [])

        assert profile.rows == ()
        assert profile.total_voters == 0


class TestValidation:
    def test_no_candidates(self):
        with pytest.raises(InvalidProfileError):
            create_ranked_profile([], [])

    def test_duplicate_candidates(self):
        with pytest.raises(InvalidProfileError):
            create_ranked_profile(["a", "a", "b"], [])

    def test_negative_count(self):
        with pytest.raises(InvalidProfileError):
            create_ranked_profile(ABC, [(-1, ["a", "b", "c"])])

    def test_incomplete_ranking(self):
        with pytest.raises(InvalidRankingError):
            create_ranked_profile(ABC, [(1, ["a", "b"])])

    def test_unknown_candidate(self):
        with pytest.raises(InvalidRankingError):
            create_ranked_profile(ABC, [(1, ["a", "b", "z"])])

    def test_repeated_candidate_in_ranking(self):
        with pytest.raises(InvalidRankingError):
            create_ranked_profile(ABC, [(1, ["a", "a", "b"])])


class TestBallots:
    def test_expands_one_ballot_per_voter_in_row_order(self):
        profile = create_ranked_profile(ABC, [(1, ["b", "a", "c"]), (2, ["a", "c", "b"])])

        ballots = profile_ballots(profile)

        assert [b.voter_id for b in ballots] == ["v1", "v2", "v3"]
        assert [b.ranking for b in ballots] == [
            ["a", "c", "b"],
            ["a", "c", "b"],
            ["b", "a", "c"],
        ]
        assert ballots[0].rank_lookup == {"a": 1, "c": 2, "b": 3}

    def test_ballots_resolve_like_the_profile(self):
        profile = create_ranked_profile(
            ABC,
            [(4, ["a", "c", "b"]), (6, ["b", "a", "c"]), (3, ["c", "a", "b"]), (2, ["c", "b", "a"])],
        )
        candidates = [Candidate(id=c, name=c.upper()) for c in ABC]

        result = resolve_ranked_pairs(candidates, profile_ballots(profile))

        assert result.total_ballots == 15
        assert result.pairwise_matrix["a"]["c"] == 10
        assert result.winners == ["a"]
