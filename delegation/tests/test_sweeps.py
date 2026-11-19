from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from delegation.comparison import simulate_population
from delegation.comparison.beliefs import SWISS_TURNOUT, BeliefCityConfig
from delegation.comparison.population import TURNOUT_LOGIT_SD, PopulationConfig
from delegation.comparison.protocol import TURNOUT_GRID, primary_city_seeds
from delegation.comparison.sweeps import (
    CES_MATCHED_CORRELATION,
    DIAL_TURNOUT,
    FRONTIER_FLOORS,
    PRIMARY_POINT,
    STRUCTURAL_BASE,
    SWEEP_CITIES,
    SWEEPS,
    frontier_policy,
)


def test_every_point_builds_a_valid_city_config_at_every_level():
    for point in (PRIMARY_POINT, *SWEEPS):
        for position in (1, 9, SWEEP_CITIES):
            for level in (TURNOUT_GRID[0], SWISS_TURNOUT, TURNOUT_GRID[-1]):
                config = point.config(position, level)
                assert config.seed == primary_city_seeds(position)[-1]
                assert config.turnout_mean == level
                expected = PopulationConfig if point.population == "structural" else BeliefCityConfig
                assert isinstance(config, expected)
    # The primary runs on all 200 cities, a sweep point on 48
    assert PRIMARY_POINT.config(200, 0.5).seed == primary_city_seeds(200)[-1]
    with pytest.raises(ValueError):
        SWEEPS[0].config(SWEEP_CITIES + 1, 0.5)


def test_each_point_changes_one_family_from_the_primary():
    primary = PRIMARY_POINT.config(3, SWISS_TURNOUT)
    assert primary == BeliefCityConfig(seed=primary.seed)
    for point in SWEEPS:
        if point.population != "fitted" or point.family == "stress":
            continue
        config = point.config(3, SWISS_TURNOUT)
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
            "turnout_spread": {"turnout_logit_sd"},
            "attendance": {"attendance_cluster"},
        }[point.family]
        assert changed == allowed, point.label


def test_the_dial_moves_only_turnout_and_keeps_residents():
    from delegation.comparison.beliefs import load_beliefs, simulate_belief_city

    model = load_beliefs()
    small = dict(districts=2, residents_per_district=60, history_questions_per_topic=5,
                 evaluation_questions_per_topic=2)
    low = simulate_belief_city(model, BeliefCityConfig(seed=4, turnout_mean=0.2, **small))
    high = simulate_belief_city(model, BeliefCityConfig(seed=4, turnout_mean=0.8, **small))
    assert np.array_equal(low.positions, high.positions)
    assert np.array_equal(low.evaluation.sincere, high.evaluation.sincere)
    assert np.array_equal(low.evaluation.turnout_draw, high.evaluation.turnout_draw)
    # Everyone's log-odds move together, so ranks are kept and ballots only added
    assert np.array_equal(np.argsort(low.turnout), np.argsort(high.turnout))
    assert (high.turnout > low.turnout).all()
    assert not (low.history.casts & ~high.history.casts).any()


def test_heavy_topics_rotate_over_cities():
    point = next(p for p in SWEEPS if p.family == "evaluation_mix" and "4x" in p.label)
    heavy = [int(np.argmax(point.config(i, 0.5).evaluation_topic_weights)) for i in range(1, 17)]
    assert heavy == list(range(8)) * 2
    stress = next(p for p in SWEEPS if p.family == "stress")
    config = stress.config(3, 0.5)
    assert config.history_questions_per_topic == 10
    assert int(np.argmax(config.history_topic_weights)) == 2
    assert int(np.argmax(config.evaluation_topic_weights)) == 6


def test_rotations_are_complete():
    assert SWEEP_CITIES % 8 == 0
    point = next(p for p in SWEEPS if p.family == "evaluation_mix" and "4x" in p.label)
    heavy = [
        int(np.argmax(point.config(i, 0.5).evaluation_topic_weights))
        for i in range(1, SWEEP_CITIES + 1)
    ]
    assert np.bincount(heavy, minlength=8).tolist() == [SWEEP_CITIES // 8] * 8


def test_structural_points_have_the_declared_correlations():
    for point in SWEEPS:
        if point.population != "structural":
            continue
        config = point.config(1, 0.5)
        assert isinstance(config, PopulationConfig)
        assert config.factor_loading**2 == pytest.approx(point.correlation)
        assert config.turnout_logit_sd == TURNOUT_LOGIT_SD
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


def test_the_dial_condition_is_delegates_at_their_own_rate():
    assert DIAL_TURNOUT.resolver_turnout == 0.0
    assert DIAL_TURNOUT.office_rate == 0.96
    assert frontier_policy(0.6).resolver_turnout == 0.6
    assert frontier_policy(0.6).office_rate == 0.96
    assert FRONTIER_FLOORS[0] == 0.0 and 0.96 in FRONTIER_FLOORS and FRONTIER_FLOORS[-1] == 1.0


def test_rotating_points_carry_heavy_topic_strata():
    positions = np.arange(1, SWEEP_CITIES + 1)
    for point in SWEEPS:
        strata = point.strata(positions)
        if point.family in ("evaluation_mix", "stress"):
            assert strata is not None
            assert np.bincount(strata).tolist() == [SWEEP_CITIES // 8] * 8
            heavy = [
                int(np.argmax(point.config(i, 0.5).evaluation_topic_weights))
                for i in (1, 2, 9)
            ]
            assert heavy[0] == heavy[2] != heavy[1] or point.family == "stress"
        else:
            assert strata is None
    assert PRIMARY_POINT.strata(positions) is None


def test_ballot_day_attendance_shares_draws():
    from delegation.comparison.beliefs import load_beliefs, simulate_belief_city

    point = next(p for p in SWEEPS if p.family == "attendance")
    config = point.config(2, 0.45)
    small = dict(districts=2, residents_per_district=20, history_questions_per_topic=3,
                 evaluation_questions_per_topic=3)
    from dataclasses import replace as _replace
    city = simulate_belief_city(load_beliefs(), _replace(config, **small))
    draws = city.history.turnout_draw
    assert np.array_equal(draws[:, 0], draws[:, 1]) and np.array_equal(draws[:, 1], draws[:, 2])
    assert not np.array_equal(draws[:, 2], draws[:, 3])

