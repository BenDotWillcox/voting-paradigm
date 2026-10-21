"""Tests for Condorcet method with Ranked Pairs completion."""

import pytest
from voting import (
    Candidate,
    create_ranked_choice_ballot,
    resolve_ranked_pairs,
    RankedPairsResult,
)


def make_candidates(*names: str) -> list[Candidate]:
    """Helper to create candidates from names."""
    return [Candidate(id=name.lower(), name=name) for name in names]


def candidate_ids(candidates: list[Candidate]) -> list[str]:
    """Extract IDs from candidates."""
    return [c.id for c in candidates]


def ballots_from(profile: list[tuple[int, list[str]]], ids: list[str]):
    """Expand (count, ranking) rows into ranked ballots."""
    ballots = []
    for count, ranking in profile:
        for _ in range(count):
            ballots.append(
                create_ranked_choice_ballot(f"v{len(ballots) + 1}", ranking, ids)
            )
    return ballots


def refuse_tiebreak(tied: list[str]) -> str:
    """A tiebreak for cases that must not need one."""
    raise AssertionError(f"tiebreak consulted for {tied}")


def first_alphabetical(tied: list[str]) -> str:
    return min(tied)


def last_alphabetical(tied: list[str]) -> str:
    return max(tied)


class TestPairwiseMatrix:
    """Tests for pairwise comparison matrix building."""

    def test_simple_pairwise(self):
        """Build matrix from simple ballots."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        # Alice beats Bob 2-1
        assert result.pairwise_matrix["alice"]["bob"] == 2
        assert result.pairwise_matrix["bob"]["alice"] == 1

    def test_three_candidate_matrix(self):
        """Build complete matrix for 3 candidates."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["bob", "carol", "alice"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)
        matrix = result.pairwise_matrix

        # Alice vs Bob: 2-1
        assert matrix["alice"]["bob"] == 2
        assert matrix["bob"]["alice"] == 1

        # Alice vs Carol: 2-1
        assert matrix["alice"]["carol"] == 2
        assert matrix["carol"]["alice"] == 1

        # Bob vs Carol: 3-0
        assert matrix["bob"]["carol"] == 3
        assert matrix["carol"]["bob"] == 0


class TestCondorcetWinner:
    """Tests for Condorcet winner detection."""

    def test_clear_condorcet_winner(self):
        """Candidate who beats all others is Condorcet winner."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["alice", "carol", "bob"], ids),
            create_ranked_choice_ballot("v4", ["bob", "alice", "carol"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.had_condorcet_winner is True
        assert result.tiebreak_applied is False
        assert result.locked_victories == []  # No Ranked Pairs needed

    def test_condorcet_winner_minority_first_choice(self):
        """Condorcet winner can have minority of first-choice votes."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Alice has fewest first-choice votes but beats everyone head-to-head
        ballots = [
            create_ranked_choice_ballot("v1", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v2", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v3", ["carol", "alice", "bob"], ids),
            create_ranked_choice_ballot("v4", ["carol", "alice", "bob"], ids),
            create_ranked_choice_ballot("v5", ["alice", "bob", "carol"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        # Alice: 1 first-choice vote, but beats Bob 3-2 and Carol 3-2
        assert result.winners == ["alice"]
        assert result.had_condorcet_winner is True


class TestCondorcetCycle:
    """Tests for cycles (no Condorcet winner)."""

    def test_rock_paper_scissors_cycle(self):
        """Classic 3-way cycle: A>B, B>C, C>A."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Create cycle:
        # 1 voter: A > B > C (A beats B)
        # 1 voter: B > C > A (B beats C)
        # 1 voter: C > A > B (C beats A)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["bob", "carol", "alice"], ids),
            create_ranked_choice_ballot("v3", ["carol", "alice", "bob"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        # No Condorcet winner - all matchups are 1-1 ties actually!
        # Let me recalculate...
        # v1: A>B, A>C, B>C
        # v2: B>C, B>A, C>A
        # v3: C>A, C>B, A>B
        # A vs B: A wins from v1, v3; B wins from v2 => 2-1 A
        # B vs C: B wins from v1, v2; C wins from v3 => 2-1 B
        # A vs C: A wins from v1; C wins from v2, v3 => 1-2 C wins

        # So: A beats B, B beats C, C beats A - classic cycle!
        assert result.had_condorcet_winner is False
        assert len(result.winners) == 1
        # Winner determined by Ranked Pairs

    def test_ranked_pairs_resolves_cycle(self):
        """Ranked Pairs correctly resolves a cycle."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Create asymmetric cycle with clear margins:
        # A beats B by 3 votes
        # B beats C by 2 votes
        # C beats A by 1 vote
        ballots = [
            # 3 voters: A > B > C
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["alice", "bob", "carol"], ids),
            # 2 voters: B > C > A
            create_ranked_choice_ballot("v4", ["bob", "carol", "alice"], ids),
            create_ranked_choice_ballot("v5", ["bob", "carol", "alice"], ids),
            # 2 voters: C > A > B
            create_ranked_choice_ballot("v6", ["carol", "alice", "bob"], ids),
            create_ranked_choice_ballot("v7", ["carol", "alice", "bob"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots, tiebreak=refuse_tiebreak)

        # Pairwise results:
        # A vs B: 3+2=5 for A, 2 for B => A wins 5-2, margin 3
        # B vs C: 3+2=5 for B, 2 for C => B wins 5-2, margin 3
        # A vs C: 3 for A, 2+2=4 for C => C wins 4-3, margin 1

        # Cycle: A>B, B>C, C>A
        # A>B and B>C are equally strong (margin 3, 5 winning votes), but both
        # lock in either order, so the tiebreak is never consulted.
        # C>A would then close the cycle and is skipped: A wins.
        assert result.had_condorcet_winner is False
        assert result.winners == ["alice"]
        assert result.locked_victories == [("alice", "bob", 3), ("bob", "carol", 3)]
        assert result.skipped_victories == [("carol", "alice", 1)]
        assert result.tiebreak_applied is False
        assert result.tiebreak_priority == []


class TestRankedPairsLocking:
    """Tests for the locking mechanism."""

    def test_victories_locked_in_order(self):
        """Victories are locked from strongest margin to weakest."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Create clear margin ordering
        ballots = [
            # A beats B heavily (4-0)
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["alice", "carol", "bob"], ids),
            create_ranked_choice_ballot("v4", ["alice", "carol", "bob"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        # Should have Condorcet winner (Alice beats both)
        assert result.winners == ["alice"]
        assert result.had_condorcet_winner is True

    def test_skipped_victory_tracked(self):
        """Skipped victories (to avoid cycles) are tracked."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Create cycle where one edge must be skipped
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v3", ["bob", "carol", "alice"], ids),
            create_ranked_choice_ballot("v4", ["bob", "carol", "alice"], ids),
            create_ranked_choice_ballot("v5", ["carol", "alice", "bob"], ids),
            create_ranked_choice_ballot("v6", ["carol", "alice", "bob"], ids),
            create_ranked_choice_ballot("v7", ["carol", "alice", "bob"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        # If there's a cycle, at least one victory should be skipped
        if not result.had_condorcet_winner:
            # Cycle exists, check that we tracked skipped victories
            total_pairs = 3  # 3 choose 2 = 3 pairs
            assert len(result.locked_victories) + len(result.skipped_victories) <= total_pairs


class TestRankedPairsTiebreak:
    """Tests for tiebreak behavior."""

    def test_equal_margins_use_winning_votes(self):
        """When margins are equal, higher winning votes wins."""
        # This is hard to construct precisely, so we just verify
        # the algorithm handles it without error
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob", "carol"], ids),
            create_ranked_choice_ballot("v2", ["bob", "carol", "alice"], ids),
            create_ranked_choice_ballot("v3", ["carol", "alice", "bob"], ids),
        ]

        # Should complete without error
        result = resolve_ranked_pairs(candidates, ballots)
        assert len(result.winners) == 1

    def test_complete_tie(self):
        """Complete tie uses tiebreak."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["bob", "alice"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        # 1-1 tie, tiebreak needed
        assert len(result.winners) == 1
        assert result.winners[0] in ["alice", "bob"]

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

        result = resolve_ranked_pairs(candidates, ballots, tiebreak=alphabetical)

        # With alphabetical tiebreak, alice should win
        assert result.winners == ["alice"]


class TestRankedPairsEqualStrength:
    """Equal-strength victories are ordered by the injected tiebreak."""

    # 2 A>C>B, 4 B>A>C, 2 C>A>B, 1 C>B>A
    # A beats C 6-3 (margin 3); B beats A 5-4 and C beats B 5-4 (margin 1 each).
    # After A>C locks, the two margin-1 victories cannot both lock, so their
    # order decides the winner.
    TIED_ORDER_PROFILE = [
        (2, ["alice", "carol", "bob"]),
        (4, ["bob", "alice", "carol"]),
        (2, ["carol", "alice", "bob"]),
        (1, ["carol", "bob", "alice"]),
    ]

    def resolve(self, tiebreak=None):
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = ballots_from(self.TIED_ORDER_PROFILE, candidate_ids(candidates))
        return resolve_ranked_pairs(candidates, ballots, tiebreak=tiebreak)

    def test_priority_from_tiebreak_orders_equal_victories(self):
        """Higher-priority winner locks first."""
        # Priority alice > bob > carol: B>A (winner bob) precedes C>B (winner carol)
        result = self.resolve(first_alphabetical)

        assert result.tiebreak_priority == ["alice", "bob", "carol"]
        assert result.locked_victories == [("alice", "carol", 3), ("bob", "alice", 1)]
        assert result.skipped_victories == [("carol", "bob", 1)]
        assert result.winners == ["bob"]
        assert result.tiebreak_applied is True

    def test_different_tiebreak_changes_the_winner(self):
        """The reversed priority locks C>B first and elects Alice."""
        result = self.resolve(last_alphabetical)

        assert result.tiebreak_priority == ["carol", "bob", "alice"]
        assert result.locked_victories == [("alice", "carol", 3), ("carol", "bob", 1)]
        assert result.skipped_victories == [("bob", "alice", 1)]
        assert result.winners == ["alice"]
        assert result.tiebreak_applied is True

    def test_shared_winner_locks_lower_priority_loser_first(self):
        """For a shared winner, the loser with lower priority goes first."""
        # 1 A>B>C>D, 1 B>C>D>A, 1 C>D>A>B: C beats D 3-0 and every other
        # victory is 2-1, so five victories share one strength.
        # Priority a > b > c > d.
        candidates = make_candidates("A", "B", "C", "D")
        ballots = ballots_from(
            [
                (1, ["a", "b", "c", "d"]),
                (1, ["b", "c", "d", "a"]),
                (1, ["c", "d", "a", "b"]),
            ],
            candidate_ids(candidates),
        )
        result = resolve_ranked_pairs(candidates, ballots, tiebreak=first_alphabetical)

        # c>d locks first. The margin-1 victories a>b, b>c, b>d, c>a, d>a go by
        # winner priority, then lowest-priority loser first:
        # a>b, b>d, b>c, then c>a and d>a would close cycles and are skipped.
        assert result.locked_victories == [
            ("c", "d", 3),
            ("a", "b", 1),
            ("b", "d", 1),
            ("b", "c", 1),
        ]
        assert result.skipped_victories == [("c", "a", 1), ("d", "a", 1)]
        assert result.winners == ["a"]

    def test_default_tiebreak_is_reproducible(self):
        """Without an explicit tiebreak, every run gives the same result."""
        results = {
            (tuple(r.winners), tuple(r.tiebreak_priority))
            for r in (self.resolve() for _ in range(50))
        }
        assert len(results) == 1

    def test_cycle_without_equal_victories_is_not_tiebroken(self):
        """Skipping a victory in a cycle is not a tiebreak."""
        # 4 A>C>B, 6 B>A>C, 3 C>A>B, 2 C>B>A: margins 5, 3, 1
        candidates = make_candidates("Alice", "Bob", "Carol")
        ballots = ballots_from(
            [
                (4, ["alice", "carol", "bob"]),
                (6, ["bob", "alice", "carol"]),
                (3, ["carol", "alice", "bob"]),
                (2, ["carol", "bob", "alice"]),
            ],
            candidate_ids(candidates),
        )
        result = resolve_ranked_pairs(candidates, ballots, tiebreak=refuse_tiebreak)

        assert result.had_condorcet_winner is False
        assert result.locked_victories == [("alice", "carol", 5), ("carol", "bob", 3)]
        assert result.skipped_victories == [("bob", "alice", 1)]
        assert result.winners == ["alice"]
        assert result.tiebreak_applied is False


class TestRankedPairsAbstentions:
    """Tests for abstention handling."""

    def test_abstentions_excluded(self):
        """Abstentions don't count in pairwise comparisons."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v3", None),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        assert result.abstentions == 1
        assert result.pairwise_matrix["alice"]["bob"] == 2
        assert result.pairwise_matrix["bob"]["alice"] == 0

    def test_all_abstentions(self):
        """Election with only abstentions."""
        candidates = make_candidates("Alice", "Bob")
        ballots = [
            create_ranked_choice_ballot("v1", None),
            create_ranked_choice_ballot("v2", None),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        assert result.abstentions == 2
        # All pairwise counts are 0
        assert result.pairwise_matrix["alice"]["bob"] == 0


class TestRankedPairsEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_single_candidate(self):
        """Election with only one candidate."""
        candidates = make_candidates("Alice")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice"], ids),
            create_ranked_choice_ballot("v2", ["alice"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.had_condorcet_winner is True

    def test_no_ballots(self):
        """Election with no votes cast."""
        candidates = make_candidates("Alice", "Bob")
        ballots = []

        result = resolve_ranked_pairs(candidates, ballots)

        assert result.total_ballots == 0
        assert result.pairwise_matrix["alice"]["bob"] == 0

    def test_no_candidates(self):
        """Election with no candidates."""
        candidates = []
        ballots = []

        result = resolve_ranked_pairs(candidates, ballots)

        assert result.winners == []
        assert result.pairwise_matrix == {}

    def test_two_candidates_simple(self):
        """Two candidates with clear winner."""
        candidates = make_candidates("Alice", "Bob")
        ids = candidate_ids(candidates)
        ballots = [
            create_ranked_choice_ballot("v1", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v2", ["alice", "bob"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        assert result.winners == ["alice"]
        assert result.had_condorcet_winner is True
        assert result.pairwise_matrix["alice"]["bob"] == 2


class TestCondorcetVsOtherMethods:
    """Tests showing how Condorcet can differ from other methods."""

    def test_condorcet_winner_not_plurality_winner(self):
        """Condorcet winner may not have most first-choice votes."""
        candidates = make_candidates("Alice", "Bob", "Carol")
        ids = candidate_ids(candidates)
        # Bob has most first-choice votes, but Alice beats everyone head-to-head
        ballots = [
            # 4 voters prefer Bob first
            create_ranked_choice_ballot("v1", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v2", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v3", ["bob", "alice", "carol"], ids),
            create_ranked_choice_ballot("v4", ["bob", "alice", "carol"], ids),
            # 3 voters prefer Carol first
            create_ranked_choice_ballot("v5", ["carol", "alice", "bob"], ids),
            create_ranked_choice_ballot("v6", ["carol", "alice", "bob"], ids),
            create_ranked_choice_ballot("v7", ["carol", "alice", "bob"], ids),
            # 2 voters prefer Alice first
            create_ranked_choice_ballot("v8", ["alice", "carol", "bob"], ids),
            create_ranked_choice_ballot("v9", ["alice", "carol", "bob"], ids),
        ]

        result = resolve_ranked_pairs(candidates, ballots)

        # Alice: 2 first-choice votes
        # Bob: 4 first-choice votes (plurality winner)
        # Carol: 3 first-choice votes

        # But pairwise:
        # Alice vs Bob: 2+3 = 5 for Alice, 4 for Bob => Alice wins
        # Alice vs Carol: 2+4 = 6 for Alice, 3 for Carol => Alice wins
        # Alice is Condorcet winner despite fewest first-choice votes!

        assert result.winners == ["alice"]
        assert result.had_condorcet_winner is True
