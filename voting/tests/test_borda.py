"""Tests for Borda Count voting method."""

import pytest
from voting import (
    Candidate,
    create_ranked_choice_ballot,
    resolve_borda,
    BordaResult,
)


def make_candidates(*names: str) -> list[Candidate]:
    """Helper to create candidates from names."""
    return [Candidate(id=name.lower(), name=name) for name in names]


def candidate_ids(candidates: list[Candidate]) -> list[str]:
    """Extract IDs from candidates."""
    return [c.id for c in candidates]


class TestBordaPointCalculation:
    """Tests for point calculation."""

    def test_standard_scoring_three_candidates(self):
        """With 3 candidates: 1st=2pts, 2nd=1pt, 3rd=0pts."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        assert result.point_totals["alice"] == 2  # 1st place
        assert result.point_totals["bob"] == 1    # 2nd place
        assert result.point_totals["carol"] == 0  # 3rd place
        assert result.max_points_per_ballot == 2

    def test_standard_scoring_four_candidates(self):
        """With 4 candidates: 1st=3pts, 2nd=2pts, 3rd=1pt, 4th=0pts."""
        candidates = make_candidates("Alice", "Bob", "Carol", "Dave")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol", "dave"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        assert result.point_totals["alice"] == 3
        assert result.point_totals["bob"] == 2
        assert result.point_totals["carol"] == 1
        assert result.point_totals["dave"] == 0
        assert result.max_points_per_ballot == 3

    def test_points_accumulate_across_ballots(self):
        """Points sum across all ballots."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice", "carol"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        # Alice: 2 + 2 + 1 = 5
        # Bob: 1 + 1 + 2 = 4
        # Carol: 0 + 0 + 0 = 0
        assert result.point_totals["alice"] == 5
        assert result.point_totals["bob"] == 4
        assert result.point_totals["carol"] == 0

    def test_two_candidates(self):
        """With 2 candidates: 1st=1pt, 2nd=0pts."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        assert result.point_totals["alice"] == 1
        assert result.point_totals["bob"] == 0
        assert result.max_points_per_ballot == 1


class TestBordaWinner:
    """Tests for determining the winner."""

    def test_clear_winner(self):
        """Candidate with most points wins."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "carol", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice", "carol"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        # Alice: 2 + 2 + 1 = 5
        # Bob: 1 + 0 + 2 = 3
        # Carol: 0 + 1 + 0 = 1
        assert result.winners == ["alice"]
        assert result.point_totals["alice"] == 5
        assert result.tiebreak_applied is False

    def test_consensus_candidate_wins(self):
        """Borda favors broadly acceptable candidates."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Alice is polarizing (some love, some hate)
        # Bob is everyone's second choice (consensus)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["carol", "bob", "alice"], ids),
            create_ranked_choice_ballot("v4", ["carol", "bob", "alice"], ids),
            create_ranked_choice_ballot("v5", ["carol", "bob", "alice"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        # Alice: 2+2+0+0+0 = 4
        # Bob: 1+1+1+1+1 = 5 (everyone's 2nd choice)
        # Carol: 0+0+2+2+2 = 6
        assert result.winners == ["carol"]
        assert result.point_totals["carol"] == 6
        assert result.point_totals["bob"] == 5
        assert result.point_totals["alice"] == 4


class TestBordaTiebreak:
    """Tests for tiebreak behavior."""

    def test_two_way_tie(self):
        """Two candidates with equal points triggers tiebreak."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["bob", "alice"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        # Alice: 1 + 0 = 1
        # Bob: 0 + 1 = 1
        assert result.tiebreak_applied is True
        assert len(result.winners) == 1
        assert result.winners[0] in ["alice", "bob"]

    def test_three_way_tie(self):
        """Three candidates with equal points."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["bob", "carol", "alice"], ids),
            create_ranked_choice_ballot("v3", ["carol", "alice", "bob"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        # Each candidate gets 2+1+0 = 3 points
        assert result.point_totals["alice"] == 3
        assert result.point_totals["bob"] == 3
        assert result.point_totals["carol"] == 3
        assert result.tiebreak_applied is True
        assert len(result.winners) == 1

    def test_custom_tiebreak(self):
        """Can provide custom tiebreak function."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["bob", "alice"], ids),
        ]

        def alphabetical(tied: list[str]) -> str:
            return sorted(tied)[0]

        result = resolve_borda(candidates, ballots, tiebreak=alphabetical)

        assert result.winners == ["alice"]
        assert result.tiebreak_applied is True


class TestBordaAbstentions:
    """Tests for abstention handling."""

    def test_abstentions_excluded(self):
        """Abstentions don't contribute points."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", None),  # abstention
        ]

        result = resolve_borda(candidates, ballots)

        assert result.abstentions == 1
        assert result.total_ballots == 3
        # Only 2 ballots contribute
        assert result.point_totals["alice"] == 4  # 2 + 2

    def test_all_abstentions(self):
        """Election with only abstentions."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_ranked_choice_ballot("v1", None),
            create_ranked_choice_ballot("v2", None),
        ]

        result = resolve_borda(candidates, ballots)

        assert result.abstentions == 2
        assert result.point_totals["alice"] == 0
        assert result.point_totals["bob"] == 0
        assert result.tiebreak_applied is True


class TestBordaMetrics:
    """Tests for Borda-specific metrics."""

    def test_avg_points_per_candidate(self):
        """Average points calculation."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["bob", "carol", "alice"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        # Total points: 2+1+0 + 2+1+0 = 6
        # 3 candidates, so avg = 2.0
        assert result.avg_points_per_candidate == 2.0

    def test_vote_counts_equals_point_totals(self):
        """vote_counts field contains point totals for compatibility."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        assert result.vote_counts == result.point_totals


class TestBordaEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_single_candidate(self):
        """Election with only one candidate."""
        candidates = make_candidates("Alice")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice"], ids),
            create_ranked_choice_ballot("v2", ["alice"], ids),
        ]

        result = resolve_borda(candidates, ballots)

        assert result.winners == ["alice"]
        # With 1 candidate, max points = 0
        assert result.point_totals["alice"] == 0
        assert result.max_points_per_ballot == 0

    def test_no_ballots(self):
        """Election with no votes cast."""
        candidates = make_candidates("Alice", "Bob")
        ballots = []

        result = resolve_borda(candidates, ballots)

        assert result.total_ballots == 0
        assert result.point_totals["alice"] == 0
        assert result.point_totals["bob"] == 0
        assert result.tiebreak_applied is True

    def test_no_candidates(self):
        """Election with no candidates."""
        candidates = []
        ballots = []

        result = resolve_borda(candidates, ballots)

        assert result.winners == []
        assert result.max_points_per_ballot == 0
        assert result.avg_points_per_candidate == 0.0

    def test_invalid_candidate_in_ranking_ignored(self):
        """Votes for non-existent candidates don't count."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        # Create ballot with valid ranking
        ballot = create_ranked_choice_ballot("v1", ["alice", "bob"], ids)
        # Manually add invalid candidate (simulating corrupted data)
        ballot.ranking.append("charlie")

        result = resolve_borda(candidates, [ballot])

        # Only Alice and Bob should have points
        assert "charlie" not in result.point_totals
        assert result.point_totals["alice"] == 1
        assert result.point_totals["bob"] == 0
