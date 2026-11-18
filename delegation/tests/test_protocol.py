from __future__ import annotations

import numpy as np
import pytest

from delegation.comparison.protocol import (
    DEVELOPMENT_SEEDS,
    FIRST_STAGE,
    MAX_CITIES,
    Interval,
    direction,
    h1_size,
    h1_verdict,
    joint_share,
    primary_city_seeds,
    specialisation_size,
    stein_city_count,
    stein_interval,
    t_interval,
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


def test_stein_count_reads_only_the_spread():
    rng = np.random.default_rng(0)
    first = rng.normal(0.0, 0.01, FIRST_STAGE)
    assert stein_city_count(first) == stein_city_count(first + 0.3)
    assert stein_city_count(np.zeros(FIRST_STAGE)) == FIRST_STAGE
    assert stein_city_count(rng.normal(0.0, 1.0, FIRST_STAGE)) == MAX_CITIES
    with pytest.raises(ValueError):
        stein_city_count(first[:-1])


def test_stein_interval_meets_the_half_width_when_uncapped():
    rng = np.random.default_rng(1)
    first = rng.normal(0.01, 0.025, FIRST_STAGE)
    n = stein_city_count(first)
    assert FIRST_STAGE < n < MAX_CITIES
    rest = rng.normal(0.01, 0.025, n - FIRST_STAGE)
    interval = stein_interval(np.concatenate([first, rest]))
    assert interval.half_width <= 0.005 + 1e-12


def test_stein_interval_has_its_nominal_coverage():
    rng = np.random.default_rng(2)
    hits = 0
    trials = 2000
    for _ in range(trials):
        first = rng.normal(0.0, 0.012, FIRST_STAGE)
        n = stein_city_count(first)
        values = np.concatenate([first, rng.normal(0.0, 0.012, n - FIRST_STAGE)])
        i = stein_interval(values)
        hits += i.lower <= 0.0 <= i.upper
    assert hits / trials == pytest.approx(0.95, abs=0.015)


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
    assert h1_size(Interval(0.025, 0.015, 0.035)) == "estimated at least delta, not established"
    assert h1_size(Interval(0.01, 0.005, 0.015)) == "below delta"


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
