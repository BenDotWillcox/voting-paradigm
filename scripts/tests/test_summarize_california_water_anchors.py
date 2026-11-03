"""Reject active/misattributed anchor evidence and never publish failed maps."""
from copy import deepcopy
from contextlib import contextmanager
from fractions import Fraction
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import summarize_california_water_anchors as summary


def manifest():
    return {'status': 'complete', 'finished_at': '2026-10-25T10:00:00Z',
            'jobs': [{'district_count': k, 'status': summary.ACCEPTED,
                      'exit_code': 0, 'finished_at': '2026-10-25T09:00:00Z'} for k in summary.COUNTS]}


def test_accept_terminal_three_anchor_manifest():
    summary.verify_manifest(manifest())


@pytest.mark.parametrize('mutation', [
    lambda m: m.update(status='running'),
    lambda m: m.pop('finished_at'),
    lambda m: m['jobs'].pop(),
    lambda m: m['jobs'][0].update(district_count=52),
    lambda m: m['jobs'][0].update(exit_code=True),
    lambda m: m['jobs'][0].update(exit_code=1),
    lambda m: m['jobs'][0].pop('finished_at'),
    lambda m: m['jobs'][0].update(status='pending'),
    lambda m: m.update(status='complete_with_numerical_failures'),
])
def test_rejects_active_incomplete_or_contradictory_manifest(mutation):
    record = manifest()
    mutation(record)
    with pytest.raises(ValueError):
        summary.verify_manifest(record)


def test_accepts_numerical_failure_without_accepting_map(tmp_path):
    record = manifest()
    record['status'] = 'complete_with_numerical_failures'
    record['jobs'][1].update(status='failed', exit_code=1)
    summary.verify_manifest(record)
    result = summary.verify_plan(tmp_path, {'status': 'failed', 'error': 'inner iteration cap'}, {}, 83)
    assert result['accepted_plan'] is False
    assert not list(tmp_path.iterdir())


def test_stopped_suite_preserves_unstarted_work():
    record = manifest()
    record['status'] = 'stopped'
    record['jobs'][1:] = [{'district_count': 83, 'status': 'needs_inspection'},
                          {'district_count': 120, 'status': 'pending'}]
    summary.verify_manifest(record)
    for job in record['jobs'][1:]:
        row = summary.load_run(job['district_count'], {}, {}, job=job)
        assert row['accepted_plan'] is False
        assert row['map_url'] is None


def settings(k):
    threshold = Fraction(summary.pilot.TOTAL * 99, 100 * k)
    return {'seed': 20200955, 'max_outer_iterations': 80, 'inner_max_iterations': 1000,
            'center_tolerance_m': 1e-4, 'max_rebalance_moves': 1000,
            'root_eligibility_relative_band': .01, 'group_population_preflight_tolerance': .01,
            'minimum_district_population_for_root_classification': float(threshold),
            'minimum_district_population_exact': str(threshold),
            'inner_optimization': {'max_line_search_steps': 100}}


@pytest.mark.parametrize('k', [52, 69, 83, 120])
def test_only_per_anchor_population_threshold_changes(k):
    summary.verify_configuration(settings(k), settings(52), k)


@pytest.mark.parametrize('key,value', [('seed', 4), ('inner_max_iterations', 300),
                                    ('new_algorithm_setting', True),
                                    ('minimum_district_population_for_root_classification', 1),
                                    ('minimum_district_population_exact', '1/2')])
def test_changed_settings_rejected(key, value):
    config = settings(69)
    config[key] = value
    with pytest.raises(ValueError):
        summary.verify_configuration(config, settings(52), 69)


@pytest.mark.parametrize('filename', ['benchmark.json', 'terminal-report.json'])
@pytest.mark.parametrize('relative', [False, True])
def test_accepts_only_launcher_selected_hashed_terminal_report(tmp_path, filename, relative):
    path = tmp_path / filename
    path.write_text('{}', encoding='utf-8')
    job = {'terminal_validation': {'passed': True, 'report_path': filename if relative else str(path),
                                  'benchmark_sha256': summary.pilot.sha256(path)}}
    assert summary.selected_report_path(job, tmp_path) == path.resolve()


@pytest.mark.parametrize('change', ['unvalidated', 'wrong_path', 'wrong_hash'])
def test_rejects_ambiguous_or_modified_terminal_report(tmp_path, change):
    path = tmp_path / 'terminal-report.json'
    path.write_text('{}', encoding='utf-8')
    record = {'passed': True, 'report_path': str(path), 'benchmark_sha256': summary.pilot.sha256(path)}
    if change == 'unvalidated':
        record['passed'] = False
    elif change == 'wrong_path':
        record['report_path'] = str(tmp_path / 'unapproved.json')
    else:
        record['benchmark_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        summary.selected_report_path({'terminal_validation': record}, tmp_path)


def test_failed_and_unstarted_rows_never_render_a_map_link():
    reference = {'district_count': 52, 'house_size': 435, 'read_only_reference': True,
                 'status': 'failed', 'accepted_plan': False,
                 'failure': {'error': '<untrusted failure text>'}}
    data = {'reference_k52': reference,
            'runs': [dict(reference, district_count=k, house_size=summary.ANCHORS[k], read_only_reference=False) for k in summary.COUNTS],
            'scope': 'Anchor comparison', 'status': 'stopped',
            'preservation': {'files_rehashed': 20}, 'validation_note': 'Test data', 'limitations': []}
    page = summary.html(data)
    assert 'Open validated district map' not in page
    assert 'states/06/districts-' not in page
    assert page.count('no accepted map') == 4
    assert '<untrusted failure text>' not in page
    assert '&lt;untrusted failure text&gt;' in page


def test_summary_does_not_open_any_report_while_launcher_is_active(monkeypatch):
    reads = []
    def read(path):
        reads.append(path)
        return {'status': 'running'}
    monkeypatch.setattr(summary.pilot, 'read_json', read)
    with pytest.raises(ValueError, match='not terminal'):
        summary.summary()
    assert reads == [summary.OUTPUT / 'run.json']


def test_separate_serial_and_preparation_timing():
    record = {'preparation_wall_seconds': 3., 'serial_child_process_wall_seconds': 100.,
              'elapsed_wall_seconds': 110., 'jobs': [{'process_wall_seconds': 40.}, {'process_wall_seconds': 60.}]}
    assert summary.execution_timing(record)['serial_child_process_wall_seconds'] == 100.


@pytest.mark.parametrize('key,value', [('serial_child_process_wall_seconds', 99.),
                                    ('elapsed_wall_seconds', 102.),
                                    ('preparation_wall_seconds', -1.)])
def test_contradictory_execution_timing_is_rejected(key, value):
    record = {'preparation_wall_seconds': 3., 'serial_child_process_wall_seconds': 100.,
              'elapsed_wall_seconds': 110., 'jobs': [{'process_wall_seconds': 100.}]}
    record[key] = value
    with pytest.raises(ValueError):
        summary.execution_timing(record)


def policy_report(k):
    return {'island_policy_audit': {'district_count': k,
            'base_verification_district_count': 52, 'target_selection_verified_against_diagnosis': True,
            'connection_records_reused_unchanged': True, 'source_geometry_modified': False,
            'augmented_graph_connected': True, 'all_source_parts_reached': True,
            'population_selection': {'district_count': k, 'ideal_population': summary.pilot.TOTAL / k,
                'minimum_root_population': float(Fraction(summary.pilot.TOTAL * 99, 100*k)),
                'eligible_root_component_ids': [0], 'selected_link_ids': ['a', 'b', 'c', 'd', 'e', 'f'],
                'groups': [{'district_count': k, 'population': summary.pilot.TOTAL,
                            'component_ids': list(range(7))}]}}}


def test_target_policy_keeps_only_mainland_root_and_same_links():
    summary.verify_target_policy(policy_report(120), policy_report(52), 120)


@pytest.mark.parametrize('mutation', [
    lambda r: r['island_policy_audit'].update(district_count=52),
    lambda r: r['island_policy_audit'].update(connection_records_reused_unchanged=False),
    lambda r: r['island_policy_audit']['population_selection'].update(eligible_root_component_ids=[0, 2]),
    lambda r: r['island_policy_audit']['population_selection']['groups'][0].update(district_count=52),
    lambda r: r['island_policy_audit']['population_selection'].update(selected_link_ids=['changed']),
])
def test_rejects_reused_52_arithmetic_or_changed_policy(mutation):
    report = policy_report(120)
    mutation(report)
    with pytest.raises(ValueError):
        summary.verify_target_policy(report, policy_report(52), 120)


def process_manifest():
    return {'pid': 101, 'jobs': [{'status': summary.ACCEPTED, 'pid': 102,
                                 'launcher_pid': 102, 'child_pid': 103},
                                {'status': 'pending'}]}


def test_recorded_process_ids_include_parent_launcher_and_child_only():
    assert summary.recorded_process_ids(process_manifest()) == [101, 102, 103]


def launch_record():
    return {'launcher_pid': 100, 'script': 'scripts/run_california_water_anchors.py',
            'counts': [69, 83, 120], 'execution': 'serial_fresh_processes', 'output': str(summary.OUTPUT)}


def test_top_level_launch_record_adds_its_exact_pid():
    assert summary.recorded_process_ids(process_manifest(), launch_record()) == [100, 101, 102, 103]


@pytest.mark.parametrize('key,value', [('script', 'unrelated.py'), ('counts', [52]), ('launcher_pid', None)])
def test_unrelated_or_invalid_top_level_launch_record_is_rejected(key, value):
    launch = launch_record()
    launch[key] = value
    with pytest.raises(ValueError):
        summary.recorded_process_ids(process_manifest(), launch)


@pytest.mark.parametrize('mutation', [
    lambda m: m.pop('pid'),
    lambda m: m.update(pid=True),
    lambda m: m.update(pid=-1),
    lambda m: m.update(pid='101'),
    lambda m: m['jobs'][0].update(child_pid=None),
    lambda m: m['jobs'].append({'status': summary.ACCEPTED}),
])
def test_missing_or_invalid_recorded_pid_blocks_validation(mutation):
    record = process_manifest()
    mutation(record)
    with pytest.raises(ValueError):
        summary.recorded_process_ids(record)


def test_windows_query_is_limited_to_recorded_pids_and_specific_absence_error(monkeypatch):
    def run(args, **kwargs):
        script = args[-1]
        assert 'Get-CimInstance' not in script
        assert 'Get-Process -Id $recordedId -ErrorAction Stop' in script
        assert '@(101,102,103)' in script
        assert "-notlike 'NoProcessFoundForGivenId,*'" in script
        assert kwargs['check'] is True and kwargs['timeout'] == 30
        return SimpleNamespace(stdout=json.dumps([{'pid': n, 'active': False} for n in (101, 102, 103)]), stderr='')
    monkeypatch.setattr(summary.subprocess, 'run', run)
    assert all(not row['active'] for row in summary.windows_pid_status([101, 102, 103]))


@pytest.mark.parametrize('stdout,stderr', [
    ('[]', ''),
    ('[{"pid":101,"active":false},{"pid":101,"active":false}]', ''),
    ('[{"pid":101,"active":0},{"pid":102,"active":false}]', ''),
    ('[{"pid":101,"active":false},{"pid":102,"active":false}]', 'Access denied'),
    ('{"pid":101,"active":false}', ''),
    ('not json', ''),
])
def test_pid_query_errors_or_partial_results_fail_closed(monkeypatch, stdout, stderr):
    monkeypatch.setattr(summary.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=stdout, stderr=stderr))
    with pytest.raises(ValueError):
        summary.windows_pid_status([101, 102])


def test_process_query_failure_is_not_treated_as_absence(monkeypatch):
    def denied(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(summary.subprocess, 'run', denied)
    with pytest.raises(subprocess.CalledProcessError):
        summary.windows_pid_status([101])


def test_absent_recorded_processes_and_free_lock_are_both_required(monkeypatch):
    events = []
    @contextmanager
    def lock(state):
        events.append(('acquire', state))
        yield
        events.append(('release', state))
    monkeypatch.setattr(summary, 'WINDOWS', True)
    monkeypatch.setattr(summary, 'windows_pid_status', lambda pids: [{'pid': p, 'active': False} for p in pids])
    monkeypatch.setattr(summary, 'state_execution_lock', lock)
    result = summary.verify_no_active_children(process_manifest())
    assert result['recorded_pids_checked'] == [101, 102, 103]
    assert result['california_state_os_lock_acquired_and_released'] is True
    assert 'No full-system command-line inventory' in result['scope']
    assert events == [('acquire', '06'), ('release', '06')]


def test_active_recorded_process_blocks_before_lock_check(monkeypatch):
    monkeypatch.setattr(summary, 'WINDOWS', True)
    monkeypatch.setattr(summary, 'windows_pid_status', lambda pids: [{'pid': p, 'active': p == 103} for p in pids])
    monkeypatch.setattr(summary, 'state_execution_lock', lambda state: pytest.fail('Should not acquire lock while recorded child is active'))
    with pytest.raises(ValueError, match='103'):
        summary.verify_no_active_children(process_manifest())


def test_owned_state_lock_blocks_even_when_recorded_pids_are_absent(monkeypatch):
    @contextmanager
    def locked(state):
        raise RuntimeError('State06 is locked')
        yield
    monkeypatch.setattr(summary, 'WINDOWS', True)
    monkeypatch.setattr(summary, 'windows_pid_status', lambda pids: [{'pid': p, 'active': False} for p in pids])
    monkeypatch.setattr(summary, 'state_execution_lock', locked)
    with pytest.raises(RuntimeError, match='locked'):
        summary.verify_no_active_children(process_manifest())


def prelaunch_record():
    return {'phase': 'prelaunch', 'passed': 844, 'failed': 0, 'elapsed_seconds': 36.2,
            'command': 'venv/Scripts/python.exe -X utf8 -m pytest districting/tests scripts/tests -q',
            'recorded_at': '2026-10-25T16:35:17.171709+00:00'}


def test_accepts_original_prelaunch_schema_without_invented_status_field():
    record = prelaunch_record()
    before = deepcopy(record)
    audit = summary.verify_prelaunch_tests(record, '2026-10-25T16:35:26.7931058Z')
    assert audit['passed'] == 844 and audit['failed'] == 0
    assert audit['recorded_before_launch'] is True
    assert record == before and 'status' not in record


def test_accepts_explicit_passed_label_with_zero_failures():
    record = prelaunch_record()
    record.update(phase='before launch', status='passed')
    summary.verify_prelaunch_tests(record, '2026-10-25T16:35:26+00:00')


@pytest.mark.parametrize('key,value', [
    ('passed', 0), ('passed', True), ('passed', '844'),
    ('failed', 1), ('failed', False), ('failed', None),
    ('status', 'failed'), ('phase', 'after launch'), ('elapsed_seconds', -1),
    ('command', ''), ('recorded_at', '2026-10-25T16:35:27Z'),
    ('recorded_at', '2026-10-25T16:35:17'), ('recorded_at', 'not a date'),
])
def test_failed_ambiguous_or_late_prelaunch_evidence_is_rejected(key, value):
    record = prelaunch_record()
    record[key] = value
    with pytest.raises(ValueError):
        summary.verify_prelaunch_tests(record, '2026-10-25T16:35:26Z')
