"""Tests for utility profiles and the sincere ballot model."""

import random

import pytest

from voting.ballot_models import (
    SINCERE_V1,
    UTILITY_SCALE,
    cast_profile,
    create_utility_profile,
    evenly_spaced,
    rankings_of,
    rated_ballots,
)
from voting.ballots.ranked_profile import InvalidProfileError

ABC = ("A", "B", "C")


def cast(*utilities: int, candidates=ABC):
    return SINCERE_V1.cast(candidates[: len(utilities)], list(utilities))


class TestSincereRanking:
    def test_highest_utility_first(self):
        ballots = cast(20, 90, 55)

        assert ballots.ranking == ("B", "C", "A")
        assert ballots.choice == "B"

    def test_equal_utilities_keep_candidate_order(self):
        assert cast(50, 80, 50).ranking == ("B", "A", "C")


class TestSincereApproval:
    def test_strictly_above_the_mean(self):
        # Mean 50: B at 50 is not above it
        assert cast(100, 50, 0).approvals == ("A",)

    def test_close_second_is_approved(self):
        # Mean 53.3: B at 60 is above it
        assert cast(100, 60, 0).approvals == ("A", "B")

    def test_indifferent_voter_abstains(self):
        assert cast(40, 40, 40).approvals == ()


class TestSincereScore:
    def test_rescaled_from_least_to_most_favorite(self):
        assert cast(100, 75, 0).scores == {"A": 10, "B": 8, "C": 0}  # 7.5 rounds up

    def test_rescaling_ignores_absolute_level(self):
        assert cast(60, 50, 40).scores == cast(100, 50, 0).scores

    def test_indifferent_voter_scores_the_midpoint(self):
        assert cast(70, 70, 70).scores == {"A": 5, "B": 5, "C": 5}


class TestSincereQuadratic:
    def test_votes_follow_distance_from_the_mean(self):
        ballots = cast(100, 50, 0)

        assert ballots.allocations == {"A": 7, "C": -7}
        assert ballots.credits_used == 98

    def test_uneven_spacing(self):
        assert cast(90, 75, 10).allocations == {"A": 5, "B": 3, "C": -8}

    def test_rounding_overshoot_is_trimmed_from_the_largest_vote(self):
        ballots = cast(100, 100, 100, 0, candidates=("A", "B", "C", "D"))

        # 2.9 x 3 and -8.7 round to 3, 3, 3, -9 (108 credits); -9 is trimmed to -8
        assert ballots.allocations == {"A": 3, "B": 3, "C": 3, "D": -8}
        assert ballots.credits_used <= ballots.credit_budget

    def test_indifferent_voter_casts_no_votes(self):
        assert cast(30, 30, 30).allocations == {}

    def test_never_exceeds_the_budget(self):
        rng = random.Random(4)
        for _ in range(500):
            k = rng.randint(2, 5)
            utilities = [rng.randint(0, UTILITY_SCALE) for _ in range(k)]
            ballots = SINCERE_V1.cast(("A", "B", "C", "D", "E")[:k], utilities)
            assert ballots.credits_used <= ballots.credit_budget


class TestUtilityProfile:
    def test_keeps_row_order_and_does_not_merge(self):
        profile = create_utility_profile(
            ABC,
            [(2, {"A": 0, "B": 50, "C": 100}), (1, {"A": 100, "B": 50, "C": 0}), (3, {"A": 0, "B": 50, "C": 100})],
        )

        assert profile.rows == ((2, (0, 50, 100)), (1, (100, 50, 0)), (3, (0, 50, 100)))
        assert profile.total_voters == 6

    @pytest.mark.parametrize(
        "rows",
        [
            [(1, {"A": 0, "B": 50})],  # missing a candidate
            [(1, {"A": 0, "B": 50, "C": 100, "D": 5})],  # unknown candidate
            [(1, {"A": 0, "B": 50, "C": 101})],  # above the scale
            [(-1, {"A": 0, "B": 50, "C": 100})],  # negative count
        ],
    )
    def test_rejects_invalid_rows(self, rows):
        with pytest.raises(InvalidProfileError):
            create_utility_profile(ABC, rows)

    def test_rankings_merge_into_a_canonical_ranked_profile(self):
        profile = create_utility_profile(
            ABC,
            [(2, {"A": 90, "B": 60, "C": 0}), (1, {"A": 100, "B": 10, "C": 5})],
        )

        assert rankings_of(profile, SINCERE_V1).rows == ((3, ("A", "B", "C")),)

    def test_rated_ballots_one_per_voter(self):
        profile = create_utility_profile(
            ABC,
            [(2, {"A": 100, "B": 60, "C": 0}), (1, {"A": 0, "B": 0, "C": 0})],
        )

        approval, score, quadratic = rated_ballots(profile, SINCERE_V1)

        assert [sorted(b.approvals) for b in approval] == [["A", "B"], ["A", "B"], []]
        assert len(score) == len(quadratic) == 3
        assert cast_profile(profile, SINCERE_V1)[1].allocations == {}

    def test_evenly_spaced(self):
        assert evenly_spaced(ABC, ["C", "A", "B"]) == {"C": 100, "A": 50, "B": 0}
