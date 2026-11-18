"""
Does choosing a resolver from a voting record predict agreement on a fresh
question, with real people? (Pre-freeze review, finding 4.)

The simulation's whole mechanism is that a person chosen for agreeing with a
voter on past questions will agree with them on the next one. This checks
that on real CES 2024 respondents instead of simulated ones, so it does not
depend on the fitted belief model at all.

  - Cities: a seeded sample of five real congressional districts with at
    least 100 complete respondents, 100 drawn from each, 500 people.
  - Leave one item out: for each of the 36 items in turn, every resident's
    resolver is chosen from their answers to the other 35, and scored on
    whether that person's real answer to the held-out item matches theirs.
  - Choices, each ranked as the simulation ranks them (lower bound of the
    80% credible interval, then posterior mean):
      random          anyone else in the city (the expected agreement)
      representative  plurality of residents' record-based preferences
                      among three random residents of the district (the
                      matched representative)
      own of three    each resident's own preferred one of those three
      proxy           the best match on all 35 other items
      topic           the best match on the held-out item's topic only
      topic pooled    the same with the prior borrowing strength from the
                      other topics (amendment A3), as liquid chooses
  - Ties (revised 2026-11-18, second review). Rows are grouped by district,
    so breaking ties by row index sent most tied choices to the first
    district (96% for the topic-only arm, which averaged 99 tied
    candidates). Every choice now scores the average agreement over its
    tied best candidates, the expectation under a uniform random
    tie-break; a resident whose preference among the three is tied splits
    their election ballot equally among the tied candidates.
  - One population for every method: the 485 residents who are not one of
    their district's three candidates, so a contrast never compares means
    over different people.
  - Everyone answered every item here, so this measures agreement only:
    attendance plays no part.

Uncertainty. The 20 x 36 city-by-item scores are not independent: the same
items recur in every city and the same residents in every fold. Two
intervals are reported for each method and contrast: over cities (average
the items within each city, then a t-interval over the 20 cities: inference
to new cities on these 36 items), and two-way (crossed city and item random
effects by the method of moments: inference to new cities and new items
like these). The two-way interval is the one a margin is read against. The
items are a fixed national survey grid, not a random sample of questions, so
even the two-way interval is a convenience.

Limits: a topic has two to six items, so a topic delegate is chosen from one
to five questions; the per-topic results say where that is too thin. The
items are national and salient. This is development evidence about the
mechanism, not a test of H1.

Run through scripts/validate_beliefs.py (`selection`).
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.stats import t as student_t

from delegation.comparison.choice import Agreement, agreement, pooled_agreements
from delegation.comparison.population import NO, YES
from scripts.fit_ces_beliefs import ITEMS, load_survey

SEED = 20261119
CITIES = 20
DISTRICTS_PER_CITY = 5
PER_DISTRICT = 100
CANDIDATES = 3
METHODS = ("random", "representative", "own_of_three", "proxy", "topic", "topic_pooled")
WORKERS = 8
CONTRASTS = {
    "own_of_three_minus_representative": ("own_of_three", "representative"),
    "proxy_minus_own_of_three": ("proxy", "own_of_three"),
    "topic_pooled_minus_proxy": ("topic_pooled", "proxy"),
    "topic_minus_proxy": ("topic", "proxy"),
    "proxy_minus_random": ("proxy", "random"),
}


def _votes(y: np.ndarray) -> np.ndarray:
    return np.where(y == 1.0, YES, NO).astype(np.int8)


def _tied_best(a: Agreement, pool: np.ndarray) -> np.ndarray:
    """
    [voter, candidate]: whether the candidate is among the voter's best in
    `pool` (a [voter, candidate] mask) by lower bound, then posterior mean.
    """
    lower = np.where(pool, a.lower, -np.inf)
    top = pool & (lower == lower.max(axis=1, keepdims=True))
    mean = np.where(top, a.mean, -np.inf)
    return np.asarray(top & (mean == mean.max(axis=1, keepdims=True)))


def _expected(same: np.ndarray, tied: np.ndarray) -> np.ndarray:
    """Agreement averaged over each voter's tied candidates."""
    return np.asarray((same & tied).sum(axis=1) / tied.sum(axis=1))


def winner_probabilities(choices: np.ndarray) -> np.ndarray:
    """
    Exact winner probabilities of a three-candidate plurality election.

    `choices` is [voter, candidate]: the candidates each voter is tied
    among (one True for a decided voter). Each candidate also votes for
    themself. A tied voter picks one of their candidates uniformly at
    random, and a tie for most votes is broken uniformly at random, the
    expectation of a randomized integer-ballot election (third review,
    2026-11-18: splitting tied ballots fractionally and then taking the
    plurality is a different rule and can pick a different winner).
    """
    if choices.ndim != 2 or choices.shape[1] != 3 or not choices.any(axis=1).all():
        raise ValueError("each voter needs at least one of three candidates")
    sizes = choices.sum(axis=1)
    base = np.ones(3, dtype=np.int64) + choices[sizes == 1].sum(axis=0)
    tied = choices[sizes > 1]
    n = tied.shape[0]
    # dist[a, b]: probability that tied voters gave a to the first
    # candidate and b to the second (the rest to the third)
    dist = np.zeros((n + 1, n + 1))
    dist[0, 0] = 1.0
    for row in tied:
        k = int(row.sum())
        new = np.zeros_like(dist)
        if row[0]:
            new[1:, :] += dist[:-1, :] / k
        if row[1]:
            new[:, 1:] += dist[:, :-1] / k
        if row[2]:
            new += dist / k
        dist = new
    a, b = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
    valid = a + b <= n
    totals = np.stack([base[0] + a, base[1] + b, base[2] + n - a - b])
    top = totals == totals.max(axis=0)
    share = np.where(valid, dist, 0.0) / top.sum(axis=0)
    return np.asarray([(share * top[c]).sum() for c in range(3)])


def _city(args: tuple[np.ndarray, np.ndarray, list[np.ndarray], int]) -> dict[str, np.ndarray]:
    """Each method's mean agreement over the scored residents, per held-out item."""
    votes, item_topic, slates, topics = args
    people = votes.shape[0]
    district = np.repeat(np.arange(DISTRICTS_PER_CITY), PER_DISTRICT)
    on_slate = np.zeros(people, dtype=bool)
    for slate in slates:
        on_slate[slate] = True
    scored = ~on_slate
    others = ~np.eye(people, dtype=bool)
    slate_pool = np.zeros((people, people), dtype=bool)
    for d, slate in enumerate(slates):
        members = np.flatnonzero(district == d)
        slate_pool[np.ix_(members, slate)] = True
    slate_pool &= others
    out = {m: np.empty(len(ITEMS)) for m in METHODS}
    for j in range(len(ITEMS)):
        train = np.delete(np.arange(len(ITEMS)), j)
        answer = votes[:, j]
        same = answer[:, None] == answer[None, :]
        whole = agreement(votes[:, train])
        topic_cols = train[item_topic[train] == item_topic[j]]
        topic_only = agreement(votes[:, topic_cols])
        pooled = pooled_agreements(votes[:, train], item_topic[train], topics).agreements[
            item_topic[j]
        ]
        result = {
            "random": (same & others).sum(axis=1) / (people - 1),
            "proxy": _expected(same, _tied_best(whole, others)),
            "topic": _expected(same, _tied_best(topic_only, others)),
            "topic_pooled": _expected(same, _tied_best(pooled, others)),
        }
        # The matched pair: three random residents per district. A
        # candidate votes for themself; a tied resident picks one of their
        # tied candidates at random, and the election is scored by its
        # exact winner probabilities.
        own_tied = _tied_best(whole, slate_pool)
        own = np.full(people, np.nan)
        rep = np.full(people, np.nan)
        for d, slate in enumerate(slates):
            members = np.flatnonzero((district == d) & scored)
            win = winner_probabilities(own_tied[np.ix_(members, slate)])
            own[members] = _expected(same[members], own_tied[members])
            rep[members] = same[np.ix_(members, slate)].astype(float) @ win
        result["own_of_three"] = own
        result["representative"] = rep
        for method in METHODS:
            out[method][j] = float(np.mean(result[method][scored]))
    return out


def _interval(values: np.ndarray) -> dict[str, object]:
    """
    Mean of a [city, item] matrix with an interval over cities and a two-way
    (crossed city and item) interval, both 95%.
    """
    cities, items = values.shape
    mean = float(values.mean())
    city_means = values.mean(axis=1)
    item_means = values.mean(axis=0)
    se_city = float(city_means.std(ddof=1) / np.sqrt(cities))
    ms_city = items * float(((city_means - mean) ** 2).sum()) / (cities - 1)
    ms_item = cities * float(((item_means - mean) ** 2).sum()) / (items - 1)
    resid = values - city_means[:, None] - item_means[None, :] + mean
    ms_resid = float((resid**2).sum()) / ((cities - 1) * (items - 1))
    # Var(mean) = s2_city / C + s2_item / I + s2_resid / (C I); a variance
    # component estimated below zero is set to zero
    var_two_way = max(ms_city + ms_item - ms_resid, ms_city, ms_item, ms_resid) / (cities * items)
    se_two_way = float(np.sqrt(var_two_way))
    t_city = float(student_t.ppf(0.975, cities - 1))
    t_two = float(student_t.ppf(0.975, min(cities, items) - 1))
    return {
        "mean": round(mean, 4),
        "se_over_cities": round(se_city, 4),
        "ci95_over_cities": [round(mean - t_city * se_city, 4), round(mean + t_city * se_city, 4)],
        "se_two_way": round(se_two_way, 4),
        "ci95_two_way": [round(mean - t_two * se_two_way, 4), round(mean + t_two * se_two_way, 4)],
    }


def selection() -> dict[str, object]:
    survey = load_survey()
    complete = ~np.isnan(survey.y).any(axis=1)
    keys = np.array(survey.district)
    topics = sorted({t for _, t, _ in ITEMS})
    item_topic = np.array([topics.index(t) for _, t, _ in ITEMS])
    eligible = sorted(
        g for g in set(keys[complete].tolist()) if g and int((complete & (keys == g)).sum()) >= PER_DISTRICT
    )
    rng = np.random.default_rng(SEED)
    district = np.repeat(np.arange(DISTRICTS_PER_CITY), PER_DISTRICT)
    # Draw every city first, in the same order as before, so the cities are
    # those of the first run
    jobs: list[tuple[np.ndarray, np.ndarray, list[np.ndarray], int]] = []
    for _ in range(CITIES):
        chosen = rng.choice(len(eligible), size=DISTRICTS_PER_CITY, replace=False)
        rows = np.concatenate(
            [
                rng.choice(np.flatnonzero(complete & (keys == eligible[c])), size=PER_DISTRICT, replace=False)
                for c in chosen
            ]
        )
        slates = [
            rng.choice(np.flatnonzero(district == d), size=CANDIDATES, replace=False)
            for d in range(DISTRICTS_PER_CITY)
        ]
        jobs.append((_votes(survey.y[rows]), item_topic, slates, len(topics)))
    # One BLAS thread per worker process
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        per_city = list(pool.map(_city, jobs))
    scores = {m: np.stack([city[m] for city in per_city]) for m in METHODS}  # [city, item]
    by_method = {m: _interval(scores[m]) for m in METHODS}
    gaps = {name: _interval(scores[a] - scores[b]) for name, (a, b) in CONTRASTS.items()}
    per_topic: dict[str, object] = {}
    for k, name in enumerate(topics):
        cols = item_topic == k
        per_topic[name] = {
            "items": int(cols.sum()),
            **{m: round(float(scores[m][:, cols].mean()), 4) for m in METHODS},
            "topic_pooled_minus_proxy": round(
                float((scores["topic_pooled"] - scores["proxy"])[:, cols].mean()), 4
            ),
            "topic_minus_proxy": round(float((scores["topic"] - scores["proxy"])[:, cols].mean()), 4),
        }
    return {
        "cities": CITIES,
        "residents_per_city": DISTRICTS_PER_CITY * PER_DISTRICT,
        "scored_residents_per_city": DISTRICTS_PER_CITY * (PER_DISTRICT - CANDIDATES),
        "held_out_items": len(ITEMS),
        "evidence": "development: real respondents, agreement only (no attendance)",
        "ties": "averaged over tied best candidates; tied election ballots split equally",
        "by_method": by_method,
        "paired_gaps": gaps,
        "per_topic": per_topic,
        "city_item_scores": {m: np.round(scores[m], 5).tolist() for m in METHODS},
    }
