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


def test_break_even_brackets_one_crossing():
    floors = (0.3, 0.5, 1.0)
    i = lambda m: Interval(m, m - 0.01, m + 0.01)  # noqa: E731
    result = break_even(floors, (i(-0.04), i(-0.02), i(0.02)))
    assert result.status == "crosses"
    assert result.bracket == (0.5, 1.0)
    assert result.interpolated == pytest.approx(0.75)
    assert len(result.pointwise) == 3
    ahead = break_even(floors, (i(0.01), i(0.02), i(0.03)))
    assert ahead.status == "liquid ahead throughout" and ahead.bracket is None
    none = break_even(floors, (i(-0.05), i(-0.03), i(-0.005)))
    assert none.status == "no crossing in the tested range" and none.interpolated is None
    with pytest.raises(ValueError):
        break_even((0.5, 0.3), (i(0.0), i(0.0)))


def test_a_tie_at_ordinary_turnout_is_not_a_lead():
    i = lambda m: Interval(m, m - 0.01, m + 0.01)  # noqa: E731
    tie = break_even((0.3, 0.5), (i(0.0), i(0.01)))
    assert tie.status == "equal at ordinary turnout"
    assert tie.bracket == (0.3, 0.3) and tie.interpolated == 0.3


def test_the_grid_starts_where_the_floor_starts_to_matter():
    from delegation.comparison import ChoicePolicy, liquid
    from delegation.comparison.beliefs import load_beliefs, simulate_belief_city
    from delegation.comparison.sweeps import ORDINARY_PLATEAU, break_even_policy

    assert BREAK_EVEN_FLOORS[0] == ORDINARY_PLATEAU == BeliefCityConfig().min_turnout
    assert 0.96 in BREAK_EVEN_FLOORS and BREAK_EVEN_FLOORS[-1] == 1.0
    # The reviewer's case: flat from ordinary to 0.30, then positive by 0.40.
    # With the plateau endpoint on the grid the crossing cannot fall below 0.30
    i = lambda m: Interval(m, m - 0.002, m + 0.002)  # noqa: E731
    result = break_even((ORDINARY_PLATEAU, 0.4), (i(-0.001), i(0.004)))
    assert result.bracket == (ORDINARY_PLATEAU, 0.4)
    assert result.interpolated is not None and result.interpolated >= ORDINARY_PLATEAU
    # Every floor up to the plateau is exactly ordinary turnout
    city = simulate_belief_city(
        load_beliefs(),
        BeliefCityConfig(seed=11, districts=2, residents_per_district=40,
                         history_questions_per_topic=6, evaluation_questions_per_topic=3),
    )
    assert city.turnout.min() >= ORDINARY_PLATEAU
    policy = ChoicePolicy(acceptance=0.3)
    zero = liquid(city, policy, break_even_policy(0.0))
    plateau = liquid(city, policy, break_even_policy(ORDINARY_PLATEAU))
    assert np.array_equal(zero.counted, plateau.counted)


def test_rotations_are_complete():
    assert SWEEP_CITIES % 8 == 0
    point = next(p for p in SWEEPS if p.family == "evaluation_mix" and "4x" in p.label)
    heavy = [int(np.argmax(point.config(i).evaluation_topic_weights)) for i in range(1, SWEEP_CITIES + 1)]
    assert np.bincount(heavy, minlength=8).tolist() == [SWEEP_CITIES // 8] * 8
