#!/usr/bin/env python3
"""Precompute the liquid walkthrough's illustrative city with the frozen code.

The walkthrough (prompts/demo-5-walkthrough.md) draws one city of 500
residents as dots. This is a real city of the frozen benchmark: primary
position 1, recomputed at every turnout level with the frozen arrangements
(`delegation.comparison.compare`), exactly as the benchmark ran it. Nothing
here is fitted or tuned for the page.

It writes public/data/liquid-story/city.json:

- the city's design, read from its configuration and population;
- every resident's district, and their own turnout rate at each level;
- one featured question, chosen by a fixed rule (below), and for each level
  and arrangement every resident's ballot on it: whose it was and whether
  it matched them;
- each arrangement's totals over all 80,000 voter-question pairs per level;
- the mechanism the page animates, at Swiss turnout: one resident's
  candidates for one topic, a short and an empty record, a ballot routed by
  topic, a chain, a loop, a lost vote and the calibration curve.

The featured question is the evaluation question whose match, contrary and
no-ballot shares, under direct voting, the representative and liquid at
Swiss turnout, lie closest to the city's shares over all questions (sum of
absolute differences; ties to the earlier question). The same question is
shown at every level.

Usage:
    python scripts/build_liquid_example_city.py          # write city.json
    python scripts/build_liquid_example_city.py --check  # recompute; compare with the committed file

Where the frozen benchmark's city records are present locally
(eval/benchmarks/delegation_frontier_v1/primary_cities.jsonl.gz), both
modes first check this city's recomputed totals and acceptance levels
against the recorded city. Takes about three minutes.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from delegation.comparison import Comparison, compare, runner  # noqa: E402
from delegation.comparison.arrangements import (  # noqa: E402
    DIAL_TURNOUT,
    _liquid_agreements,
    choose_liquid,
    history_overhead,
    population_tie_key,
    resolve_with_loops,
)
from delegation.comparison.beliefs import BeliefCityConfig  # noqa: E402
from delegation.comparison.choice import KEEP, ChoicePolicy, top_candidates  # noqa: E402
from delegation.comparison.population import NOT_CAST, Population  # noqa: E402
from delegation.comparison.protocol import SWISS_MARKER, TURNOUT_GRID  # noqa: E402
from delegation.comparison.runner import CAP  # noqa: E402
from delegation.comparison.sweeps import PRIMARY_POINT  # noqa: E402


CITY_VERSION: Final = 1
POSITION: Final = 1
OUT: Final = ROOT / "public" / "data" / "liquid-story" / "city.json"
RECORDED: Final = ROOT / "eval" / "benchmarks" / "delegation_frontier_v1" / "primary_cities.jsonl.gz"
RECORDED_POINT: Final = "primary: primary settings"
# The arrangements the page shows, in its order
ARRANGEMENTS: Final = ("full_turnout", "direct", "representative", "proxy", "liquid")
# Arrangements whose shares pick the featured question
FEATURE_BY: Final = ("direct", "representative", "liquid")
# Candidates listed for the showcase resident's topic
CANDIDATES_SHOWN: Final = 5
# Acceptance levels at which the calibration curve is drawn, besides the chosen one
# (every 0.05 from 0 to 0.9, and every 0.01 where the curve turns)
CURVE_LEVELS: Final = tuple(sorted({round(0.05 * i, 2) for i in range(19)} | {round(0.01 * i, 2) for i in range(55, 66)}))

# One character per resident: whose ballot counted and how it compared.
# Own ballot: M (cast, so it matches) or N (not cast). Someone else's: m
# (matched), c (contrary) or n (not cast).
OWN_MATCH, OWN_NONE, OTHER_MATCH, OTHER_CONTRARY, OTHER_NONE = "M", "N", "m", "c", "n"


class CityError(RuntimeError):
    """The recomputed city disagrees with the frozen record or its own invariants."""


# ---------------------------------------------------------------------------
# One level
# ---------------------------------------------------------------------------


def _level(level: float) -> tuple[Population, Comparison]:
    config = PRIMARY_POINT.config(POSITION, level)
    population = runner._population(config)
    return population, compare(population, DIAL_TURNOUT, CAP)


def _codes(population: Population, result: Comparison, name: str, question: int) -> str:
    outcome = result.outcomes[name]
    sincere = population.evaluation.sincere[:, question]
    counted = outcome.counted[:, question]
    resolver = outcome.resolver[:, question]
    codes = []
    for voter in range(population.size):
        own = int(resolver[voter]) == voter
        if counted[voter] == NOT_CAST:
            codes.append(OWN_NONE if own else OTHER_NONE)
        elif counted[voter] == sincere[voter]:
            codes.append(OWN_MATCH if own else OTHER_MATCH)
        elif own:
            raise CityError(f"{name}: voter {voter}'s own ballot contradicts them")
        else:
            codes.append(OTHER_CONTRARY)
    return "".join(codes)


def _totals(population: Population, result: Comparison, name: str) -> dict[str, Any]:
    outcome = result.outcomes[name]
    sincere = population.evaluation.sincere
    none = int((outcome.counted == NOT_CAST).sum())
    match = int((outcome.counted == sincere).sum())
    measures = result.measures[name]
    return {
        "match": match,
        "contrary": int(sincere.size) - match - none,
        "none": none,
        "fidelity": measures.fidelity,
        "overhead": measures.overhead,
    }


def _feature(population: Population, result: Comparison) -> int:
    """The evaluation question whose shares lie closest to the city's (see the module docstring)."""
    sincere = population.evaluation.sincere
    distance = np.zeros(sincere.shape[1])
    for name in FEATURE_BY:
        counted = result.outcomes[name].counted
        match_q = (counted == sincere).mean(axis=0)
        none_q = (counted == NOT_CAST).mean(axis=0)
        contrary_q = 1.0 - match_q - none_q
        match, none = (counted == sincere).mean(), (counted == NOT_CAST).mean()
        contrary = 1.0 - match - none
        distance += np.abs(match_q - match) + np.abs(none_q - none) + np.abs(contrary_q - contrary)
    return int(np.argmin(distance))


# ---------------------------------------------------------------------------
# The mechanism at Swiss turnout
# ---------------------------------------------------------------------------


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _mechanism(population: Population, result: Comparison, question: int) -> dict[str, Any]:
    acceptance = result.liquid_acceptance.acceptance
    policy = replace(ChoicePolicy(), acceptance=acceptance)
    agreements = _liquid_agreements(population, ChoicePolicy())
    tie = population_tie_key(population)
    top, best = top_candidates(agreements, tie)
    choice = choose_liquid(population, policy)
    liquid = result.outcomes["liquid"]
    dimension = population.evaluation.dimension
    history = population.history

    # The chosen delegations must give the frozen outcome's resolvers
    for k in range(len(population.categories)):
        resolver, _, _ = resolve_with_loops(choice.delegate[:, k])
        columns = np.flatnonzero(dimension == k)
        if not (liquid.resolver[:, columns] == resolver[:, None]).all():
            raise CityError(f"topic {k}: the recomputed delegations do not give the frozen resolvers")

    record = np.stack(
        [(history.own_votes[:, history.on_dimension(k)] != NOT_CAST).sum(axis=1)
         for k in range(len(population.categories))],
        axis=1,
    )
    held = choice.delegate != KEEP

    def candidates(voter: int, topic: int, count: int) -> list[dict[str, Any]]:
        a = agreements[topic]
        return [
            {
                "person": int(c),
                "district": int(population.district[c]),
                "matches": int(a.matches[voter, c]),
                "trials": int(a.trials[voter, c]),
                "mean": _round(a.mean[voter, c]),
                "lower": _round(a.lower[voter, c]),
            }
            for c in a.ranking(voter, tie)[:count]
        ]

    # Showcase: the first resident (by index) who hands over some topics but
    # not all (so their ballot shows both), has at least 20 ballots in their
    # best delegated topic, and whose delegate there lives in another
    # district. Most residents hand over every topic; `handed_over` says how
    # many hand over each number of topics.
    topics = len(population.categories)
    showcase = None
    for voter in range(population.size):
        if not topics // 2 < held[voter].sum() < topics:
            continue
        delegated = [k for k in range(topics) if held[voter, k]]
        topic = max(delegated, key=lambda k: (best[voter, k], -k))
        delegate = int(choice.delegate[voter, topic])
        if record[voter, topic] >= 20 and population.district[delegate] != population.district[voter]:
            showcase = (voter, topic)
            break
    if showcase is None:
        raise CityError("no resident meets the showcase rule")
    voter, topic = showcase

    # Short record: of the residents with any ballot, the one with the fewest
    # (ties to the lower index) whose best candidate in the showcase topic
    # falls short of the acceptance level
    total = record.sum(axis=1)
    short = next(
        (
            v
            for v in sorted(range(population.size), key=lambda v: (total[v], v))
            if total[v] > 0 and np.isfinite(best[v, topic]) and best[v, topic] < acceptance
        ),
        None,
    )
    if short is None:
        raise CityError("no resident meets the short-record rule")
    empty = np.flatnonzero(total == 0)

    # A ballot: the first question of each of the showcase resident's first
    # kept topic and first two delegated topics, in topic order
    kept_topics = [k for k in range(topics) if not held[voter, k]]
    delegated_topics = [k for k in range(topics) if held[voter, k]]
    ballot = []
    for k in sorted(kept_topics[:1] + delegated_topics[:2]):
        q = int(np.flatnonzero(dimension == k)[0])
        ballot.append(
            {
                "question": q,
                "topic": k,
                "resolver": int(liquid.resolver[voter, q]),
                "code": _codes(population, result, "liquid", q)[voter],
            }
        )

    # A chain: the longest path from a resident to whoever decides for them
    # (first by topic, then by index), ending at someone who keeps the topic
    # or at a loop member; and a loop: the first mutual pair. Also how many
    # handed-over (resident, topic) pairs end with a loop member.
    chain: dict[str, Any] | None = None
    loop: dict[str, Any] | None = None
    loops_per_topic = []
    handed = ends_on_loop = 0
    for k in range(topics):
        delegate_of = choice.delegate[:, k]
        resolver, on_loop, loops = resolve_with_loops(delegate_of)
        loops_per_topic.append(int(loops))
        delegating = delegate_of != KEEP
        handed += int(delegating.sum())
        ends_on_loop += int((delegating & on_loop[resolver] & (resolver != np.arange(population.size))).sum())
        for start in range(population.size):
            path = [start]
            while path[-1] != resolver[start]:
                path.append(int(delegate_of[path[-1]]))
            if chain is None or len(path) > len(chain["path"]):
                end = path[-1]
                # The loop the chain ends on, from its end round to it again
                cycle = []
                if on_loop[end]:
                    cycle = [end]
                    while int(delegate_of[cycle[-1]]) != end:
                        cycle.append(int(delegate_of[cycle[-1]]))
                chain = {"topic": k, "path": path, "ends": "loop" if on_loop[end] else "keeps", "cycle": cycle}
            if loop is None and on_loop[start]:
                partner = int(delegate_of[start])
                if int(delegate_of[partner]) == start:
                    loop = {"topic": k, "members": [start, partner]}
    if chain is None or loop is None:
        raise CityError("no chain or no mutual loop in the city")

    # A typical resident, for one person's ballots: of those who hand over
    # every topic, the one whose own turnout rate is closest to the city's
    # mean rate (ties to the lower index)
    everything = np.flatnonzero(held.sum(axis=1) == topics)
    mean_rate = float(population.turnout.mean())
    typical = int(min(everything, key=lambda v: (abs(population.turnout[v] - mean_rate), v)))

    # A lost vote on the featured question: the first resident whose
    # resolver is someone else and cast nothing
    codes = _codes(population, result, "liquid", question)
    lost_voter = codes.find(OTHER_NONE)
    lost = None if lost_voter < 0 else {
        "voter": lost_voter,
        "resolver": int(liquid.resolver[lost_voter, question]),
        "question": question,
    }

    curve_levels = sorted({*CURVE_LEVELS, _round(acceptance)})
    curve = [
        {"acceptance": a, "overhead": _round(history_overhead(population, replace(ChoicePolicy(), acceptance=a)))}
        for a in curve_levels
    ]
    return {
        "level": SWISS_MARKER,
        "acceptance": _round(acceptance),
        "history_overhead": _round(result.liquid_acceptance.history_overhead),
        "cap": CAP,
        "credible_mass": ChoicePolicy().credible_mass,
        "showcase": {
            "voter": voter,
            "topic": topic,
            "record": int(record[voter, topic]),
            "candidates": candidates(voter, topic, CANDIDATES_SHOWN),
            "delegates": [int(d) for d in choice.delegate[voter]],
            "resolvers": [int(liquid.resolver[voter, np.flatnonzero(dimension == k)[0]])
                          for k in range(len(population.categories))],
        },
        # How many residents hand over 0, 1, ... every topic
        "handed_over": [int(n) for n in np.bincount(held.sum(axis=1), minlength=topics + 1)],
        "short_record": {
            "voter": int(short),
            "topic": topic,
            "record": int(record[short, topic]),
            "total_record": int(total[short]),
            "candidates": candidates(int(short), topic, 1),
        },
        "empty_records": {"count": int(empty.size), "example": int(empty[0]) if empty.size else None},
        "ballot": ballot,
        "chain": chain,
        "loop": loop,
        "loops_per_topic": loops_per_topic,
        "handed_pairs": handed,
        "handed_pairs_ending_on_loop": ends_on_loop,
        "typical": {
            "voter": typical,
            "turnout": _round(population.turnout[typical], 3),
            # Their ballot on every evaluation question, in question order,
            # under direct voting, the representative and liquid
            "questions": [int(k) for k in dimension],
            "strips": {name: "".join(_codes(population, result, name, q)[typical] for q in range(dimension.size))
                       for name in ("direct", "representative", "liquid")},
        },
        "lost": lost,
        "calibration": curve,
    }


# ---------------------------------------------------------------------------
# The city
# ---------------------------------------------------------------------------


def build() -> dict[str, Any]:
    by_level = {level: _level(level) for level in TURNOUT_GRID}
    swiss_population, swiss = by_level[SWISS_MARKER]
    question = _feature(swiss_population, swiss)
    config = PRIMARY_POINT.config(POSITION, SWISS_MARKER)
    if not isinstance(config, BeliefCityConfig):
        raise CityError("the primary point is no longer the fitted belief city")

    representative = swiss.outcomes["representative"].resolver
    if not (representative == representative[:, :1]).all():
        raise CityError("a voter's representative changes between questions")
    representatives = [int(representative[swiss_population.residents_of(d)[0], 0])
                       for d in range(config.districts)]

    # Within each district, residents in order of their own turnout rate
    # (highest first); the rate's order is the same at every level
    order = sorted(range(swiss_population.size),
                   key=lambda v: (int(swiss_population.district[v]), -swiss_population.turnout[v], v))

    levels = {}
    for level, (population, result) in by_level.items():
        if population.ids != swiss_population.ids or not (population.district == swiss_population.district).all():
            raise CityError(f"the residents differ at {level}")
        levels[repr(level)] = {
            "acceptance": _round(result.liquid_acceptance.acceptance),
            "meets_cap": bool(result.liquid_acceptance.feasible),
            "codes": {name: _codes(population, result, name, question) for name in ARRANGEMENTS},
            "liquid_resolver": [int(r) for r in result.outcomes["liquid"].resolver[:, question]],
            "totals": {name: _totals(population, result, name) for name in ARRANGEMENTS},
        }

    return {
        "city_version": CITY_VERSION,
        "generator": "scripts/build_liquid_example_city.py",
        "benchmark": "eval/benchmarks/delegation_frontier_v1",
        "position": POSITION,
        "seed": config.seed,
        "design": {
            "residents": swiss_population.size,
            "districts": config.districts,
            "residents_per_district": config.residents_per_district,
            "candidates_per_district": config.candidates_per_district,
            "topics": len(swiss_population.categories),
            "history_per_topic": config.history_questions_per_topic,
            "evaluation_per_topic": config.evaluation_questions_per_topic,
            "turnout_logit_sd": config.turnout_logit_sd,
            "office_rate": DIAL_TURNOUT.office_rate,
            "cap": CAP,
        },
        "topics": list(swiss_population.categories),
        "district_names": list(swiss_population.district_names),
        "district": [int(d) for d in swiss_population.district],
        "representatives": representatives,
        "order": order,
        # Each resident's own turnout rate per level, in thousandths
        "turnout": {repr(level): [int(round(1000 * t)) for t in population.turnout]
                    for level, (population, _) in by_level.items()},
        "question": {
            "index": question,
            "id": swiss_population.evaluation.ids[question],
            "topic": int(swiss_population.evaluation.dimension[question]),
        },
        "levels": levels,
        "mechanism": _mechanism(swiss_population, swiss, question),
    }


def check_recorded(city: dict[str, Any]) -> bool:
    """Compare totals and acceptance levels with the recorded city; False when the records are absent."""
    if not RECORDED.exists():
        return False
    with gzip.open(RECORDED, "rt", encoding="utf-8") as handle:
        recorded = next(
            (row for row in map(json.loads, handle)
             if row["point"] == RECORDED_POINT and row["position"] == POSITION),
            None,
        )
    if recorded is None:
        raise CityError(f"position {POSITION} is not in the city records")
    for level, values in city["levels"].items():
        reading = recorded["levels"][level]
        if values["acceptance"] != _round(reading["liquid_acceptance"]["acceptance"]):
            raise CityError(f"{level}: acceptance differs from the recorded city")
        for name in ARRANGEMENTS:
            totals = values["totals"][name]
            if totals["match"] != reading["matches"][name]:
                raise CityError(f"{level} {name}: matches differ from the recorded city")
            for key in ("fidelity", "overhead"):
                if totals[key] != reading["measures"][name][key]:
                    raise CityError(f"{level} {name}: {key} differs from the recorded city")
    return True


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="recompute and compare with the committed file")
    args = parser.parse_args(argv)
    city = build()
    print("checked against the recorded city" if check_recorded(city) else
          "the recorded city is not present; its check was skipped")
    body = dumps(city).encode("utf-8")
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != body:
            print(f"{OUT} differs from a fresh build")
            return 1
        print(f"{OUT.name} rebuilds byte for byte ({hashlib.sha256(body).hexdigest()[:12]})")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Bytes, not text mode: Windows text mode would write CRLF
    OUT.write_bytes(body)
    print(f"wrote {OUT} ({len(body) / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
