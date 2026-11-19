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
from fractions import Fraction
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
# A6 review, 2026-11-19, and the fourth, 2026-11-19)
# ---------------------------------------------------------------------------


def _positive(counts: npt.NDArray[np.float64], use: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """
    Whether each level's total over the cities in `use` is strictly
    positive, decided with an exactly rounded sum of signed match counts, so
    float noise cannot turn a tie into a lead. Both curves are ratios of a
    total to a city count, so the total's sign is the curve's sign, with or
    without strata.
    """
    return np.asarray(
        [bool(use[:, j].any()) and math.fsum(counts[use[:, j], j]) > 0.0 for j in range(counts.shape[1])],
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


def _reversals(positive: npt.NDArray[np.bool_], observed: npt.NDArray[np.bool_]) -> int:
    """Changes between leading and not leading along the observed levels."""
    flags = positive[observed].astype(np.int8)
    return int((flags[1:] != flags[:-1]).sum())


@dataclass(frozen=True)
class CurveReading:
    """Where one mean curve becomes strictly positive for good."""

    # "crosses", "liquid ahead throughout", "no crossing in the tested
    # range" or "unobserved at the top of the range" (no city contributes at
    # the highest level, so nothing can be claimed)
    status: str
    index: int
    bracket: tuple[float, float] | None
    # Linear interpolation inside the bracket, a grid approximation; None
    # when the bracket's lower level is unobserved
    interpolated: float | None
    # The lowest level at which the sustained lead is observed
    first_supported: float | None
    # Changes between leading and not leading; more than one is a reversal
    reversals: int


def read_curve(
    levels: tuple[float, ...],
    means: npt.ArrayLike,
    positive: npt.ArrayLike,
    observed: npt.ArrayLike | None = None,
) -> CurveReading:
    """The sustained strict crossing of a mean curve, observed levels only."""
    if any(b <= a for a, b in zip(levels, levels[1:])):
        raise ValueError("levels must increase")
    m = np.asarray(means, dtype=np.float64)
    pos = np.asarray(positive, dtype=np.bool_)
    seen = np.ones(len(levels), dtype=np.bool_) if observed is None else np.asarray(observed, dtype=np.bool_)
    n = len(levels)
    flips = _reversals(pos, seen)
    if not seen[-1]:
        return CurveReading("unobserved at the top of the range", n, None, None, None, flips)
    k = sustained_index(pos & seen)
    if k == n:
        return CurveReading("no crossing in the tested range", n, None, None, None, flips)
    if k == 0:
        return CurveReading("liquid ahead throughout", 0, None, None, levels[0], flips)
    at: float | None = None
    if seen[k - 1] and np.isfinite(m[k - 1]) and m[k] != m[k - 1]:
        share = min(1.0, max(0.0, float(-m[k - 1] / (m[k] - m[k - 1]))))
        at = levels[k - 1] + (levels[k] - levels[k - 1]) * share
    return CurveReading("crosses", k, (levels[k - 1], levels[k]), at, levels[k], flips)


@dataclass(frozen=True)
class Threshold:
    """
    The break-even turnout: the level of the dial from which liquid's
    fidelity is strictly above the representative's at that level and every
    level above it.

    It is read on two curves, every city and the cities meeting the overhead
    cap at each level, and the claimed threshold is the later of the two, so
    cities over the cap cannot carry it.
    """

    status: str
    bracket: tuple[float, float] | None
    # The later of the two curves' interpolations when they share a bracket;
    # None when either is unavailable (the bracket and first supported
    # level are then the reading)
    interpolated: float | None
    first_supported: float | None
    # Nominal 95% confidence set on the grid: the threshold lies above the
    # first value and at or below the second; -inf and +inf mean beyond the
    # range. It comes from one simultaneous bootstrap-t band over both
    # curves. Coverage is approximate: a rare outcome absent from the sample
    # cannot be recovered by resampling, whatever the sample's spread
    confidence: tuple[float, float]
    all_cities: CurveReading
    cap_meeting: CurveReading
    # Whether at least FEASIBLE_SHARE of cities meet the cap at every level
    # where liquid is claimed ahead (vacuous when it is not ahead anywhere)
    gate_holds: bool
    cap_share: tuple[float, ...]
    band_critical: float
    # The all-city fidelity difference's 95% t-interval at every level, in
    # fidelity units
    pointwise: tuple[Interval, ...]
    # Levels where every city (on either curve) has the same count. This
    # flags only that degenerate case; its absence says nothing about rare
    # outcomes missing from a sample that otherwise varies
    zero_spread_levels: tuple[float, ...] = ()


def _resample(rng: np.random.Generator, strata: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    """City indices resampled with replacement within each stratum."""
    picks = [
        rng.choice(members, size=members.size, replace=True)
        for members in (np.flatnonzero(strata == h) for h in np.unique(strata))
    ]
    return np.concatenate(picks)


# Whole numbers below this sum exactly in float64
_EXACT = 2.0**52


def _totals(d: npt.NDArray[np.float64], use: npt.NDArray[np.bool_]) -> npt.NDArray[np.float64]:
    """
    Exact per-level totals over the cities in `use`. Signed match counts are
    whole numbers, which float64 adds exactly while the sum stays below
    2^52, so a vectorized sum is exact; other inputs use an exactly rounded
    sum per level.
    """
    masked = np.where(use, d, 0.0)
    if np.all(masked == np.round(masked)) and float(np.abs(masked).sum()) < _EXACT:
        return np.asarray(masked.sum(axis=0), dtype=np.float64)
    return np.array([math.fsum(masked[:, j]) for j in range(d.shape[1])])


@dataclass(frozen=True)
class _Curve:
    """One curve's per-level statistics, in count units."""

    # Exactly rounded totals of signed counts, and the number of cities
    total: npt.NDArray[np.float64]
    denom: npt.NDArray[np.float64]
    # total / denom, NaN where no city contributes
    mean: npt.NDArray[np.float64]
    # Standard error, NaN where undefined
    se: npt.NDArray[np.float64]


def _curve_stats(
    d: npt.NDArray[np.float64], use: npt.NDArray[np.bool_], strata: npt.NDArray[np.int64]
) -> _Curve:
    """
    One curve over the cities in `use`: the mean is the ratio of their total
    signed count to their number, divided once, so it is the same quantity
    as in the primary and an exact tie stays exactly zero (sixth and seventh
    A6 reviews). Its standard error is the stratified ratio estimator's:
    with residuals u_i = use_i * (d_i - mean), se^2 = sum_h n_h * var_h(u)
    / denom^2, var_h the within-stratum variance over all n_h cities of
    stratum h. With every city used this is the fixed-weight stratified
    standard error; with one stratum, the ordinary one.

    The standard error is undefined (NaN) when one city or none contributes,
    or a stratum has a single city: a lone city has no estimable spread,
    which is not the same as zero spread.
    """
    levels = d.shape[1]
    total = _totals(d, use)
    denom = use.sum(axis=0).astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(denom > 0, total / denom, np.nan)
    u = np.where(use, d - np.nan_to_num(mean)[None, :], 0.0)
    var_total = np.zeros(levels)
    estimable = denom > 1
    for h in np.unique(strata):
        rows = strata == h
        n_h = int(rows.sum())
        if n_h < 2:
            estimable &= False
            continue
        var_total += n_h * u[rows].var(axis=0, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        se = np.where(estimable, np.sqrt(var_total) / denom, np.nan)
    return _Curve(total, denom, np.asarray(mean, dtype=np.float64), np.asarray(se, dtype=np.float64))


def _curves(
    d: npt.NDArray[np.float64],
    cap: npt.NDArray[np.bool_],
    strata: npt.NDArray[np.int64] | None = None,
) -> tuple[_Curve, _Curve]:
    """
    The all-city and cap-meeting curves, on signed match counts. With
    `strata` (the rotating-agenda sweep points, a fixed number of cities
    per heavy topic) the standard errors use within-stratum variance; the
    means are the same ratios as without strata, so a sweep measures the
    same quantity as the primary.
    """
    groups = np.zeros(d.shape[0], dtype=np.int64) if strata is None else strata
    return _curve_stats(d, np.ones_like(cap), groups), _curve_stats(d, cap, groups)


def _deviation(resampled: _Curve, original: _Curve) -> npt.NDArray[np.float64]:
    """
    Studentized deviations of a resampled curve, by the resample's own
    standard error. Where that spread is zero or undefined, whether the
    mean moved is decided exactly on count totals (total' * denom against
    total * denom'), so rounding cannot fake a move: a moved mean is
    infinite, an unmoved one is 0. A level observed in the data but missing
    from the resample is infinite. Levels unobserved in the data are left
    out.
    """
    known = np.isfinite(original.mean)
    present = np.isfinite(resampled.mean)
    usable = np.isfinite(resampled.se) & (resampled.se > 0)
    out = np.zeros_like(original.mean)
    for j in np.flatnonzero(known):
        if not present[j]:
            out[j] = np.inf
        elif usable[j]:
            out[j] = abs(resampled.mean[j] - original.mean[j]) / resampled.se[j]
        else:
            moved = Fraction(resampled.total[j]) * Fraction(original.denom[j]) != Fraction(
                original.total[j]
            ) * Fraction(resampled.denom[j])
            out[j] = np.inf if moved else 0.0
    return out


def _band(
    mean: npt.NDArray[np.float64], se: npt.NDArray[np.float64], critical: float
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """
    Lower and upper band. The half-width is unbounded where it is undefined:
    an undefined standard error, or zero spread under an infinite critical
    value.
    """
    usable = np.isfinite(se) & (se > 0)
    zero = np.isfinite(se) & (se == 0)
    finite = math.isfinite(critical)
    half = np.where(usable, critical * np.where(usable, se, 0.0) if finite else np.inf, np.inf)
    half = np.where(zero, 0.0 if finite else np.inf, half)
    lower = np.where(np.isfinite(mean), mean - half, -np.inf)
    upper = np.where(np.isfinite(mean), mean + half, np.inf)
    return np.asarray(np.nan_to_num(lower, nan=-np.inf)), np.asarray(np.nan_to_num(upper, nan=np.inf))


def _band_index(lower: npt.NDArray[np.float64], upper: npt.NDArray[np.float64]) -> tuple[int, int]:
    """
    Confidence bounds on the sustained index from a band: the earliest index
    any curve inside the band could cross at, and the latest it must.
    """
    return sustained_index(upper > 0.0), sustained_index(lower > 0.0)


def threshold(
    levels: tuple[float, ...],
    counts: npt.ArrayLike,
    meets_cap: npt.ArrayLike,
    *,
    pairs: float,
    strata: npt.ArrayLike | None = None,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> Threshold:
    """
    The threshold from [city, level] signed match counts (liquid's matching
    ballots minus the representative's, over the same voter-question pairs)
    and [city, level] flags for the overhead cap.

    `pairs` is the number of voter-question pairs in one city (voters times
    evaluation questions); it is the same for every city of one
    configuration and converts counts to fidelity. Signs, and so ties, are
    decided on the counts; means, intervals and the band are in fidelity.

    The bootstrap resamples whole cities with their cap flags, within
    `strata` when given (the rotating-agenda sweep points: one stratum per
    heavy topic), and gives one critical value for the maximum studentized
    deviation over both curves and every level.
    """
    raw = np.asarray(counts, dtype=np.float64)
    cap = np.asarray(meets_cap, dtype=np.bool_)
    if raw.ndim != 2 or raw.shape[1] != len(levels) or cap.shape != raw.shape:
        raise ValueError("counts and cap flags must be [city, level]")
    if not pairs > 0:
        raise ValueError("pairs must be positive")
    d = raw / pairs
    cities = d.shape[0]
    groups = np.zeros(cities, dtype=np.int64) if strata is None else np.asarray(strata, dtype=np.int64)
    if groups.shape != (cities,):
        raise ValueError("one stratum per city")

    # All curve arithmetic is on counts; fidelity only for reported intervals
    layered = None if strata is None else groups
    curve_all, curve_cap = _curves(raw, cap, layered)
    mean_all, se_all, mean_cap, se_cap = curve_all.mean, curve_all.se, curve_cap.mean, curve_cap.se
    observed_cap = np.isfinite(mean_cap)
    all_cities = read_curve(levels, mean_all, _positive(raw, np.ones_like(cap)))
    cap_meeting = read_curve(levels, mean_cap, _positive(raw, cap), observed_cap)

    n = len(levels)
    readings = (all_cities, cap_meeting)
    unobserved = next((r for r in readings if r.status == "unobserved at the top of the range"), None)
    none = next((r for r in readings if r.status == "no crossing in the tested range"), None)
    if unobserved is not None:
        status, index, bracket, at, first = unobserved.status, n, None, None, None
    elif none is not None:
        status, index, bracket, at, first = none.status, n, None, None, None
    else:
        later = max(readings, key=lambda r: r.index)
        status, index, bracket, first = later.status, later.index, later.bracket, later.first_supported
        if all_cities.index == cap_meeting.index:
            both = [r.interpolated for r in readings]
            at = None if any(x is None for x in both) else max(x for x in both if x is not None)
        else:
            at = later.interpolated

    rng = np.random.default_rng(np.random.SeedSequence([BOOTSTRAP_SEED]))
    maxima = np.empty(resamples)
    for b in range(resamples):
        idx = _resample(rng, groups)
        # Bootstrap-t: each resample is studentized by its own spread (fifth
        # A6 review: the original spread let a resample with a moved mean and
        # no spread of its own count as a finite deviation)
        r_all, r_cap = _curves(raw[idx], cap[idx], None if layered is None else groups[idx])
        maxima[b] = float(np.concatenate([_deviation(r_all, curve_all), _deviation(r_cap, curve_cap)]).max())
    critical = float(np.quantile(maxima, CONFIDENCE, method="higher"))
    lower_a, upper_a = _band(mean_all, se_all, critical)
    lower_c, upper_c = _band(mean_cap, se_cap, critical)
    earliest_a, latest_a = _band_index(lower_a, upper_a)
    earliest_c, latest_c = _band_index(lower_c, upper_c)
    earliest, latest = max(earliest_a, earliest_c), max(latest_a, latest_c)
    confidence = (
        -math.inf if earliest == 0 else levels[earliest - 1],
        math.inf if latest == n else levels[latest],
    )

    share = cap.mean(axis=0)
    gate_holds = bool((share[index:] >= FEASIBLE_SHARE).all())
    pointwise = tuple(t_interval(d[:, j]) for j in range(n))
    # Levels where a curve's sample has no spread: a rare outcome absent from
    # the sample cannot be recovered by resampling it, so the set is not
    # validated there and these levels are reported
    flat = (se_all == 0) | ((se_cap == 0) & np.isfinite(mean_cap))
    return Threshold(
        status,
        bracket,
        at,
        first,
        confidence,
        all_cities,
        cap_meeting,
        gate_holds,
        tuple(float(x) for x in share),
        critical,
        pointwise,
        tuple(levels[j] for j in np.flatnonzero(flat)),
    )


def threshold_verdict(result: Threshold) -> str:
    """
    The primary finding's label, exactly as declared. A reversal on either
    curve is appended to whatever the base verdict is.
    """
    if result.status == "unobserved at the top of the range":
        base = "overhead condition not met at the top of the range"
    elif result.status == "no crossing in the tested range":
        base = result.status
    elif not result.gate_holds:
        base = "overhead condition not met where liquid is ahead"
    else:
        base = result.status
    if max(result.all_cities.reversals, result.cap_meeting.reversals) > 1:
        return f"{base} (curve reverses)"
    return base


# ---------------------------------------------------------------------------
# The frontier (amendment A6): the same strict two-curve criterion per level
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrontierReading:
    """
    At one level of the dial, the lowest delegate attendance floor from
    which liquid strictly leads on both the all-city and the cap-meeting
    curve. Raising the floor only adds ballots and leaves delegations (and
    so the cap flags) unchanged, so each curve never falls along the floors
    and the first lead is sustained.
    """

    # "leads at the lowest floor", "crosses", "no lead in the tested range"
    # or "no city meets the cap at this level"
    status: str
    bracket: tuple[float, float] | None
    # Linear interpolation inside the bracket (a grid approximation), the
    # later of the two curves'. It equals the bracket's lower floor when the
    # difference there is an exact tie: that marks where the lead begins,
    # not a lead at that floor. Only status "leads at the lowest floor" is a
    # lead with delegates at their own rate
    interpolated: float | None
    # The all-city fidelity difference's 95% t-interval at every floor
    pointwise: tuple[Interval, ...]


def frontier_reading(
    floors: tuple[float, ...],
    counts: npt.ArrayLike,
    meets_cap: npt.ArrayLike,
    *,
    pairs: float,
) -> FrontierReading:
    """
    [city, floor] signed match counts at one dial level, the [city] cap flags
    of that level, and the pairs per city. The criterion is the threshold's:
    a strict lead, decided on counts, on both curves, the later taken. The
    frontier meets floor 0 exactly where H1's lead holds at that level; H1
    additionally requires the lead to be sustained up the dial and the
    overhead gate.
    """
    raw = np.asarray(counts, dtype=np.float64)
    flags = np.asarray(meets_cap, dtype=np.bool_)
    if raw.ndim != 2 or raw.shape[1] != len(floors) or flags.shape != (raw.shape[0],):
        raise ValueError("counts must be [city, floor] and cap flags [city]")
    if not pairs > 0:
        raise ValueError("pairs must be positive")
    cap = np.broadcast_to(flags[:, None], raw.shape)
    d = raw / pairs
    curve_all, curve_cap = _curves(raw, cap)
    mean_all, mean_cap = curve_all.mean, curve_cap.mean
    seen = np.full(len(floors), bool(flags.any()))
    a = read_curve(floors, mean_all, _positive(raw, np.ones_like(cap)))
    c = read_curve(floors, mean_cap, _positive(raw, cap), seen)
    pointwise = tuple(t_interval(d[:, j]) for j in range(len(floors)))
    if c.status == "unobserved at the top of the range":
        return FrontierReading("no city meets the cap at this level", None, None, pointwise)
    if max(a.index, c.index) == 0:
        return FrontierReading("leads at the lowest floor", None, None, pointwise)
    if max(a.index, c.index) == len(floors):
        return FrontierReading("no lead in the tested range", None, None, pointwise)
    later = max((a, c), key=lambda r: r.index)
    if a.index == c.index:
        both = [a.interpolated, c.interpolated]
        at = None if any(x is None for x in both) else max(x for x in both if x is not None)
    else:
        at = later.interpolated
    return FrontierReading("crosses", later.bracket, at, pointwise)
