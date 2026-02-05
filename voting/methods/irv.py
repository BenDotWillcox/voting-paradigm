"""
Instant Runoff Voting (IRV) resolution method.

Also known as Ranked Choice Voting (RCV) or Alternative Vote (AV).

Algorithm:
1. Count first-choice votes for each remaining candidate
2. If a candidate has a majority (>50% of non-exhausted ballots), they win
3. Otherwise, eliminate the candidate(s) with the fewest votes
4. Redistribute eliminated candidates' votes to each voter's next choice
5. Repeat until a candidate achieves majority

Elimination tiebreak:
- If multiple candidates are tied for fewest votes, eliminate all of them
  if at least one candidate would remain
- Otherwise, use random tiebreak to select one for elimination
"""

from dataclasses import dataclass, field

from ..ballots.ranked_choice import (
    RankedChoiceBallot,
    is_abstention,
    get_first_choice,
)
from ..types import (
    Candidate,
    CandidateId,
    ElectionResult,
    VoteCounts,
    TiebreakFunction,
    random_tiebreak,
)


@dataclass
class IRVRound:
    """Data for a single round of IRV counting."""
    round_number: int
    vote_counts: VoteCounts
    exhausted_ballots: int
    active_ballots: int
    eliminated: list[CandidateId]
    elimination_was_tiebreak: bool


@dataclass
class IRVResult(ElectionResult):
    """Extended result with IRV-specific round data."""
    # Round-by-round voting data
    rounds: list[IRVRound] = field(default_factory=list)
    # Total ballots that became exhausted (all choices eliminated)
    total_exhausted: int = 0
    # The round in which the winner achieved majority
    winning_round: int = 0


def _get_active_choice(
    ballot: RankedChoiceBallot,
    eliminated: set[CandidateId],
) -> CandidateId | None:
    """
    Get the voter's top choice among non-eliminated candidates.

    Returns None if all of the voter's ranked candidates have been eliminated
    (exhausted ballot).
    """
    for candidate_id in ballot.ranking:
        if candidate_id not in eliminated:
            return candidate_id
    return None


def resolve_irv(
    candidates: list[Candidate],
    ballots: list[RankedChoiceBallot],
    tiebreak: TiebreakFunction = random_tiebreak,
) -> IRVResult:
    """
    Resolve an election using Instant Runoff Voting.

    Args:
        candidates: All candidates in the election
        ballots: All cast ballots
        tiebreak: Function to break ties when elimination would leave no candidates

    Returns:
        IRV result with winner, round-by-round data, and metadata
    """
    # Filter out abstentions
    active_ballots = [b for b in ballots if not is_abstention(b)]
    abstention_count = len(ballots) - len(active_ballots)

    # Track eliminated candidates
    eliminated: set[CandidateId] = set()
    remaining_candidates = {c.id for c in candidates}

    # Track rounds
    rounds: list[IRVRound] = []
    round_number = 0
    total_exhausted = 0

    while True:
        round_number += 1

        # Count votes for remaining candidates
        vote_counts: VoteCounts = {cid: 0 for cid in remaining_candidates}
        exhausted_this_round = 0
        active_this_round = 0

        for ballot in active_ballots:
            choice = _get_active_choice(ballot, eliminated)
            if choice is None:
                exhausted_this_round += 1
            else:
                vote_counts[choice] += 1
                active_this_round += 1

        # Check for majority winner
        majority_threshold = active_this_round / 2

        winner: CandidateId | None = None
        for candidate_id, count in vote_counts.items():
            if count > majority_threshold:
                winner = candidate_id
                break

        if winner is not None:
            # Record final round
            rounds.append(IRVRound(
                round_number=round_number,
                vote_counts=dict(vote_counts),
                exhausted_ballots=exhausted_this_round,
                active_ballots=active_this_round,
                eliminated=[],
                elimination_was_tiebreak=False,
            ))

            return IRVResult(
                winners=[winner],
                vote_counts=vote_counts,
                total_ballots=len(ballots),
                abstentions=abstention_count,
                tiebreak_applied=False,  # Winner achieved majority
                rounds=rounds,
                total_exhausted=exhausted_this_round,
                winning_round=round_number,
            )

        # No majority - find candidate(s) with fewest votes
        if not vote_counts:
            # No candidates left (edge case)
            return IRVResult(
                winners=[],
                vote_counts={},
                total_ballots=len(ballots),
                abstentions=abstention_count,
                tiebreak_applied=False,
                rounds=rounds,
                total_exhausted=exhausted_this_round,
                winning_round=0,
            )

        min_votes = min(vote_counts.values())
        candidates_with_min = [
            cid for cid, count in vote_counts.items()
            if count == min_votes
        ]

        # Determine who to eliminate
        elimination_was_tiebreak = False

        if len(candidates_with_min) >= len(remaining_candidates):
            # All remaining candidates are tied - use tiebreak to pick winner
            # This is a final-round tie
            winner = tiebreak(list(remaining_candidates))
            to_eliminate = [cid for cid in remaining_candidates if cid != winner]
            elimination_was_tiebreak = True
        elif len(remaining_candidates) - len(candidates_with_min) >= 1:
            # Eliminating all tied candidates leaves at least 1
            to_eliminate = candidates_with_min
        else:
            # Would eliminate too many - use tiebreak
            to_eliminate = [tiebreak(candidates_with_min)]
            elimination_was_tiebreak = True

        # Record this round
        rounds.append(IRVRound(
            round_number=round_number,
            vote_counts=dict(vote_counts),
            exhausted_ballots=exhausted_this_round,
            active_ballots=active_this_round,
            eliminated=to_eliminate,
            elimination_was_tiebreak=elimination_was_tiebreak,
        ))

        # Perform elimination
        for cid in to_eliminate:
            eliminated.add(cid)
            remaining_candidates.remove(cid)

        # Check if only one candidate remains
        if len(remaining_candidates) == 1:
            final_winner = next(iter(remaining_candidates))

            # Count final round
            round_number += 1
            final_vote_counts: VoteCounts = {final_winner: 0}
            final_exhausted = 0
            final_active = 0

            for ballot in active_ballots:
                choice = _get_active_choice(ballot, eliminated)
                if choice is None:
                    final_exhausted += 1
                else:
                    final_vote_counts[choice] += 1
                    final_active += 1

            rounds.append(IRVRound(
                round_number=round_number,
                vote_counts=dict(final_vote_counts),
                exhausted_ballots=final_exhausted,
                active_ballots=final_active,
                eliminated=[],
                elimination_was_tiebreak=False,
            ))

            return IRVResult(
                winners=[final_winner],
                vote_counts=final_vote_counts,
                total_ballots=len(ballots),
                abstentions=abstention_count,
                tiebreak_applied=elimination_was_tiebreak,
                rounds=rounds,
                total_exhausted=final_exhausted,
                winning_round=round_number,
            )

        if len(remaining_candidates) == 0:
            # All candidates eliminated (edge case)
            return IRVResult(
                winners=[],
                vote_counts={},
                total_ballots=len(ballots),
                abstentions=abstention_count,
                tiebreak_applied=elimination_was_tiebreak,
                rounds=rounds,
                total_exhausted=len(active_ballots),
                winning_round=0,
            )
