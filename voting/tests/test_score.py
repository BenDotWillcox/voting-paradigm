"""Tests for Score voting (Range voting) ballot and method."""

import pytest
from voting import (
    Candidate,
    create_score_ballot,
    resolve_score,
    ScoreResult,
    is_score_abstention,
    get_score,
    candidates_scored,
    total_points_given,
    max_score_on_ballot,
    min_score_on_ballot,
    InvalidScoreError,
    MIN_SCORE,
    MAX_SCORE,
)


def make_candidates(*names: str) -> list[Candidate]:
    """Helper to create candidates from names."""
    return [Candidate(id=name.lower(), name=name) for name in names]


class TestScoreBallotCreation:
    """Tests for creating score ballots."""

    def test_create_with_scores(self):
        """Create ballot with valid scores."""
        ballot = create_score_ballot("v1", {"alice": 10, "bob": 5, "carol": 0})
        assert ballot.scores == {"alice": 10, "bob": 5, "carol": 0}
        assert ballot.voter_id == "v1"

    def test_create_partial_scores(self):
        """Create ballot with only some candidates scored."""
        ballot = create_score_ballot("v1", {"alice": 8})
        assert ballot.scores == {"alice": 8}
        assert get_score(ballot, "bob") == 0  # Unscored = 0

    def test_create_abstention_with_none(self):
        """Create abstention by passing None."""
        ballot = create_score_ballot("v1", None)
        assert ballot.scores == {}
        assert is_score_abstention(ballot)

    def test_create_abstention_with_empty_dict(self):
        """Create abstention by passing empty dict."""
        ballot = create_score_ballot("v1", {})
        assert is_score_abstention(ballot)

    def test_reject_score_below_min(self):
        """Score below 0 raises error."""
        with pytest.raises(InvalidScoreError, match="must be 0-10"):
            create_score_ballot("v1", {"alice": -1})

    def test_reject_score_above_max(self):
        """Score above 10 raises error."""
        with pytest.raises(InvalidScoreError, match="must be 0-10"):
            create_score_ballot("v1", {"alice": 11})

    def test_reject_non_integer_score(self):
        """Non-integer score raises error."""
        with pytest.raises(InvalidScoreError, match="must be an integer"):
            create_score_ballot("v1", {"alice": 5.5})

    def test_validation_can_be_disabled(self):
        """Validation can be skipped if needed."""
        # This is for internal use or testing edge cases
        ballot = create_score_ballot("v1", {"alice": 100}, validate=False)
        assert ballot.scores["alice"] == 100

    def test_score_range_constants(self):
        """Check score range constants."""
        assert MIN_SCORE == 0
        assert MAX_SCORE == 10


class TestScoreBallotHelpers:
    """Tests for score ballot helper functions."""

    def test_get_score_existing(self):
        """Get score for a scored candidate."""
        ballot = create_score_ballot("v1", {"alice": 7, "bob": 3})
        assert get_score(ballot, "alice") == 7
        assert get_score(ballot, "bob") == 3

    def test_get_score_unscored(self):
        """Get score for unscored candidate returns 0."""
        ballot = create_score_ballot("v1", {"alice": 7})
        assert get_score(ballot, "bob") == 0

    def test_candidates_scored(self):
        """Count candidates scored on ballot."""
        ballot = create_score_ballot("v1", {"alice": 10, "bob": 5})
        assert candidates_scored(ballot) == 2

    def test_total_points_given(self):
        """Sum of all points on ballot."""
        ballot = create_score_ballot("v1", {"alice": 10, "bob": 5, "carol": 3})
        assert total_points_given(ballot) == 18

    def test_max_score_on_ballot(self):
        """Highest score given on ballot."""
        ballot = create_score_ballot("v1", {"alice": 10, "bob": 5, "carol": 3})
        assert max_score_on_ballot(ballot) == 10

    def test_min_score_on_ballot(self):
        """Lowest score given on ballot."""
        ballot = create_score_ballot("v1", {"alice": 10, "bob": 5, "carol": 3})
        assert min_score_on_ballot(ballot) == 3

    def test_max_min_abstention(self):
        """Max/min on abstention returns None."""
        ballot = create_score_ballot("v1", None)
        assert max_score_on_ballot(ballot) is None
        assert min_score_on_ballot(ballot) is None


class TestScoreResolutionWinner:
    """Tests for score tally winner determination."""

    def test_clear_winner(self):
        """Candidate with highest total score wins."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5, "carol": 0}),
            create_score_ballot("v2", {"alice": 8, "bob": 6, "carol": 4}),
            create_score_ballot("v3", {"alice": 9, "bob": 7, "carol": 2}),
        ]

        result = resolve_score(candidates, ballots)

        # Alice: 10+8+9 = 27
        # Bob: 5+6+7 = 18
        # Carol: 0+4+2 = 6
        assert result.winners == ["alice"]
        assert result.score_totals["alice"] == 27
        assert result.score_totals["bob"] == 18
        assert result.score_totals["carol"] == 6
        assert result.tiebreak_applied is False

    def test_partial_scoring(self):
        """Unscored candidates receive 0."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_score_ballot("v1", {"alice": 10}),  # Only scores Alice
            create_score_ballot("v2", {"bob": 8}),     # Only scores Bob
            create_score_ballot("v3", {"alice": 5, "bob": 5, "carol": 10}),
        ]

        result = resolve_score(candidates, ballots)

        # Alice: 10+0+5 = 15
        # Bob: 0+8+5 = 13
        # Carol: 0+0+10 = 10
        assert result.winners == ["alice"]
        assert result.score_totals["alice"] == 15

    def test_all_candidates_get_max_score(self):
        """All candidates can receive maximum scores."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 10}),
            create_score_ballot("v2", {"alice": 10, "bob": 10}),
        ]

        result = resolve_score(candidates, ballots)

        assert result.score_totals["alice"] == 20
        assert result.score_totals["bob"] == 20
        assert result.tiebreak_applied is True


class TestScoreResolutionMetrics:
    """Tests for score-specific metrics."""

    def test_avg_scores(self):
        """Average score per candidate."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 4}),
            create_score_ballot("v2", {"alice": 6, "bob": 8}),
        ]

        result = resolve_score(candidates, ballots)

        # Alice: (10+6)/2 = 8.0
        # Bob: (4+8)/2 = 6.0
        assert result.avg_scores["alice"] == 8.0
        assert result.avg_scores["bob"] == 6.0

    def test_max_possible_score(self):
        """Maximum possible score calculation."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5}),
            create_score_ballot("v2", {"alice": 8, "bob": 6}),
            create_score_ballot("v3", {"alice": 9, "bob": 7}),
        ]

        result = resolve_score(candidates, ballots)

        # 3 ballots × 10 max score = 30
        assert result.max_possible_score == 30

    def test_score_percentages(self):
        """Score as percentage of maximum possible."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5}),
            create_score_ballot("v2", {"alice": 10, "bob": 5}),
        ]

        result = resolve_score(candidates, ballots)

        # Max possible = 20
        # Alice: 20/20 = 100%
        # Bob: 10/20 = 50%
        assert result.score_percentages["alice"] == 100.0
        assert result.score_percentages["bob"] == 50.0

    def test_vote_counts_equals_score_totals(self):
        """vote_counts field contains score totals for compatibility."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5}),
        ]

        result = resolve_score(candidates, ballots)

        assert result.vote_counts == result.score_totals


class TestScoreResolutionTiebreak:
    """Tests for tiebreak behavior."""

    def test_two_way_tie(self):
        """Two candidates with equal total triggers tiebreak."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5}),
            create_score_ballot("v2", {"alice": 5, "bob": 10}),
        ]

        result = resolve_score(candidates, ballots)

        # Both have 15 total
        assert result.tiebreak_applied is True
        assert len(result.winners) == 1
        assert result.winners[0] in ["alice", "bob"]

    def test_custom_tiebreak(self):
        """Can provide custom tiebreak function."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5}),
            create_score_ballot("v2", {"alice": 5, "bob": 10}),
        ]

        def alphabetical(tied: list[str]) -> str:
            return sorted(tied)[0]

        result = resolve_score(candidates, ballots, tiebreak=alphabetical)

        assert result.winners == ["alice"]
        assert result.tiebreak_applied is True


class TestScoreResolutionAbstentions:
    """Tests for abstention handling."""

    def test_abstentions_excluded(self):
        """Abstentions don't affect totals or averages."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5}),
            create_score_ballot("v2", {"alice": 10, "bob": 5}),
            create_score_ballot("v3", None),  # abstention
        ]

        result = resolve_score(candidates, ballots)

        assert result.abstentions == 1
        assert result.total_ballots == 3
        # Only 2 ballots count
        assert result.score_totals["alice"] == 20
        assert result.avg_scores["alice"] == 10.0
        assert result.max_possible_score == 20  # 2 × 10

    def test_all_abstentions(self):
        """Election with only abstentions."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", None),
            create_score_ballot("v2", None),
        ]

        result = resolve_score(candidates, ballots)

        assert result.abstentions == 2
        assert result.score_totals["alice"] == 0
        assert result.max_possible_score == 0
        assert result.tiebreak_applied is True


class TestScoreResolutionEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_single_candidate(self):
        """Election with only one candidate."""
        candidates = make_candidates("Alice")
        ballots = [
            create_score_ballot("v1", {"alice": 8}),
            create_score_ballot("v2", {"alice": 6}),
        ]

        result = resolve_score(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.score_totals["alice"] == 14

    def test_no_ballots(self):
        """Election with no votes cast."""
        candidates = make_candidates("Alice", "Bob")
        ballots = []

        result = resolve_score(candidates, ballots)

        assert result.total_ballots == 0
        assert result.score_totals["alice"] == 0
        assert result.max_possible_score == 0

    def test_no_candidates(self):
        """Election with no candidates."""
        candidates = []
        ballots = []

        result = resolve_score(candidates, ballots)

        assert result.winners == []

    def test_all_zeros(self):
        """All candidates receive zero scores."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 0, "bob": 0}),
            create_score_ballot("v2", {"alice": 0, "bob": 0}),
        ]

        result = resolve_score(candidates, ballots)

        assert result.score_totals["alice"] == 0
        assert result.score_totals["bob"] == 0
        assert result.tiebreak_applied is True

    def test_scores_for_unknown_candidates_ignored(self):
        """Scores for non-existent candidates don't appear in results."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_score_ballot("v1", {"alice": 10, "bob": 5, "charlie": 8}),
        ]

        result = resolve_score(candidates, ballots)

        assert "charlie" not in result.score_totals
        assert result.score_totals["alice"] == 10
        assert result.score_totals["bob"] == 5
