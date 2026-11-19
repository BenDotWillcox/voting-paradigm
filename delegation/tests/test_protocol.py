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
    frontier_reading,
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
FOUR = (0.2, 0.4, 0.6, 0.8)
FAST = 400


def _curves(means, cities=200, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    return np.asarray(means)[None, :] + rng.normal(0.0, noise, (cities, len(means)))


def _all(d):
    return np.ones(np.shape(d), dtype=bool)


def _pos(m):
    return np.asarray(m) > 0


def _t(levels, d, cap=None, **kw):
    """Fidelity differences already in fidelity units: one pair per city."""
    return threshold(levels, d, _all(d) if cap is None else cap, pairs=1.0, resamples=FAST, **kw)


def test_the_crossing_is_the_last_entry_into_a_strict_lead():
    m = [-0.05, -0.02, 0.02, 0.03, 0.04]
    reading = read_curve(LEVELS, m, _pos(m))
    assert (reading.status, reading.bracket) == ("crosses", (0.3, 0.5))
    assert reading.interpolated == pytest.approx(0.4)
    assert reading.first_supported == 0.5
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
    result = threshold(LEVELS, zeros, _all(zeros), pairs=80_000, resamples=FAST)
    assert threshold_verdict(result) == "no crossing in the tested range"


def test_no_crossing_is_not_hidden_by_a_cap_failure():
    d = _curves([-0.05, -0.04, -0.03, -0.02, -0.01], noise=0.001)
    cap = _all(d)
    cap[:30, 0] = False
    assert threshold_verdict(_t(LEVELS, d, cap)) == "no crossing in the tested range"


def test_cities_over_the_cap_cannot_carry_the_threshold():
    # Every city loses 3 points at the lowest level; above it 190 compliant
    # cities lose 0.1 points and ten over-cap cities gain 10 points
    levels = TURNOUT_GRID
    d = np.full((200, len(levels)), -0.001)
    d[:, 0] = -0.03
    d[:10, 1:] = 0.10
    cap = np.ones(d.shape, dtype=bool)
    cap[:10, 1:] = False
    result = _t(levels, d, cap)
    assert result.all_cities.status == "crosses"
    assert result.cap_meeting.status == "no crossing in the tested range"
    assert threshold_verdict(result) == "no crossing in the tested range"


def test_a_shared_bracket_takes_the_later_interpolation():
    # The reviewer's case: both curves cross in [0.2, 0.4]; the all-city
    # interpolation is 25.71% and the compliant one 36%
    d = np.tile(np.array([-40.0, 10.0, 40.0, 40.0]), (200, 1))
    d[:10] = [-40.0, 1810.0, 40.0, 40.0]
    cap = _all(d)
    cap[:10, 1:] = False
    result = _t(FOUR, d, cap)
    assert result.all_cities.interpolated == pytest.approx(0.2 + 0.2 * 40 / 140)
    assert result.cap_meeting.interpolated == pytest.approx(0.36)
    assert result.bracket == (0.2, 0.4)
    assert result.interpolated == pytest.approx(0.36)


def test_an_unobserved_lower_end_gives_no_interpolation():
    # The reviewer's case: +0.05 everywhere, no city meets the cap at 0.1
    levels = (0.1, 0.2, 0.3)
    d = np.full((200, 3), 0.05)
    cap = _all(d)
    cap[:, 0] = False
    result = _t(levels, d, cap)
    assert result.cap_meeting.bracket == (0.1, 0.2)
    assert result.cap_meeting.interpolated is None
    assert result.first_supported == 0.2
    assert result.interpolated is None


def test_an_unobserved_top_is_not_a_finding():
    levels = (0.1, 0.2, 0.3)
    d = np.full((200, 3), -0.05)
    cap = _all(d)
    cap[:, 2] = False
    result = _t(levels, d, cap)
    assert result.status == "unobserved at the top of the range"
    assert threshold_verdict(result) == "overhead condition not met at the top of the range"


def test_a_reversal_on_the_cap_meeting_curve_is_flagged():
    # The reviewer's case: the all-city curve changes sign once, the
    # compliant curve goes loss, lead, loss, lead
    d = np.tile(np.array([-20.0, 5.0, -3.0, 10.0]), (200, 1))
    d[:10] = [-20.0, 5.0, 197.0, 10.0]
    cap = _all(d)
    cap[:10, 2] = False
    result = _t(FOUR, d, cap)
    assert result.all_cities.reversals == 1
    assert result.cap_meeting.reversals == 3
    assert threshold_verdict(result) == "crosses (curve reverses)"


def test_signed_counts_are_converted_to_fidelity():
    # 800 extra matches among 500 x 160 pairs is one fidelity point, not two
    counts = np.full((200, len(LEVELS)), 800, dtype=np.int64)
    result = threshold(LEVELS, counts, _all(counts), pairs=500 * 160, resamples=FAST)
    assert result.pointwise[0].estimate == pytest.approx(0.01)
    assert h1_size(result.pointwise[0]) == "gain below delta established"
    with pytest.raises(ValueError):
        threshold(LEVELS, counts, _all(counts), pairs=0, resamples=FAST)


def test_the_threshold_takes_the_higher_of_the_two_curves():
    d = _curves([-0.05, -0.02, 0.02, 0.03, 0.04], noise=0.001)
    cap = _all(d)
    # At 0.5 the only leaders are fifteen cities over the cap
    d[:15, 2] = 0.5
    d[15:, 2] = -0.01
    cap[:15, 2] = False
    result = _t(LEVELS, d, cap)
    assert result.all_cities.bracket == (0.3, 0.5)
    assert result.cap_meeting.bracket == (0.5, 0.7)
    assert result.bracket == (0.5, 0.7)


def test_a_clean_crossing_is_covered():
    levels = TURNOUT_GRID
    truth = np.array([-0.04, -0.03, -0.02, -0.01, -0.005, 0.005, 0.01, 0.02, 0.03, 0.04])
    covered = 0
    runs = 60
    for seed in range(runs):
        low, high = _t(levels, _curves(truth, noise=0.02, seed=seed)).confidence
        covered += low < levels[5] <= high
    assert covered / runs >= 0.9


def test_a_plateau_at_zero_is_covered():
    # Two columns at -0.02, four whose population mean is exactly zero, four
    # at +0.02. Ties are not a lead, so the true threshold is 0.6
    levels = TURNOUT_GRID
    rng = np.random.default_rng(456)
    covered = 0
    runs = 60
    for _ in range(runs):
        d = np.empty((200, len(levels)))
        d[:, :2] = -0.02
        d[:, 2:6] = rng.uniform(-0.01, 0.01, (200, 4))
        d[:, 6:] = 0.02
        low, high = _t(levels, d).confidence
        covered += low < 0.6 <= high
    assert covered / runs >= 0.9


def test_sparse_outcomes_widen_the_band():
    # The reviewer's case: three levels at -20 matches, and at the top +3
    # with probability 199/202 or -199 with probability 3/202, a true mean
    # of exactly zero, so the strict threshold lies above the grid. Before,
    # resamples with a changed mean and no spread counted as zero deviation
    # and the set excluded the truth in about 20% of samples
    rng = np.random.default_rng(7)
    covered = 0
    runs = 200
    for _ in range(runs):
        d = np.full((200, 4), -20.0)
        rare = rng.random(200) < 3 / 202
        d[:, 3] = np.where(rare, -199.0, 3.0)
        result = threshold(FOUR, d, _all(d), pairs=80_000, resamples=FAST)
        covered += result.confidence[1] == np.inf
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
    stratified = _t(levels, d, strata=strata)
    plain = _t(levels, d)
    assert stratified.band_critical == 0.0
    assert stratified.confidence == stratified.bracket
    assert plain.confidence[0] <= stratified.confidence[0]
    assert plain.confidence[1] >= stratified.confidence[1]
    assert plain.confidence != stratified.confidence


def test_threshold_is_reproducible_and_reports_its_parts():
    d = _curves([-0.05, -0.02, 0.02, 0.03, 0.04])
    a = _t(LEVELS, d)
    assert a == _t(LEVELS, d)
    assert threshold_verdict(a) == "crosses" and a.gate_holds
    assert len(a.pointwise) == len(LEVELS) and len(a.cap_share) == len(LEVELS)
    cap = _all(d)
    cap[:20, 3] = False
    assert threshold_verdict(_t(LEVELS, d, cap)) == "overhead condition not met where liquid is ahead"


def test_a_non_monotone_curve_is_flagged():
    d = _curves([0.02, -0.02, 0.02, 0.03, 0.04], noise=0.001)
    assert threshold_verdict(_t(LEVELS, d)) == "crosses (curve reverses)"


def test_the_frontier_uses_the_thresholds_criterion():
    floors = (0.0, 0.5, 1.0)
    pairs = 80_000
    # Ties at every floor are no lead, not floor zero
    ties = np.zeros((100, 3), dtype=np.int64)
    flags = np.ones(100, dtype=bool)
    assert frontier_reading(floors, ties, flags, pairs=pairs).status == "no lead in the tested range"
    leads = np.full((100, 3), 5, dtype=np.int64)
    assert frontier_reading(floors, leads, flags, pairs=pairs).status == "leads at the lowest floor"
    rising = np.tile(np.array([-40, 10, 40]), (100, 1))
    rising[:5] = [-40, 1000, 1000]
    over = flags.copy()
    over[:5] = False
    reading = frontier_reading(floors, rising, over, pairs=1.0)
    assert reading.status == "crosses" and reading.bracket == (0.0, 0.5)
    # The later of the two curves' interpolations, the compliant one here
    assert reading.interpolated == pytest.approx(0.5 * 40 / 50)
    none = frontier_reading(floors, leads, np.zeros(100, dtype=bool), pairs=pairs)
    assert none.status == "no city meets the cap at this level"


def test_the_grid_contains_the_swiss_marker():
    assert 0.45 in TURNOUT_GRID and TURNOUT_GRID == tuple(sorted(TURNOUT_GRID))
    assert TURNOUT_GRID[0] > 0.0 and TURNOUT_GRID[-1] < 1.0


def test_an_exact_tie_in_counts_stays_a_tie_through_the_band():
    # The reviewer's case: 48 cities in their rotating order, six per topic,
    # -20 matches at the first nine levels; at 0.9 the eight topics give
    # [16, -28, 1, 10, 12, -24, 16, -3], identical within each topic. The
    # top mean is exactly zero on every balanced resample
    levels = TURNOUT_GRID
    strata = np.arange(48) % 8
    top = np.array([16, -28, 1, 10, 12, -24, 16, -3])
    counts = np.full((48, len(levels)), -20, dtype=np.int64)
    counts[:, -1] = top[strata]
    result = threshold(levels, counts, _all(counts), pairs=80_000, strata=strata, resamples=FAST)
    assert threshold_verdict(result) == "no crossing in the tested range"
    assert result.confidence[1] == np.inf


def test_resamples_are_studentized_by_their_own_spread():
    # The reviewer's variant: the rare loss is -196 with probability 3/199,
    # a true top mean of zero. With the original spread, samples holding one
    # rare city excluded the truth (coverage at most 80.5%)
    rng = np.random.default_rng(11)
    covered = 0
    runs = 200
    for _ in range(runs):
        d = np.full((200, 4), -20.0)
        rare = rng.random(200) < 3 / 199
        d[:, 3] = np.where(rare, -196.0, 3.0)
        result = threshold(FOUR, d, _all(d), pairs=80_000, resamples=FAST)
        covered += result.confidence[1] == np.inf
    assert covered / runs >= 0.9
    # One rare city: a resample without it moves the mean and has no spread
    d = np.full((200, 4), -20.0)
    d[:, 3] = 3.0
    d[17, 3] = -196.0
    assert threshold(FOUR, d, _all(d), pairs=80_000, resamples=FAST).confidence[1] == np.inf


def test_identical_samples_are_reported_as_zero_spread():
    d = np.full((200, 4), -20.0)
    d[:, 3] = 3.0
    result = threshold(FOUR, d, _all(d), pairs=80_000, resamples=FAST)
    assert result.zero_spread_levels == FOUR


def test_a_reversal_is_flagged_on_every_verdict():
    d = np.tile(np.array([1.0, -1.0, 1.0, -1.0]), (100, 1))
    result = threshold(FOUR, d, _all(d), pairs=1.0, resamples=FAST)
    assert threshold_verdict(result) == "no crossing in the tested range (curve reverses)"


def test_a_frontier_tie_at_the_lowest_floor_is_not_a_lead_there():
    floors = (0.0, 0.2, 0.4)
    counts = np.tile(np.array([0, 1, 2]), (100, 1))
    reading = frontier_reading(floors, counts, np.ones(100, dtype=bool), pairs=80_000)
    assert reading.status == "crosses"
    assert reading.bracket == (0.0, 0.2) and reading.interpolated == 0.0



def test_balanced_sweeps_use_within_topic_spread():
    # Four topics offset +1000 matches and four -1000, six cities each in
    # rotating order. Nine levels at offset - 20; the top at offset + 4 with
    # one city losing a further 60. Pooled spread made the set (0.8, 0.9]
    # for every loss position; within-topic spread leaves it unbounded
    levels = TURNOUT_GRID
    strata = np.arange(48) % 8
    offset = np.where(strata < 4, 1000, -1000)
    for position in (0, 7, 23, 47):
        counts = np.repeat((offset - 20)[:, None], len(levels), axis=1).astype(float)
        counts[:, -1] = offset + 4
        counts[position, -1] -= 60
        result = threshold(levels, counts, _all(counts), pairs=80_000, strata=strata, resamples=FAST)
        assert result.gate_holds
        assert result.confidence[1] == np.inf


def test_a_lone_cap_meeting_city_is_not_zero_spread():
    # Five compliant cities at 0.8, every city at 0.9: a resample holding one
    # compliant city at 0.8 has an undefined spread, and a moved mean there
    # must widen the band
    i = np.arange(200)
    counts = np.stack([100 + i % 2, 200 + i % 2], axis=1).astype(float)
    counts[:5, 0] = [-106, -104, -103, -102, -101]
    cap = np.ones(counts.shape, dtype=bool)
    cap[5:, 0] = False
    result = threshold((0.8, 0.9), counts, cap, pairs=80_000, resamples=FAST)
    assert result.gate_holds
    assert result.confidence == (-np.inf, np.inf)


def test_the_cap_meeting_curve_keeps_the_primary_quantity_at_balanced_points():
    # The reviewer's case: 48 cities in rotating order, offsets
    # [-2, -1, 0, 0, 1, 2] within each topic; -20 + offset for nine levels;
    # at 0.9, topic 0 gets +150 + offset and the rest -20 + offset; one
    # zero-offset city in topic 0 fails the cap at 0.9. The 47 compliant
    # cities lose 90 matches in total, so the compliant curve does not lead
    levels = TURNOUT_GRID
    strata = np.arange(48) % 8
    rank = np.arange(48) // 8
    offset = np.array([-2, -1, 0, 0, 1, 2])[rank]
    counts = np.repeat((offset - 20)[:, None], len(levels), axis=1).astype(float)
    counts[:, -1] = np.where(strata == 0, 150 + offset, -20 + offset)
    cap = _all(counts)
    failing = np.flatnonzero((strata == 0) & (offset == 0))[0]
    cap[failing, -1] = False
    assert counts[cap[:, -1], -1].sum() == -90
    result = threshold(levels, counts, cap, pairs=80_000, strata=strata, resamples=FAST)
    assert result.gate_holds
    assert result.cap_meeting.status == "no crossing in the tested range"
    assert threshold_verdict(result) == "no crossing in the tested range"


def test_an_unmoved_resample_mean_is_decided_on_exact_totals():
    # The reviewer's case: topic counts [4, 5, 3, 4, 4, 4, 4, 4] at 0.9, one
    # match added in topic 2 and removed in topic 4; the mean is exactly 4.
    # Rounding a weighted sum made unmoved resamples look moved and the set
    # unbounded; on exact totals it is (0.8, 0.9]
    levels = TURNOUT_GRID
    strata = np.arange(48) % 8
    counts = np.full((48, len(levels)), -20.0)
    counts[:, -1] = np.array([4, 5, 3, 4, 4, 4, 4, 4])[strata]
    counts[np.flatnonzero(strata == 2)[0], -1] += 1
    counts[np.flatnonzero(strata == 4)[0], -1] -= 1
    assert counts[:, -1].sum() / 48 == 4
    result = threshold(levels, counts, _all(counts), pairs=80_000, strata=strata, resamples=2000)
    assert result.confidence == (0.8, 0.9)
    # Relabelling the topics does not change it
    rolled = threshold(levels, counts, _all(counts), pairs=80_000, strata=(strata + 1) % 8, resamples=2000)
    assert rolled.confidence == (0.8, 0.9)
