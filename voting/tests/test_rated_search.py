"""Tests for utility transformations and the rated-method search."""

import random

import numpy as np
import pytest

from voting.ballot_models import create_utility_profile
from voting.ballots.ranked_profile import InvalidProfileError
from voting.criteria.utility_transformations import (
    add_clone,
    add_voters,
    combine,
    is_raise,
    move_voters,
    remove_candidate,
    utility_counts,
)
from voting.search import RATED_METHODS, certify, resolve_rated, search
from voting.search.rated import count_vectors, type_ballots, voter_types, winners

ABC = ("A", "B", "C")


def profile(*rows: tuple[int, tuple[int, int, int]]):
    return create_utility_profile(ABC, [(count, dict(zip(ABC, u))) for count, u in rows])


class TestIsRaise:
    def test_raising_the_middle_candidate(self):
        assert is_raise((100, 50, 0), (100, 75, 0), 1)

    def test_rescaled_raise_of_the_top_candidate(self):
        # C at 100 with B at 50 becomes C at 100 with B at 25: as if C rose to 200
        assert is_raise((0, 50, 100), (0, 25, 100), 2)

    def test_lowering_is_not_a_raise(self):
        assert not is_raise((100, 75, 0), (100, 50, 0), 1)

    def test_changing_the_others_is_not_a_raise(self):
        assert not is_raise((100, 50, 0), (0, 50, 100), 1)


class TestUtilityTransformations:
    BASE = profile((2, (100, 50, 0)), (1, (0, 100, 50)))

    def test_move_voters(self):
        after = move_voters(self.BASE, (100, 50, 0), (100, 75, 0), 1)

        assert utility_counts(after) == {(100, 50, 0): 1, (100, 75, 0): 1, (0, 100, 50): 1}

    def test_cannot_move_more_than_hold_the_utilities(self):
        with pytest.raises(InvalidProfileError):
            move_voters(self.BASE, (0, 100, 50), (0, 100, 75), 2)

    def test_add_voters_and_combine(self):
        assert utility_counts(add_voters(self.BASE, (0, 100, 50), 2)) == {(100, 50, 0): 2, (0, 100, 50): 3}
        assert utility_counts(combine(self.BASE, self.BASE)) == {(100, 50, 0): 4, (0, 100, 50): 2}

    def test_remove_candidate_keeps_the_other_utilities(self):
        after = remove_candidate(self.BASE, "B")

        assert after.candidates == ("A", "C")
        assert utility_counts(after) == {(100, 0): 2, (0, 50): 1}

    def test_exact_clone_copies_the_original(self):
        after = add_clone(self.BASE, "B", "D")

        assert after.candidates == ("A", "B", "C", "D")
        assert utility_counts(after) == {(100, 50, 0, 50): 2, (0, 100, 50, 100): 1}


class TestKernelMatchesTheReference:
    @pytest.mark.parametrize("method", RATED_METHODS)
    def test_winners_and_ties(self, method):
        """The search totals ballots as matrices; the reference methods must agree."""
        types = voter_types(ABC)
        ballots = type_ballots(ABC, types)
        rng = random.Random(11)
        for _ in range(300):
            n = rng.randint(1, 9)
            counts = np.zeros(len(types), dtype=np.int64)
            for _ in range(n):
                counts[rng.randrange(len(types))] += 1
            kernel = int(winners((counts @ ballots.matrix(method))[None, :])[0])

            rows = [(int(c), dict(zip(ABC, types[t]))) for t, c in enumerate(counts) if c]
            reference = resolve_rated(method, create_utility_profile(ABC, rows))

            if reference.tiebreak_applied:
                assert kernel == -1
            else:
                assert ABC[kernel] == reference.winners[0]

    def test_count_vectors_cover_every_profile_once(self):
        vectors = count_vectors(3, 4)

        assert len(vectors) == 20
        assert len({tuple(v) for v in vectors}) == 20
        assert (vectors.sum(axis=1) == 3).all()


class TestRatedSearch:
    def test_approval_fails_majority_and_certifies(self):
        result = search("approval", "majority", 4)

        assert result.specimen is not None
        certify(result.specimen)

    def test_quadratic_monotonicity_specimen(self):
        """Raising C for two voters moves their credits from opposing A to opposing B."""
        specimen = search("quadratic", "monotonicity", 4).specimen

        assert specimen is not None
        certify(specimen)
        assert specimen.profile("before").winner == "C"
        assert specimen.profile("after").winner == "A"

    def test_score_has_no_exact_clone_failure(self):
        assert search("score", "clones", 5).specimen is None
