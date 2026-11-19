from __future__ import annotations

import numpy as np
import pytest

from delegation.comparison.protocol import (
    DEVELOPMENT_SEEDS,
    MAX_CITIES,
    TURNOUT_GRID,
    Interval,
    direction,
    h1_size,
    h1_size_verdict,
    h1_verdict,
    joint_share,
    primary_city_seeds,
    specialisation_size,
    specialisation_verdict,
    sustained_crossing,
    t_interval,
    threshold,
    threshold_verdict,
)


def test_primary_seeds_are_a_fixed_sequence_disjoint_from_development():
    seeds = primary_city_seeds(MAX_CITIES)
    assert seeds[:3] == primary_city_seeds(3)
    assert len(set(seeds)) == MAX_CITIES
    assert not set(seeds) & DEVELOPMENT_SEEDS
    # Test fixtures and diagnostics use small seeds
    assert min(seeds) > 10**8
    with pytest.raises(ValueError):
        primary_city_seeds(MAX_CITIES + 1)


def test_conflicting_directions_are_inconclusive():
    # The reviewer's case: positive over all cities, negative over those
    # meeting the cap, exactly 95% feasible
    positive = Interval(0.009, 0.0024, 0.0157)
    negative = Interval(-0.001, -0.0015, -0.0005)
    assert h1_verdict(positive, negative, 0.95) == "inconclusive about the sign"
    assert h1_verdict(positive, positive, 0.95) == "supported"
    assert h1_verdict(positive, Interval(0.0, -0.001, 0.001), 0.95) == "inconclusive about the sign"
    assert h1_verdict(negative, negative, 1.0).startswith("evidence against")
    assert h1_verdict(positive, positive, 0.94) == "overhead condition not met"


def test_size_categories_do_not_overlap():
    assert specialisation_size(Interval(-0.01, -0.015, -0.005)) == "practically equivalent"
    assert direction(Interval(-0.01, -0.015, -0.005)) == "negative"
    assert specialisation_size(Interval(-0.03, -0.04, -0.02)) == "proxy materially better"
    assert specialisation_size(Interval(0.03, 0.02, 0.04)) == "worthwhile"
    assert specialisation_size(Interval(0.015, 0.005, 0.025)) == "size unresolved"
    assert h1_size(Interval(0.03, 0.021, 0.039)) == "gain of at least delta established"
    assert h1_size(Interval(0.03, 0.02, 0.04)) == "gain of at least delta established"
    assert h1_size(Interval(0.025, 0.015, 0.035)) == "estimate at least delta, size unresolved"
    assert h1_size(Interval(0.01, 0.005, 0.015)) == "gain below delta established"
    # An estimate below delta whose interval still allows delta
    assert h1_size(Interval(0.019, 0.015, 0.023)) == "estimate below delta, size unresolved"
    # An upper end exactly at delta does not rule delta out
    assert h1_size(Interval(0.015, 0.01, 0.02)) == "estimate below delta, size unresolved"


def test_cities_over_the_cap_cannot_carry_a_size_claim():
    # The reviewer's case, read at one level of the dial: 190 cities
    # meeting the cap gain 1.8 points, ten over the cap gain 18 points
    values = np.full(200, 0.018)
    over = np.array([5] + list(range(30, 200, 19)))[:10]
    values[over] = 0.18
    meets = np.ones(200, dtype=bool)
    meets[over] = False
    assert meets.mean() == 0.95
    all_cities = t_interval(values)
    meeting = t_interval(values[meets])
    assert h1_size(all_cities) == "gain of at least delta established"
    assert h1_size(meeting) == "gain below delta established"
    assert h1_verdict(all_cities, meeting, meets.mean()) == "supported"
    assert h1_size_verdict(all_cities, meeting, meets.mean()) == "size unresolved"
    sign, size = specialisation_verdict(all_cities, meeting, meets.mean())
    assert specialisation_size(all_cities) == "worthwhile"
    assert (sign, size) == ("liquid better", "size unresolved")
    assert specialisation_verdict(all_cities, meeting, 0.9) == ("not assessable at matched overhead",) * 2
    assert h1_size_verdict(meeting, meeting, 0.94) == "overhead condition not met"


def test_joint_share_is_the_intersection():
    liquid = np.ones(20, dtype=bool)
    proxy = np.ones(20, dtype=bool)
    liquid[0] = False
    proxy[1] = False
    assert liquid.mean() == proxy.mean() == 0.95
    assert joint_share(liquid, proxy) == pytest.approx(0.90)


def test_t_interval():
    i = t_interval([0.0, 0.02, 0.04])
    assert i.estimate == pytest.approx(0.02)
    assert i.lower < 0.02 < i.upper


LEVELS = (0.1, 0.3, 0.5, 0.7, 0.9)


def _curves(means, cities=200, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    return np.asarray(means)[None, :] + rng.normal(0.0, noise, (cities, len(means)))


def test_sustained_crossing_takes_the_last_entry_into_non_negative():
    assert sustained_crossing(LEVELS, [-0.05, -0.02, 0.01, 0.03, 0.04])[:2] == ("crosses", (0.3, 0.5))
    status, bracket, at = sustained_crossing(LEVELS, [-0.05, -0.02, 0.02, 0.03, 0.04])
    assert at == pytest.approx(0.4)
    # Positive, negative, then positive again: the sustained crossing is the last one
    assert sustained_crossing(LEVELS, [0.01, -0.01, 0.02, 0.03, 0.04])[1] == (0.3, 0.5)
    assert sustained_crossing(LEVELS, [0.01, 0.02, 0.0, 0.03, 0.04])[0] == "liquid ahead throughout"
    assert sustained_crossing(LEVELS, [-0.05, -0.02, 0.01, 0.03, -0.01])[0] == (
        "no crossing in the tested range"
    )
    with pytest.raises(ValueError):
        sustained_crossing((0.5, 0.3), [0.0, 0.0])


def test_threshold_is_read_with_a_city_bootstrap():
    d = _curves([-0.05, -0.02, 0.02, 0.03, 0.04])
    result = threshold(LEVELS, d, np.ones(d.shape, dtype=bool))
    assert result.status == "crosses" and result.bracket == (0.3, 0.5)
    low, high = result.interval
    assert low <= result.interpolated <= high
    assert 0.3 <= low and high <= 0.5
    assert result.sign_changes == 1 and result.gate_holds
    assert threshold_verdict(result) == "crosses"
    assert len(result.pointwise) == len(LEVELS)
    # Reproducible: the bootstrap is seeded
    assert threshold(LEVELS, d, np.ones(d.shape, dtype=bool)) == result


def test_threshold_intervals_reach_past_the_range_when_uncertain():
    flat = _curves([0.0, 0.0, 0.0, 0.0, 0.0], noise=0.02)
    result = threshold(LEVELS, flat, np.ones(flat.shape, dtype=bool))
    assert result.interval[0] == -np.inf or result.interval[1] == np.inf


def test_the_overhead_gate_applies_where_liquid_is_claimed_ahead():
    d = _curves([-0.05, -0.02, 0.02, 0.03, 0.04])
    cap = np.ones(d.shape, dtype=bool)
    # Failing the cap below the crossing does not matter
    cap[:20, 0] = False
    assert threshold(LEVELS, d, cap).gate_holds
    # Failing it at a level where liquid is claimed ahead does
    cap[:20, 3] = False
    result = threshold(LEVELS, d, cap)
    assert not result.gate_holds
    assert threshold_verdict(result) == "overhead condition not met where liquid is ahead"


def test_a_non_monotone_curve_is_flagged():
    d = _curves([0.02, -0.02, 0.02, 0.03, 0.04], noise=0.001)
    result = threshold(LEVELS, d, np.ones(d.shape, dtype=bool))
    assert result.sign_changes == 2
    assert threshold_verdict(result) == "crosses (non-monotone curve)"


def test_the_grid_contains_the_swiss_marker():
    assert 0.45 in TURNOUT_GRID and TURNOUT_GRID == tuple(sorted(TURNOUT_GRID))
    assert TURNOUT_GRID[0] > 0.0 and TURNOUT_GRID[-1] < 1.0
