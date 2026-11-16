"""
Choosing delegates from vote history.

Nobody knows another person's positions. What they can see, because votes are
public, is how that person voted. A voter compares a candidate's past votes
with their own:

  - Only questions the voter voted on themself count as trials.
  - A trial is a match when the candidate voted the same way themself. A
    question the candidate did not vote on counts as a miss: a delegation
    would not have represented the voter there either.
  - Agreement is a Beta-binomial posterior with a uniform prior, and
    candidates are ranked by the lower end of a central credible interval
    (80% by default), so 18 of 20 beats 2 of 2.
  - A voter delegates only to a candidate whose lower bound clears the
    acceptance level, and never to themself.
  - Everyone chooses at once; loops are left to the resolution rule (see
    `choose`).

Agreement is raw, not corrected for chance (decided 2026-11-14): on a
question most of the city agrees on, everyone matches everyone. That lifts
every candidate's score equally and leaves the ranking alone, but overstates
how good the best candidate is. The benchmark reports the inflation.

Choosing the best of many candidates is optimistic (winner's curse), which is
why arrangements are scored on the evaluation period only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.stats import beta

from .population import NO, NOT_CAST, YES, BoolArray, FloatArray, IntArray, VoteArray

DEFAULT_CREDIBLE_MASS = 0.8


@dataclass(frozen=True, eq=False)
class Agreement:
    """
    Pairwise agreement over a set of history questions.

    Arrays are indexed [voter, candidate].
    """

    matches: IntArray
    trials: IntArray
    lower: FloatArray
    credible_mass: float

    @property
    def mean(self) -> FloatArray:
        """The posterior mean agreement."""
        return np.asarray((self.matches + 1.0) / (self.trials + 2.0))

    def ranking(self, voter: int) -> IntArray:
        """
        Candidates for one voter, best first: by lower bound, then posterior
        mean, then index. The voter themself is excluded.
        """
        order = np.lexsort(
            (
                np.arange(self.lower.shape[1]),
                -self.mean[voter],
                -self.lower[voter],
            )
        )
        return np.asarray(order[order != voter], dtype=np.int64)


def agreement_counts(votes: VoteArray) -> tuple[IntArray, IntArray]:
    """
    Matches and trials for every (voter, candidate) pair.

    Args:
        votes: [person, question] ballots cast themselves: YES, NO or
            NOT_CAST

    Returns:
        matches[v, c]: questions v voted on where c cast the same ballot.
        trials[v, c]: questions v voted on, the same for every c.
    """
    if votes.ndim != 2:
        raise ValueError("votes must be a [person, question] matrix")
    if not np.isin(votes, (YES, NO, NOT_CAST)).all():
        raise ValueError("votes must be YES, NO or NOT_CAST")
    yes = (votes == YES).astype(np.int64)
    no = (votes == NO).astype(np.int64)
    matches = yes @ yes.T + no @ no.T
    cast = (votes != NOT_CAST).sum(axis=1).astype(np.int64)
    trials = np.broadcast_to(cast[:, None], matches.shape).copy()
    return np.asarray(matches, dtype=np.int64), trials


def lower_bound(
    matches: npt.ArrayLike,
    trials: npt.ArrayLike,
    credible_mass: float = DEFAULT_CREDIBLE_MASS,
) -> FloatArray:
    """
    The lower end of the central credible interval for agreement, under a
    uniform Beta(1, 1) prior.
    """
    if not 0.0 < credible_mass < 1.0:
        raise ValueError("credible_mass must be in (0, 1)")
    m = np.asarray(matches, dtype=np.float64)
    t = np.asarray(trials, dtype=np.float64)
    if (m < 0).any() or (m > t).any():
        raise ValueError("matches must be between 0 and trials")
    return np.asarray(beta.ppf((1.0 - credible_mass) / 2.0, m + 1.0, t - m + 1.0))


def agreement(
    votes: VoteArray, credible_mass: float = DEFAULT_CREDIBLE_MASS
) -> Agreement:
    """Pairwise agreement with lower bounds; a person never matches themself."""
    matches, trials = agreement_counts(votes)
    lower = lower_bound(matches, trials, credible_mass)
    np.fill_diagonal(lower, -np.inf)
    return Agreement(matches, trials, lower, credible_mass)


@dataclass(frozen=True)
class ChoicePolicy:
    """How voters turn agreement into delegations."""

    # A candidate is acceptable when their lower bound reaches this
    acceptance: float = 0.0
    # At most this many categories per voter, best first; None for no limit
    max_categories: int | None = None
    credible_mass: float = DEFAULT_CREDIBLE_MASS

    def __post_init__(self) -> None:
        if not 0.0 <= self.acceptance <= 1.0:
            raise ValueError("acceptance must be in [0, 1]")
        if self.max_categories is not None and self.max_categories < 0:
            raise ValueError("max_categories must be non-negative")
        if not 0.0 < self.credible_mass < 1.0:
            raise ValueError("credible_mass must be in (0, 1)")


@dataclass(frozen=True, eq=False)
class Choice:
    """
    Each voter's chosen delegate per category, or KEEP.

    `delegate[v, k]` is the index of v's delegate for category k.
    """

    delegate: IntArray
    # The lower bound of the chosen delegate, NaN when kept
    lower: FloatArray

    @property
    def categories(self) -> int:
        return int(self.delegate.shape[1])

    def held(self) -> BoolArray:
        """Whether each voter delegates each category."""
        return np.asarray(self.delegate >= 0)


KEEP = -1


def choose(
    agreements: Sequence[Agreement],
    policy: ChoicePolicy,
) -> Choice:
    """
    Choose delegates for every voter and category, all at once.

    A voter's categories are taken in order of their best candidate's lower
    bound, keeping only those that reach the acceptance level, up to
    `max_categories`. In each, the voter delegates to their top-ranked
    candidate.

    Everyone chooses simultaneously, so no voter's choice depends on the
    order voters are processed in. The creation check of the account app
    (graph.add_delegation refuses a delegation that closes a loop within one
    category) is a rule for edits made one at a time; applied in sequence
    here it would hand the last voter processed every vote, because when
    everyone delegates someone must be refused. Loops are left to the rule
    applied when a question is resolved instead: everyone on a loop decides
    for themself. Mutual best matches therefore both keep the category.

    Args:
        agreements: One agreement per category, all over the same people
        policy: Acceptance level and category limit
    """
    if not agreements:
        raise ValueError("at least one category is needed")
    people = agreements[0].lower.shape[0]
    if any(a.lower.shape != (people, people) for a in agreements):
        raise ValueError("every agreement must cover the same people")

    count = len(agreements)
    top = np.full((people, count), KEEP, dtype=np.int64)
    best = np.full((people, count), -np.inf, dtype=np.float64)
    for k, a in enumerate(agreements):
        for v in range(people):
            ranked = a.ranking(v)
            if len(ranked):
                top[v, k] = ranked[0]
                best[v, k] = a.lower[v, ranked[0]]

    delegate = np.full((people, count), KEEP, dtype=np.int64)
    chosen_lower = np.full((people, count), np.nan, dtype=np.float64)
    for voter in range(people):
        wanted = [k for k in range(count) if best[voter, k] >= policy.acceptance]
        # Best category first; ties by category index (the sort is stable)
        wanted.sort(key=lambda k: -best[voter, k])
        if policy.max_categories is not None:
            wanted = wanted[: policy.max_categories]
        for k in wanted:
            delegate[voter, k] = top[voter, k]
            chosen_lower[voter, k] = best[voter, k]
    return Choice(delegate=delegate, lower=chosen_lower)
