"""Independent experiment checks must not turn diagnostics into valid plans."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from scripts import summarize_new_york_budget as summary


def reports():
    baseline = {
        'state_fips': '36', 'district_count': 26, 'house_sizes': [435],
        'policy': summary.checks.POLICY, 'status': 'failed', 'failed_phase': 'solve',
        'optimizer_failure': {'iterations': 300},
        'configuration': {'seed': 20200955, 'max_outer_iterations': 80, 'inner_max_iterations': 300,
                          'inner_optimization': {'max_line_search_steps': 100}},
        'source': {'archive_sha256': 'same-source'}, 'recorded_connections': [{'kind': 'water'}, {'kind': 'exclave'}],
        'code_sha256': {'districting/algorithm.py': 'same-numerics'},
        'environment': {'packages': {'scipy': 'same-version'}, 'python': 'same-interpreter'},
    }
    current = deepcopy(baseline)
    current['configuration']['inner_max_iterations'] = 1000
    current['code_sha256']['scripts/district_optimizer_trace.py'] = 'observer-code'
    return baseline, current


def trace_fixture(*, iterations: int = 2, success: bool = True):
    rows = []
    # Population imbalance intentionally worsens at an accepted step while the
    # objective improves. The reporter must not impose false monotonicity.
    vectors = [[10, 1]] + ([[11, 0]] * max(0, iterations - 1)) + [[6, 5]]
    objectives = [1.0 - i * .01 for i in range(iterations + 1)]
    for iteration, (vector, objective) in enumerate(zip(vectors, objectives)):
        targets = [6, 5]
        gradients = [(a - b) / 11 for a, b in zip(vector, targets)]
        deviations = [abs(a - 5.5) for a in vector]
        rows.append({
            'schema_version': 1, 'event': 'baseline' if iteration == 0 else 'iteration',
            'balance_pass': 1, 'iteration': iteration, 'objective_evaluations': iteration + 1,
            'objective': objective, 'improvement_from_initial': 1 - objective,
            'improvement_from_previous': 0 if iteration == 0 else objectives[iteration - 1] - objective,
            'elapsed_seconds': iteration + .1, 'pass_elapsed_seconds': iteration + .1,
            'normalized_gradient': gradients,
            'population': {
                'assigned_populations': vector, 'target_populations': targets, 'total_population': 11,
                'fractional_ideal_population': 5.5, 'max_absolute_deviation_people': max(deviations),
                'max_absolute_deviation_percent': max(deviations) * 100 / 5.5,
                'mean_absolute_deviation_people': sum(deviations) / 2,
                'max_absolute_target_deviation_people': max(abs(a - b) for a, b in zip(vector, targets)),
                'max_normalized_gradient': max(map(abs, gradients)), 'population_reconstruction_tolerance_people': 1e-6,
            },
        })
    last = deepcopy(rows[-1])
    last.update({'event': 'terminal', 'improvement_from_previous': 0,
                 'elapsed_seconds': iterations + .2, 'pass_elapsed_seconds': iterations + .2,
                 'optimizer': {'success': success, 'status': 0 if success else 1,
                               'message': 'converged' if success else 'limit', 'iterations': iterations,
                               'function_evaluations': iterations + 1, 'iteration_limit_reached': iterations >= 1000,
                               'actual_maxiter': 1000}})
    rows.append(last)
    payload = lambda row: {key: value for key, value in row.items() if key != 'schema_version'}
    report = {
        'observation_ok': True, 'telemetry_errors': [], 'recorded_elapsed_seconds': iterations + 1,
        'observed_overhead_seconds': .01,
        'passes': [{'balance_pass': 1, 'inner_optimizer': last['optimizer'],
                    'initial_sample': payload(rows[0]), 'terminal_sample': payload(last),
                    'accepted_iterations': iterations, 'objective_evaluations': iterations + 1,
                    'errors': [], 'wall_seconds': iterations + .3}],
    }
    return rows, report


def test_only_authorized_numerical_setting_changes():
    baseline, current = reports()
    result = summary.verify_fixed_experiment(baseline, current)
    assert result['only_numerical_setting_changed'] == {'inner_max_iterations': {'before': 300, 'after': 1000}}
    assert result['same_original_code_snapshot']


@pytest.mark.parametrize('mutation', [
    lambda r: r['configuration'].update(seed=20200956),
    lambda r: r['configuration']['inner_optimization'].update(max_line_search_steps=200),
    lambda r: r['code_sha256'].update({'districting/algorithm.py': 'changed'}),
    lambda r: r['source'].update(archive_sha256='changed'),
    lambda r: r['recorded_connections'][0].update(kind='exclave'),
    lambda r: r['environment']['packages'].update(scipy='new-version'),
    lambda r: r['environment'].update(python='new-interpreter'),
])
def test_rejects_uncontrolled_experiments(mutation):
    baseline, current = reports()
    mutation(current)
    with pytest.raises(ValueError):
        summary.verify_fixed_experiment(baseline, current)


def test_intermediate_imbalance_can_worsen_without_invalidating_trace():
    rows, report = trace_fixture()
    assert rows[1]['population']['max_absolute_deviation_people'] > rows[0]['population']['max_absolute_deviation_people']
    result = summary.verify_trace(rows, report, k=2, total=11)
    assert result['passed']
    assert result['passes'][0]['terminal_max_deviation_people'] == .5
    assert result['passes'][0]['terminal_max_deviation_percent'] == pytest.approx(.5 / 5.5 * 100)
    assert 'intermediate point assignments' in result['scope']
    assert 'accepted_plan' not in result  # No fabricated acceptance classification.


def test_failure_keeps_diagnostic_terminal_population_not_acceptance():
    rows, report = trace_fixture(success=False)
    result = summary.verify_trace(rows, report, k=2, total=11)
    assert result['all_inner_passes_succeeded'] is False
    assert result['passes'][0]['terminal_max_deviation_people'] == .5
    assert 'accepted_plan' not in result


def test_original_budget_marker_is_new_run_observation():
    rows, report = trace_fixture(iterations=302)
    result = summary.verify_trace(rows, report, k=2, total=11)
    data = result['passes'][0]
    assert data['at_original_budget']['iteration'] == 300
    assert data['objective_improvement_after_original_budget'] == pytest.approx(.02)
    assert data['max_deviation_people_at_original_budget'] == 5.5


@pytest.mark.parametrize('mutate', [
    lambda rows, report: rows[1].update(improvement_from_initial=555),
    lambda rows, report: rows[1].update(objective=float('nan')),
    lambda rows, report: rows[1].update(iteration=2),
    lambda rows, report: rows[1].update(elapsed_seconds=-1),
    lambda rows, report: rows[1]['population'].update(max_absolute_deviation_people=0),
    lambda rows, report: rows[1]['population'].update(max_absolute_deviation_percent=0),
    lambda rows, report: rows[1]['population'].update(total_population=12),
    lambda rows, report: rows[1]['population'].update(assigned_populations=[11, 1]),
    lambda rows, report: rows[1]['population'].update(target_populations=[5, 6]),
    lambda rows, report: rows[-1]['optimizer'].update(actual_maxiter=1001),
    lambda rows, report: report.update(observation_ok=False),
    lambda rows, report: report.update(observed_overhead_seconds=-1),
    lambda rows, report: report.update(observed_overhead_seconds=float('nan')),
    lambda rows, report: report.update(recorded_elapsed_seconds=float('inf')),
    lambda rows, report: report['passes'][0].update(accepted_iterations=300),
    lambda rows, report: rows.append({'schema_version': 1, 'event': 'telemetry_error'}),
])
def test_inconsistent_trace_is_rejected(mutate):
    rows, report = trace_fixture()
    mutate(rows, report)
    with pytest.raises(ValueError):
        summary.verify_trace(rows, report, k=2, total=11)


def test_first_pass_must_match_baseline_numerical_prefix():
    rows, report = trace_fixture()
    trace = summary.verify_trace(rows, report, k=2, total=11)
    baseline = {'solver_progress': [{'balance_pass': 1, 'inner_optimizer': deepcopy(rows[-1]['optimizer'])}]}
    assert summary.verify_first_pass(baseline, trace)['matched']
    baseline['solver_progress'][0]['inner_optimizer']['iterations'] = 300
    with pytest.raises(ValueError, match='prefix'):
        summary.verify_first_pass(baseline, trace)


def test_process_manifest_must_be_terminal_and_match_report(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, 'OUTPUT', tmp_path)
    benchmark = tmp_path / 'benchmark.json'
    benchmark.write_text('{}')
    process = {'status': 'finished', 'finished_at': '2026-10-23', 'exit_code': 1,
               'benchmark_sha256': summary.checks.sha256(benchmark), 'process_wall_seconds': 12}
    path = tmp_path / 'process.json'
    path.write_text(json.dumps(process))
    report = {'status': 'failed', 'timed_pipeline_wall_seconds': 10}
    assert summary.verify_execution(report, benchmark)['exit_code'] == 1
    process['status'] = 'running'
    path.write_text(json.dumps(process))
    with pytest.raises(ValueError, match='terminal process'):
        summary.verify_execution(report, benchmark)


def test_viewer_cannot_break_out_of_data_script():
    result = summary.viewer({'note': '</script><script>alert(1)</script>'})
    assert '\\u003c/script>' in result
    assert '__EXPERIMENT_DATA__' not in result
    assert 'Compare objective improvement' in result
    assert 'Original 300-iteration budget' in result
