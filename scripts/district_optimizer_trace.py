"""Observe the unchanged balanced-power optimizer without extra evaluations.

This offline, single-threaded context temporarily wraps the two optimizer entry
points. It records the *normalized assignment* at existing objective evaluations,
not a public-weight assignment or a repaired/final district plan. Objective values
have a fresh reference and scale in every balancing pass and must not be compared
across passes. Opening the JSONL file exclusively preserves previous attempts.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import inspect
import json
from pathlib import Path
import time
from typing import Any, TextIO

import numpy as np

from districting import algorithm


_ACTIVE_TRACE: OptimizerTrace | None = None


def _key(value: Any) -> tuple[str, tuple[int, ...], bytes]:
    array = np.asarray(value)
    return array.dtype.str, array.shape, array.tobytes()


def _population_sample(gradient: np.ndarray, targets: np.ndarray, total: int) -> dict[str, Any]:
    """Invert the existing negative-dual gradient and validate integer counts."""
    if gradient.shape != targets.shape or not np.all(np.isfinite(gradient)):
        raise ValueError('Objective gradient has invalid shape or nonfinite entries.')
    reconstructed = targets + gradient * total
    rounded = np.rint(reconstructed)
    tolerance = max(1e-6, total * np.finfo(float).eps * 4096)
    if (not np.all(np.isfinite(reconstructed))
            or np.max(np.abs(reconstructed - rounded)) > tolerance
            or np.any(rounded < 0)
            or int(rounded.sum()) != total):
        raise ValueError('Gradient does not reconstruct nonnegative whole-person populations with the expected total.')
    populations = rounded.astype(np.int64)
    ideal = total / len(targets)
    deviations = np.abs(populations - ideal)
    return {
        'assigned_populations': populations.tolist(),
        'target_populations': targets.tolist(),
        'total_population': total,
        'fractional_ideal_population': ideal,
        'max_absolute_deviation_people': float(deviations.max()),
        'max_absolute_deviation_percent': float(deviations.max() / ideal * 100),
        'mean_absolute_deviation_people': float(deviations.mean()),
        'max_absolute_target_deviation_people': float(np.max(np.abs(populations - targets))),
        'max_normalized_gradient': float(np.max(np.abs(gradient))),
        'population_reconstruction_tolerance_people': tolerance,
        'interpretation': 'Diagnostic normalized-cost assignment inferred from the existing objective gradient; not the final public-weight or repaired plan.',
    }


class OptimizerTrace:
    """Live and terminal observations; summaries remain available after failure."""

    def __init__(self, path: Path, stream: TextIO) -> None:
        self.path = path
        self.stream = stream
        self.passes: list[dict[str, Any]] = []
        self.telemetry_errors: list[dict[str, Any]] = []
        self.started = time.perf_counter()
        self.finished: float | None = None
        self.observed_overhead_seconds = 0.0
        self.last_log = self.started
        self._current: dict[str, Any] | None = None
        self._targets: np.ndarray | None = None
        self._total: int | None = None
        self._pass_started = self.started

    @property
    def observation_ok(self) -> bool:
        return not self.telemetry_errors

    def _write(self, record: dict[str, Any]) -> None:
        self.stream.write(json.dumps({'schema_version': 1, **record}, allow_nan=False, separators=(',', ':')) + '\n')
        self.stream.flush()

    def _error(self, where: str, error: Exception) -> None:
        entry = {'event': 'telemetry_error', 'where': where, 'message': f'{type(error).__name__}: {error}',
                 'balance_pass': self._current['balance_pass'] if self._current else None,
                 'elapsed_seconds': time.perf_counter() - self.started}
        self.telemetry_errors.append(entry)
        if self._current is not None:
            self._current['errors'].append(entry)
        try:
            self._write(entry)
        except Exception:
            # A broken trace file must not alter optimization or invent samples.
            pass

    def summary(self) -> dict[str, Any]:
        return {
            'schema_version': 1, 'path': str(self.path), 'observation_ok': self.observation_ok,
            'passes': self.passes, 'telemetry_errors': self.telemetry_errors,
            'recorded_elapsed_seconds': (self.finished or time.perf_counter()) - self.started,
            'observed_overhead_seconds': self.observed_overhead_seconds,
            'objective_evaluations': sum(p['objective_evaluations'] for p in self.passes),
            'accepted_iterations': sum(p['accepted_iterations'] for p in self.passes),
            'notes': [
                'No additional objective evaluations, optimizer restarts, RNG calls, or numerical setting changes are introduced by this observer.',
                'Normalized negative-dual objective is minimized; positive improvement is a decrease within one pass only. Centers and normalization can change between passes.',
                'Population samples reconstruct existing objective-gradient assignments, with integer and total-population checks. Final public-weight assignments can differ at floating-point ties.',
                'Runtime includes telemetry I/O and Python bookkeeping; observed overhead is measured separately but is not a controlled estimate of all instrumentation effects.',
            ],
        }

    def _sample(self, event: str, iteration: int, objective: float, gradient: np.ndarray,
                *, optimizer: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self._current is not None and self._targets is not None and self._total is not None
        if not np.isfinite(objective):
            raise ValueError('Objective is nonfinite.')
        record = self._current
        initial = record.get('initial_sample')
        previous = record.get('last_iteration_sample', initial)
        sample = {
            'event': event, 'balance_pass': record['balance_pass'], 'iteration': iteration,
            'objective_evaluations': record['objective_evaluations'], 'objective': objective,
            'improvement_from_initial': (initial['objective'] - objective) if initial else 0.0,
            'improvement_from_previous': (previous['objective'] - objective) if previous else 0.0,
            'elapsed_seconds': time.perf_counter() - self.started,
            'pass_elapsed_seconds': time.perf_counter() - self._pass_started,
            'normalized_gradient': gradient.tolist(),
            'population': _population_sample(gradient, self._targets, self._total),
        }
        if optimizer is not None:
            sample['optimizer'] = optimizer
        self._write(sample)
        if event == 'baseline':
            record['initial_sample'] = sample
        elif event == 'iteration':
            record['last_iteration_sample'] = sample
        else:
            record['terminal_sample'] = sample
        return sample


@contextmanager
def trace_optimizer(path: Path) -> Iterator[OptimizerTrace]:
    """Observe one solver workload; always restore the original module functions.

    This must not be combined with ``observe_solver`` or a concurrent solve.
    A telemetry error marks the trace invalid, but never substitutes numerical
    results or suppresses the solver's own exception. The caller can separately
    reject incomplete telemetry when deciding whether a benchmark is acceptable.
    """
    global _ACTIVE_TRACE
    if _ACTIVE_TRACE is not None:
        raise RuntimeError('An optimizer trace is already active.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('x', encoding='utf-8', newline='\n')
    trace = OptimizerTrace(path, stream)
    original_balance = algorithm._balance_weights
    original_minimize = algorithm.minimize
    balance_signature = inspect.signature(original_balance)

    def observed_minimize(fun: Any, *args: Any, **kwargs: Any) -> Any:
        record = trace._current
        if record is None:
            return original_minimize(fun, *args, **kwargs)
        options = kwargs.get('options', {})
        record['actual_options'] = dict(options)
        record['actual_method'] = kwargs.get('method')
        cache: dict[tuple[str, tuple[int, ...], bytes], tuple[float, np.ndarray]] = {}
        x0 = kwargs.get('x0', args[0] if args else None)
        x0_key = _key(x0)
        if kwargs.get('callback') is not None or kwargs.get('jac') is not True or kwargs.get('method') != 'L-BFGS-B':
            trace._error('minimize_contract', ValueError('Expected L-BFGS-B with jac=True and no preexisting callback.'))
            return original_minimize(fun, *args, **kwargs)

        def observed_fun(value: Any, *fun_args: Any) -> Any:
            result = fun(value, *fun_args)
            began = time.perf_counter()
            try:
                record['objective_evaluations'] += 1
                objective, gradient = result
                saved = (float(objective), np.asarray(gradient, dtype=float).copy())
                cache[_key(value)] = saved
                if 'initial_sample' not in record and _key(value) == x0_key:
                    trace._sample('baseline', 0, *saved)
            except Exception as error:
                trace._error('objective_observation', error)
            finally:
                trace.observed_overhead_seconds += time.perf_counter() - began
            return result

        def callback(xk: Any) -> None:
            began = time.perf_counter()
            try:
                record['accepted_iterations'] += 1
                # Exact keys prevent accidentally reporting a nearby trial point.
                objective, gradient = cache[_key(xk)]
                sample = trace._sample('iteration', record['accepted_iterations'], objective, gradient)
                now = time.perf_counter()
                if record['accepted_iterations'] % 100 == 0 or now - trace.last_log >= 20:
                    print(f"Solver pass {record['balance_pass']} iteration {record['accepted_iterations']}: "
                          f"objective={objective:.12g}, improvement={sample['improvement_from_initial']:.6g}, "
                          f"max population deviation={sample['population']['max_absolute_deviation_people']:.6f} people, "
                          f"{sample['pass_elapsed_seconds']:.2f}s", flush=True)
                    trace.last_log = now
            except Exception as error:
                trace._error('accepted_iteration', error)
            finally:
                trace.observed_overhead_seconds += time.perf_counter() - began

        observed_kwargs = dict(kwargs)
        observed_kwargs['callback'] = callback
        result = original_minimize(observed_fun, *args, **observed_kwargs)
        began = time.perf_counter()
        try:
            actual_limit = options.get('maxiter')
            optimizer = {
                'success': bool(result.success), 'status': int(result.status), 'message': str(result.message),
                'iterations': int(result.nit), 'function_evaluations': int(result.nfev),
                'iteration_limit_reached': actual_limit is not None and int(result.nit) >= int(actual_limit),
                'actual_maxiter': int(actual_limit) if actual_limit is not None else None,
            }
            record['inner_optimizer'] = optimizer
            if record['objective_evaluations'] != int(result.nfev):
                trace._error('function_evaluation_count', ValueError('Observed objective evaluations differ from OptimizeResult.nfev.'))
            if record['accepted_iterations'] != int(result.nit):
                trace._error('accepted_iteration_count', ValueError('Callback count differs from OptimizeResult.nit.'))
            objective, gradient = cache[_key(result.x)]
            if objective != float(result.fun) or not np.array_equal(gradient, np.asarray(result.jac)):
                raise ValueError('Cached terminal objective/gradient does not match OptimizeResult.')
            trace._sample('terminal', int(result.nit), objective, gradient, optimizer=optimizer)
        except Exception as error:
            trace._error('terminal_observation', error)
        finally:
            trace.observed_overhead_seconds += time.perf_counter() - began
        return result

    def observed_balance(*args: Any, **kwargs: Any) -> Any:
        record: dict[str, Any] = {'balance_pass': len(trace.passes) + 1,
                                  'objective_evaluations': 0, 'accepted_iterations': 0, 'errors': []}
        trace.passes.append(record)
        trace._current = record
        trace._pass_started = time.perf_counter()
        began = time.perf_counter()
        try:
            bound = balance_signature.bind(*args, **kwargs)
            bound.apply_defaults()
            pops = np.asarray(bound.arguments['pops'], dtype=float)
            targets = np.asarray(bound.arguments['targets'], dtype=float)
            total = float(pops.sum())
            if (not np.all(np.isfinite(pops)) or np.any(pops < 0)
                    or not np.array_equal(pops, np.rint(pops)) or total <= 0
                    or not np.all(np.isfinite(targets)) or abs(float(targets.sum()) - total) > 1e-6):
                raise ValueError('Trace requires finite nonnegative whole-person populations and targets conserving their total.')
            trace._targets = targets.copy()
            trace._total = int(total)
            record['requested_maxiter'] = int(bound.arguments['max_iter'])
        except Exception as error:
            trace._error('balance_inputs', error)
            trace._targets = None
            trace._total = None
        finally:
            trace.observed_overhead_seconds += time.perf_counter() - began
        try:
            return original_balance(*args, **kwargs)
        except Exception as error:
            record['solver_exception'] = {'type': type(error).__name__, 'message': str(error)}
            try:
                trace._write({'event': 'pass_exception', 'balance_pass': record['balance_pass'], **record['solver_exception']})
            except Exception as write_error:
                trace._error('pass_exception_write', write_error)
            raise
        finally:
            record['wall_seconds'] = time.perf_counter() - trace._pass_started
            try:
                trace._write({'event': 'pass_complete', 'balance_pass': record['balance_pass'],
                              'wall_seconds': record['wall_seconds'],
                              'objective_evaluations': record['objective_evaluations'],
                              'accepted_iterations': record['accepted_iterations'],
                              'inner_optimizer': record.get('inner_optimizer'),
                              'solver_exception': record.get('solver_exception')})
            except Exception as error:
                trace._error('pass_complete_write', error)
            optimizer = record.get('inner_optimizer', {})
            try:
                print(f"Solver balance pass {record['balance_pass']}: {record['wall_seconds']:.2f}s, "
                      f"inner iterations={optimizer.get('iterations', 'incomplete')}, "
                      f"success={optimizer.get('success', False)}", flush=True)
            except Exception as error:
                trace._error('pass_log', error)
            trace._current = None
            trace._targets = None
            trace._total = None

    _ACTIVE_TRACE = trace
    algorithm._balance_weights = observed_balance
    algorithm.minimize = observed_minimize
    try:
        yield trace
    finally:
        algorithm._balance_weights = original_balance
        algorithm.minimize = original_minimize
        _ACTIVE_TRACE = None
        trace.finished = time.perf_counter()
        try:
            stream.close()
        except Exception as error:
            trace._error('close', error)
