"""
The declared robustness sweeps and the break-even turnout grid (declared
2026-11-18, before any primary city was simulated). Design:
prompts/demo-5-liquid-democracy.md, "Robustness sweeps".

Each sweep point changes one family from the primary settings and runs on
the first SWEEP_CITIES positions of the primary seed sequence, so every
point is paired with the primary configuration on the same cities. Every
point is run under both turnout conditions. Sweeps say where H1 holds; they
are reported as curves with their intervals and are not tested as
hypotheses.

Two populations appear:
  fitted       the primary population, drawn from the CES 2024 fit
               (`beliefs.py`); every family but belief structure
  structural   the one-factor model of `population.py`, with eight
               dimensions standing for the eight topics and its other
               parameters matched to the fitted population, so that cross-
               topic structure is the main thing that differs
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from .arrangements import ORDINARY_RESOLVER_TURNOUT, PRIMARY_TURNOUT, TurnoutPolicy
from .beliefs import BeliefCityConfig
from .population import PopulationConfig
from .protocol import Interval, primary_city_seeds

# Cities per sweep point: positions 1..SWEEP_CITIES of the primary sequence.
# A fixed count, so an ordinary t-interval over them is exact
SWEEP_CITIES: Final = 50
TURNOUT_CONDITIONS: Final = {"primary": PRIMARY_TURNOUT, "ordinary": ORDINARY_RESOLVER_TURNOUT}
TOPICS: Final = 8
# How much heavier the heavy topic is in an uneven agenda: a stated stress
# value, not measured (decided 2026-11-18; Voteview's roll-call files carry
# no topic codes)
HEAVY: Final = 4.0

# The structural population, matched on the same simulated summaries to the
# fitted one (2026-11-18): within-topic median |r| 0.464 against 0.458,
# between-topic 0.379 against 0.379, item support-rate SD 0.232 against
# 0.235, district SD of support 0.065 against 0.067. Noise stands in for the
# fitted model's within-topic spread of questions
STRUCTURAL_BASE: Final = PopulationConfig(
    districts=5,
    residents_per_district=100,
    dimensions=TOPICS,
    factor_loading=0.87**0.5,
    district_lean_sd=0.26,
    history_questions_per_dimension=50,
    evaluation_questions_per_dimension=20,
    cutpoint_sd=1.15,
    preference_noise_sd=1.11,
)
# Cross-topic correlation of positions matching the CES fit on between-
# topic item correlation (0.77 from the fitted topic directions alone)
CES_MATCHED_CORRELATION: Final = 0.87


def _agenda(heavy: int | None, weight: float = HEAVY) -> tuple[float, ...] | None:
    if heavy is None:
        return None
    return tuple(weight if t == heavy else 1.0 for t in range(TOPICS))


@dataclass(frozen=True)
class SweepPoint:
    """One declared point: a family, a label, and how a city is configured."""

    family: str
    label: str
    population: str  # "fitted" or "structural"
    # Fitted-population overrides of BeliefCityConfig
    history_per_topic: int = 50
    districts: int = 5
    within_topic_spread: float = 1.0
    # Uneven agenda: the heavy topic's weight in each period (None: even).
    # The heavy topic rotates with the city's position so each topic is
    # heavy in an eighth of the cities; the evaluation's heavy topic is
    # offset by `evaluation_offset` from the history's
    history_heavy: float | None = None
    evaluation_heavy: float | None = None
    evaluation_offset: int = 0
    # Structural-population structure
    correlation: float = CES_MATCHED_CORRELATION
    blocks: int = 1
    within_block_correlation: float | None = None
    # The turnout condition the point is declared under; both are run
    declared_turnout: str = "both"

    def config(self, position: int) -> BeliefCityConfig | PopulationConfig:
        """The configuration of the city at `position` (1-based) of the sequence."""
        if not 1 <= position <= SWEEP_CITIES:
            raise ValueError(f"position must be in 1..{SWEEP_CITIES}")
        seed = primary_city_seeds(position)[-1]
        if self.population == "structural":
            if self.within_block_correlation is None:
                return replace(STRUCTURAL_BASE, seed=seed, factor_loading=self.correlation**0.5)
            block_part = self.within_block_correlation - self.correlation
            return replace(
                STRUCTURAL_BASE,
                seed=seed,
                factor_loading=self.correlation**0.5,
                blocks=self.blocks,
                block_loading=block_part**0.5,
            )
        heavy = (position - 1) % TOPICS
        history = _agenda(heavy, self.history_heavy) if self.history_heavy else None
        evaluation_topic = (heavy + self.evaluation_offset) % TOPICS
        evaluation = (
            _agenda(evaluation_topic, self.evaluation_heavy) if self.evaluation_heavy else None
        )
        return BeliefCityConfig(
            seed=seed,
            districts=self.districts,
            history_questions_per_topic=self.history_per_topic,
            within_topic_spread=self.within_topic_spread,
            history_topic_weights=history,
            evaluation_topic_weights=evaluation,
        )


PRIMARY_POINT: Final = SweepPoint("primary", "primary settings", "fitted")

SWEEPS: Final = (
    # A4: one Congress is 54 to 90 contested roll calls per topic; 50 primary
    SweepPoint("history", "10 per topic", "fitted", history_per_topic=10),
    SweepPoint("history", "20 per topic", "fitted", history_per_topic=20),
    SweepPoint("history", "100 per topic", "fitted", history_per_topic=100),
    # 100 residents per district throughout: liquid's pool is 199 or 999
    SweepPoint("districts", "2 districts", "fitted", districts=2),
    SweepPoint("districts", "10 districts", "fitted", districts=10),
    # x0.5 and x1.5 move within-topic |r| by about +0.08 and -0.09 around
    # the fitted value (x2 would erase the topic structure)
    SweepPoint("within_topic_spread", "spread x0.5", "fitted", within_topic_spread=0.5),
    SweepPoint("within_topic_spread", "spread x1.5", "fitted", within_topic_spread=1.5),
    # Even history, one heavy topic in evaluation, rotating over cities
    SweepPoint("evaluation_mix", "one topic 2x in evaluation", "fitted", evaluation_heavy=2.0),
    SweepPoint("evaluation_mix", "one topic 4x in evaluation", "fitted", evaluation_heavy=HEAVY),
    # Belief structure on the matched structural population
    SweepPoint("belief_structure", "correlation 0", "structural", correlation=0.0),
    SweepPoint("belief_structure", "correlation 0.4", "structural", correlation=0.4),
    SweepPoint(
        "belief_structure", "correlation 0.87 (CES-matched)", "structural",
        correlation=CES_MATCHED_CORRELATION,
    ),
    SweepPoint("belief_structure", "correlation 0.95", "structural", correlation=0.95),
    SweepPoint(
        "belief_structure", "two blocks of four: 0.87 within, 0.2 across", "structural",
        correlation=0.2, blocks=2, within_block_correlation=CES_MATCHED_CORRELATION,
    ),
    # Sparse records, an uneven agenda (a different heavy topic in each
    # period) and ordinary resolver turnout, together
    SweepPoint(
        "stress", "stress case", "fitted", history_per_topic=10,
        history_heavy=HEAVY, evaluation_heavy=HEAVY, evaluation_offset=4,
        declared_turnout="ordinary",
    ),
)

# Amendment A2: resolver-turnout floors for the break-even curve, run on the
# primary cities with the representative at the office-holder rate. 0 is
# ordinary turnout (residents' own rates run from 0.3 to 0.9), 0.96 the
# primary floor, 1 every resolver always voting
BREAK_EVEN_FLOORS: Final = (0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.96, 1.0)


def break_even_policy(floor: float) -> TurnoutPolicy:
    return TurnoutPolicy(office_rate=PRIMARY_TURNOUT.office_rate, resolver_turnout=floor)


@dataclass(frozen=True)
class BreakEven:
    """
    Where liquid's fidelity reaches the representative's as the resolver
    floor rises. Raising the floor only adds ballots, so the difference
    never falls and crosses zero at most once.
    """

    # "crosses", "liquid ahead throughout" or "no crossing in the tested range"
    status: str
    # The interpolated floor at which the mean difference reaches zero
    estimate: float | None
    # Floors whose 95% interval of the difference includes zero
    uncertain_floors: tuple[float, ...]


def break_even(floors: tuple[float, ...], intervals: tuple[Interval, ...]) -> BreakEven:
    """
    The break-even floor by linear interpolation of the mean paired
    difference (liquid minus representative) between grid floors.
    """
    if len(floors) != len(intervals) or len(floors) < 2:
        raise ValueError("one interval per floor, at least two floors")
    if any(b <= a for a, b in zip(floors, floors[1:])):
        raise ValueError("floors must increase")
    means = [i.estimate for i in intervals]
    uncertain = tuple(f for f, i in zip(floors, intervals) if i.lower <= 0.0 <= i.upper)
    if means[0] >= 0.0:
        return BreakEven("liquid ahead throughout", None, uncertain)
    for k in range(1, len(floors)):
        if means[k] >= 0.0:
            low, high = means[k - 1], means[k]
            at = floors[k - 1] + (floors[k] - floors[k - 1]) * (-low) / (high - low)
            return BreakEven("crosses", float(at), uncertain)
    return BreakEven("no crossing in the tested range", None, uncertain)
