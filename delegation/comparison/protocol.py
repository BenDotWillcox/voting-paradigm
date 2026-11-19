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
             citizen turnout on the dial from which liquid's fidelity is
             strictly above the representative's at every higher level,
             read on the all-city curve and on the curve of cities meeting
             the overhead cap, taking the higher. Its confidence set comes
             from one simultaneous bootstrap band over both curves.
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
# The threshold (amendment A6; interval and cap rules revised after the third
# A6 review, 2026-11-19)
# ---------------------------------------------------------------------------


def _positive(d: npt.NDArray[np.float64], use: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """
    Whether each level's sum over the cities in `use` is strictly positive,
    decided with an exactly rounded sum, so float noise cannot turn a tie
    into a lead.
    """
    return np.asarray(
        [bool(use[:, j].any()) and math.fsum(d[use[:, j], j]) > 0.0 for j in range(d.shape[1])],
        dtype=np.bool_,
    )


def sustained_index(positive: npt.ArrayLike) -> int:
    """
    The lowest level index from which every level is strictly positive:
    0 when liquid leads at every level, len(positive) when it does not lead
    at the top of the range.
    """
    flags = np.asarray(positive, dtype=np.bool_)
    not_positive = np.flatnonzero(~flags)
    return 0 if not_positive.size == 0 else int(not_positive[-1]) + 1


@dataclass(frozen=True)
class CurveReading:
    """Where one mean curve becomes strictly positive for good."""

    # "crosses", "liquid ahead throughout" or "no crossing in the tested range"
    status: str
    index: int
    bracket: tuple[float, float] | None
    # Linear interpolation inside the bracket: a grid approximation
    interpolated: float | None


def read_curve(levels: tuple[float, ...], means: npt.ArrayLike, positive: npt.ArrayLike) -> CurveReading:
    """The sustained strict crossing of a mean curve."""
    if any(b <= a for a, b in zip(levels, levels[1:])):
        raise ValueError("levels must increase")
    m = np.asarray(means, dtype=np.float64)
    k = sustained_index(positive)
    if k == len(levels):
        return CurveReading("no crossing in the tested range", k, None, None)
    if k == 0:
        return CurveReading("liquid ahead throughout", 0, None, None)
    low, high = m[k - 1], m[k]
    share = 0.0 if not np.isfinite(low) or high == low else float(-low / (high - low))
    at = levels[k - 1] + (levels[k] - levels[k - 1]) * min(1.0, max(0.0, share))
    return CurveReading("crosses", k, (levels[k - 1], levels[k]), float(at))


@dataclass(frozen=True)
class Threshold:
    """
    The break-even turnout: the level of the dial from which liquid's
    fidelity is strictly above the representative's at that level and every
    level above it.

    It is read on two curves, every city and the cities meeting the overhead
    cap at each level, and the claimed threshold is the higher of the two,
    so cities over the cap cannot carry it.
    """

    status: str
    bracket: tuple[float, float] | None
    interpolated: float | None
    # 95% confidence set on the grid: the threshold lies above the first
    # value and at or below the second; -inf and +inf mean beyond the range.
    # It comes from one simultaneous band over both curves, so it holds
    # whenever both true curves lie inside the band, plateaus included
    confidence: tuple[float, float]
    all_cities: CurveReading
    cap_meeting: CurveReading
    # Changes between leading and not leading along the all-city curve;
    # more than one marks a non-monotone curve
    sign_changes: int
    # Whether at least FEASIBLE_SHARE of cities meet the cap at every level
    # where liquid is claimed ahead (vacuous when it is not ahead anywhere)
    gate_holds: bool
    cap_share: tuple[float, ...]
    band_critical: float
    # The all-city difference's 95% t-interval at every level
    pointwise: tuple[Interval, ...]


def _resample(rng: np.random.Generator, strata: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    """City indices resampled with replacement within each stratum."""
    picks = [
        rng.choice(members, size=members.size, replace=True)
        for members in (np.flatnonzero(strata == h) for h in np.unique(strata))
    ]
    return np.concatenate(picks)


def _curves(
    d: npt.NDArray[np.float64], cap: npt.NDArray[np.bool_]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Means and standard errors of the all-city and cap-meeting curves."""
    n = d.shape[0]
    mean_all = d.mean(axis=0)
    se_all = d.std(axis=0, ddof=1) / math.sqrt(n)
    counts = cap.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_cap = np.where(cap, d, 0.0).sum(axis=0) / counts
        centred = np.where(cap, d - mean_cap, 0.0)
        var_cap = (centred**2).sum(axis=0) / (counts - 1)
        se_cap = np.sqrt(var_cap / counts)
    mean_cap = np.where(counts > 0, mean_cap, np.nan)
    se_cap = np.where(counts > 1, se_cap, np.inf)
    return mean_all, se_all, mean_cap, se_cap


def _band_index(lower: npt.NDArray[np.float64], upper: npt.NDArray[np.float64]) -> tuple[int, int]:
    """
    Confidence bounds on the sustained index from a band: the earliest index
    any curve inside the band could cross at, and the latest it must.
    """
    earliest = sustained_index(np.nan_to_num(upper, nan=np.inf) > 0.0)
    latest = sustained_index(np.nan_to_num(lower, nan=-np.inf) > 0.0)
    return earliest, latest


def threshold(
    levels: tuple[float, ...],
    differences: npt.ArrayLike,
    meets_cap: npt.ArrayLike,
    strata: npt.ArrayLike | None = None,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> Threshold:
    """
    The threshold from [city, level] paired differences (liquid minus the
    representative; signed match counts give exact ties) and [city, level]
    flags for the overhead cap.

    The bootstrap resamples whole cities with their cap flags, within
    `strata` when given (the rotating-agenda sweep points: one stratum per
    heavy topic), and gives one critical value for the maximum studentized
    deviation over both curves and every level.
    """
    d = np.asarray(differences, dtype=np.float64)
    cap = np.asarray(meets_cap, dtype=np.bool_)
    if d.ndim != 2 or d.shape[1] != len(levels) or cap.shape != d.shape:
        raise ValueError("differences and cap flags must be [city, level]")
    cities = d.shape[0]
    groups = np.zeros(cities, dtype=np.int64) if strata is None else np.asarray(strata, dtype=np.int64)
    if groups.shape != (cities,):
        raise ValueError("one stratum per city")

    mean_all, se_all, mean_cap, se_cap = _curves(d, cap)
    positive_all = _positive(d, np.ones_like(cap))
    positive_cap = _positive(d, cap)
    all_cities = read_curve(levels, mean_all, positive_all)
    cap_meeting = read_curve(levels, mean_cap, positive_cap)
    claimed = all_cities if all_cities.index >= cap_meeting.index else cap_meeting

    rng = np.random.default_rng(np.random.SeedSequence([BOOTSTRAP_SEED]))
    maxima = np.empty(resamples)
    with np.errstate(invalid="ignore", divide="ignore"):
        for b in range(resamples):
            idx = _resample(rng, groups)
            m_a, s_a, m_c, s_c = _curves(d[idx], cap[idx])
            dev = np.concatenate([np.abs(m_a - mean_all) / s_a, np.abs(m_c - mean_cap) / s_c])
            maxima[b] = float(np.nanmax(np.where(np.isfinite(dev), dev, 0.0)))
    critical = float(np.quantile(maxima, CONFIDENCE))
    earliest_a, latest_a = _band_index(mean_all - critical * se_all, mean_all + critical * se_all)
    earliest_c, latest_c = _band_index(mean_cap - critical * se_cap, mean_cap + critical * se_cap)
    earliest, latest = max(earliest_a, earliest_c), max(latest_a, latest_c)
    n = len(levels)
    confidence = (
        -math.inf if earliest == 0 else levels[earliest - 1],
        math.inf if latest == n else levels[latest],
    )

    share = cap.mean(axis=0)
    gate_holds = bool((share[claimed.index :] >= FEASIBLE_SHARE).all())
    flags = positive_all.astype(np.int8)
    changes = int((flags[1:] != flags[:-1]).sum())
    pointwise = tuple(t_interval(d[:, j]) for j in range(n))
    return Threshold(
        claimed.status,
        claimed.bracket,
        claimed.interpolated,
        confidence,
        all_cities,
        cap_meeting,
        changes,
        gate_holds,
        tuple(float(x) for x in share),
        critical,
        pointwise,
    )


def threshold_verdict(result: Threshold) -> str:
    """The primary finding's label, exactly as declared."""
    if result.status == "no crossing in the tested range":
        return result.status
    if not result.gate_holds:
        return "overhead condition not met where liquid is ahead"
    if result.status == "crosses" and result.sign_changes > 1:
        return "crosses (non-monotone curve)"
    return result.status
