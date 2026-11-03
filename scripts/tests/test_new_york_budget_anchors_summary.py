from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import summarize_new_york_budget_anchors as summary


def reports(k=35):
    old = {'state_fips': '36', 'district_count': k, 'house_sizes': [summary.ANCHORS[k]],
           'policy': summary.checks.POLICY, 'status': 'failed', 'failed_phase': 'solve',
           'configuration': {'inner_max_iterations': 300, 'seed': 20200955, 'max_outer_iterations': 80},
           'optimizer_failure': {'iterations': 300, 'plan_returned': False},
           'source': {'archive_sha256': 'source'}, 'recorded_connections': [{'kind': 'water'}, {'kind': 'exclave'}],
           'environment': {'python': 'same-python', 'packages': {'scipy': 'same-scipy'}},
           'code_sha256': {'districting/algorithm.py': 'fixed-numerics'}}
    new = deepcopy(old)
    new['configuration']['inner_max_iterations'] = 1000
    new['code_sha256']['scripts/new_observer.py'] = 'observer'
    return old, new


@pytest.mark.parametrize('k', [26, 35, 42, 61])
def test_own_anchor_and_only_budget_change(k):
    old, new = reports(k)
    assert summary.verify_comparison(old, new, k)['only_setting_changed'] == {'inner_max_iterations': [300, 1000]}


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(district_count=26),
    lambda r: r.update(house_sizes=[435]),
    lambda r: r.update(state_fips='06'),
    lambda r: r.update(policy='water-only'),
    lambda r: r['configuration'].update(seed=2),
    lambda r: r['configuration'].update(max_outer_iterations=1000),
    lambda r: r['source'].update(archive_sha256='changed'),
    lambda r: r['code_sha256'].update({'districting/algorithm.py': 'changed'}),
    lambda r: r['environment'].update(python='changed'),
    lambda r: r['environment']['packages'].update(scipy='changed'),
    lambda r: r['recorded_connections'][1].update(kind='water'),
])
def test_rejects_uncontrolled_or_wrong_anchor_run(mutate):
    old, new = reports()
    mutate(new)
    with pytest.raises(ValueError):
        summary.verify_comparison(old, new, 35)


def optimizer(iterations, *, success=True, evaluations=399):
    return {'success': success, 'status': 0 if success else 1,
            'message': 'ftol' if success else 'limit', 'iterations': iterations,
            'function_evaluations': evaluations, 'iteration_limit_reached': not success}


def prefix_case(k):
    successful = [] if k == 61 else [{'balance_pass': 1, 'inner_optimizer': optimizer(180, evaluations=200)}]
    fail_index = 1 if k == 61 else 2
    old = {'solver_progress': [*successful, {'balance_pass': fail_index, 'inner_optimizer': optimizer(300, success=False)}],
           'optimizer_failure': {'balance_pass': fail_index, 'function_evaluations': 399}}
    passes = [{'optimizer': row['inner_optimizer']} for row in successful]
    passes.append({'optimizer': optimizer(500, evaluations=620), 'at_original_budget': {'objective_evaluations': 399},
                   'objective_improvement_after_original_budget': .0001, 'terminal_max_deviation_people': 3.5})
    return old, {'passes': passes}


def test_k61_failed_first_pass_may_now_succeed_after_300():
    old, trace = prefix_case(61)
    result = summary.verify_prefix(old, trace)
    assert result['matched_successful_pass_count'] == 0
    assert result['additional_iterations'] == 200
    assert result['terminal_inner_success']
    assert result['new_run_checkpoint_available']


def test_successful_prior_passes_retain_counters():
    old, trace = prefix_case(35)
    assert summary.verify_prefix(old, trace)['matched_successful_pass_count'] == 1
    trace['passes'][0]['optimizer'] = optimizer(181, evaluations=200)
    with pytest.raises(ValueError, match='Previously successful'):
        summary.verify_prefix(old, trace)


def test_new_i300_counter_must_match_original_failed_pass():
    old, trace = prefix_case(61)
    trace['passes'][0]['at_original_budget']['objective_evaluations'] = 400
    with pytest.raises(ValueError, match='evaluation count'):
        summary.verify_prefix(old, trace)


def test_failure_never_becomes_accepted_from_leftover_metrics(tmp_path):
    report = {'status': 'failed', 'failed_phase': 'solve', 'error': 'iteration cap',
              'solver_progress': [], 'final_plan': {'fabricated': 'stale'}}
    result = summary.verify_plan(tmp_path, report, {}, 35)
    assert result['accepted_plan'] is False
    assert 'final_plan' not in result
    assert result['failure']['accepted_completed_map'] is False


def test_running_plan_is_not_terminal(tmp_path):
    with pytest.raises(ValueError, match='not terminal'):
        summary.verify_plan(tmp_path, {'status': 'running'}, {}, 35)


def suite_case(tmp_path, monkeypatch, *, failed=False):
    monkeypatch.setattr(summary, 'ROOT', tmp_path)
    rows, jobs = [], []
    for k in summary.COUNTS:
        directory = tmp_path / str(k)
        directory.mkdir()
        (directory / 'progress.json').write_text('{}')
        accepted = not (failed and k == 61)
        status = summary.ACCEPTED if accepted else 'failed'
        rows.append({'district_count': k, 'accepted_plan': accepted, 'status': status, 'benchmark_sha256': str(k),
                     'benchmark_path': f'{k}/benchmark.json', 'timed_pipeline_wall_seconds': 10,
                     'code_sha256': {'code.py': 'code'}, 'baseline': {'benchmark_sha256': 'baseline-'+str(k)}})
        progress_sha = summary.checks.sha256(directory / 'progress.json')
        jobs.append({'district_count': k, 'status': status, 'finished_at': 'now', 'exit_code': 0 if accepted else 1,
                     'benchmark_sha256': str(k), 'process_wall_seconds': 11,
                     'progress_sha256': progress_sha, 'terminal_validation': {'passed': True,
                         'classification': 'validated_complete_plan' if accepted else 'verified_numerical_failure',
                         'benchmark_sha256': str(k), 'progress_sha256': progress_sha}})
    manifest = {'status': 'complete_with_numerical_failures' if failed else 'complete', 'finished_at': 'now', 'jobs': jobs,
                'code_sha256': {'code.py': 'code'}, 'baseline_report_sha256': {str(k): 'baseline-'+str(k) for k in summary.COUNTS}}
    return manifest, rows


@pytest.mark.parametrize('failed', [False, True])
def test_terminal_suite_distinguishes_failures(tmp_path, monkeypatch, failed):
    manifest, rows = suite_case(tmp_path, monkeypatch, failed=failed)
    assert summary.verify_execution(manifest, rows)['status'] == manifest['status']


@pytest.mark.parametrize('mutate', [
    lambda m: m.update(status='running'),
    lambda m: m['jobs'][0].update(status='pending'),
    lambda m: m['jobs'][0].update(exit_code=1),
    lambda m: m['jobs'][0].update(benchmark_sha256='changed'),
    lambda m: m['jobs'][0].update(progress_sha256='changed'),
    lambda m: m['jobs'][0].update(district_count=26),
    lambda m: m['jobs'][0].update(process_wall_seconds=float('nan')),
    lambda m: m['jobs'][0].update(terminal_validation={'passed': False}),
    lambda m: m['jobs'][0]['terminal_validation'].update(classification='verified_numerical_failure'),
    lambda m: m['code_sha256'].update({'code.py': 'different'}),
    lambda m: m['baseline_report_sha256'].update({'35': 'wrong-baseline'}),
])
def test_suite_rejects_missing_wrong_or_unverified_child(tmp_path, monkeypatch, mutate):
    manifest, rows = suite_case(tmp_path, monkeypatch)
    mutate(manifest)
    with pytest.raises(ValueError):
        summary.verify_execution(manifest, rows)


def test_complete_suite_cannot_hide_numerical_failure(tmp_path, monkeypatch):
    manifest, rows = suite_case(tmp_path, monkeypatch, failed=True)
    manifest['status'] = 'complete'
    with pytest.raises(ValueError, match='contains failed'):
        summary.verify_execution(manifest, rows)
