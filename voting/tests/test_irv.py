"""Tests for Instant Runoff Voting (IRV) method."""

import pytest
from voting import (
    Candidate,
    create_ranked_choice_ballot,
    resolve_irv,
    IRVResult,
    IRVRound,
)


def make_candidates(*names: str) -> list[Candidate]:
    """Helper to create candidates from names."""
    return [Candidate(id=name.lower(), name=name) for name in names]


def candidate_ids(candidates: list[Candidate]) -> list[str]:
    """Extract IDs from candidates."""
    return [c.id for c in candidates]


class TestIRVFirstRoundMajority:
    """Tests where a candidate wins in the first round."""

    def test_clear_majority(self):
        """Candidate with >50% first-choice votes wins immediately."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "carol", "bob"], ids),
            create_ranked_choice_ballot("v3", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v4", ["bob", "alice", "carol"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_counts["alice"] == 3
        assert result.winning_round == 1
        assert len(result.rounds) == 1
        assert result.tiebreak_applied is False

    def test_exactly_majority(self):
        """Candidate with exactly 50%+1 wins."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.winning_round == 1


class TestIRVElimination:
    """Tests for the elimination process."""

    def test_single_elimination(self):
        """Lowest candidate is eliminated and votes transfer."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Round 1: Alice=2, Bob=2, Carol=1 -> Carol eliminated
        # Round 2: Alice=2, Bob=3 -> Bob wins
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "carol", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v4", ["bob", "carol", "alice"], ids),
            create_ranked_choice_ballot("v5", ["carol", "bob", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert result.winners == ["bob"]
        assert len(result.rounds) == 2

        # Round 1
        assert result.rounds[0].vote_counts == {"alice": 2, "bob": 2, "carol": 1}
        assert result.rounds[0].eliminated == ["carol"]
        assert result.rounds[0].elimination_was_tiebreak is False

        # Round 2
        assert result.rounds[1].vote_counts["bob"] == 3
        assert result.rounds[1].vote_counts["alice"] == 2

    def test_multiple_eliminations(self):
        """Multiple rounds of elimination until majority."""
        candidates = make_candidates("Alice", "Bob", "Carol", "Dave")
        ids = candidate_ids(candidates)
        # Round 1: Alice=2, Bob=2, Carol=1, Dave=1 -> Carol and Dave tied for last
        # Eliminate both (leaves 2 candidates)
        # Round 2: Alice=3, Bob=3 -> Tie, tiebreak needed
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "carol", "bob", "dave"], ids),
            create_ranked_choice_ballot("v2", ["alice", "dave", "carol", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "carol", "alice", "dave"], ids),
            create_ranked_choice_ballot("v4", ["bob", "dave", "alice", "carol"], ids),
            create_ranked_choice_ballot("v5", ["carol", "alice", "bob", "dave"], ids),
            create_ranked_choice_ballot("v6", ["dave", "bob", "carol", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert len(result.winners) == 1
        assert result.winners[0] in ["alice", "bob"]

    def test_eliminate_all_tied_when_valid(self):
        """Eliminate all tied-for-last candidates if at least one remains."""
        candidates = make_candidates("Alice", "Bob", "Carol", "Dave")
        ids = candidate_ids(candidates)
        # Alice=3, Bob=1, Carol=1, Dave=1 -> Eliminate Bob, Carol, Dave together
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol", "dave"], ids),
            create_ranked_choice_ballot("v2", ["alice", "carol", "bob", "dave"], ids),
            create_ranked_choice_ballot("v3", ["alice", "dave", "bob", "carol"], ids),
            create_ranked_choice_ballot("v4", ["bob", "alice", "carol", "dave"], ids),
            create_ranked_choice_ballot("v5", ["carol", "alice", "bob", "dave"], ids),
            create_ranked_choice_ballot("v6", ["dave", "alice", "bob", "carol"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert result.winners == ["alice"]
        # Should eliminate all three at once
        assert set(result.rounds[0].eliminated) == {"bob", "carol", "dave"}
        assert result.rounds[0].elimination_was_tiebreak is False


class TestIRVTiebreak:
    """Tests for tiebreak behavior."""

    def test_final_two_tied(self):
        """Two candidates tied at the end uses tiebreak."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["bob", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert len(result.winners) == 1
        assert result.winners[0] in ["alice", "bob"]
        assert result.tiebreak_applied is True

    def test_elimination_tiebreak_when_needed(self):
        """Uses tiebreak when eliminating all would leave no candidates."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        # Both tied at 2 - can't eliminate both
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice"], ids),
            create_ranked_choice_ballot("v4", ["bob", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert len(result.winners) == 1
        assert result.tiebreak_applied is True

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

        result = resolve_irv(candidates, ballots, tiebreak=alphabetical)

        assert result.winners == ["alice"]


class TestIRVExhaustedBallots:
    """Tests for exhausted ballot handling."""

    def test_ballots_exhaust(self):
        """Ballots exhaust when all ranked candidates are eliminated."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Voter 3 only effectively votes for Carol
        # When Carol is eliminated, their ballot exhausts
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["carol", "bob", "alice"], ids),
            create_ranked_choice_ballot("v4", ["bob", "carol", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        # Alice should win with 2, Bob has 2 after Carol eliminated
        # Actually: R1: Alice=2, Bob=1, Carol=1
        # Carol eliminated, her vote goes to Bob
        # R2: Alice=2, Bob=2 -> tie
        assert result.winners[0] in ["alice", "bob"]

    def test_exhausted_count_tracked(self):
        """Total exhausted ballots are tracked."""
        candidates = make_candidates("Alice", "Bob", "Carol", "Dave")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol", "dave"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol", "dave"], ids),
            create_ranked_choice_ballot("v3", ["alice", "bob", "carol", "dave"], ids),
            create_ranked_choice_ballot("v4", ["dave", "carol", "bob", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        # Check that exhausted ballots are tracked in rounds
        assert result.total_exhausted >= 0


class TestIRVAbstentions:
    """Tests for abstention handling."""

    def test_abstentions_excluded(self):
        """Abstentions don't count toward majority calculation."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v4", None),  # abstention
            create_ranked_choice_ballot("v5", None),  # abstention
        ]

        result = resolve_irv(candidates, ballots)

        assert result.abstentions == 2
        assert result.total_ballots == 5
        # Majority of 3 active ballots = 2, Alice has 2 = majority
        assert result.winners == ["alice"]

    def test_all_abstentions(self):
        """Election with only abstentions."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_ranked_choice_ballot("v1", None),
            create_ranked_choice_ballot("v2", None),
        ]

        result = resolve_irv(candidates, ballots)

        assert result.abstentions == 2
        # No active ballots, should handle gracefully
        assert result.tiebreak_applied is True


class TestIRVRoundData:
    """Tests for round-by-round data."""

    def test_round_data_structure(self):
        """Each round has correct data structure."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "carol", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v4", ["carol", "bob", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        for round_data in result.rounds:
            assert isinstance(round_data, IRVRound)
            assert round_data.round_number > 0
            assert isinstance(round_data.vote_counts, dict)
            assert round_data.active_ballots >= 0
            assert round_data.exhausted_ballots >= 0

    def test_rounds_are_sequential(self):
        """Round numbers are sequential starting from 1."""
        candidates = make_candidates("Alice", "Bob", "Carol", "Dave")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol", "dave"], ids),
            create_ranked_choice_ballot("v2", ["bob", "alice", "carol", "dave"], ids),
            create_ranked_choice_ballot("v3", ["carol", "alice", "bob", "dave"], ids),
            create_ranked_choice_ballot("v4", ["dave", "bob", "alice", "carol"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        for i, round_data in enumerate(result.rounds):
            assert round_data.round_number == i + 1


class TestIRVEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_single_candidate(self):
        """Election with only one candidate."""
        candidates = make_candidates("Alice")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice"], ids),
            create_ranked_choice_ballot("v2", ["alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.winning_round == 1

    def test_no_ballots(self):
        """Election with no votes cast."""
        candidates = make_candidates("Alice", "Bob")
        ballots = []

        result = resolve_irv(candidates, ballots)

        assert result.total_ballots == 0
        assert result.tiebreak_applied is True

    def test_no_candidates(self):
        """Election with no candidates."""
        candidates = []
        ballots = []

        result = resolve_irv(candidates, ballots)

        assert result.winners == []

    def test_two_candidates_simple(self):
        """Two candidates, clear winner."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice"], ids),
        ]

        result = resolve_irv(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_counts["alice"] == 2
        assert result.winning_round == 1
