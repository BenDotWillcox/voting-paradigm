"""Tests for approval voting method."""

import pytest
from voting import (
    Candidate,
    create_approval_ballot,
    resolve_approval,
    approval_count,
    is_approval_abstention,
)


def make_candidates(*names: str) -> list[Candidate]:
    """Helper to create candidates from names."""
    return [Candidate(id=name.lower(), name=name) for name in names]


class TestApprovalBallot:
    """Tests for the approval ballot type."""

    def test_create_with_set(self):
        """Create ballot with a set of approvals."""
        ballot = create_approval_ballot("v1", {"alice", "bob"})
        assert ballot.approvals == {"alice", "bob"}
        assert ballot.voter_id == "v1"

    def test_create_with_list(self):
        """Create ballot with a list (converted to set)."""
        ballot = create_approval_ballot("v1", ["alice", "bob"])
        assert ballot.approvals == {"alice", "bob"}

    def test_create_empty(self):
        """Create abstention ballot."""
        ballot = create_approval_ballot("v1", None)
        assert ballot.approvals == set()
        assert is_approval_abstention(ballot)

    def test_approval_count(self):
        """Count approvals on a ballot."""
        ballot = create_approval_ballot("v1", ["alice", "bob", "carol"])
        assert approval_count(ballot) == 3


class TestApprovalClearWinner:
    """Tests where one candidate has more approvals than others."""

    def test_simple_winner(self):
        """Candidate with most approvals wins."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_approval_ballot("v1", ["alice", "bob"]),
            create_approval_ballot("v2", ["alice", "carol"]),
            create_approval_ballot("v3", ["alice"]),  # Alice gets 3rd approval
        ]

        result = resolve_approval(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_counts["alice"] == 3
        assert result.vote_counts["bob"] == 1
        assert result.vote_counts["carol"] == 1
        assert result.tiebreak_applied is False

    def test_clear_winner(self):
        """Candidate with most approvals wins."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_approval_ballot("v1", ["alice", "bob"]),
            create_approval_ballot("v2", ["alice", "carol"]),
            create_approval_ballot("v3", ["alice"]),
            create_approval_ballot("v4", ["bob"]),
        ]

        result = resolve_approval(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_counts["alice"] == 3
        assert result.vote_counts["bob"] == 2
        assert result.vote_counts["carol"] == 1
        assert result.tiebreak_applied is False

    def test_approve_all_candidates(self):
        """Voter can approve all candidates."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice", "bob"]),
            create_approval_ballot("v2", ["alice", "bob"]),
            create_approval_ballot("v3", ["alice"]),
        ]

        result = resolve_approval(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_counts["alice"] == 3
        assert result.vote_counts["bob"] == 2


class TestApprovalMetrics:
    """Tests for approval-specific metrics."""

    def test_avg_approvals_per_ballot(self):
        """Calculate average approvals per ballot."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_approval_ballot("v1", ["alice", "bob"]),      # 2 approvals
            create_approval_ballot("v2", ["alice"]),             # 1 approval
            create_approval_ballot("v3", ["alice", "bob", "carol"]),  # 3 approvals
        ]

        result = resolve_approval(candidates, ballots)

        # (2 + 1 + 3) / 3 = 2.0
        assert result.avg_approvals_per_ballot == 2.0

    def test_avg_approvals_excludes_abstentions(self):
        """Average calculation excludes abstaining ballots."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice", "bob"]),  # 2 approvals
            create_approval_ballot("v2", None),              # abstention
            create_approval_ballot("v3", ["alice"]),         # 1 approval
        ]

        result = resolve_approval(candidates, ballots)

        # (2 + 1) / 2 = 1.5 (only 2 non-abstaining ballots)
        assert result.avg_approvals_per_ballot == 1.5
        assert result.abstentions == 1

    def test_approval_rates(self):
        """Calculate approval rate per candidate."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice"]),
            create_approval_ballot("v2", ["alice", "bob"]),
            create_approval_ballot("v3", ["alice"]),
            create_approval_ballot("v4", ["bob"]),
        ]

        result = resolve_approval(candidates, ballots)

        # Alice: 3/4 = 0.75, Bob: 2/4 = 0.5
        assert result.approval_rates["alice"] == 0.75
        assert result.approval_rates["bob"] == 0.5

    def test_approval_rates_with_abstentions(self):
        """Approval rates use non-abstaining ballots as denominator."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice"]),
            create_approval_ballot("v2", ["alice", "bob"]),
            create_approval_ballot("v3", None),  # abstention
            create_approval_ballot("v4", None),  # abstention
        ]

        result = resolve_approval(candidates, ballots)

        # Only 2 non-abstaining ballots
        # Alice: 2/2 = 1.0, Bob: 1/2 = 0.5
        assert result.approval_rates["alice"] == 1.0
        assert result.approval_rates["bob"] == 0.5
        assert result.total_ballots == 4
        assert result.abstentions == 2


class TestApprovalAbstentions:
    """Tests for handling abstentions."""

    def test_abstention_counted(self):
        """Abstentions are counted separately."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice"]),
            create_approval_ballot("v2", None),
            create_approval_ballot("v3", None),
        ]

        result = resolve_approval(candidates, ballots)

        assert result.abstentions == 2
        assert result.total_ballots == 3

    def test_all_abstentions(self):
        """Election where everyone abstains."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", None),
            create_approval_ballot("v2", None),
        ]

        result = resolve_approval(candidates, ballots)

        assert result.tiebreak_applied is True  # 0-0 tie
        assert result.abstentions == 2
        assert result.avg_approvals_per_ballot == 0.0


class TestApprovalTiebreak:
    """Tests for tie-breaking behavior."""

    def test_two_way_tie(self):
        """Two candidates with equal approvals triggers tiebreak."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice"]),
            create_approval_ballot("v2", ["bob"]),
        ]

        result = resolve_approval(candidates, ballots)

        assert result.tiebreak_applied is True
        assert len(result.winners) == 1
        assert result.winners[0] in ["alice", "bob"]

    def test_custom_tiebreak(self):
        """Can provide custom tiebreak logic."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice"]),
            create_approval_ballot("v2", ["bob"]),
        ]

        def alphabetical(tied: list[str]) -> str:
            return sorted(tied)[0]

        result = resolve_approval(candidates, ballots, tiebreak=alphabetical)

        assert result.winners == ["alice"]
        assert result.tiebreak_applied is True


class TestApprovalEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_no_ballots(self):
        """Election with no votes cast."""
        candidates = make_candidates("Alice", "Bob")
        ballots = []

        result = resolve_approval(candidates, ballots)

        assert result.tiebreak_applied is True  # 0-0 tie
        assert result.total_ballots == 0
        assert result.avg_approvals_per_ballot == 0.0

    def test_no_candidates(self):
        """Election with no candidates."""
        candidates = []
        ballots = [create_approval_ballot("v1", ["alice"])]

        result = resolve_approval(candidates, ballots)

        assert result.winners == []

    def test_invalid_approval_ignored(self):
        """Approval for non-existent candidate is ignored."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_approval_ballot("v1", ["alice", "charlie"]),
        ]

        result = resolve_approval(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_counts["alice"] == 1
        assert result.vote_counts["bob"] == 0
        assert "charlie" not in result.vote_counts

    def test_single_candidate(self):
        """Election with only one candidate."""
        candidates = make_candidates("Alice")
        ballots = [
            create_approval_ballot("v1", ["alice"]),
            create_approval_ballot("v2", ["alice"]),
            create_approval_ballot("v3", None),
        ]

        result = resolve_approval(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.approval_rates["alice"] == 1.0
        assert result.tiebreak_applied is False
