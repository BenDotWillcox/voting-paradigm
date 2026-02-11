"""Tests for Quadratic Voting ballot and resolution method."""

import pytest
from voting import (
    Candidate,
    create_quadratic_ballot,
    resolve_quadratic,
    QuadraticResult,
    is_quadratic_abstention,
    get_votes,
    candidates_voted_for,
    quadratic_cost,
    quadratic_total_cost,
    credits_remaining,
    credit_utilization,
    max_votes_for_budget,
    InvalidQuadraticBallotError,
    DEFAULT_CREDIT_BUDGET,
)


def make_candidates(*names: str) -> list[Candidate]:
    """Helper to create candidates from names."""
    return [Candidate(id=name.lower(), name=name) for name in names]


# ── Ballot Creation ──────────────────────────────────────────────────


class TestQuadraticBallotCreation:
    """Tests for creating quadratic ballots."""

    def test_create_with_allocations(self):
        """Create ballot with valid vote allocations."""
        ballot = create_quadratic_ballot("v1", {"alice": 5, "bob": 3})
        assert ballot.allocations == {"alice": 5, "bob": 3}
        assert ballot.voter_id == "v1"
        assert ballot.credit_budget == 100

    def test_create_with_negative_votes(self):
        """Create ballot with negative (opposition) votes."""
        ballot = create_quadratic_ballot("v1", {"alice": 5, "bob": -3})
        assert ballot.allocations["alice"] == 5
        assert ballot.allocations["bob"] == -3

    def test_create_abstention_with_none(self):
        """Create abstention by passing None."""
        ballot = create_quadratic_ballot("v1", None)
        assert ballot.allocations == {}
        assert is_quadratic_abstention(ballot)

    def test_create_abstention_with_empty_dict(self):
        """Create abstention by passing empty dict."""
        ballot = create_quadratic_ballot("v1", {})
        assert is_quadratic_abstention(ballot)

    def test_custom_credit_budget(self):
        """Budget can be configured per election."""
        ballot = create_quadratic_ballot("v1", {"alice": 3}, credit_budget=50)
        assert ballot.credit_budget == 50

    def test_reject_exceeds_budget(self):
        """Total cost exceeding budget raises error."""
        # 8² + 7² = 64 + 49 = 113 > 100
        with pytest.raises(InvalidQuadraticBallotError, match="exceeds credit budget"):
            create_quadratic_ballot("v1", {"alice": 8, "bob": 7})

    def test_reject_zero_votes(self):
        """Zero votes for a candidate raises error."""
        with pytest.raises(InvalidQuadraticBallotError, match="non-zero"):
            create_quadratic_ballot("v1", {"alice": 0})

    def test_reject_non_integer_votes(self):
        """Non-integer votes raise error."""
        with pytest.raises(InvalidQuadraticBallotError, match="must be an integer"):
            create_quadratic_ballot("v1", {"alice": 3.5})

    def test_reject_negative_when_disabled(self):
        """Negative votes rejected when allow_negative=False."""
        with pytest.raises(InvalidQuadraticBallotError, match="Negative votes not allowed"):
            create_quadratic_ballot("v1", {"alice": -3}, allow_negative=False)

    def test_allow_negative_positive_default(self):
        """Negative votes allowed by default."""
        # (-5)² = 25, fits in budget
        ballot = create_quadratic_ballot("v1", {"alice": -5})
        assert ballot.allocations["alice"] == -5

    def test_negative_votes_cost_same_as_positive(self):
        """Negative votes cost v² just like positive ones."""
        # (-9)² = 81 ≤ 100, valid
        ballot = create_quadratic_ballot("v1", {"alice": -9})
        assert quadratic_total_cost(ballot) == 81

    def test_validation_can_be_disabled(self):
        """Validation can be skipped."""
        ballot = create_quadratic_ballot("v1", {"alice": 100}, validate=False)
        assert ballot.allocations["alice"] == 100

    def test_exact_budget_usage(self):
        """Using exactly 100 credits is valid."""
        # 10² = 100
        ballot = create_quadratic_ballot("v1", {"alice": 10})
        assert quadratic_total_cost(ballot) == 100
        assert credits_remaining(ballot) == 0

    def test_default_credit_budget_constant(self):
        """Default budget constant is 100."""
        assert DEFAULT_CREDIT_BUDGET == 100

    def test_allocations_are_copied(self):
        """Allocations dict is copied, not referenced."""
        original = {"alice": 5}
        ballot = create_quadratic_ballot("v1", original)
        original["bob"] = 3
        assert "bob" not in ballot.allocations


# ── Ballot Helpers ───────────────────────────────────────────────────


class TestQuadraticBallotHelpers:
    """Tests for quadratic ballot helper functions."""

    def test_quadratic_cost_positive(self):
        """Cost of positive votes."""
        assert quadratic_cost(1) == 1
        assert quadratic_cost(3) == 9
        assert quadratic_cost(10) == 100

    def test_quadratic_cost_negative(self):
        """Cost of negative votes (same as positive)."""
        assert quadratic_cost(-3) == 9
        assert quadratic_cost(-5) == 25

    def test_quadratic_cost_zero(self):
        """Cost of zero votes is zero."""
        assert quadratic_cost(0) == 0

    def test_quadratic_total_cost(self):
        """Total cost across all allocations."""
        ballot = create_quadratic_ballot("v1", {"alice": 5, "bob": -3})
        # 25 + 9 = 34
        assert quadratic_total_cost(ballot) == 34

    def test_credits_remaining(self):
        """Credits remaining after allocations."""
        ballot = create_quadratic_ballot("v1", {"alice": 5, "bob": -3})
        # 100 - 34 = 66
        assert credits_remaining(ballot) == 66

    def test_credits_remaining_abstention(self):
        """Abstention has full budget remaining."""
        ballot = create_quadratic_ballot("v1", None)
        assert credits_remaining(ballot) == 100

    def test_get_votes_allocated(self):
        """Get votes for an allocated candidate."""
        ballot = create_quadratic_ballot("v1", {"alice": 5, "bob": -3})
        assert get_votes(ballot, "alice") == 5
        assert get_votes(ballot, "bob") == -3

    def test_get_votes_unallocated(self):
        """Get votes for unallocated candidate returns 0."""
        ballot = create_quadratic_ballot("v1", {"alice": 5})
        assert get_votes(ballot, "bob") == 0

    def test_candidates_voted_for(self):
        """Count of candidates with allocations."""
        ballot = create_quadratic_ballot("v1", {"alice": 5, "bob": -3, "carol": 2})
        assert candidates_voted_for(ballot) == 3

    def test_credit_utilization(self):
        """Fraction of budget used."""
        ballot = create_quadratic_ballot("v1", {"alice": 5, "bob": -3})
        # 34 / 100 = 0.34
        assert credit_utilization(ballot) == pytest.approx(0.34)

    def test_credit_utilization_full(self):
        """Full utilization = 1.0."""
        ballot = create_quadratic_ballot("v1", {"alice": 10})
        assert credit_utilization(ballot) == pytest.approx(1.0)

    def test_credit_utilization_abstention(self):
        """Abstention utilization = 0.0."""
        ballot = create_quadratic_ballot("v1", None)
        assert credit_utilization(ballot) == pytest.approx(0.0)

    def test_max_votes_for_budget_100(self):
        """Max single-candidate votes with 100 credits."""
        assert max_votes_for_budget(100) == 10

    def test_max_votes_for_budget_non_square(self):
        """Non-perfect-square budget floors correctly."""
        # sqrt(50) ≈ 7.07, floor = 7
        assert max_votes_for_budget(50) == 7

    def test_max_votes_for_budget_small(self):
        """Small budgets."""
        assert max_votes_for_budget(1) == 1
        assert max_votes_for_budget(0) == 0


# ── Resolution: Winner Determination ─────────────────────────────────


class TestQuadraticResolutionWinner:
    """Tests for quadratic resolution winner determination."""

    def test_clear_winner(self):
        """Candidate with highest net total wins."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5, "bob": 2}),   # A:5, B:2
            create_quadratic_ballot("v2", {"alice": 3, "carol": 4}), # A:3, C:4
            create_quadratic_ballot("v3", {"alice": 2, "bob": 1}),   # A:2, B:1
        ]

        result = resolve_quadratic(candidates, ballots)

        # Alice: 5+3+2 = 10, Bob: 2+1 = 3, Carol: 4
        assert result.winners == ["alice"]
        assert result.vote_totals["alice"] == 10
        assert result.vote_totals["bob"] == 3
        assert result.vote_totals["carol"] == 4
        assert result.tiebreak_applied is False

    def test_partial_allocation(self):
        """Voters need not allocate all credits."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 2}),  # Spends 4 of 100
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_totals["alice"] == 2
        assert result.vote_totals["bob"] == 0

    def test_negative_votes_reduce_total(self):
        """Negative votes subtract from a candidate's total."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5}),       # A:+5
            create_quadratic_ballot("v2", {"alice": -3}),      # A:-3
            create_quadratic_ballot("v3", {"bob": 4}),         # B:+4
        ]

        result = resolve_quadratic(candidates, ballots)

        # Alice: 5-3 = 2, Bob: 4
        assert result.winners == ["bob"]
        assert result.vote_totals["alice"] == 2
        assert result.vote_totals["bob"] == 4

    def test_all_negative_scenario(self):
        """All candidates can end up net-negative."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": -3, "bob": -5}),
            create_quadratic_ballot("v2", {"alice": -2, "bob": -4}),
        ]

        result = resolve_quadratic(candidates, ballots)

        # Alice: -3-2 = -5, Bob: -5-4 = -9
        # Alice "wins" with least-negative total
        assert result.winners == ["alice"]
        assert result.vote_totals["alice"] == -5
        assert result.vote_totals["bob"] == -9

    def test_mixed_positive_negative(self):
        """Mixed positive and negative across multiple voters."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 7, "bob": -5}),   # cost: 49+25=74
            create_quadratic_ballot("v2", {"bob": 6, "carol": -3}),   # cost: 36+9=45
            create_quadratic_ballot("v3", {"carol": 8, "alice": -4}), # cost: 64+16=80
        ]

        result = resolve_quadratic(candidates, ballots)

        # Alice: 7-4 = 3, Bob: -5+6 = 1, Carol: -3+8 = 5
        assert result.winners == ["carol"]
        assert result.vote_totals["alice"] == 3
        assert result.vote_totals["bob"] == 1
        assert result.vote_totals["carol"] == 5


# ── Resolution: Metrics ──────────────────────────────────────────────


class TestQuadraticResolutionMetrics:
    """Tests for quadratic-specific result metrics."""

    def test_vote_totals(self):
        """Vote totals for all candidates."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5, "bob": 3}),
            create_quadratic_ballot("v2", {"alice": 2, "bob": 7}),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.vote_totals["alice"] == 7
        assert result.vote_totals["bob"] == 10

    def test_total_credits_spent(self):
        """Sum of all credits spent across voters."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5}),  # cost: 25
            create_quadratic_ballot("v2", {"bob": 3}),    # cost: 9
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.total_credits_spent == 34

    def test_total_credits_available(self):
        """Sum of all budgets for non-abstaining voters."""
        candidates = make_candidates("Alice")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 2}, credit_budget=100),
            create_quadratic_ballot("v2", {"alice": 1}, credit_budget=50),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.total_credits_available == 150

    def test_overall_utilization(self):
        """Overall utilization: spent / available."""
        candidates = make_candidates("Alice")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5}),  # cost 25 of 100
            create_quadratic_ballot("v2", {"alice": 5}),  # cost 25 of 100
        ]

        result = resolve_quadratic(candidates, ballots)

        # 50 / 200 = 0.25
        assert result.overall_utilization == pytest.approx(0.25)

    def test_avg_voter_utilization(self):
        """Mean of individual voter utilizations."""
        candidates = make_candidates("Alice")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 10}),  # 100/100 = 1.0
            create_quadratic_ballot("v2", {"alice": 5}),   # 25/100 = 0.25
        ]

        result = resolve_quadratic(candidates, ballots)

        # Mean: (1.0 + 0.25) / 2 = 0.625
        assert result.avg_voter_utilization == pytest.approx(0.625)

    def test_candidates_with_negative_totals(self):
        """Count of candidates with net-negative totals."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5, "bob": -3, "carol": -2}),
        ]

        result = resolve_quadratic(candidates, ballots)

        # Bob: -3, Carol: -2 → 2 negative
        assert result.candidates_with_negative_totals == 2

    def test_vote_counts_equals_vote_totals(self):
        """vote_counts field matches vote_totals for compatibility."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5, "bob": 3}),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.vote_counts == result.vote_totals


# ── Resolution: Tiebreak ─────────────────────────────────────────────


class TestQuadraticResolutionTiebreak:
    """Tests for tiebreak behavior."""

    def test_two_way_tie(self):
        """Two candidates with equal net total triggers tiebreak."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5}),
            create_quadratic_ballot("v2", {"bob": 5}),
        ]

        result = resolve_quadratic(candidates, ballots)

        # Both have 5
        assert result.tiebreak_applied is True
        assert len(result.winners) == 1
        assert result.winners[0] in ["alice", "bob"]

    def test_custom_tiebreak(self):
        """Can provide custom tiebreak function."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5}),
            create_quadratic_ballot("v2", {"bob": 5}),
        ]

        def alphabetical(tied: list[str]) -> str:
            return sorted(tied)[0]

        result = resolve_quadratic(candidates, ballots, tiebreak=alphabetical)

        assert result.winners == ["alice"]
        assert result.tiebreak_applied is True


# ── Resolution: Abstentions ──────────────────────────────────────────


class TestQuadraticResolutionAbstentions:
    """Tests for abstention handling."""

    def test_abstentions_excluded_from_totals(self):
        """Abstentions don't affect vote totals or credit metrics."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5, "bob": 3}),
            create_quadratic_ballot("v2", None),  # abstention
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.abstentions == 1
        assert result.total_ballots == 2
        assert result.vote_totals["alice"] == 5
        assert result.vote_totals["bob"] == 3
        assert result.total_credits_available == 100  # Only 1 voter's budget

    def test_all_abstentions(self):
        """Election where everyone abstains."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", None),
            create_quadratic_ballot("v2", None),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.abstentions == 2
        assert result.vote_totals["alice"] == 0
        assert result.vote_totals["bob"] == 0
        assert result.total_credits_spent == 0
        assert result.total_credits_available == 0
        assert result.overall_utilization == pytest.approx(0.0)
        assert result.winners == []
        assert result.tiebreak_applied is False

    def test_mixed_abstention_and_votes(self):
        """Mix of abstentions and real votes."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 7}),  # cost 49
            create_quadratic_ballot("v2", None),
            create_quadratic_ballot("v3", {"bob": 4}),    # cost 16
            create_quadratic_ballot("v4", None),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.abstentions == 2
        assert result.total_ballots == 4
        assert result.winners == ["alice"]
        assert result.total_credits_spent == 65
        assert result.total_credits_available == 200


# ── Resolution: Edge Cases ───────────────────────────────────────────


class TestQuadraticResolutionEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_no_candidates(self):
        """Election with no candidates."""
        result = resolve_quadratic([], [])
        assert result.winners == []

    def test_no_ballots(self):
        """Election with no ballots cast."""
        candidates = make_candidates("Alice", "Bob")
        result = resolve_quadratic(candidates, [])

        assert result.winners == []
        assert result.tiebreak_applied is False
        assert result.total_ballots == 0
        assert result.vote_totals["alice"] == 0
        assert result.vote_totals["bob"] == 0
        assert result.total_credits_spent == 0

    def test_single_candidate(self):
        """Election with only one candidate."""
        candidates = make_candidates("Alice")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 8}),
            create_quadratic_ballot("v2", {"alice": 5}),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.vote_totals["alice"] == 13
        assert result.tiebreak_applied is False

    def test_unknown_candidate_votes_ignored(self):
        """Votes for non-existent candidates don't appear in results."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5, "charlie": 3}),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert "charlie" not in result.vote_totals
        assert result.vote_totals["alice"] == 5
        assert result.vote_totals["bob"] == 0

    def test_unknown_candidate_votes_excluded_from_credit_metrics(self):
        """Credits spent on unknown candidates are excluded from utilization metrics."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            # known cost: 25, unknown cost: 49
            create_quadratic_ballot("v1", {"alice": 5, "charlie": 7}),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.total_credits_spent == 25
        assert result.total_credits_available == 100
        assert result.overall_utilization == pytest.approx(0.25)
        assert result.avg_voter_utilization == pytest.approx(0.25)

    def test_only_unknown_candidate_votes_gives_no_winner(self):
        """Ballots without known-candidate votes should produce no winner."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"charlie": 5}),
            create_quadratic_ballot("v2", {"dana": -3}),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.winners == []
        assert result.tiebreak_applied is False
        assert result.vote_totals["alice"] == 0
        assert result.vote_totals["bob"] == 0

    def test_result_is_quadratic_result_type(self):
        """Result is the correct type."""
        candidates = make_candidates("Alice")
        ballots = [create_quadratic_ballot("v1", {"alice": 1})]

        result = resolve_quadratic(candidates, ballots)

        assert isinstance(result, QuadraticResult)

    def test_different_budgets_across_voters(self):
        """Different voters can have different credit budgets."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_quadratic_ballot("v1", {"alice": 5}, credit_budget=100),
            create_quadratic_ballot("v2", {"bob": 3}, credit_budget=25),
        ]

        result = resolve_quadratic(candidates, ballots)

        assert result.total_credits_available == 125
        assert result.total_credits_spent == 34  # 25 + 9
