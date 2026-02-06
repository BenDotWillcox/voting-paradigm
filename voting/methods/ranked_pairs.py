"""
Condorcet method with Ranked Pairs (Tideman) completion.

A Condorcet winner beats every other candidate in head-to-head matchups.
When no Condorcet winner exists (cyclic preferences), Ranked Pairs
resolves the cycle by locking in pairwise victories from strongest
to weakest, skipping any that would create a cycle.

Algorithm:
1. Build pairwise comparison matrix from ranked ballots
2. Check for Condorcet winner (beats all others)
3. If no Condorcet winner, apply Ranked Pairs:
   a. List all victories with margins
   b. Sort by margin (desc), then winning votes (desc), then random
   c. Lock victories in order, skipping any that would create a cycle
   d. Winner = candidate with no incoming edges in final graph
"""

import random
from dataclasses import dataclass, field
from typing import Tuple

from ..ballots.ranked_choice import RankedChoiceBallot, is_abstention, prefers
from ..types import (
    Candidate,
    CandidateId,
    ElectionResult,
    VoteCounts,
    TiebreakFunction,
    random_tiebreak,
)


# Pairwise matrix: matrix[a][b] = number of voters who prefer a over b
PairwiseMatrix = dict[CandidateId, dict[CandidateId, int]]

# A victory edge: (winner, loser, margin, winning_votes)
Victory = Tuple[CandidateId, CandidateId, int, int]


@dataclass
class RankedPairsResult(ElectionResult):
    """Extended result with Condorcet/Ranked Pairs data."""
    # Full pairwise comparison matrix
    pairwise_matrix: PairwiseMatrix = field(default_factory=dict)
    # Whether a Condorcet winner existed (won without needing Ranked Pairs)
    had_condorcet_winner: bool = False
    # Victories that were locked in (in order)
    locked_victories: list[Tuple[CandidateId, CandidateId, int]] = field(default_factory=list)
    # Victories that were skipped to avoid cycles
    skipped_victories: list[Tuple[CandidateId, CandidateId, int]] = field(default_factory=list)


def _build_pairwise_matrix(
    candidates: list[Candidate],
    ballots: list[RankedChoiceBallot],
) -> PairwiseMatrix:
    """
    Build pairwise comparison matrix from ballots.

    matrix[a][b] = number of voters who prefer candidate a over candidate b
    """
    candidate_ids = [c.id for c in candidates]

    # Initialize matrix with zeros
    matrix: PairwiseMatrix = {
        a: {b: 0 for b in candidate_ids if b != a}
        for a in candidate_ids
    }

    # Count pairwise preferences from each ballot
    for ballot in ballots:
        if is_abstention(ballot):
            continue

        # For each pair, check preference using O(1) lookup
        for i, a in enumerate(candidate_ids):
            for b in candidate_ids[i + 1:]:
                pref = prefers(ballot, a, b)
                if pref is True:
                    matrix[a][b] += 1
                elif pref is False:
                    matrix[b][a] += 1
                # None means neither ranked (shouldn't happen with complete ballots)

    return matrix


def _get_margin(matrix: PairwiseMatrix, a: CandidateId, b: CandidateId) -> int:
    """Get the margin of a over b (positive if a beats b)."""
    return matrix[a][b] - matrix[b][a]


def _find_condorcet_winner(
    candidate_ids: list[CandidateId],
    matrix: PairwiseMatrix,
) -> CandidateId | None:
    """
    Find Condorcet winner if one exists.

    A Condorcet winner beats every other candidate head-to-head.
    """
    for candidate in candidate_ids:
        beats_all = True
        for opponent in candidate_ids:
            if opponent == candidate:
                continue
            if _get_margin(matrix, candidate, opponent) <= 0:
                beats_all = False
                break
        if beats_all:
            return candidate
    return None


def _get_all_victories(
    candidate_ids: list[CandidateId],
    matrix: PairwiseMatrix,
) -> list[Victory]:
    """
    Get all pairwise victories (positive margins only).

    Returns list of (winner, loser, margin, winning_votes) tuples.
    """
    victories: list[Victory] = []

    for i, a in enumerate(candidate_ids):
        for b in candidate_ids[i + 1:]:
            margin = _get_margin(matrix, a, b)
            if margin > 0:
                victories.append((a, b, margin, matrix[a][b]))
            elif margin < 0:
                victories.append((b, a, -margin, matrix[b][a]))
            # margin == 0 means tie, no victory recorded

    return victories


def _sort_victories(victories: list[Victory]) -> list[Victory]:
    """
    Sort victories by margin (desc), then winning votes (desc), then random.

    Random tiebreaker is applied by shuffling before stable sort.
    """
    # Shuffle first to randomize ties
    shuffled = list(victories)
    random.shuffle(shuffled)

    # Stable sort by winning_votes (secondary), then margin (primary)
    # Sort is stable, so we sort by secondary key first, then primary
    shuffled.sort(key=lambda v: v[3], reverse=True)  # winning_votes desc
    shuffled.sort(key=lambda v: v[2], reverse=True)  # margin desc

    return shuffled


def _would_create_cycle(
    graph: dict[CandidateId, set[CandidateId]],
    winner: CandidateId,
    loser: CandidateId,
) -> bool:
    """
    Check if adding edge winner→loser would create a cycle.

    A cycle would exist if there's already a path from loser to winner.
    Uses DFS to check path existence.
    """
    # If adding winner→loser, check if loser can already reach winner
    visited: set[CandidateId] = set()
    stack = [loser]

    while stack:
        current = stack.pop()
        if current == winner:
            return True
        if current in visited:
            continue
        visited.add(current)

        # Add all candidates that current beats
        if current in graph:
            stack.extend(graph[current])

    return False


def _apply_ranked_pairs(
    candidate_ids: list[CandidateId],
    matrix: PairwiseMatrix,
    tiebreak: TiebreakFunction,
) -> Tuple[CandidateId | None, list[Tuple[CandidateId, CandidateId, int]], list[Tuple[CandidateId, CandidateId, int]]]:
    """
    Apply Ranked Pairs algorithm to find winner.

    Returns (winner, locked_victories, skipped_victories).
    """
    victories = _get_all_victories(candidate_ids, matrix)
    sorted_victories = _sort_victories(victories)

    # Graph: graph[a] = set of candidates that a beats (edges a→b)
    graph: dict[CandidateId, set[CandidateId]] = {cid: set() for cid in candidate_ids}

    locked: list[Tuple[CandidateId, CandidateId, int]] = []
    skipped: list[Tuple[CandidateId, CandidateId, int]] = []

    for winner, loser, margin, _ in sorted_victories:
        if _would_create_cycle(graph, winner, loser):
            skipped.append((winner, loser, margin))
        else:
            graph[winner].add(loser)
            locked.append((winner, loser, margin))

    # Find winner: candidate with no incoming edges
    has_incoming = set()
    for edges in graph.values():
        has_incoming.update(edges)

    sources = [cid for cid in candidate_ids if cid not in has_incoming]

    if len(sources) == 1:
        return sources[0], locked, skipped
    elif len(sources) == 0:
        # Shouldn't happen with correct algorithm
        return None, locked, skipped
    else:
        # Multiple sources (all tied at top) - use tiebreak
        return tiebreak(sources), locked, skipped


def resolve_ranked_pairs(
    candidates: list[Candidate],
    ballots: list[RankedChoiceBallot],
    tiebreak: TiebreakFunction = random_tiebreak,
    pairwise_matrix: PairwiseMatrix | None = None,
    include_pairwise_matrix: bool = True,
) -> RankedPairsResult:
    """
    Resolve an election using Condorcet method with Ranked Pairs completion.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties (used when no clear winner)
        pairwise_matrix: Optional precomputed pairwise matrix to reuse
        include_pairwise_matrix: Whether to include the matrix in the result

    Returns:
        Ranked Pairs result with winner, pairwise matrix, and locked/skipped edges
    """
    candidate_ids = [c.id for c in candidates]

    # Handle edge cases
    if len(candidates) == 0:
        return RankedPairsResult(
            winners=[],
            vote_counts={},
            total_ballots=len(ballots),
            abstentions=len([b for b in ballots if is_abstention(b)]),
            tiebreak_applied=False,
            pairwise_matrix={},
            had_condorcet_winner=False,
            locked_victories=[],
            skipped_victories=[],
        )

    if len(candidates) == 1:
        return RankedPairsResult(
            winners=[candidates[0].id],
            vote_counts={candidates[0].id: len([b for b in ballots if not is_abstention(b)])},
            total_ballots=len(ballots),
            abstentions=len([b for b in ballots if is_abstention(b)]),
            tiebreak_applied=False,
            pairwise_matrix={candidates[0].id: {}},
            had_condorcet_winner=True,
            locked_victories=[],
            skipped_victories=[],
        )

    # Count abstentions
    abstentions = len([b for b in ballots if is_abstention(b)])

    # Build or reuse pairwise matrix
    matrix = pairwise_matrix or _build_pairwise_matrix(candidates, ballots)

    # Check for Condorcet winner
    condorcet_winner = _find_condorcet_winner(candidate_ids, matrix)

    if condorcet_winner is not None:
        # Build vote_counts from pairwise wins
        vote_counts: VoteCounts = {}
        for cid in candidate_ids:
            # Count total "wins" (head-to-head victories)
            wins = sum(1 for opp in candidate_ids if opp != cid and _get_margin(matrix, cid, opp) > 0)
            vote_counts[cid] = wins

        return RankedPairsResult(
            winners=[condorcet_winner],
            vote_counts=vote_counts,
            total_ballots=len(ballots),
            abstentions=abstentions,
            tiebreak_applied=False,
            pairwise_matrix=matrix if include_pairwise_matrix else {},
            had_condorcet_winner=True,
            locked_victories=[],
            skipped_victories=[],
        )

    # No Condorcet winner - apply Ranked Pairs
    winner, locked, skipped = _apply_ranked_pairs(candidate_ids, matrix, tiebreak)

    # Build vote_counts from pairwise wins
    vote_counts = {}
    for cid in candidate_ids:
        wins = sum(1 for opp in candidate_ids if opp != cid and _get_margin(matrix, cid, opp) > 0)
        vote_counts[cid] = wins

    tiebreak_applied = winner is None or len(skipped) > 0

    if winner is None:
        # All candidates tied - use tiebreak
        winner = tiebreak(candidate_ids)
        tiebreak_applied = True

    return RankedPairsResult(
        winners=[winner],
        vote_counts=vote_counts,
        total_ballots=len(ballots),
        abstentions=abstentions,
        tiebreak_applied=tiebreak_applied,
        pairwise_matrix=matrix if include_pairwise_matrix else {},
        had_condorcet_winner=False,
        locked_victories=locked,
        skipped_victories=skipped,
    )
