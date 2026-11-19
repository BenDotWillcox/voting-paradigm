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
  Overhead   the share of questions a person decides, whether or not they
             then vote, counted the same way in every arrangement: they
             resolve their own vote, or anyone else's vote depends on their
             ballot (an elected resident included). The two coincide except
             for a candidate who decides for followers while their own vote
             goes to an election winner (`district_choice_voters`; third
             review, 2026-11-18). Delegations maintained are reported beside
             it.
  Lifecycle  overhead over the history period and the evaluation period
             together, for the arrangements that need a public record
             (everyone decides every history question directly).
  Outcome    whether a question's winner equals the full-turnout winner,
             what the whole city would choose if everyone voted.
  Loops      the share of votes whose owner delegated but decides for
             themself because their chain loops (the loop rule), and the
             number of loops per question.
  Attribution  a fidelity difference between two arrangements split over
             the same voter-question pairs: those the first arrangement's
             voters kept and those someone else resolved. The two
             share-weighted parts sum to the difference.

These are computed on the evaluation period only, never on the history
delegates were chosen from, except lifecycle overhead, which counts the
history period as fully decided by each voter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .arrangements import (
    DISTRICT_CHOICE,
    DISTRICT_CHOICE_VOTERS,
    LIQUID,
    PROXY,
    REPRESENTATIVE_BY_RECORD,
    Outcome,
)
from .population import NOT_CAST, Population

# A resident's record is light below this share of history questions cast
LIGHT_RECORD = 0.1

# Arrangements whose resolvers are chosen from a public voting record
NEEDS_RECORD = frozenset(
    {PROXY, LIQUID, REPRESENTATIVE_BY_RECORD, DISTRICT_CHOICE_VOTERS, DISTRICT_CHOICE}
)


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
    # Share of (voter, question) pairs on a loop, and loops per question
    loop_share: float
    mean_loops: float
    # Residents with a light public record (fewer than LIGHT_RECORD of the
    # history questions cast themselves), who can barely rank candidates:
    # their share and their fidelity, reported apart so the averages cannot
    # hide them (amendment A6)
    light_record_share: float
    light_record_fidelity: float
    # The subset with no recorded ballot at all, who keep every question
    # (fourth A6 review): light records pool them with residents holding a
    # few ballots, who may delegate
    empty_record_share: float
    empty_record_fidelity: float


@dataclass(frozen=True)
class Attribution:
    """
    A fidelity difference, first minus second, split over the same pairs:
    the pairs the first arrangement's voters kept, and the rest.

    difference = kept_share * kept_difference
                 + (1 - kept_share) * resolved_difference
    """

    first: str
    second: str
    difference: float
    kept_share: float
    # Mean match difference on the first arrangement's kept pairs, and on
    # its resolved ones; NaN when that set is empty
    kept_difference: float
    resolved_difference: float


def attribute(population: Population, first: Outcome, second: Outcome) -> Attribution:
    """
    Split first's fidelity advantage over second between the pairs first's
    voters kept and those someone else resolved, scoring both arrangements
    on the same pairs (second review, 2026-11-18). Each arrangement's own
    kept/resolved split conditions on a different set of pairs, so it
    cannot say where a difference arose.
    """
    sincere = population.evaluation.sincere
    diff = (first.counted == sincere).astype(np.float64) - (second.counted == sincere)
    kept = first.kept
    return Attribution(
        first=first.arrangement,
        second=second.arrangement,
        difference=float(diff.mean()),
        kept_share=float(kept.mean()),
        kept_difference=_mean_where(diff, kept),
        resolved_difference=_mean_where(diff, ~kept),
    )


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
    # A resolver holding others' votes voted when they cast a ballot
    # themself; their own counted ballot may be someone else's
    resolver_voted = holds & outcome.cast
    largest = np.array(
        [np.bincount(outcome.resolver[:, q], minlength=people).max() for q in range(questions)],
        dtype=np.float64,
    ) / people
    agree = [a == b for a, b in zip(outcome.winners, reference.winners, strict=True)]
    per_voter = match.mean(axis=1)
    below = per_voter < 0.5
    light = population.history.casts.mean(axis=1) < LIGHT_RECORD
    empty = np.asarray(~population.history.casts.any(axis=1), dtype=np.bool_)
    # A person decides a question when they resolve their own vote or hold
    # anyone else's
    overhead = float((outcome.kept | holds).mean())
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
        loop_share=float(outcome.looped.mean()),
        mean_loops=float(outcome.loops.mean()),
        light_record_share=float(light.mean()),
        light_record_fidelity=_mean_where(per_voter, light),
        empty_record_share=float(empty.mean()),
        empty_record_fidelity=_mean_where(per_voter, empty),
    )
