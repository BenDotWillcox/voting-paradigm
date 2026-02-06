"""Tests for ranked choice ballot type."""

import pytest
from voting import (
    Candidate,
    create_ranked_choice_ballot,
    is_ranked_choice_abstention,
    get_rank,
    get_choice_at_rank,
    get_first_choice,
    prefers,
    InvalidRankingError,
)


def make_candidates(*names: str) -> list[Candidate]:
    """Helper to create candidates from names."""
    return [Candidate(id=name.lower(), name=name) for name in names]


def candidate_ids(candidates: list[Candidate]) -> list[str]:
    """Extract IDs from candidates."""
    return [c.id for c in candidates]


class TestRankedChoiceBallotCreation:
    """Tests for creating ranked choice ballots."""

    def test_create_valid_ranking(self):
        """Create a ballot with a valid complete ranking."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )
        assert ballot.voter_id == "v1"
        assert ballot.ranking == ["alice", "bob", "carol"]

    def test_create_abstention_with_none(self):
        """Create abstention by passing None."""
        ballot = create_ranked_choice_ballot("v1", ranking=None)
        assert ballot.ranking == []
        assert is_ranked_choice_abstention(ballot)

    def test_create_abstention_with_empty_list(self):
        """Create abstention by passing empty list."""
        ballot = create_ranked_choice_ballot("v1", ranking=[])
        assert ballot.ranking == []
        assert is_ranked_choice_abstention(ballot)

    def test_reject_duplicate_candidates(self):
        """Ranking with duplicates should raise error."""
        with pytest.raises(InvalidRankingError, match="duplicate"):
            create_ranked_choice_ballot(
                "v1",
                ranking=["alice", "bob", "alice"],
            )

    def test_validate_against_candidate_list(self):
        """Validate ranking contains exactly the expected candidates."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)

        # Valid ranking
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["bob", "alice", "carol"],
            candidates=ids,
        )
        assert ballot.ranking == ["bob", "alice", "carol"]

    def test_reject_incomplete_ranking(self):
        """Ranking missing candidates should raise error."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)

        with pytest.raises(InvalidRankingError, match="incomplete"):
            create_ranked_choice_ballot(
                "v1",
                ranking=["alice", "bob"],  # missing carol
                candidates=ids,
            )

    def test_reject_unknown_candidates(self):
        """Ranking with unknown candidates should raise error."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)

        with pytest.raises(InvalidRankingError, match="unknown"):
            create_ranked_choice_ballot(
                "v1",
                ranking=["alice", "bob", "charlie"],  # charlie not in candidates
                candidates=ids,
            )

    def test_reject_wrong_candidates(self):
        """Ranking with both missing and extra candidates."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)

        with pytest.raises(InvalidRankingError, match="Missing.*Extra"):
            create_ranked_choice_ballot(
                "v1",
                ranking=["alice", "bob", "david"],  # missing carol, has david
                candidates=ids,
            )


class TestRankedChoiceAbstention:
    """Tests for abstention handling."""

    def test_is_abstention_empty(self):
        """Empty ranking is an abstention."""
        ballot = create_ranked_choice_ballot("v1", ranking=[])
        assert is_ranked_choice_abstention(ballot) is True

    def test_is_not_abstention_with_ranking(self):
        """Ballot with ranking is not an abstention."""
        ballot = create_ranked_choice_ballot("v1", ranking=["alice", "bob"])
        assert is_ranked_choice_abstention(ballot) is False


class TestRankQueries:
    """Tests for querying ranks on a ballot."""

    def test_get_rank(self):
        """Get the rank of each candidate."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )

        assert get_rank(ballot, "alice") == 1
        assert get_rank(ballot, "bob") == 2
        assert get_rank(ballot, "carol") == 3

    def test_get_rank_not_found(self):
        """Get rank of candidate not on ballot returns None."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob"],
        )
        assert get_rank(ballot, "charlie") is None

    def test_get_rank_abstention(self):
        """Get rank on abstention ballot returns None."""
        ballot = create_ranked_choice_ballot("v1", ranking=None)
        assert get_rank(ballot, "alice") is None

    def test_get_choice_at_rank(self):
        """Get the candidate at each rank position."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )

        assert get_choice_at_rank(ballot, 1) == "alice"
        assert get_choice_at_rank(ballot, 2) == "bob"
        assert get_choice_at_rank(ballot, 3) == "carol"

    def test_get_choice_at_rank_out_of_bounds(self):
        """Get choice at invalid rank returns None."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob"],
        )

        assert get_choice_at_rank(ballot, 0) is None  # ranks are 1-indexed
        assert get_choice_at_rank(ballot, 3) is None  # out of range
        assert get_choice_at_rank(ballot, -1) is None

    def test_get_first_choice(self):
        """Get first choice from ballot."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["bob", "alice", "carol"],
        )
        assert get_first_choice(ballot) == "bob"

    def test_get_first_choice_abstention(self):
        """Get first choice from abstention returns None."""
        ballot = create_ranked_choice_ballot("v1", ranking=None)
        assert get_first_choice(ballot) is None


class TestRankingImmutability:
    """Tests to ensure rankings are copied, not referenced."""

    def test_ranking_is_copied(self):
        """Modifying original list doesn't affect ballot."""
        original = ["alice", "bob", "carol"]
        ballot = create_ranked_choice_ballot("v1", ranking=original)

        original.append("david")
        original[0] = "changed"

        assert ballot.ranking == ["alice", "bob", "carol"]
        assert len(ballot.ranking) == 3


class TestDualRepresentation:
    """Tests for the dual list/dict representation."""

    def test_rank_lookup_created(self):
        """rank_lookup dict is created alongside ranking list."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )

        assert ballot.rank_lookup == {"alice": 1, "bob": 2, "carol": 3}

    def test_rank_lookup_empty_for_abstention(self):
        """Abstention has empty rank_lookup."""
        ballot = create_ranked_choice_ballot("v1", ranking=None)
        assert ballot.rank_lookup == {}

    def test_representations_are_consistent(self):
        """Both representations give the same answers."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["bob", "carol", "alice"],
        )

        # Check each candidate
        for i, candidate in enumerate(ballot.ranking):
            expected_rank = i + 1
            assert ballot.rank_lookup[candidate] == expected_rank
            assert get_rank(ballot, candidate) == expected_rank

    def test_get_rank_uses_dict_lookup(self):
        """get_rank should be O(1) using dict, not O(n) list scan."""
        # This is more of a design verification - the implementation
        # should use rank_lookup.get() not ranking.index()
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )

        # Verify it works correctly (implementation detail is in code)
        assert get_rank(ballot, "bob") == 2
        assert get_rank(ballot, "unknown") is None


class TestPrefers:
    """Tests for pairwise preference comparisons."""

    def test_prefers_higher_ranked(self):
        """Voter prefers higher-ranked candidate."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )

        assert prefers(ballot, "alice", "bob") is True
        assert prefers(ballot, "alice", "carol") is True
        assert prefers(ballot, "bob", "carol") is True

    def test_prefers_lower_ranked_is_false(self):
        """Voter does not prefer lower-ranked candidate."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )

        assert prefers(ballot, "bob", "alice") is False
        assert prefers(ballot, "carol", "alice") is False
        assert prefers(ballot, "carol", "bob") is False

    def test_prefers_unknown_candidate_returns_none(self):
        """Unknown candidate returns None."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob"],
        )

        assert prefers(ballot, "alice", "unknown") is None
        assert prefers(ballot, "unknown", "alice") is None
        assert prefers(ballot, "unknown", "other") is None

    def test_prefers_abstention_returns_none(self):
        """Abstention ballot returns None for any comparison."""
        ballot = create_ranked_choice_ballot("v1", ranking=None)

        assert prefers(ballot, "alice", "bob") is None

    def test_prefers_same_candidate(self):
        """Comparing candidate to themselves returns False (not preferred over self)."""
        ballot = create_ranked_choice_ballot(
            "v1",
            ranking=["alice", "bob", "carol"],
        )

        # rank_a < rank_b is False when a == b
        assert prefers(ballot, "alice", "alice") is False
