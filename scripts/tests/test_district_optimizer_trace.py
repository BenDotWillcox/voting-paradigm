"""The offline trace observes the existing solve; it must not change it."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from districting import DistrictingOptimizationError, Unit, balanced_power_diagram
from districting import algorithm
from scripts.district_optimizer_trace import _population_sample, trace_optimizer


def workload():
    rng = np.random.default_rng(0)
    coords = rng.normal(size=(40, 2))
    pops = rng.integers(1, 8, size=40).astype(float)
    targets = np.full(3, int(pops.sum()) // 3, dtype=float)
    targets[:int(pops.sum()) % 3] += 1
    return coords[[0, 5, 15]], coords, pops, targets


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_trace_preserves_exact_weights_labels_options_and_evaluation_counts(tmp_path, monkeypatch):
    original = algorithm.minimize
    observations = []

    def counted_minimize(fun, *args, **kwargs):
        count = 0

        def counted_fun(*values):
            nonlocal count
            count += 1
            return fun(*values)

        result = original(counted_fun, *args, **kwargs)
        observations.append((count, result.nfev, result.nit, kwargs['options'].copy(), kwargs['x0'].copy()))
        return result

    monkeypatch.setattr(algorithm, 'minimize', counted_minimize)
    before_balance = algorithm._balance_weights
    expected = algorithm._balance_weights(*workload(), max_iter=1000)
    path = tmp_path / 'trace.jsonl'
    with trace_optimizer(path) as trace:
        actual = algorithm._balance_weights(*workload(), max_iter=1000)
    assert algorithm.minimize is counted_minimize
    assert algorithm._balance_weights is before_balance
    assert np.array_equal(actual[0], expected[0])
    assert np.array_equal(actual[1], expected[1])
    assert observations[0][:4] == observations[1][:4]
    assert np.array_equal(observations[0][4], observations[1][4])
    assert trace.observation_ok
    result = trace.passes[0]
    assert result['inner_optimizer']['actual_maxiter'] == 1000
    assert result['objective_evaluations'] == observations[0][0] == observations[0][1]
    assert result['accepted_iterations'] == observations[0][2]
    assert trace.summary()['observed_overhead_seconds'] >= 0
    samples = [r for r in rows(path) if r['event'] in ('baseline', 'iteration', 'terminal')]
    assert samples[0]['event'] == 'baseline'
    assert samples[-1]['event'] == 'terminal'
    assert len(samples) == observations[0][2] + 2
    for sample in samples:
        population = sample['population']
        assert all(isinstance(p, int) for p in population['assigned_populations'])
        assert sum(population['assigned_populations']) == population['total_population']
        assert population['fractional_ideal_population'] == population['total_population'] / 3


def test_public_seeded_solver_is_observationally_identical(tmp_path):
    units = [Unit(str(i * 6 + j), (float(i), float(j)), 3 + (i + j) % 3)
             for i in range(6) for j in range(6)]
    kwargs = {'n_districts': 3, 'seed': 59, 'max_outer_iterations': 2, 'inner_max_iterations': 1000}
    expected = balanced_power_diagram(units, **kwargs)
    with trace_optimizer(tmp_path / 'trace.jsonl') as trace:
        actual = balanced_power_diagram(units, **kwargs)
    assert trace.observation_ok
    assert actual == expected


def test_population_samples_match_independent_normalized_cost_assignments(tmp_path, monkeypatch):
    original_minimize = algorithm.minimize
    weights_seen = []

    def capture_weights(fun, *args, **kwargs):
        callback = kwargs['callback']
        weights_seen.append(kwargs['x0'].copy())

        def capture_callback(xk):
            weights_seen.append(xk.copy())
            return callback(xk)

        result = original_minimize(fun, *args, **{**kwargs, 'callback': capture_callback})
        weights_seen.append(result.x.copy())
        return result

    monkeypatch.setattr(algorithm, 'minimize', capture_weights)
    centers, coords, pops, targets = workload()
    path = tmp_path / 'independent.jsonl'
    with trace_optimizer(path) as trace:
        algorithm._balance_weights(centers, coords, pops, targets, max_iter=1000)
    assert trace.observation_ok
    squared = np.sum((coords[:, None, :] - centers[None, :, :]) ** 2, axis=2)
    shifted = squared - squared.min(axis=1, keepdims=True)
    costs = shifted / shifted[pops > 0].max()
    samples = [r for r in rows(path) if r['event'] in ('baseline', 'iteration', 'terminal')]
    assert len(weights_seen) == len(samples)
    for weights, sample in zip(weights_seen, samples, strict=True):
        scores = costs - weights[None, :]
        assignment = scores.argmin(axis=1)
        populations = np.bincount(assignment, weights=pops, minlength=3).astype(int).tolist()
        assert sample['population']['assigned_populations'] == populations
        objective = -float(np.sum(pops / pops.sum() * scores.min(axis=1)) + np.sum(targets / pops.sum() * weights))
        assert sample['objective'] == objective


def test_optimizer_failure_keeps_terminal_result_and_restores_wrappers(tmp_path):
    old_balance, old_minimize = algorithm._balance_weights, algorithm.minimize
    path = tmp_path / 'failure.jsonl'
    with pytest.raises(DistrictingOptimizationError):
        with trace_optimizer(path) as trace:
            algorithm._balance_weights(*workload(), max_iter=1)
    assert algorithm._balance_weights is old_balance and algorithm.minimize is old_minimize
    assert trace.observation_ok
    record = trace.passes[0]
    assert record['inner_optimizer']['success'] is False
    assert record['inner_optimizer']['actual_maxiter'] == 1
    assert record['inner_optimizer']['iteration_limit_reached'] is True
    assert record['terminal_sample']['iteration'] == 1
    assert record['solver_exception']['type'] == 'DistrictingOptimizationError'
    events = [r['event'] for r in rows(path)]
    assert events[-3:] == ['terminal', 'pass_exception', 'pass_complete']


def test_each_pass_has_its_own_objective_reference_and_zero_iteration_baseline(tmp_path):
    centers, coords, pops, targets = workload()
    with trace_optimizer(tmp_path / 'trace.jsonl') as trace:
        weights, _ = algorithm._balance_weights(centers, coords, pops, targets, max_iter=1000)
        algorithm._balance_weights(centers + np.array([[.1, 0], [0, .1], [-.1, .1]]), coords, pops,
                                   targets, weights_init=weights, max_iter=1000)
    assert trace.observation_ok
    assert len(trace.passes) == 2
    assert trace.passes[0]['initial_sample']['objective'] != trace.passes[1]['initial_sample']['objective']
    for i, record in enumerate(trace.passes, start=1):
        baseline, terminal = record['initial_sample'], record['terminal_sample']
        assert baseline['balance_pass'] == i and baseline['iteration'] == 0
        assert baseline['improvement_from_initial'] == 0
        assert baseline['improvement_from_previous'] == 0
        assert terminal['improvement_from_initial'] == baseline['objective'] - terminal['objective']
        assert terminal['pass_elapsed_seconds'] <= terminal['elapsed_seconds']


def test_integer_target_and_fractional_ideal_metrics_are_distinct():
    targets = np.array([4., 3.])
    populations = np.array([5., 2.])
    sample = _population_sample((populations - targets) / 7, targets, 7)
    assert sample['assigned_populations'] == [5, 2]
    assert sample['max_absolute_deviation_people'] == 1.5
    assert sample['max_absolute_target_deviation_people'] == 1
    assert sample['fractional_ideal_population'] == 3.5


@pytest.mark.parametrize('gradient', [np.array([0.1, -0.1]), np.array([.5, .5]),
                                    np.array([-2., 2.]), np.array([np.nan, 0.])])
def test_gradient_reconstruction_rejects_fractional_wrong_total_negative_and_nonfinite(gradient):
    with pytest.raises(ValueError):
        _population_sample(gradient, np.array([5., 5.]), 10 if gradient[0] != .1 else 7)


def test_missing_exact_callback_evaluation_marks_invalid_without_changing_result(tmp_path, monkeypatch):
    original_minimize = algorithm.minimize
    expected = algorithm._balance_weights(*workload(), max_iter=1000)

    def extra_callback(fun, *args, **kwargs):
        result = original_minimize(fun, *args, **kwargs)
        if kwargs.get('callback'):
            kwargs['callback'](result.x + 12345)
        return result

    monkeypatch.setattr(algorithm, 'minimize', extra_callback)
    with trace_optimizer(tmp_path / 'missing.jsonl') as trace:
        actual = algorithm._balance_weights(*workload(), max_iter=1000)
    assert np.array_equal(expected[0], actual[0]) and np.array_equal(expected[1], actual[1])
    assert not trace.observation_ok
    assert any(error['where'] == 'accepted_iteration' for error in trace.telemetry_errors)
    assert trace.passes[0]['inner_optimizer']['success'] is True


def test_trace_write_failure_does_not_change_solver_result(tmp_path, monkeypatch):
    expected = algorithm._balance_weights(*workload(), max_iter=1000)
    with trace_optimizer(tmp_path / 'write-error.jsonl') as trace:
        def broken_write(record):
            raise OSError('simulated disk write failure')
        monkeypatch.setattr(trace, '_write', broken_write)
        actual = algorithm._balance_weights(*workload(), max_iter=1000)
    assert np.array_equal(actual[0], expected[0]) and np.array_equal(actual[1], expected[1])
    assert not trace.observation_ok
    assert trace.passes[0]['inner_optimizer']['success'] is True


def test_log_failure_cannot_replace_a_solver_failure(tmp_path, monkeypatch):
    def broken_print(*args, **kwargs):
        raise BrokenPipeError('closed log pipe')
    monkeypatch.setattr('builtins.print', broken_print)
    with pytest.raises(DistrictingOptimizationError):
        with trace_optimizer(tmp_path / 'log-error.jsonl') as trace:
            algorithm._balance_weights(*workload(), max_iter=1)
    assert not trace.observation_ok
    assert trace.passes[0]['inner_optimizer']['success'] is False
    assert any(item['where'] == 'pass_log' for item in trace.telemetry_errors)


def test_existing_file_and_nested_trace_are_refused_without_replacing_wrappers(tmp_path):
    old = algorithm._balance_weights, algorithm.minimize
    path = tmp_path / 'trace.jsonl'
    path.write_text('preserved\n')
    with pytest.raises(FileExistsError):
        with trace_optimizer(path):
            pass
    assert path.read_text() == 'preserved\n'
    assert (algorithm._balance_weights, algorithm.minimize) == old
    with trace_optimizer(tmp_path / 'outer.jsonl'):
        outer = algorithm._balance_weights, algorithm.minimize
        with pytest.raises(RuntimeError, match='already active'):
            with trace_optimizer(tmp_path / 'inner.jsonl'):
                pass
        assert (algorithm._balance_weights, algorithm.minimize) == outer
    assert (algorithm._balance_weights, algorithm.minimize) == old


def test_zero_accepted_iterations_still_records_baseline_and_terminal(tmp_path):
    coords = np.array([[0., 0.], [10., 0.]])
    with trace_optimizer(tmp_path / 'zero.jsonl') as trace:
        algorithm._balance_weights(coords, coords, np.array([5., 5.]), np.array([5., 5.]), max_iter=1000)
    assert trace.observation_ok
    assert trace.passes[0]['accepted_iterations'] == 0
    assert trace.passes[0]['initial_sample']['iteration'] == trace.passes[0]['terminal_sample']['iteration'] == 0
