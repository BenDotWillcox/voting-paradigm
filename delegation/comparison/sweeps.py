"""
The declared robustness sweeps and the frontier grid (declared 2026-11-18,
before any primary city was simulated; restated for the threshold H1 under
amendment A6). Design: prompts/demo-5-liquid-democracy.md, "Robustness
sweeps".

H1 is a threshold on the turnout dial, so every sweep point is run across
the whole dial (protocol.TURNOUT_GRID) and reports how the threshold moves.
Turnout follows the dial for everyone, delegates included (they vote at
their own rate); the representative votes at the measured office-holder
rate. Each point changes one family from the primary settings and runs on
the first SWEEP_CITIES positions of the primary seed sequence, so each point
is indexed by the same positions as the primary configuration. What that
pairing holds fixed depends on the family (second sweep review,
2026-11-18):
  - a history point keeps the same residents and evaluation questions;
  - a spread, agenda-mix, stress or turnout-spread point keeps the same
    residents' positions and draws new questions or turnout rates;
  - a district-count point draws different districts, so it compares
    generated cities, not one geography;
  - the structural population is a different generator, so its points are
    compared with its own 0.87 point.
The arrangement contrasts inside each city are always paired, and every
city's curve keeps its residents across the dial. Sweeps say where H1
holds; they are reported as curves with their intervals and are not tested
as hypotheses.

Two populations appear:
  fitted       the primary population, drawn from the CES 2024 fit
               (`beliefs.py`); every family but belief structure
  structural   the one-factor model of `population.py`, with eight
               dimensions standing for the eight topics and its other
               parameters matched to the fitted population, so that cross-
               topic structure is the main thing that differs

The frontier (the study's main figure) is computed on the primary cities
only: at every level of the dial, the delegate attendance floor at which
liquid matches the representative.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

import numpy as np
import numpy.typing as npt

from .arrangements import DIAL_TURNOUT as _DIAL_TURNOUT
from .arrangements import TurnoutPolicy
from .beliefs import BeliefCityConfig
from .population import TURNOUT_LOGIT_SD, PopulationConfig
from .protocol import MAX_CITIES, TURNOUT_GRID, Interval, primary_city_seeds

# Cities per sweep point: positions 1..SWEEP_CITIES of the primary sequence,
# six complete rotations of the eight topics, so a rotating heavy topic is
# heavy in exactly 6 cities each and the plain city mean weights topics
# equally. A fixed count removes optional stopping; the t-interval's
# coverage is still approximate (normal theory), and for rotating points it
# ignores the design's stratification, which makes it conservative
SWEEP_CITIES: Final = 48
# The policy every point of the dial is run under: delegates at their own
# rate, the representative at the office-holder rate (amendment A6)
DIAL_TURNOUT: Final = _DIAL_TURNOUT
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
    turnout_logit_sd=TURNOUT_LOGIT_SD,
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
    # Spread of engagement on the logit scale (both populations)
    turnout_logit_sd: float = TURNOUT_LOGIT_SD
    # Questions per shared attendance draw (1: every question its own)
    attendance_cluster: int = 1
    # Structural-population structure
    correlation: float = CES_MATCHED_CORRELATION
    blocks: int = 1
    within_block_correlation: float | None = None

    def config(self, position: int, turnout: float) -> BeliefCityConfig | PopulationConfig:
        """
        The configuration of the city at `position` (1-based) of the
        sequence, at mean turnout `turnout` on the dial.
        """
        limit = MAX_CITIES if self.family == "primary" else SWEEP_CITIES
        if not 1 <= position <= limit:
            raise ValueError(f"position must be in 1..{limit}")
        seed = primary_city_seeds(position)[-1]
        if self.population == "structural":
            base = replace(
                STRUCTURAL_BASE,
                seed=seed,
                factor_loading=self.correlation**0.5,
                turnout_mean=turnout,
                turnout_logit_sd=self.turnout_logit_sd,
                attendance_cluster=self.attendance_cluster,
            )
            if self.within_block_correlation is None:
                return base
            block_part = self.within_block_correlation - self.correlation
            return replace(base, blocks=self.blocks, block_loading=block_part**0.5)
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
            turnout_mean=turnout,
            turnout_logit_sd=self.turnout_logit_sd,
            attendance_cluster=self.attendance_cluster,
        )

    @property
    def rotates(self) -> bool:
        """Whether a heavy topic rotates with city position."""
        return bool(self.history_heavy or self.evaluation_heavy)

    def strata(self, positions: npt.ArrayLike) -> npt.NDArray[np.int64] | None:
        """
        The bootstrap strata for cities at `positions`: one per heavy topic at
        a rotating point (six cities each over 48 positions), so resampling
        keeps the balanced design (third A6 review); None elsewhere.
        """
        if not self.rotates:
            return None
        return np.asarray((np.asarray(positions) - 1) % TOPICS, dtype=np.int64)


PRIMARY_POINT: Final = SweepPoint("primary", "primary settings", "fitted")

SWEEPS: Final = (
    # A4: one Congress is 54 to 90 contested roll calls per topic; 50 primary
    SweepPoint("history", "10 per topic", "fitted", history_per_topic=10),
    SweepPoint("history", "20 per topic", "fitted", history_per_topic=20),
    SweepPoint("history", "100 per topic", "fitted", history_per_topic=100),
    # 100 residents per district throughout: liquid's pool is 199 or 999
    SweepPoint("districts", "2 districts", "fitted", districts=2),
    SweepPoint("districts", "10 districts", "fitted", districts=10),
    # A declared sensitivity range, half to one and a half times the fitted
    # spread; it is not derived from a diagnostic. (Equal-weight median |r|
    # within / between topics, W + T covariance: x0.5 0.538 / 0.422, x1
    # 0.449 / 0.353, x1.5 0.382 / 0.321.)
    SweepPoint("within_topic_spread", "spread x0.5", "fitted", within_topic_spread=0.5),
    SweepPoint("within_topic_spread", "spread x1.5", "fitted", within_topic_spread=1.5),
    # Even history, one heavy topic in evaluation, rotating over cities
    SweepPoint("evaluation_mix", "one topic 2x in evaluation", "fitted", evaluation_heavy=2.0),
    SweepPoint("evaluation_mix", "one topic 4x in evaluation", "fitted", evaluation_heavy=HEAVY),
    # Spread of engagement (amendment A6). The primary 2.81 is calibrated to
    # Geneva's ten-ballot table (20.2% never, 15.9% always at mean 0.493;
    # the model gives 18.6% and 17.6%). 2.07 fits only the never-voter figure
    # of a 20-ballot report; 3.5 is a more polarized electorate, as on online
    # platforms where activity is power-law distributed; 1.0 is a fairly
    # even electorate in which nearly everyone votes sometimes
    SweepPoint("turnout_spread", "engagement spread 1.0", "fitted", turnout_logit_sd=1.0),
    SweepPoint("turnout_spread", "engagement spread 2.07", "fitted", turnout_logit_sd=2.07),
    SweepPoint("turnout_spread", "engagement spread 3.5", "fitted", turnout_logit_sd=3.5),
    # Attendance shared by groups of three questions, like a Swiss ballot
    # day of about 2.8 measures: the register counts ballot days, the model
    # questions, so this tests that transfer (third A6 review)
    SweepPoint("attendance", "ballot days of three questions", "fitted", attendance_cluster=3),
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
    # Sparse records and an uneven agenda (a different heavy topic in each
    # period), together; delegates at their own rate, as everywhere on the dial
    SweepPoint(
        "stress", "stress case", "fitted", history_per_topic=10,
        history_heavy=HEAVY, evaluation_heavy=HEAVY, evaluation_offset=4,
    ),
)

# The frontier (amendment A6, replacing the single break-even of A2): at
# every level of the dial, resolver-turnout floors from 0 (delegates at their
# own rate, the dial's condition) up to 1, with the representative at the
# office-holder rate. Own rates now run down to about 0, so every floor
# changes some ballots and the grid starts at 0
FRONTIER_FLOORS: Final = (0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.96, 1.0)
FRONTIER_LEVELS: Final = TURNOUT_GRID


def break_even_policy(floor: float) -> TurnoutPolicy:
    return TurnoutPolicy(office_rate=DIAL_TURNOUT.office_rate, resolver_turnout=floor)


@dataclass(frozen=True)
class BreakEven:
    """
    Where liquid's fidelity reaches the representative's as the resolver
    floor rises, at one level of the dial. Raising the floor only adds
    ballots, so the difference never falls and crosses zero at most once.

    It reports the grid bracket and the pointwise intervals, not an interval
    for the crossing itself (second sweep review, 2026-11-18): an interval
    at each floor says whether the difference there could be zero, which is
    a different question from where the crossing lies.
    """

    # "liquid ahead throughout" (strictly ahead at the lowest floor),
    # "equal at the lowest floor", "crosses" or "no crossing in the tested
    # range"
    status: str
    # The grid floors between which the mean difference first reaches zero
    # (both the lowest floor when equal there)
    bracket: tuple[float, float] | None
    # Linear interpolation inside the bracket: a grid approximation
    interpolated: float | None
    # The 95% interval of the difference at every floor, in grid order
    pointwise: tuple[Interval, ...]


def break_even(floors: tuple[float, ...], intervals: tuple[Interval, ...]) -> BreakEven:
    """
    The break-even bracket on the grid, and a linear interpolation inside
    it, from the mean paired difference (liquid minus representative).
    """
    if len(floors) != len(intervals) or len(floors) < 2:
        raise ValueError("one interval per floor, at least two floors")
    if any(b <= a for a, b in zip(floors, floors[1:])):
        raise ValueError("floors must increase")
    means = [i.estimate for i in intervals]
    if means[0] > 0.0:
        return BreakEven("liquid ahead throughout", None, None, intervals)
    if means[0] == 0.0:
        return BreakEven("equal at the lowest floor", (floors[0], floors[0]), floors[0], intervals)
    for k in range(1, len(floors)):
        if means[k] >= 0.0:
            low, high = means[k - 1], means[k]
            at = floors[k - 1] + (floors[k] - floors[k - 1]) * (-low) / (high - low)
            return BreakEven("crosses", (floors[k - 1], floors[k]), float(at), intervals)
    return BreakEven("no crossing in the tested range", None, None, intervals)
