"""
Ballot models: how a voter with given utilities fills in each ballot format.

Every method in this package reads a ballot, and voters' preferences become
ballots only through a model of how they vote. A ballot model makes that
step explicit, named and versioned, so a comparison of methods can say which
behavior it assumed. A strategic model would be another BallotModel, built
with beliefs about the other voters.

SincereModelV1 is the instrument's sincere voter:
- Single choice: the top-ranked candidate.
- Ranked: candidates by utility, highest first; equal utilities keep
  candidate order.
- Approval: every candidate strictly above the voter's mean utility. A voter
  indifferent among all candidates approves no one (an abstention).
- Score: utilities rescaled so the voter's least favorite scores 0 and
  favorite scores MAX_SCORE, rounded half up. An indifferent voter scores
  every candidate at the midpoint, which changes no outcome.
- Quadratic: votes proportional to each utility's distance from the voter's
  mean, positive above it and negative below, scaled to spend the whole
  credit budget, rounded half away from zero, then trimmed (largest votes
  first, candidate order breaking ties) until the cost fits the budget. An
  indifferent voter casts no votes.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..ballots.quadratic import DEFAULT_CREDIT_BUDGET
from ..ballots.score import MAX_SCORE
from ..types import CandidateId


@dataclass(frozen=True)
class VoterBallots:
    """The ballot one voter casts in every ballot format."""
    choice: CandidateId
    ranking: tuple[CandidateId, ...]
    # Approved candidates, in candidate order; empty means an abstention
    approvals: tuple[CandidateId, ...]
    scores: dict[CandidateId, int]
    # Quadratic votes, nonzero only; empty means an abstention
    allocations: dict[CandidateId, int]
    credit_budget: int

    @property
    def credits_used(self) -> int:
        return sum(votes * votes for votes in self.allocations.values())


class BallotModel(Protocol):
    """Turns one voter's utilities into the ballots that voter casts."""

    @property
    def model_id(self) -> str: ...

    def cast(
        self,
        candidates: Sequence[CandidateId],
        utilities: Sequence[int],
    ) -> VoterBallots:
        """Ballots for a voter whose utilities align with `candidates`."""
        ...


class SincereModelV1:
    """The sincere voter described in this module's docstring."""

    model_id = "sincere-v1"

    def __init__(self, credit_budget: int = DEFAULT_CREDIT_BUDGET) -> None:
        self.credit_budget = credit_budget

    def cast(
        self,
        candidates: Sequence[CandidateId],
        utilities: Sequence[int],
    ) -> VoterBallots:
        if len(candidates) != len(utilities) or not candidates:
            raise ValueError("Give one utility per candidate")
        k = len(candidates)
        total = sum(utilities)

        order = sorted(range(k), key=lambda i: (-utilities[i], i))
        ranking = tuple(candidates[i] for i in order)

        # Strictly above the mean, in integers: k * u > sum(u)
        approvals = tuple(c for c, u in zip(candidates, utilities) if k * u > total)

        return VoterBallots(
            choice=ranking[0],
            ranking=ranking,
            approvals=approvals,
            scores=_scores(candidates, utilities),
            allocations=_allocations(candidates, utilities, self.credit_budget),
            credit_budget=self.credit_budget,
        )


SINCERE_V1 = SincereModelV1()


def _scores(candidates: Sequence[CandidateId], utilities: Sequence[int]) -> dict[CandidateId, int]:
    low, high = min(utilities), max(utilities)
    if high == low:
        return {c: MAX_SCORE // 2 for c in candidates}
    span = high - low
    # Round half up of MAX_SCORE * (u - low) / span, in integers
    return {
        c: (2 * MAX_SCORE * (u - low) + span) // (2 * span)
        for c, u in zip(candidates, utilities)
    }


def _allocations(
    candidates: Sequence[CandidateId],
    utilities: Sequence[int],
    budget: int,
) -> dict[CandidateId, int]:
    k = len(utilities)
    total = sum(utilities)
    # k times each distance from the mean, kept in integers
    deviations = [k * u - total for u in utilities]
    squares = sum(d * d for d in deviations)
    if squares == 0:
        return {}
    scale = math.sqrt(budget / squares)
    votes = [_round_half_away(d * scale) for d in deviations]
    while sum(v * v for v in votes) > budget:
        largest = max(range(k), key=lambda i: (abs(votes[i]), -i))
        votes[largest] -= 1 if votes[largest] > 0 else -1
    return {c: v for c, v in zip(candidates, votes) if v != 0}


def _round_half_away(value: float) -> int:
    magnitude = math.floor(abs(value) + 0.5)
    return magnitude if value >= 0 else -magnitude
