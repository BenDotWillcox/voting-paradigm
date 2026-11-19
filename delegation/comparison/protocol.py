"""
The research protocol's fixed rules as code, so a second person can replay
the primary run and read its verdicts the same way (third review,
2026-11-18). Design: prompts/demo-5-liquid-democracy.md, "Research
protocol".

  Seeds      Primary cities come from their own namespace: the city at
             position i (1, 2, ...) has seed PRIMARY_SEED_BASE + i. No
             development seed (pilot cities 1-3, diagnostic cities 4-5,
             config defaults, test fixtures) lies in that range, so "the
             first 20" and "21 to N" are positions in this sequence, never
             reused development IDs.
  Estimand   H1 is a threshold (amendment A6, 2026-11-18): the mean
             citizen turnout on the dial above which liquid's fidelity
             stays at or above the representative's. It is read from the
             paired difference curve over TURNOUT_GRID on PRIMARY_CITIES
             cities, with a city-bootstrap interval.
  Count      A fixed PRIMARY_CITIES, so nothing stops on the data. (Stein's
             two-stage rule, declared for the earlier single-difference H1,
             is withdrawn with it.)
  Verdicts   The threshold's status and overhead gate, and, at any one
             level of the dial, the direction and size labels and the
             specialisation categories, exactly as declared.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from scipy.stats import t as student_t

PRIMARY_SEED_BASE: Final = 1_000_000_000
MAX_CITIES: Final = 200
# Every primary city is run at every level of the dial
PRIMARY_CITIES: Final = MAX_CITIES
CONFIDENCE: Final = 0.95
# The turnout dial's levels (mean own turnout rate). 0.45, the Swiss mean
# per federal vote, is the reference marker, not an assumption
TURNOUT_GRID: Final = (0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9)
SWISS_MARKER: Final = 0.45
BOOTSTRAP_RESAMPLES: Final = 2000
BOOTSTRAP_SEED: Final = 20261118
# The share of cities that must meet the overhead cap before a claim made
# at that overhead is assessed
FEASIBLE_SHARE: Final = 0.95
DELTA: Final = 0.02

# Every city seed used in development, for the disjointness check
DEVELOPMENT_SEEDS: Final = frozenset({1, 2, 3, 4, 5, 20261114, 20261116})


def primary_city_seeds(count: int) -> list[int]:
    """The seeds of the first `count` primary cities, in order."""
    if not 0 < count <= MAX_CITIES:
        raise ValueError(f"count must be in 1..{MAX_CITIES}")
    return [PRIMARY_SEED_BASE + position for position in range(1, count + 1)]


def _t(df: int) -> float:
    return float(student_t.ppf(0.5 + CONFIDENCE / 2.0, df))


@dataclass(frozen=True)
class Interval:
    estimate: float
    lower: float
    upper: float

    @property
    def half_width(self) -> float:
        return (self.upper - self.lower) / 2.0


def t_interval(values: npt.ArrayLike) -> Interval:
    """
    An ordinary 95% t-interval over cities. The count is fixed in advance,
    so nothing stops on the data; coverage is approximate (normal theory).
    """
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size < 2:
        raise ValueError("need at least two cities")
    mean = float(data.mean())
    half = _t(data.size - 1) * float(data.std(ddof=1)) / math.sqrt(data.size)
    return Interval(mean, mean - half, mean + half)


def direction(interval: Interval) -> str:
    """'positive', 'negative' or 'inconclusive' (the interval includes zero)."""
    if interval.lower > 0.0:
        return "positive"
    if interval.upper < 0.0:
        return "negative"
    return "inconclusive"


H1_VERDICTS: Final = {
    "positive": "supported",
    "negative": "evidence against H1 in the modelled population",
    "inconclusive": "inconclusive about the sign",
}


def h1_verdict(all_cities: Interval, meeting_cap: Interval, share_meeting_cap: float) -> str:
    """
    The H1 direction verdict. Assessed only if at least FEASIBLE_SHARE of
    cities meet the cap; a direction stands only when the all-city interval
    and the interval over cities meeting the cap agree. Any disagreement,
    including opposite signs, is inconclusive.
    """
    if share_meeting_cap < FEASIBLE_SHARE:
        return "overhead condition not met"
    first, second = direction(all_cities), direction(meeting_cap)
    if first != second:
        return H1_VERDICTS["inconclusive"]
    return H1_VERDICTS[first]


def h1_size(interval: Interval) -> str:
    """
    Practical size of one interval against delta, reported separately from
    direction. A gain of at least delta is established when the lower end
    reaches it and ruled out when the upper end is below it; an interval
    that still contains delta (an upper end exactly at delta included)
    leaves the size unresolved, labelled by which side the estimate falls.
    """
    if interval.lower >= DELTA:
        return "gain of at least delta established"
    if interval.upper < DELTA:
        return "gain below delta established"
    if interval.estimate >= DELTA:
        return "estimate at least delta, size unresolved"
    return "estimate below delta, size unresolved"


def h1_size_verdict(all_cities: Interval, meeting_cap: Interval, share_meeting_cap: float) -> str:
    """
    The size verdict for a claim at low overhead. Both intervals are
    reported with their own `h1_size` label; a size category is the
    verdict only when the two agree, so cities over the cap can never carry
    a claim of that size on their own (fourth review, 2026-11-18).
    """
    if share_meeting_cap < FEASIBLE_SHARE:
        return "overhead condition not met"
    first, second = h1_size(all_cities), h1_size(meeting_cap)
    return first if first == second else "size unresolved"


def specialisation_size(interval: Interval) -> str:
    """Practical size of liquid minus proxy against Delta, for one interval."""
    if interval.lower >= DELTA:
        return "worthwhile"
    if interval.upper <= -DELTA:
        return "proxy materially better"
    if -DELTA < interval.lower and interval.upper < DELTA:
        return "practically equivalent"
    return "size unresolved"


SPECIALISATION_DIRECTIONS: Final = {
    "positive": "liquid better",
    "negative": "proxy better",
    "inconclusive": "sign inconclusive",
}


def specialisation_verdict(
    all_cities: Interval, both_meet_cap: Interval, joint: float
) -> tuple[str, str]:
    """
    Direction and practical size of liquid minus proxy. Assessed only if
    both arms meet the cap together in at least FEASIBLE_SHARE of cities
    (`joint_share`); each verdict stands only when the all-city interval
    and the interval over cities where both arms meet the cap agree.
    """
    if joint < FEASIBLE_SHARE:
        return ("not assessable at matched overhead",) * 2
    first, second = direction(all_cities), direction(both_meet_cap)
    sign = SPECIALISATION_DIRECTIONS[first if first == second else "inconclusive"]
    size_first, size_second = specialisation_size(all_cities), specialisation_size(both_meet_cap)
    size = size_first if size_first == size_second else "size unresolved"
    return sign, size


def joint_share(liquid_meets_cap: npt.ArrayLike, proxy_meets_cap: npt.ArrayLike) -> float:
    """
    The share of cities where both arms meet the cap: the gate for the
    paired specialisation contrast, which needs comparable overhead within
    the same cities. The two marginal shares are reported beside it.
    """
    liquid = np.asarray(liquid_meets_cap, dtype=np.bool_)
    proxy = np.asarray(proxy_meets_cap, dtype=np.bool_)
    if liquid.shape != proxy.shape or liquid.ndim != 1:
        raise ValueError("one flag per city for each arm is needed")
    return float((liquid & proxy).mean())


# ---------------------------------------------------------------------------
# The threshold (amendment A6)
# ---------------------------------------------------------------------------


def sustained_crossing(
    levels: tuple[float, ...], means: npt.ArrayLike
) -> tuple[str, tuple[float, float] | None, float | None]:
    """
    Where the mean difference becomes non-negative and stays so at every
    higher level: the status, the grid bracket and a linear interpolation
    inside it (a grid approximation).
    """
    m = np.asarray(means, dtype=np.float64)
    if m.shape != (len(levels),) or len(levels) < 2:
        raise ValueError("one mean per level, at least two levels")
    if any(b <= a for a, b in zip(levels, levels[1:])):
        raise ValueError("levels must increase")
    if m[-1] < 0.0:
        return "no crossing in the tested range", None, None
    below = np.flatnonzero(m < 0.0)
    if below.size == 0:
        return "liquid ahead throughout", None, None
    k = int(below[-1]) + 1
    low, high = float(m[k - 1]), float(m[k])
    at = levels[k - 1] + (levels[k] - levels[k - 1]) * (-low) / (high - low)
    return "crosses", (levels[k - 1], levels[k]), float(at)


@dataclass(frozen=True)
class Threshold:
    """
    The break-even turnout: the level of the dial above which liquid's
    fidelity stays at or above the representative's.
    """

    status: str
    bracket: tuple[float, float] | None
    # Linear interpolation inside the bracket: a grid approximation
    interpolated: float | None
    # 95% city-bootstrap percentile interval of the threshold; -inf means
    # "below the tested range" (liquid ahead throughout) and +inf "above it"
    interval: tuple[float, float]
    # How often the mean curve changes sign; more than one is reported as
    # a non-monotone curve
    sign_changes: int
    # Whether the overhead gate holds at every level from the bracket's
    # upper end (or the lowest level, when ahead throughout) upward
    gate_holds: bool
    # The difference's 95% t-interval at every level, in grid order
    pointwise: tuple[Interval, ...]


def _threshold_value(levels: tuple[float, ...], means: npt.NDArray[np.float64]) -> float:
    status, _, at = sustained_crossing(levels, means)
    if status == "liquid ahead throughout":
        return -math.inf
    if status == "no crossing in the tested range":
        return math.inf
    assert at is not None
    return at


def threshold(
    levels: tuple[float, ...],
    differences: npt.ArrayLike,
    meets_cap: npt.ArrayLike,
) -> Threshold:
    """
    The threshold from [city, level] paired differences (liquid minus the
    representative) and [city, level] flags for the overhead cap. The
    bootstrap resamples whole cities, so each city's curve stays together.
    """
    d = np.asarray(differences, dtype=np.float64)
    cap = np.asarray(meets_cap, dtype=np.bool_)
    if d.ndim != 2 or d.shape[1] != len(levels) or cap.shape != d.shape:
        raise ValueError("differences and cap flags must be [city, level]")
    means = d.mean(axis=0)
    status, bracket, at = sustained_crossing(levels, means)
    signs = np.sign(means)
    nonzero = signs[signs != 0]
    changes = int((nonzero[1:] != nonzero[:-1]).sum())
    gate = cap.mean(axis=0) >= FEASIBLE_SHARE
    if status == "no crossing in the tested range":
        gate_holds = bool(gate.all())
    else:
        start = 0 if bracket is None else levels.index(bracket[1])
        gate_holds = bool(gate[start:].all())
    rng = np.random.default_rng(np.random.SeedSequence([BOOTSTRAP_SEED]))
    cities = d.shape[0]
    draws = np.array(
        [
            _threshold_value(levels, d[rng.integers(0, cities, cities)].mean(axis=0))
            for _ in range(BOOTSTRAP_RESAMPLES)
        ]
    )
    alpha = (1.0 - CONFIDENCE) / 2.0
    interval = (
        float(np.quantile(draws, alpha, method="inverted_cdf")),
        float(np.quantile(draws, 1.0 - alpha, method="inverted_cdf")),
    )
    pointwise = tuple(t_interval(d[:, j]) for j in range(len(levels)))
    return Threshold(status, bracket, at, interval, changes, gate_holds, pointwise)


def threshold_verdict(result: Threshold) -> str:
    """The primary finding's label, exactly as declared."""
    if not result.gate_holds:
        return "overhead condition not met where liquid is ahead"
    if result.status == "crosses":
        return "crosses" if result.sign_changes <= 1 else "crosses (non-monotone curve)"
    return result.status
