"""Serial admission, child ownership and metadata failures never rerun solvers."""
from contextlib import nullcontext
import json
from types import SimpleNamespace

import pytest

from scripts import run_california_water_anchors as launcher


def fixture(tmp_path, monkeypatch):
    output = tmp_path / 'new-suite'
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'OUTPUT', output)
    monkeypatch.setattr(launcher, 'state_execution_lock', lambda state: nullcontext())
    b = launcher.benchmark
    monkeypatch.setattr(b, 'validate_output', lambda *args: None)
    monkeypatch.setattr(b, 'load_reference', lambda: {'code_sha256': {}, 'timed_pipeline_wall_seconds': 2274.55})
    monkeypatch.setattr(b, 'EXTRA_CODE', ())
    monkeypatch.setattr(b, 'protected_inventory', lambda: {})
    events = []
    def popen(command, **kwargs):
        count = int(command[command.index('--district-count') + 1])
        events.append(('start', count))
        def wait():
            events.append(('wait', count))
            return 1 if count == 83 else 0
        assert kwargs['stdout'] is not None and kwargs['stderr'] == launcher.subprocess.STDOUT
        if launcher.os.name == 'nt':
            assert kwargs['creationflags'] == launcher.subprocess.CREATE_NO_WINDOW
        return SimpleNamespace(pid=count + 10000, wait=wait)
    monkeypatch.setattr(launcher.subprocess, 'Popen', popen)
    def validate(count, output, exit_code, **kwargs):
        assert events[-1] == ('wait', count)
        return {'status': 'failed' if count == 83 else launcher.COMPLETE,
                'classification': 'verified_numerical_failure' if count == 83 else 'validated_complete_plan',
                'benchmark_sha256': 'report', 'progress_sha256': 'progress',
                'timed_pipeline_wall_seconds': 0, 'passed': True, 'report_path': 'benchmark.json'}
    monkeypatch.setattr(launcher, 'validate_terminal_job', validate)
    return output, events


def test_serial_queue_waits_and_continues_only_verified_numerical_failure(tmp_path, monkeypatch):
    output, events = fixture(tmp_path, monkeypatch)
    launcher.main()
    assert events == [(action, k) for k in (69, 83, 120) for action in ('start', 'wait')]
    data = json.loads((output / 'run.json').read_text())
    assert data['status'] == 'complete_with_numerical_failures'
    assert data['completed_k52_reference']['reused_without_rerun']
    assert all(job['terminal_validation']['passed'] for job in data['jobs'])
    assert data['jobs'][1]['exit_code'] == 1


def test_duplicate_admission_cannot_launch_children(tmp_path, monkeypatch):
    output, events = fixture(tmp_path, monkeypatch)
    output.mkdir()
    (output / 'run.json').write_text('preserved')
    with pytest.raises(FileExistsError):
        launcher.main()
    assert not events and (output / 'run.json').read_text() == 'preserved'


def test_ambiguous_child_stops_without_starting_next_count(tmp_path, monkeypatch):
    output, events = fixture(tmp_path, monkeypatch)
    def fail(*args, **kwargs):
        raise ValueError('polygon acceptance unclear')
    monkeypatch.setattr(launcher, 'validate_terminal_job', fail)
    with pytest.raises(ValueError, match='unclear'):
        launcher.main()
    assert events == [('start', 69), ('wait', 69)]
    data = json.loads((output / 'run.json').read_text())
    assert data['status'] == 'stopped' and data['jobs'][0]['status'] == 'needs_inspection'
    assert data['jobs'][1]['status'] == 'pending'


def test_metadata_error_after_launch_still_waits_for_child(tmp_path, monkeypatch):
    output, events = fixture(tmp_path, monkeypatch)
    original = launcher.write_json
    def write(path, data):
        if path.name == 'run.json' and data['jobs'][0]['status'] == 'running':
            raise PermissionError('sharing violation')
        return original(path, data)
    monkeypatch.setattr(launcher, 'write_json', write)
    with pytest.raises(PermissionError):
        launcher.main()
    assert events == [('start', 69), ('wait', 69)]
    data = json.loads((output / 'run.json').read_text())
    assert data['jobs'][0]['exit_code'] == 0 and data['status'] == 'stopped'


def test_terminal_manifest_failure_leaves_exclusive_emergency_evidence(tmp_path, monkeypatch):
    output, events = fixture(tmp_path, monkeypatch)
    original = launcher.write_json
    def write(path, data):
        if path.name == 'run.json' and data.get('finished_at'):
            raise PermissionError('terminal sharing violation')
        return original(path, data)
    monkeypatch.setattr(launcher, 'write_json', write)
    with pytest.raises(PermissionError):
        launcher.main()
    emergency = list(output.glob('emergency-*.json'))
    assert len(emergency) == 1
    data = json.loads(emergency[0].read_text())
    assert data['status'] == 'complete_with_numerical_failures' and data['finished_at']
    assert data['manifest_write_error'].startswith('PermissionError')
    assert len(events) == 6


def test_artifact_escape_rejected(tmp_path):
    with pytest.raises(ValueError, match='escapes'):
        launcher.artifact_path(tmp_path / 'child', '../older/benchmark.json')


def terminal_fixture(tmp_path, monkeypatch):
    b = launcher.benchmark
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(b, 'protected_inventory', lambda: {})
    monkeypatch.setattr(b, 'configuration_for_run', lambda count, **kwargs: {'inner_max_iterations': 1000, 'district_count': count,
        'minimum_district_population_for_root_classification': 39_538_223/count*.99})
    output = tmp_path / 'child'
    output.mkdir()
    reference = {'source': {'archive_sha256': 'source'}, 'water_connections': [{'id': 'fixed'}],
                 'environment': {'python': 'same', 'packages': {}}, 'artifact_sha256': {}}
    launcher.write_json(output / 'water-connections.json', reference['water_connections'])
    (output / 'optimizer-trace.jsonl').write_text('trace')
    reference['artifact_sha256']['water-connections.json'] = launcher.sha256(output / 'water-connections.json')
    optimizer = {'success': False, 'actual_maxiter': 1000, 'iterations': 1000,
                 'function_evaluations': 1100, 'status': 1, 'message': 'budget exhausted'}
    passes = [{'inner_optimizer': optimizer}]
    preservation = {key: True for key in ('all_original_strict_files_byte_identical',
        'all_original_diagnostic_files_byte_identical', 'national_suite_byte_identical',
        'source_archive_byte_identical', 'run_code_unchanged', 'completed_k52_tree_byte_identical',
        'water_connections_byte_identical_to_k52')}
    report = {'state_fips': '06', 'district_count': 69, 'run_kind': 'california_population_aware_water_anchors_v1',
              'policy': b.POLICY, 'status': 'failed', 'finished_at': 'done', 'active_phase': None,
              'solver_progress': passes, 'configuration': b.configuration_for_run(69),
              'completed_k52_reference': {'report_sha256': b.REFERENCE_REPORT_SHA256, 'reused_without_rerun': True},
              'water_connections_byte_identical_to_k52': True, 'source': reference['source'],
              'water_connections': reference['water_connections'], 'environment': reference['environment'],
              'code_sha256': {}, 'preservation_audit': {**preservation, 'protected_file_count': 0},
              'artifact_sha256': {name: launcher.sha256(output / name) for name in ('water-connections.json', 'optimizer-trace.jsonl')},
              'optimizer_trace': {'observation_ok': True, 'telemetry_errors': [], 'passes': passes},
              'timed_pipeline_wall_seconds': 20., 'peak_process_working_set_bytes': 1000,
              'failed_phase': 'solve', 'error': 'DistrictingOptimizationError: budget exhausted',
              'optimizer_failure': {'plan_returned': False, 'balance_pass': 1, **{key: optimizer[key] for key in ('iterations', 'function_evaluations', 'status', 'message')}}}
    report['configuration_sha256'] = b._digest(report['configuration'])
    report['final_progress_snapshot_written'] = True
    report['island_policy_audit'] = {'district_count': 69, 'base_verification_district_count': 52,
        'target_selection_verified_against_diagnosis': True, 'connection_records_reused_unchanged': True,
        'population_selection': {'district_count': 69, 'ideal_population': 39_538_223/69,
            'minimum_root_population': 39_538_223/69*.99, 'eligible_root_component_ids': [0],
            'selected_link_ids': list(launcher.AUTHORIZED_CANDIDATE_IDS),
            'groups': [{'district_count': 69, 'population': 39_538_223, 'component_ids': list(range(7))}]},
        'wrapper_provenance': {'target_district_count': 69, 'base_verification_district_count': 52,
            'base_builder_sha256': launcher.PINNED_BASE_MODULE_SHA256}}
    progress = {'status': 'failed', 'district_count': 69, 'active_phase': None, 'solver_progress': passes}
    launcher.write_json(output / 'preserved-file-inventory.json', {})
    return output, reference, report, progress


def save_terminal(output, report, progress):
    launcher.write_json(output / 'benchmark.json', report)
    launcher.write_json(output / 'progress.json', progress)


def test_verified_numerical_failure_is_terminal_not_a_valid_map(tmp_path, monkeypatch):
    output, reference, report, progress = terminal_fixture(tmp_path, monkeypatch)
    save_terminal(output, report, progress)
    result = launcher.validate_terminal_job(69, output, 1, reference=reference, code={}, inventory={})
    assert result['classification'] == 'verified_numerical_failure' and result['report_path'] == 'benchmark.json'


@pytest.mark.parametrize('mutation', ['settings', 'links', 'progress', 'physical_audit', 'trace', 'memory', 'preservation', 'artifact', 'policy_count', 'policy_threshold'])
def test_terminal_validator_refuses_changed_or_ambiguous_evidence(mutation, tmp_path, monkeypatch):
    output, reference, report, progress = terminal_fixture(tmp_path, monkeypatch)
    if mutation == 'settings': report['configuration']['inner_max_iterations'] = 2000
    if mutation == 'links': report['water_connections'] = [{'id': 'changed'}]
    if mutation == 'progress': progress['active_phase'] = 'solve'
    if mutation == 'physical_audit': report['failed_phase'] = 'polygon_validation'
    if mutation == 'trace': report['optimizer_trace']['observation_ok'] = False
    if mutation == 'memory': report['peak_process_working_set_bytes'] = 0
    if mutation == 'preservation': report['preservation_audit']['completed_k52_tree_byte_identical'] = False
    if mutation == 'artifact': (output / 'optimizer-trace.jsonl').write_text('changed')
    if mutation == 'policy_count': report['island_policy_audit']['population_selection']['district_count'] = 52
    if mutation == 'policy_threshold': report['island_policy_audit']['population_selection']['minimum_root_population'] = 39_538_223/52*.99
    save_terminal(output, report, progress)
    with pytest.raises(ValueError):
        launcher.validate_terminal_job(69, output, 1, reference=reference, code={}, inventory={})


def test_completed_plan_requires_independent_polygon_acceptance(tmp_path, monkeypatch):
    output, reference, report, progress = terminal_fixture(tmp_path, monkeypatch)
    report['status'] = progress['status'] = launcher.COMPLETE
    report['solver_progress'][0]['inner_optimizer']['success'] = True
    manifest = {'connectivity_validation': {'policy': launcher.benchmark.POLICY, 'passed': True,
        'source_coverage_preserved_exactly': True, 'source_geometry_modified': False,
        'districts': [{'district_id': i, 'connected_components_after_links': 1} for i in range(69)]}}
    report['maps'] = manifest
    report['final_plan'] = {'all_districts_policy_connected': True, 'policy_part_components': [1]*69,
        'all_blocks_assigned_once': True, 'population_sum_matches_source': True, 'total_population': 39_538_223}
    for name in ('initial-solver-result.json', 'after-repair-result.json', 'solver-result.json',
                 'move-audit.json', 'maps/map-manifest.json', 'index.html'):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_json(path, manifest if name == 'maps/map-manifest.json' else {})
        report['artifact_sha256'][name] = launcher.sha256(path)
    save_terminal(output, report, progress)
    assert launcher.validate_terminal_job(69, output, 0, reference=reference, code={}, inventory={})['classification'] == 'validated_complete_plan'
    report['final_plan']['policy_part_components'][10] = 2
    save_terminal(output, report, progress)
    with pytest.raises(ValueError, match='acceptance'):
        launcher.validate_terminal_job(69, output, 0, reference=reference, code={}, inventory={})


def test_explicit_emergency_report_can_replace_stale_running_metadata(tmp_path, monkeypatch):
    output, reference, report, progress = terminal_fixture(tmp_path, monkeypatch)
    save_terminal(output, {'status': 'running'}, progress)
    report.update(authoritative_terminal_report='terminal-report.json', terminal_report_write_error='PermissionError: locked')
    launcher.write_json(output / 'terminal-report.json', report)
    result = launcher.validate_terminal_job(69, output, 1, reference=reference, code={}, inventory={})
    assert result['report_path'] == 'terminal-report.json'
