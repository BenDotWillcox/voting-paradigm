"""
Fidelity, overhead and outcome agreement, with the breakdowns that show how
a fidelity difference arose.

  Fidelity   per voter and question, 1 when the ballot counted for the voter
             equals their sincere vote, else 0 (an abstention never
             matches). Unweighted: every question counts the same (decided
             2026-11-14).
  Shares     every counted ballot is a match, a contrary ballot or no ballot;
             the three shares sum to one and fidelity is the first. A voter
             whose resolver never voted and one whose resolver voted against
             them both lose fidelity, for different reasons.
  Overhead   the share of questions a voter decides themself, whether or
             not they then vote, counted the same way in every arrangement:
             whoever resolves a question for themself, an elected resident
             included. Delegations maintained are reported beside it.
  Lifecycle  overhead over the history period and the evaluation period
             together, for the arrangements that need a public record
             (everyone decides every history question directly).
  Outcome    whether a question's winner equals the full-turnout winner,
             what the whole city would choose if everyone voted.

These are computed on the evaluation period only, never on the history
delegates were chosen from, except lifecycle overhead, which counts the
history period as fully decided by each voter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .arrangements import (
    DISTRICT_CHOICE,
    LIQUID,
    PROXY,
    REPRESENTATIVE_BY_RECORD,
    Outcome,
)
from .population import NOT_CAST, Population

# Arrangements whose resolvers are chosen from a public voting record
NEEDS_RECORD = frozenset({PROXY, LIQUID, REPRESENTATIVE_BY_RECORD, DISTRICT_CHOICE})


@dataclass(frozen=True)
class Measures:
    """The headline numbers for one arrangement."""

    arrangement: str
    fidelity: float
    # The counted ballot was cast against the voter's sincere vote
    contrary_share: float
    # No ballot was counted (the resolver did not vote)
    none_share: float
    overhead: float
    # Overhead over history and evaluation together, when a record is needed
    lifecycle_overhead: float
    delegations_per_voter: float
    # Share of questions whose winner is the full-turnout winner
    outcome_agreement: float
    # Share of votes decided by someone else
    delegated_share: float
    # Share of delegated votes whose resolver did not vote
    lost_share: float
    # Share of (resolver, question) pairs, for resolvers holding at least one
    # other voter's vote, on which the resolver voted
    resolver_attendance: float
    # Fidelity on the questions voters kept, and on those someone else resolved
    fidelity_kept: float
    fidelity_resolved: float
    # Per-voter fidelity: share of voters below one half, and the 10th
    # percentile; and, among voters below one half, the mean share of their
    # questions with no ballot and with a contrary ballot
    share_below_half: float
    p10_voter_fidelity: float
    below_half_none_share: float
    below_half_contrary_share: float
    # The largest share of all votes on one question held by one resolver,
    # averaged over questions and at its worst
    mean_largest_share: float
    max_largest_share: float


def fidelity_by_voter(population: Population, outcome: Outcome) -> np.ndarray:
    """Each voter's fidelity over the evaluation questions."""
    matches = outcome.counted == population.evaluation.sincere
    return np.asarray(matches.mean(axis=1), dtype=np.float64)


def _mean_where(values: np.ndarray, mask: np.ndarray) -> float:
    return float(values[mask].mean()) if mask.any() else float("nan")


def measure(population: Population, outcome: Outcome, reference: Outcome) -> Measures:
    """The headline numbers for one arrangement, against the reference."""
    people, questions = outcome.counted.shape
    sincere = population.evaluation.sincere
    match = outcome.counted == sincere
    none = outcome.counted == NOT_CAST
    contrary = ~match & ~none
    delegated = ~outcome.kept
    delegated_votes = int(delegated.sum())
    lost = int((delegated & none).sum())
    columns = np.broadcast_to(np.arange(questions)[None, :], outcome.resolver.shape)
    holds = np.zeros((people, questions), dtype=np.bool_)
    others = outcome.resolver != np.arange(people)[:, None]
    holds[outcome.resolver[others], columns[others]] = True
    # A resolver holding others' votes voted when their own counted ballot
    # (they resolve for themself) is not empty
    resolver_voted = holds & ~none
    largest = np.array(
        [np.bincount(outcome.resolver[:, q], minlength=people).max() for q in range(questions)],
        dtype=np.float64,
    ) / people
    agree = [a == b for a, b in zip(outcome.winners, reference.winners, strict=True)]
    per_voter = match.mean(axis=1)
    below = per_voter < 0.5
    overhead = float(outcome.kept.mean())
    history = len(population.history)
    if outcome.arrangement in NEEDS_RECORD:
        lifecycle = (history + overhead * questions) / (history + questions)
    else:
        lifecycle = overhead
    return Measures(
        arrangement=outcome.arrangement,
        fidelity=float(match.mean()),
        contrary_share=float(contrary.mean()),
        none_share=float(none.mean()),
        overhead=overhead,
        lifecycle_overhead=float(lifecycle),
        delegations_per_voter=float(outcome.delegations.mean()),
        outcome_agreement=float(np.mean(agree)),
        delegated_share=float(delegated.mean()),
        lost_share=lost / delegated_votes if delegated_votes else 0.0,
        resolver_attendance=(
            float(resolver_voted.sum() / holds.sum()) if holds.any() else float("nan")
        ),
        fidelity_kept=_mean_where(match, outcome.kept),
        fidelity_resolved=_mean_where(match, delegated),
        share_below_half=float(below.mean()),
        p10_voter_fidelity=float(np.quantile(per_voter, 0.1)),
        below_half_none_share=_mean_where(none.mean(axis=1), below),
        below_half_contrary_share=_mean_where(contrary.mean(axis=1), below),
        mean_largest_share=float(largest.mean()),
        max_largest_share=float(largest.max()),
    )
