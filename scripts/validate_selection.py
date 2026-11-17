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
    80% credible interval, then mean, then index):
      random          anyone else in the city (the expected agreement)
      representative  plurality of residents' record-based preferences
                      among three random residents of the district (the
                      matched representative)
      own of three    each resident's own preferred one of those three
      proxy           the best match on all 35 other items
      topic           the best match on the held-out item's topic only
      topic pooled    the same with the prior borrowing strength from the
                      other topics (amendment A3), as liquid chooses
  - Everyone answered every item here, so this measures agreement only:
    attendance plays no part.

Limits: a topic has two to six items, so a topic delegate is chosen from one
to five questions; the per-topic results say where that is too thin. The
items are national and salient. This is development evidence about the
mechanism, not a test of H1.

Run through scripts/validate_beliefs.py (`selection`).
"""

from __future__ import annotations

import numpy as np

from delegation.comparison.choice import agreement, pooled_agreements, top_candidates
from delegation.comparison.population import NO, YES
from scripts.fit_ces_beliefs import ITEMS, load_survey

SEED = 20261119
CITIES = 20
DISTRICTS_PER_CITY = 5
PER_DISTRICT = 100
CANDIDATES = 3
METHODS = ("random", "representative", "own_of_three", "proxy", "topic", "topic_pooled")


def _votes(y: np.ndarray) -> np.ndarray:
    return np.where(y == 1.0, YES, NO).astype(np.int8)


def _preferred(lower: np.ndarray, mean: np.ndarray, voter: int, pool: np.ndarray) -> int:
    order = np.lexsort((pool, -mean[voter, pool], -lower[voter, pool]))
    return int(pool[order[0]])


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
    scores: dict[str, list[float]] = {m: [] for m in METHODS}
    by_topic: dict[str, dict[str, list[float]]] = {m: {t: [] for t in topics} for m in METHODS}
    for _ in range(CITIES):
        chosen = rng.choice(len(eligible), size=DISTRICTS_PER_CITY, replace=False)
        rows = np.concatenate(
            [
                rng.choice(np.flatnonzero(complete & (keys == eligible[c])), size=PER_DISTRICT, replace=False)
                for c in chosen
            ]
        )
        votes = _votes(survey.y[rows])
        people = rows.size
        district = np.repeat(np.arange(DISTRICTS_PER_CITY), PER_DISTRICT)
        slates = [
            rng.choice(np.flatnonzero(district == d), size=CANDIDATES, replace=False)
            for d in range(DISTRICTS_PER_CITY)
        ]
        others = ~np.eye(people, dtype=bool)
        for j in range(len(ITEMS)):
            train = np.delete(np.arange(len(ITEMS)), j)
            answer = votes[:, j]
            same = answer[:, None] == answer[None, :]
            whole = agreement(votes[:, train])
            topic_cols = train[item_topic[train] == item_topic[j]]
            topic_only = agreement(votes[:, topic_cols])
            pooled = pooled_agreements(votes[:, train], item_topic[train], len(topics)).agreements[
                item_topic[j]
            ]
            picks = {
                "proxy": top_candidates([whole])[0][:, 0],
                "topic": top_candidates([topic_only])[0][:, 0],
                "topic_pooled": top_candidates([pooled])[0][:, 0],
            }
            # The matched pair: three random residents per district
            own = np.empty(people, dtype=np.int64)
            elected = np.empty(people, dtype=np.int64)
            for d, slate in enumerate(slates):
                members = np.flatnonzero(district == d)
                prefs = np.array(
                    [v if v in slate else _preferred(whole.lower, whole.mean, int(v), slate) for v in members]
                )
                own[members] = prefs
                counts = np.array([(prefs == c).sum() for c in slate])
                elected[members] = slate[int(np.argmax(counts))]
            picks["own_of_three"] = own
            picks["representative"] = elected
            voters = np.arange(people)
            result = {"random": (same & others).sum(axis=1) / (people - 1)}
            for method, pick in picks.items():
                result[method] = same[voters, pick].astype(float)
                # A resident who is their own resolver agrees with themself;
                # score only residents represented by someone else
                result[method] = np.where(pick == voters, np.nan, result[method])
            topic_name = topics[item_topic[j]]
            for method in METHODS:
                value = float(np.nanmean(result[method]))
                scores[method].append(value)
                by_topic[method][topic_name].append(value)
    summary = {
        method: {
            "mean_agreement": round(float(np.mean(values)), 4),
            "se_over_city_items": round(float(np.std(values, ddof=1) / np.sqrt(len(values))), 4),
        }
        for method, values in scores.items()
    }
    gaps = {
        "own_of_three_minus_representative": _gap(scores, "own_of_three", "representative"),
        "proxy_minus_own_of_three": _gap(scores, "proxy", "own_of_three"),
        "topic_pooled_minus_proxy": _gap(scores, "topic_pooled", "proxy"),
        "topic_minus_proxy": _gap(scores, "topic", "proxy"),
        "proxy_minus_random": _gap(scores, "proxy", "random"),
    }
    per_topic = {
        t: {method: round(float(np.mean(by_topic[method][t])), 4) for method in METHODS} for t in topics
    }
    return {
        "cities": CITIES,
        "residents_per_city": DISTRICTS_PER_CITY * PER_DISTRICT,
        "held_out_items": len(ITEMS),
        "evidence": "development: real respondents, agreement only (no attendance)",
        "by_method": summary,
        "paired_gaps": gaps,
        "per_topic": per_topic,
    }


def _gap(scores: dict[str, list[float]], a: str, b: str) -> dict[str, float]:
    diff = np.array(scores[a]) - np.array(scores[b])
    return {
        "mean": round(float(diff.mean()), 4),
        "se": round(float(diff.std(ddof=1) / np.sqrt(diff.size)), 4),
    }
