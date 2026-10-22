"""Tests for criteria checked against a single profile."""

from voting import (
    condorcet_loser,
    condorcet_winner,
    create_ranked_profile,
    majority_winner,
    pairwise_counts,
)

ABC = ["a", "b", "c"]


def profile(*rows: tuple[int, str]):
    """Build a profile from rows like (4, "acb")."""
    return create_ranked_profile(ABC, [(count, list(ranking)) for count, ranking in rows])


# 35 A>C>B, 33 B>C>A, 32 C>B>A: C beats A 65-35 and B 67-33; A loses to both
CENTER_SQUEEZE = profile((35, "acb"), (33, "bca"), (32, "cba"))

# 4 A>C>B, 6 B>A>C, 3 C>A>B, 2 C>B>A: B>A, C>B, A>C
MAJORITY_CYCLE = profile((4, "acb"), (6, "bac"), (3, "cab"), (2, "cba"))


class TestPairwiseCounts:
    def test_counts_every_ordered_pair(self):
        matrix = pairwise_counts(CENTER_SQUEEZE)

        assert matrix["c"]["a"] == 65
        assert matrix["a"]["c"] == 35
        assert matrix["c"]["b"] == 67
        assert matrix["b"]["c"] == 33
        assert matrix["b"]["a"] == 65
        assert matrix["a"]["b"] == 35

    def test_each_pair_sums_to_the_electorate(self):
        matrix = pairwise_counts(MAJORITY_CYCLE)

        for a in ABC:
            for b in ABC:
                if a != b:
                    assert matrix[a][b] + matrix[b][a] == 15


class TestMajorityWinner:
    def test_more_than_half_first_choices(self):
        assert majority_winner(profile((3, "abc"), (2, "bca"))) == "a"

    def test_exactly_half_is_not_a_majority(self):
        assert majority_winner(profile((2, "abc"), (2, "bca"))) is None

    def test_plurality_without_majority(self):
        assert majority_winner(CENTER_SQUEEZE) is None

    def test_empty_profile(self):
        assert majority_winner(profile()) is None


class TestCondorcetWinner:
    def test_center_squeeze_winner(self):
        assert condorcet_winner(CENTER_SQUEEZE) == "c"

    def test_cycle_has_none(self):
        assert condorcet_winner(MAJORITY_CYCLE) is None

    def test_pairwise_tie_blocks_a_winner(self):
        # A beats C 2-0, but A and B tie 1-1
        assert condorcet_winner(profile((1, "abc"), (1, "bac"))) is None

    def test_majority_winner_is_condorcet_winner(self):
        majority = profile((3, "abc"), (2, "cba"))

        assert condorcet_winner(majority) == majority_winner(majority) == "a"


class TestCondorcetLoser:
    def test_center_squeeze_loser(self):
        assert condorcet_loser(CENTER_SQUEEZE) == "a"

    def test_cycle_has_none(self):
        assert condorcet_loser(MAJORITY_CYCLE) is None

    def test_pairwise_tie_blocks_a_loser(self):
        # C loses to A 0-2 but ties B 1-1 (and B also loses to A but ties C)
        assert condorcet_loser(profile((1, "abc"), (1, "acb"))) is None
