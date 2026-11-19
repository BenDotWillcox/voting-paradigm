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
    (80% by default). For one voter on one topic every candidate has the
    same number of trials (the voter's own votes), so among candidates the
    ranking follows the match count; the interval's width matters across
    voters and topics, where it decides whether the best candidate clears
    the acceptance level.
  - Because a candidate's absence counts as a miss, agreement mixes
    political agreement with attendance. That is what a delegation
    delivers, so choice uses it; but it means pooling strength across
    topics partly measures attendance (see `agreement_counts`).
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
from scipy.optimize import minimize_scalar
from scipy.special import betaln
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
    # The posterior mean when the prior is not uniform (pooled agreement)
    posterior_mean: FloatArray | None = None

    @property
    def mean(self) -> FloatArray:
        """The posterior mean agreement."""
        if self.posterior_mean is not None:
            return self.posterior_mean
        return np.asarray((self.matches + 1.0) / (self.trials + 2.0))

    def ranking(self, voter: int, tie_key: FloatArray | None = None) -> IntArray:
        """
        Candidates for one voter, best first: by lower bound, then posterior
        mean, then `tie_key[voter]` (ascending), then index. The voter
        themself is excluded.

        Equal counts give equal bounds, so ties are common with short
        records. Without a tie key they go to the lowest index, and when
        rows are grouped by district that means the first district; the
        simulation passes a seeded random key (`tie_key`) instead.
        """
        index = np.arange(self.lower.shape[1])
        secondary = tie_key[voter] if tie_key is not None else index
        order = np.lexsort((index, secondary, -self.mean[voter], -self.lower[voter]))
        return np.asarray(order[order != voter], dtype=np.int64)


def agreement_counts(
    votes: VoteArray, absence_is_miss: bool = True
) -> tuple[IntArray, IntArray]:
    """
    Matches and trials for every (voter, candidate) pair.

    Args:
        votes: [person, question] ballots cast themselves: YES, NO or
            NOT_CAST
        absence_is_miss: True (what delegate choice uses) counts a question
            the candidate skipped as a miss, so agreement mixes political
            agreement with attendance. False counts only questions both
            voted on: political agreement alone, a diagnostic.

    Returns:
        matches[v, c]: questions v voted on where c cast the same ballot.
        trials[v, c]: questions v voted on (the same for every c), or with
            `absence_is_miss` False, questions both voted on.
    """
    if votes.ndim != 2:
        raise ValueError("votes must be a [person, question] matrix")
    if not np.isin(votes, (YES, NO, NOT_CAST)).all():
        raise ValueError("votes must be YES, NO or NOT_CAST")
    yes = (votes == YES).astype(np.int64)
    no = (votes == NO).astype(np.int64)
    matches = yes @ yes.T + no @ no.T
    if not absence_is_miss:
        cast_matrix = (votes != NOT_CAST).astype(np.int64)
        return np.asarray(matches, dtype=np.int64), np.asarray(cast_matrix @ cast_matrix.T)
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


@dataclass(frozen=True, eq=False)
class PooledAgreements:
    """Per-category agreement that borrows strength from the whole record."""

    agreements: tuple[Agreement, ...]
    # Prior strength in pseudo-questions, estimated from the history
    strength: float


# Search range for the prior strength, in pseudo-questions
_STRENGTH_BOUNDS = (0.1, 10_000.0)


def pooled_agreements(
    votes: VoteArray,
    category: IntArray,
    categories: int,
    credible_mass: float = DEFAULT_CREDIBLE_MASS,
    absence_is_miss: bool = True,
) -> PooledAgreements:
    """
    Agreement per category, with a prior centred on the pair's agreement
    over every other category (amendment A3).

    For voter v, candidate c and category k, the prior is
    Beta(s mu, s (1 - mu)), where mu is the posterior mean of v's agreement
    with c on all history questions outside k (leaving k out, so its own
    questions are not counted twice) and s is one prior strength for the
    whole population. s is estimated by maximising the beta-binomial
    marginal likelihood of every (voter, candidate, category) count, so a
    population whose agreement varies little between categories gets a
    strong prior and one whose agreement varies a lot gets a weak one. A
    category with a thin record then leans on the rest of the record, and
    one with a long record stands on its own.

    Args:
        votes: [person, question] ballots cast themselves
        category: The category of each question (column)
        categories: How many categories there are
        credible_mass: Width of the credible interval for the lower bound
        absence_is_miss: As in `agreement_counts`; False is a diagnostic of
            how much of the pooling strength reflects attendance
    """
    if not 0.0 < credible_mass < 1.0:
        raise ValueError("credible_mass must be in (0, 1)")
    if category.shape != (votes.shape[1],):
        raise ValueError("one category per question is needed")
    counts = [
        agreement_counts(votes[:, category == k], absence_is_miss) for k in range(categories)
    ]
    total_m = np.sum([m for m, _ in counts], axis=0)
    total_n = np.sum([n for _, n in counts], axis=0)
    people = votes.shape[0]
    off = ~np.eye(people, dtype=bool)
    m_k = np.stack([m[off] for m, _ in counts]).astype(np.float64)
    n_k = np.stack([n[off] for _, n in counts]).astype(np.float64)
    mu = (total_m[off] - m_k + 1.0) / (total_n[off] - n_k + 2.0)

    def negative_log_marginal(log_s: float) -> float:
        s = np.exp(log_s)
        a0, b0 = s * mu, s * (1.0 - mu)
        return -float((betaln(m_k + a0, n_k - m_k + b0) - betaln(a0, b0)).sum())

    low, high = np.log(_STRENGTH_BOUNDS[0]), np.log(_STRENGTH_BOUNDS[1])
    fit = minimize_scalar(negative_log_marginal, bounds=(low, high), method="bounded")
    strength = float(np.exp(fit.x))
    q = (1.0 - credible_mass) / 2.0
    agreements: list[Agreement] = []
    for k, (m, n) in enumerate(counts):
        prior_mean = (total_m - m + 1.0) / (total_n - n + 2.0)
        a = strength * prior_mean + m
        b = strength * (1.0 - prior_mean) + n - m
        lower = np.asarray(beta.ppf(q, a, b), dtype=np.float64)
        np.fill_diagonal(lower, -np.inf)
        agreements.append(
            Agreement(m, n, lower, credible_mass, posterior_mean=np.asarray(a / (a + b)))
        )
    return PooledAgreements(tuple(agreements), strength)


@dataclass(frozen=True)
class ChoicePolicy:
    """How voters turn agreement into delegations."""

    # A candidate is acceptable when their lower bound reaches this
    acceptance: float = 0.0
    # At most this many categories per voter, best first; None for no limit
    max_categories: int | None = None
    credible_mass: float = DEFAULT_CREDIBLE_MASS
    # Per-category agreement borrows strength from the whole record (A3);
    # False gives each category a uniform prior of its own
    borrow_strength: bool = True

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


def tie_key(seed: int, people: int) -> FloatArray:
    """
    A seeded [voter, candidate] key for breaking ties between equally
    ranked candidates: a uniform random order per voter, independent of
    row order (rows are grouped by district).
    """
    rng = np.random.default_rng(np.random.SeedSequence([seed, _TIE_STREAM]))
    return np.asarray(rng.random((people, people)))


# Seed stream for tie keys, distinct from the population's streams
_TIE_STREAM = 31


def top_candidates(
    agreements: Sequence[Agreement], tie_key: FloatArray | None = None
) -> tuple[IntArray, FloatArray]:
    """
    Each voter's top-ranked candidate per category and that candidate's
    lower bound: [voter, category] arrays, KEEP and -inf when there is none.
    Ties are broken by `tie_key` as in `Agreement.ranking`.

    A voter with an empty record (no ballot of their own in any of the
    categories given) has no evidence to rank anyone: every candidate ties
    on the prior alone. They get no candidate and keep everything, rather
    than delegating by the tie-break lottery (third A6 review, 2026-11-19).
    """
    if not agreements:
        raise ValueError("at least one category is needed")
    people = agreements[0].lower.shape[0]
    if tie_key is not None and tie_key.shape != (people, people):
        raise ValueError("the tie key must be [voter, candidate]")
    # Each voter's own ballots in each category: trials[v, c] counts the
    # questions v voted on, the same for every candidate c
    record = np.sum([a.trials.max(axis=1) for a in agreements], axis=0)
    top = np.full((people, len(agreements)), KEEP, dtype=np.int64)
    best = np.full((people, len(agreements)), -np.inf, dtype=np.float64)
    for k, a in enumerate(agreements):
        for v in range(people):
            if record[v] == 0:
                continue
            ranked = a.ranking(v, tie_key)
            if len(ranked):
                top[v, k] = ranked[0]
                best[v, k] = a.lower[v, ranked[0]]
    return top, best


def choose(
    agreements: Sequence[Agreement],
    policy: ChoicePolicy,
    tie_key: FloatArray | None = None,
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
        tie_key: Breaks ties between equally ranked candidates (see
            `tie_key`); None breaks them by index
    """
    if not agreements:
        raise ValueError("at least one category is needed")
    people = agreements[0].lower.shape[0]
    if any(a.lower.shape != (people, people) for a in agreements):
        raise ValueError("every agreement must cover the same people")

    count = len(agreements)
    top, best = top_candidates(agreements, tie_key)

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
