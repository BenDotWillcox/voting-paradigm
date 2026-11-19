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
    read_curve,
    sustained_index,
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
FAST = 400


def _curves(means, cities=200, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    return np.asarray(means)[None, :] + rng.normal(0.0, noise, (cities, len(means)))


def _all(d):
    return np.ones(np.shape(d), dtype=bool)


def _pos(m):
    return np.asarray(m) > 0


def test_the_crossing_is_the_last_entry_into_a_strict_lead():
    m = [-0.05, -0.02, 0.02, 0.03, 0.04]
    reading = read_curve(LEVELS, m, _pos(m))
    assert (reading.status, reading.bracket) == ("crosses", (0.3, 0.5))
    assert reading.interpolated == pytest.approx(0.4)
    m = [0.01, -0.01, 0.02, 0.03, 0.04]
    assert read_curve(LEVELS, m, _pos(m)).bracket == (0.3, 0.5)
    # A tie is not a lead
    m = [0.01, 0.02, 0.0, 0.03, 0.04]
    assert read_curve(LEVELS, m, _pos(m)).bracket == (0.5, 0.7)
    m = [-0.05, -0.02, 0.01, 0.03, -0.01]
    assert read_curve(LEVELS, m, _pos(m)).status == "no crossing in the tested range"
    assert sustained_index([True, True]) == 0 and sustained_index([True, False]) == 2


def test_ties_everywhere_are_no_lead():
    zeros = np.zeros((50, len(LEVELS)), dtype=np.int64)
    result = threshold(LEVELS, zeros, _all(zeros), resamples=FAST)
    assert result.status == "no crossing in the tested range"
    assert threshold_verdict(result) == "no crossing in the tested range"


def test_no_crossing_is_not_hidden_by_a_cap_failure():
    d = _curves([-0.05, -0.04, -0.03, -0.02, -0.01], noise=0.001)
    cap = _all(d)
    cap[:30, 0] = False
    result = threshold(LEVELS, d, cap, resamples=FAST)
    assert threshold_verdict(result) == "no crossing in the tested range"


def test_cities_over_the_cap_cannot_carry_the_threshold():
    # The reviewer's case on the real grid: every city loses 3 points at the
    # lowest level; above it 190 compliant cities lose 0.1 points and ten
    # over-cap cities gain 10 points
    levels = TURNOUT_GRID
    d = np.full((200, len(levels)), -0.001)
    d[:, 0] = -0.03
    d[:10, 1:] = 0.10
    cap = np.ones(d.shape, dtype=bool)
    cap[:10, 1:] = False
    result = threshold(levels, d, cap, resamples=FAST)
    assert result.all_cities.status == "crosses"
    assert result.cap_meeting.status == "no crossing in the tested range"
    assert threshold_verdict(result) == "no crossing in the tested range"


def test_the_threshold_takes_the_higher_of_the_two_curves():
    d = _curves([-0.05, -0.02, 0.02, 0.03, 0.04], noise=0.001)
    cap = _all(d)
    # At 0.5 the only leaders are fifteen cities over the cap
    leaders = np.arange(15)
    d[leaders, 2] = 0.5
    d[15:, 2] = -0.01
    cap[leaders, 2] = False
    result = threshold(LEVELS, d, cap, resamples=FAST)
    assert result.all_cities.bracket == (0.3, 0.5)
    assert result.cap_meeting.bracket == (0.5, 0.7)
    assert result.bracket == (0.5, 0.7)


def test_a_clean_crossing_is_covered():
    levels = TURNOUT_GRID
    truth = np.array([-0.04, -0.03, -0.02, -0.01, -0.005, 0.005, 0.01, 0.02, 0.03, 0.04])
    true_level = levels[5]
    covered = 0
    runs = 60
    for seed in range(runs):
        d = _curves(truth, noise=0.02, seed=seed)
        low, high = threshold(levels, d, _all(d), resamples=FAST).confidence
        covered += low < true_level <= high
    assert covered / runs >= 0.9


def test_a_plateau_at_zero_is_covered():
    # The reviewer's case: two columns at -0.02, four whose population mean
    # is exactly zero, four at +0.02. Ties are not a lead, so the true
    # threshold is the first +0.02 level, 0.6
    levels = TURNOUT_GRID
    rng = np.random.default_rng(456)
    covered = 0
    runs = 60
    for _ in range(runs):
        d = np.empty((200, len(levels)))
        d[:, :2] = -0.02
        d[:, 2:6] = rng.uniform(-0.01, 0.01, (200, 4))
        d[:, 6:] = 0.02
        low, high = threshold(levels, d, _all(d), resamples=FAST).confidence
        covered += low < 0.6 <= high
    assert covered / runs >= 0.9


def test_rotating_agenda_points_resample_within_strata():
    # Identical curves within each heavy-topic stratum, eight strata whose
    # crossings are spread across the range: the equal-weight curve is
    # fixed, so stratified resampling cannot move it
    levels = TURNOUT_GRID
    strata = np.repeat(np.arange(8), 6)
    crossings = np.linspace(0.22, 0.64, 8)
    lv = np.asarray(levels)
    d = np.stack([np.tanh((lv - crossings[h]) * 10) * 0.05 for h in strata])
    stratified = threshold(levels, d, _all(d), strata=strata, resamples=FAST)
    plain = threshold(levels, d, _all(d), resamples=FAST)
    assert stratified.band_critical == 0.0
    assert stratified.confidence == stratified.bracket
    assert plain.confidence[0] <= stratified.confidence[0]
    assert plain.confidence[1] >= stratified.confidence[1]
    assert plain.confidence != stratified.confidence


def test_threshold_is_reproducible_and_reports_its_parts():
    d = _curves([-0.05, -0.02, 0.02, 0.03, 0.04])
    a = threshold(LEVELS, d, _all(d), resamples=FAST)
    assert a == threshold(LEVELS, d, _all(d), resamples=FAST)
    assert threshold_verdict(a) == "crosses" and a.gate_holds
    assert len(a.pointwise) == len(LEVELS) and len(a.cap_share) == len(LEVELS)
    cap = _all(d)
    cap[:20, 3] = False
    assert threshold_verdict(threshold(LEVELS, d, cap, resamples=FAST)) == (
        "overhead condition not met where liquid is ahead"
    )


def test_a_non_monotone_curve_is_flagged():
    d = _curves([0.02, -0.02, 0.02, 0.03, 0.04], noise=0.001)
    result = threshold(LEVELS, d, _all(d), resamples=FAST)
    assert result.sign_changes == 2
    assert threshold_verdict(result) == "crosses (non-monotone curve)"


def test_the_grid_contains_the_swiss_marker():
    assert 0.45 in TURNOUT_GRID and TURNOUT_GRID == tuple(sorted(TURNOUT_GRID))
    assert TURNOUT_GRID[0] > 0.0 and TURNOUT_GRID[-1] < 1.0
