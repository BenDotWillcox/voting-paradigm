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
   b. Sort by margin (desc), then winning votes (desc)
   c. Lock victories in order, skipping any that would create a cycle
   d. Winner = candidate with no incoming edges in final graph

Equal-strength victories (same margin and winning votes) are ordered by the
tiebreak only when their order could change which of them get locked. The
tiebreak is applied repeatedly to rank the candidates; equal victories then
go by winner priority, and for a shared winner the lower-priority loser goes
first. Because that priority need not keep clones adjacent, independence of
clones can fail in such exact ties.

Criteria:
- Satisfies majority, Condorcet winner, Condorcet loser, monotonicity, and
  independence of clones (outside the exact ties above)
- Violates participation (with four or more candidates; Moulin 1988),
  consistency, independence of irrelevant alternatives, and later-no-harm
"""

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
    # Candidate priority drawn from the tiebreak to order equal-strength
    # victories, highest first; empty when no such order was needed
    tiebreak_priority: list[CandidateId] = field(default_factory=list)


@dataclass
class _LockOutcome:
    """Outcome of the locking pass, before the edge-case fallbacks."""
    winner: CandidateId | None
    locked: list[Tuple[CandidateId, CandidateId, int]]
    skipped: list[Tuple[CandidateId, CandidateId, int]]
    priority: list[CandidateId]
    tiebreak_applied: bool


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


def _strength_groups(victories: list[Victory]) -> list[list[Victory]]:
    """
    Group victories by strength, strongest first.

    Strength is margin, then winning votes. Victories of equal strength share
    a group and keep their candidate-list order until the tiebreak is needed.
    """
    ordered = sorted(victories, key=lambda v: (-v[2], -v[3]))
    groups: list[list[Victory]] = []
    for victory in ordered:
        if groups and groups[-1][0][2:] == victory[2:]:
            groups[-1].append(victory)
        else:
            groups.append([victory])
    return groups


def _priority_order(
    candidate_ids: list[CandidateId],
    tiebreak: TiebreakFunction,
) -> list[CandidateId]:
    """Rank candidates by repeatedly letting the tiebreak pick from those left."""
    remaining = list(candidate_ids)
    order: list[CandidateId] = []
    while len(remaining) > 1:
        pick = tiebreak(remaining)
        order.append(pick)
        remaining.remove(pick)
    return order + remaining


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


def _stays_acyclic(
    graph: dict[CandidateId, set[CandidateId]],
    victories: list[Victory],
) -> bool:
    """Whether locking every one of these victories keeps the graph acyclic."""
    trial = {cid: set(edges) for cid, edges in graph.items()}
    for winner, loser, _, _ in victories:
        if _would_create_cycle(trial, winner, loser):
            return False
        trial[winner].add(loser)
    return True


def _apply_ranked_pairs(
    candidate_ids: list[CandidateId],
    matrix: PairwiseMatrix,
    tiebreak: TiebreakFunction,
) -> _LockOutcome:
    """Apply Ranked Pairs algorithm to find winner."""
    # Graph: graph[a] = set of candidates that a beats (edges a→b)
    graph: dict[CandidateId, set[CandidateId]] = {cid: set() for cid in candidate_ids}

    locked: list[Tuple[CandidateId, CandidateId, int]] = []
    skipped: list[Tuple[CandidateId, CandidateId, int]] = []
    priority: list[CandidateId] = []
    tiebreak_applied = False

    for group in _strength_groups(_get_all_victories(candidate_ids, matrix)):
        # A victory that already closes a cycle is skipped in any order
        open_victories: list[Victory] = []
        for victory in group:
            winner, loser, margin, _ = victory
            if _would_create_cycle(graph, winner, loser):
                skipped.append((winner, loser, margin))
            else:
                open_victories.append(victory)

        # If the rest can all be locked, their order cannot matter; otherwise
        # it can, so order them by the tiebreak priority
        if len(open_victories) > 1 and not _stays_acyclic(graph, open_victories):
            if not priority:
                priority = _priority_order(candidate_ids, tiebreak)
            rank = {cid: i for i, cid in enumerate(priority)}
            open_victories.sort(key=lambda v: (rank[v[0]], -rank[v[1]]))
            tiebreak_applied = True

        for winner, loser, margin, _ in open_victories:
            if _would_create_cycle(graph, winner, loser):
                skipped.append((winner, loser, margin))
            else:
                graph[winner].add(loser)
                locked.append((winner, loser, margin))

    # Find winner: candidate with no incoming edges
    has_incoming: set[CandidateId] = set()
    for edges in graph.values():
        has_incoming.update(edges)

    sources = [cid for cid in candidate_ids if cid not in has_incoming]

    winner_id: CandidateId | None
    if len(sources) == 1:
        winner_id = sources[0]
    elif len(sources) == 0:
        # Shouldn't happen: a graph built without cycles always has a source
        winner_id = None
    else:
        # Several unbeaten candidates (pairwise ties) - use tiebreak
        winner_id = tiebreak(sources)
        tiebreak_applied = True

    return _LockOutcome(
        winner=winner_id,
        locked=locked,
        skipped=skipped,
        priority=priority,
        tiebreak_applied=tiebreak_applied,
    )


def resolve_ranked_pairs(
    candidates: list[Candidate],
    ballots: list[RankedChoiceBallot],
    tiebreak: TiebreakFunction | None = None,
    pairwise_matrix: PairwiseMatrix | None = None,
    include_pairwise_matrix: bool = True,
) -> RankedPairsResult:
    """
    Resolve an election using Condorcet method with Ranked Pairs completion.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties (defaults to random_tiebreak()).
            Orders equal-strength victories when their order could change
            which are locked, and picks among unbeaten candidates when
            pairwise ties leave more than one.
        pairwise_matrix: Optional precomputed pairwise matrix to reuse
        include_pairwise_matrix: Whether to include the matrix in the result

    Returns:
        Ranked Pairs result with winner, pairwise matrix, and locked/skipped edges
    """
    if tiebreak is None:
        tiebreak = random_tiebreak()

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
    outcome = _apply_ranked_pairs(candidate_ids, matrix, tiebreak)

    # Build vote_counts from pairwise wins
    vote_counts = {}
    for cid in candidate_ids:
        wins = sum(1 for opp in candidate_ids if opp != cid and _get_margin(matrix, cid, opp) > 0)
        vote_counts[cid] = wins

    winner = outcome.winner
    tiebreak_applied = outcome.tiebreak_applied

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
        locked_victories=outcome.locked,
        skipped_victories=outcome.skipped,
        tiebreak_priority=outcome.priority,
    )
