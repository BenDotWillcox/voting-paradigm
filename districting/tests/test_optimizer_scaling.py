"""Inner transport scaling, weight units, and explicit failure semantics."""
from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from districting import Unit, balanced_power_diagram
from districting import algorithm
from districting.algorithm import DistrictingError, DistrictingOptimizationError, _balance_weights


def island_inputs():
    """An overweight population cluster separated from another by 300 km.

    The old raw-meter objective stalled at zero weights on this scale. The
    empty distant point represents retained zero-population island coverage.
    """
    coords = np.column_stack((
        np.r_[np.linspace(-12_000, 12_000, 180), np.linspace(270_000, 330_000, 20), -3_000_000],
        np.r_[np.sin(np.arange(200)) * 3000, 2_000_000],
    ))
    pops = np.r_[np.full(200, 1000.0), 0.0]
    centers = np.array([[-2000.0, 0.0], [300_000.0, 0.0]])
    return centers, coords, pops, np.array([100_000.0, 100_000.0])


@pytest.mark.parametrize('factor', [0.001, 1.0, 1000.0])
def test_large_separated_clusters_balance_independently_of_coordinate_units(factor):
    centers, coords, pops, targets = island_inputs()
    reference_weights, reference_labels = _balance_weights(centers, coords, pops, targets)
    weights, labels = _balance_weights(centers * factor, coords * factor, pops, targets)
    assert np.array_equal(labels, reference_labels)
    assert np.array_equal(np.bincount(labels, weights=pops), targets)
    assert np.allclose(weights / factor ** 2, reference_weights, rtol=1e-9)
    assert np.max(np.abs(weights)) > 1e10 * factor ** 2
    scores = np.sum((coords[:, None] * factor - centers[None] * factor) ** 2, axis=2) - weights
    assert np.array_equal(labels, scores.argmin(axis=1))


def test_large_translation_keeps_the_same_population_partition():
    centers, coords, pops, targets = island_inputs()
    _, labels = _balance_weights(centers, coords, pops, targets)
    offset = np.array([1e9, -1e9])
    _, translated = _balance_weights(centers + offset, coords + offset, pops, targets)
    assert np.array_equal(labels, translated)


def test_warm_start_weights_keep_original_squared_units_and_ignore_common_offset():
    centers, coords, pops, targets = island_inputs()
    weights, labels = _balance_weights(centers, coords, pops, targets)
    factor = 0.001
    warm_weights = weights * factor ** 2 + 12345.0
    untouched = warm_weights.copy()
    next_weights, next_labels = _balance_weights(
        centers * factor, coords * factor, pops, targets, weights_init=warm_weights,
    )
    assert np.array_equal(labels, next_labels)
    assert np.array_equal(warm_weights, untouched)
    assert np.allclose(next_weights / factor ** 2, weights, rtol=1e-9)
    assert abs(next_weights.sum()) < 1e-9


def test_zero_population_outlier_does_not_set_population_objective_scale(monkeypatch):
    centers, coords, pops, targets = island_inputs()
    captured = []
    minimize = algorithm.minimize
    def observe(fun, *args, **kwargs):
        captured.append(fun(np.array([0.25, -0.25])))
        return minimize(fun, *args, **kwargs)
    monkeypatch.setattr(algorithm, 'minimize', observe)
    _balance_weights(centers, coords, pops, targets)
    _balance_weights(centers, coords[:-1], pops[:-1], targets)
    assert captured[0][0] == pytest.approx(captured[1][0])
    assert np.array_equal(captured[0][1], captured[1][1])


def test_coincident_zero_cost_scale_is_finite_for_single_district():
    weights, labels = _balance_weights(np.zeros((1, 2)), np.zeros((3, 2)),
                                     np.array([10., 20., 0.]), np.array([30.]))
    assert np.array_equal(weights, [0.])
    assert np.array_equal(labels, [0, 0, 0])


def _fake_result(**overrides):
    fields = dict(success=True, status=0, message='test termination', nit=1,
                  nfev=1, x=np.zeros(2), fun=0.0, jac=np.zeros(2))
    return OptimizeResult(**(fields | overrides))


@pytest.mark.parametrize('status,message', [(1, 'iteration limit'), (2, 'ABNORMAL: ')])
def test_failed_inner_optimizer_cannot_be_reported_as_center_convergence(monkeypatch, status, message):
    monkeypatch.setattr(algorithm, 'minimize', lambda *args, **kwargs:
                        _fake_result(success=False, status=status, message=message, nit=0, nfev=21))
    units = [Unit('a', (0., 0.), 10), Unit('b', (1000., 0.), 10)]
    with pytest.raises(DistrictingOptimizationError) as caught:
        balanced_power_diagram(units, 2, seed=0)
    assert caught.value.status == status
    assert caught.value.iterations == 0
    assert caught.value.function_evaluations == 21
    assert caught.value.optimizer_message == message


@pytest.mark.parametrize('field,value', [('x', np.array([np.nan, 0.])),
                                      ('x', np.zeros(3)), ('fun', float('inf')),
                                      ('jac', np.array([0., np.nan])), ('jac', np.zeros(1))])
def test_optimizer_success_flag_cannot_mask_invalid_output(monkeypatch, field, value):
    monkeypatch.setattr(algorithm, 'minimize', lambda *args, **kwargs: _fake_result(**{field: value}))
    with pytest.raises(DistrictingOptimizationError, match='nonfinite optimizer output'):
        _balance_weights(*island_inputs())


@pytest.mark.parametrize('coordinate', [float('inf'), float('nan')])
def test_nonfinite_coordinates_rejected_before_optimization(coordinate):
    with pytest.raises(DistrictingError, match='finite'):
        balanced_power_diagram([Unit('invalid', (coordinate, 0.), 10)], 1)


def test_nonsmooth_indivisible_population_is_reported_without_claiming_exact_balance():
    # Target7.5 cannot be reached with indivisible units of10 and5 people.
    weights, labels = _balance_weights(np.array([[0., 0.], [100_000., 0.]]),
                                     np.array([[0., 0.], [100_000., 0.]]),
                                     np.array([10., 5.]), np.array([7.5, 7.5]))
    assert np.isfinite(weights).all()
    assert np.bincount(labels, weights=[10., 5.], minlength=2).sum() == 15
    assert not np.array_equal(np.bincount(labels, weights=[10., 5.], minlength=2), [7.5, 7.5])
