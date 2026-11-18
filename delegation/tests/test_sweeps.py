from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from delegation.comparison import simulate_population
from delegation.comparison.beliefs import BeliefCityConfig
from delegation.comparison.population import PopulationConfig
from delegation.comparison.protocol import Interval, primary_city_seeds
from delegation.comparison.sweeps import (
    BREAK_EVEN_FLOORS,
    CES_MATCHED_CORRELATION,
    PRIMARY_POINT,
    STRUCTURAL_BASE,
    SWEEP_CITIES,
    SWEEPS,
    break_even,
)


def test_every_point_builds_a_valid_city_config():
    for point in (PRIMARY_POINT, *SWEEPS):
        for position in (1, 2, 9, SWEEP_CITIES):
            config = point.config(position)
            assert config.seed == primary_city_seeds(position)[-1]
            expected = PopulationConfig if point.population == "structural" else BeliefCityConfig
            assert isinstance(config, expected)


def test_each_point_changes_one_family_from_the_primary():
    primary = PRIMARY_POINT.config(3)
    assert primary == BeliefCityConfig(seed=primary.seed)
    for point in SWEEPS:
        if point.population != "fitted" or point.family == "stress":
            continue
        config = point.config(3)
        changed = {
            f.name
            for f in fields(BeliefCityConfig)
            if getattr(config, f.name) != getattr(primary, f.name)
        }
        allowed = {
            "history": {"history_questions_per_topic"},
            "districts": {"districts"},
            "within_topic_spread": {"within_topic_spread"},
            "evaluation_mix": {"evaluation_topic_weights"},
        }[point.family]
        assert changed == allowed, point.label


def test_heavy_topics_rotate_over_cities():
    point = next(p for p in SWEEPS if p.family == "evaluation_mix" and "4x" in p.label)
    heavy = [int(np.argmax(point.config(i).evaluation_topic_weights)) for i in range(1, 17)]
    assert heavy == list(range(8)) * 2
    stress = next(p for p in SWEEPS if p.family == "stress")
    config = stress.config(3)
    assert config.history_questions_per_topic == 10
    assert int(np.argmax(config.history_topic_weights)) == 2
    assert int(np.argmax(config.evaluation_topic_weights)) == 6


def test_structural_points_have_the_declared_correlations():
    for point in SWEEPS:
        if point.population != "structural":
            continue
        config = point.config(1)
        assert isinstance(config, PopulationConfig)
        assert config.factor_loading**2 == pytest.approx(point.correlation)
        if point.within_block_correlation is not None:
            within = config.factor_loading**2 + config.block_loading**2
            assert within == pytest.approx(CES_MATCHED_CORRELATION)
            assert config.blocks == 2
    big = simulate_population(
        PopulationConfig(
            seed=3, dimensions=8, districts=20, residents_per_district=400,
            district_lean_sd=0.0, factor_loading=0.2**0.5, blocks=2,
            block_loading=(CES_MATCHED_CORRELATION - 0.2) ** 0.5,
        )
    )
    corr = np.corrcoef(big.positions.T)
    assert corr[0, 1] == pytest.approx(CES_MATCHED_CORRELATION, abs=0.02)
    assert corr[0, 7] == pytest.approx(0.2, abs=0.03)


def test_structural_base_keeps_the_one_axis_default_draws():
    # The block factor uses its own stream: one-axis cities are unchanged
    one_axis = simulate_population(STRUCTURAL_BASE)
    explicit = simulate_population(
        PopulationConfig(**{**STRUCTURAL_BASE.__dict__, "blocks": 1, "block_loading": 0.0})
    )
    assert np.array_equal(one_axis.positions, explicit.positions)


def test_break_even_interpolates_one_crossing():
    floors = (0.0, 0.5, 1.0)
    i = lambda m: Interval(m, m - 0.01, m + 0.01)  # noqa: E731
    result = break_even(floors, (i(-0.04), i(-0.02), i(0.02)))
    assert result.status == "crosses"
    assert result.estimate == pytest.approx(0.75)
    assert result.uncertain_floors == ()
    assert break_even(floors, (i(0.01), i(0.02), i(0.03))).status == "liquid ahead throughout"
    none = break_even(floors, (i(-0.05), i(-0.03), i(-0.005)))
    assert none.status == "no crossing in the tested range" and none.estimate is None
    assert none.uncertain_floors == (1.0,)
    assert BREAK_EVEN_FLOORS[0] == 0.0 and 0.96 in BREAK_EVEN_FLOORS
    with pytest.raises(ValueError):
        break_even((0.5, 0.0), (i(0.0), i(0.0)))
