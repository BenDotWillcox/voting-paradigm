"""
Liquid's handover curve: an exploratory analysis made after the freeze
(declared 2026-11-19 in prompts/demo-5-liquid-democracy.md, "Exploratory
analyses after the freeze"). It changes no frozen reading.

Each voter hands over topics one at a time, best first: in the order of
their top candidate's lower bound, to that candidate. At depth d every voter
hands over their d best topics (fewer when they have fewer candidates, and
none with an empty record). Depth 0 is direct voting; depth 8 is liquid with
no acceptance level. Every depth is the frozen `liquid` arrangement under
`ChoicePolicy(max_categories=d)`, whose `choose` already takes a voter's
categories best first, so the curve uses the frozen choice, routing, loop
rule, turnout draws and measures unchanged. Delegates vote at their own rate
(DIAL_TURNOUT), as in the benchmark.

The frozen benchmark holds only the calibrated arrangement (the acceptance
level that keeps history overhead at or under 10%), so it has one point on
the overhead-fidelity plane per level. This traces the curve between direct
voting and full delegation that the design called for.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Final

from .arrangements import DIAL_TURNOUT, direct, full_turnout, liquid
from .choice import ChoicePolicy
from .measures import measure
from .population import Population

# 1: the declared analysis (2026-11-19)
HANDOVER_VERSION: Final = 1


def depths(population: Population) -> range:
    """Every handover depth: none to every category."""
    return range(len(population.categories) + 1)


def handover_policy(depth: int) -> ChoicePolicy:
    """The frozen choice policy at one depth: no acceptance level, best `depth` categories."""
    return ChoicePolicy(max_categories=depth)


def handover_level(population: Population) -> dict[str, Any]:
    """
    Liquid at every handover depth in one city at one turnout level: each
    depth's measures, and its matching ballots over the evaluation pairs.
    Direct voting is recorded beside depth 0, which must reproduce it.
    """
    reference = full_turnout(population)
    sincere = population.evaluation.sincere
    record: dict[str, Any] = {"pairs": int(sincere.size), "depths": {}}
    for depth in depths(population):
        outcome = liquid(population, handover_policy(depth), DIAL_TURNOUT)
        record["depths"][str(depth)] = {
            "matches": int((outcome.counted == sincere).sum()),
            "measures": asdict(measure(population, outcome, reference)),
        }
    plain = direct(population)
    record["direct_matches"] = int((plain.counted == sincere).sum())
    return record
