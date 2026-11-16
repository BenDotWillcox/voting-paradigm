"""
Fidelity, overhead and outcome agreement.

  Fidelity   per voter and question, 1 when the ballot counted for the voter
             equals their sincere vote, else 0 (an abstention never
             matches). Unweighted: every question counts the same (decided
             2026-11-14).
  Overhead   the share of questions a voter decides themself, whether or
             not they then vote. Delegations maintained are reported beside
             it, so liquid's upkeep is not hidden.
  Outcome    whether a question's winner equals the full-turnout winner,
             what the whole city would choose if everyone voted.

These are computed on the evaluation period only, never on the history
delegates were chosen from.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .arrangements import Outcome
from .population import NOT_CAST, Population


@dataclass(frozen=True)
class Measures:
    """The headline numbers for one arrangement."""

    arrangement: str
    fidelity: float
    overhead: float
    delegations_per_voter: float
    # Share of questions whose winner is the full-turnout winner
    outcome_agreement: float
    # Share of votes decided by someone else
    delegated_share: float
    # Share of delegated votes whose resolver did not vote
    lost_share: float
    # The largest share of all votes on one question held by one resolver,
    # averaged over questions and at its worst
    mean_largest_share: float
    max_largest_share: float


def fidelity_by_voter(population: Population, outcome: Outcome) -> np.ndarray:
    """Each voter's fidelity over the evaluation questions."""
    matches = outcome.counted == population.evaluation.sincere
    return np.asarray(matches.mean(axis=1), dtype=np.float64)


def measure(population: Population, outcome: Outcome, reference: Outcome) -> Measures:
    """The headline numbers for one arrangement, against the reference."""
    people, questions = outcome.counted.shape
    sincere = population.evaluation.sincere
    delegated = ~outcome.kept
    delegated_votes = int(delegated.sum())
    lost = int((delegated & (outcome.counted == NOT_CAST)).sum())
    largest = np.array(
        [np.bincount(outcome.resolver[:, q], minlength=people).max() for q in range(questions)],
        dtype=np.float64,
    ) / people
    agree = [a == b for a, b in zip(outcome.winners, reference.winners, strict=True)]
    return Measures(
        arrangement=outcome.arrangement,
        fidelity=float((outcome.counted == sincere).mean()),
        overhead=float(outcome.kept.mean()),
        delegations_per_voter=float(outcome.delegations.mean()),
        outcome_agreement=float(np.mean(agree)),
        delegated_share=float(delegated.mean()),
        lost_share=lost / delegated_votes if delegated_votes else 0.0,
        mean_largest_share=float(largest.mean()),
        max_largest_share=float(largest.max()),
    )
