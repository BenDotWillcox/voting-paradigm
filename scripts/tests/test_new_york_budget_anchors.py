"""Controlled anchors preserve history and never retry ambiguous child attempts."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from districting import DistrictCenter, DistrictingResult, Unit
from districting.part_connectivity import PartGraph
from scripts import benchmark_new_york_budget_anchors as benchmark
from scripts import run_new_york_budget_anchors as launcher


def configuration(k):
    return {'seed': benchmark.SEED, 'max_outer_iterations': 80, 'inner_max_iterations': 300,
        'center_tolerance_m': 1e-4, 'max_rebalance_moves': 1000,
        'inner_optimization': {'max_line_search_steps': 100},
        'minimum_district_population_exact': f'1999923651/{100*k}'}


@pytest.mark.parametrize('k', [35, 42, 61])
def test_only_authorized_iteration_budget_changes(k):
    baseline = {'configuration': configuration(k)}
    expected = deepcopy(baseline)
    result = benchmark.configuration_for_experiment(baseline)
    assert result['inner_max_iterations'] == 1000
    result['inner_max_iterations'] = 300
    assert result == expected['configuration'] and baseline == expected


@pytest.mark.parametrize('k', [26, 34, 98])
def test_unauthorized_count_is_rejected(k, tmp_path):
    with pytest.raises(ValueError, match='requires K35/K42/K61'):
        benchmark.run(k, tmp_path)


@pytest.mark.parametrize('relative,k', [
    ('policies/new-york-links-v1/states/36/districts-35', 35),
    ('corrections/new-york-inner-budget-v1/states/36/districts-26', 35),
    ('corrections/new-york-inner-budget-anchors-v1/states/36/districts-42', 35),
    ('corrections/new-york-inner-budget-anchors-v1/states/36/districts-35/nested', 35),
])
def test_output_isolation(relative, k):
    with pytest.raises(ValueError, match='matching new anchor'):
        benchmark.validate_output(benchmark.SUITE / relative, k)


def test_previous_attempt_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'corrections/new-york-inner-budget-anchors-v1/states/36/districts-35'
    output.mkdir(parents=True)
    (output / 'benchmark.json').write_text('preserved')
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(35, output)
    assert (output / 'benchmark.json').read_text() == 'preserved'


def test_known_failed_baseline_pins_and_failed_passes():
    assert benchmark.BASELINE_REPORT_SHA256 == {
        35: '4336e1bda980a413fe280f1a8907a6337638f2743f7257cd20e5c4d46db621dd',
        42: '4c401a542d90f88e0070c88a7dd63b8d1ccbb0bd4113276803cdc20a933d4c45',
        61: 'fd1bf5e38f699181c04c8e76c7e18fc1de813575864d5be13dff7e92d4365be5'}
    assert benchmark.K26_REPORT_SHA256 == '6332da0dbe1f8fd202a6f281267407876ed458bed3806a482e3aeca46292b36b'
    assert benchmark.baseline_directory(61).name == 'districts-61'
    assert benchmark.reference_directory().name == 'districts-26'


@pytest.mark.parametrize('k', [35, 42, 61])
def test_measured_pipeline_uses_same_solver_call_and_own_baseline(k, tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path / 'suite')
    monkeypatch.setattr(benchmark, 'EXTRA_CODE', ())
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    paths = [benchmark.SUITE / f'states/36/districts-{k}/benchmark.json',
        benchmark.SUITE / 'diagnostics/new-york/diagnosis.json',
        tmp_path / '.cache/state-block-benchmark/source/36/tl_2020_36_tabblock20.zip']
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('preserved evidence')
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {p.relative_to(tmp_path).as_posix(): benchmark.sha256(p) for p in paths})
    source_hash = benchmark.sha256(paths[-1])
    connections = ({'kind': 'recorded-water-connection'}, {'kind': 'recorded-exclave-connection'})
    link_path = tmp_path / 'old-connections.json'
    benchmark.write_json(link_path, {'policy': benchmark.POLICY, 'connections': list(connections), 'source_sha256': source_hash})
    baseline = {'status': 'failed', 'configuration': configuration(k), 'code_sha256': {},
        'timed_pipeline_wall_seconds': 140, 'solver_progress': [], 'optimizer_failure': {},
        'recorded_connections': list(connections),
        'artifact_sha256': {'recorded-connections.json': benchmark.sha256(link_path)}}
    calls = []
    monkeypatch.setattr(benchmark, 'load_baseline', lambda count: calls.append(('baseline', count)) or baseline)
    monkeypatch.setattr(benchmark, 'load_reference', lambda: {'code_sha256': {}, 'timed_pipeline_wall_seconds': 1900})
    monkeypatch.setattr(benchmark, 'load_strict_baseline', lambda count: {
        'strict_report_path': 'suite/states/36/districts-26/benchmark.json',
        'strict_preflight_reused': True,
        'strict_suite_job': {'district_count': count, 'status': 'unsupported_topology'}})
    monkeypatch.setattr(benchmark, 'prepare_source', lambda *args: (tmp_path / 'source.shp', {'archive_sha256': source_hash}))
    populations = [0, 0] + [10] * k
    geoids = [f'36001000100{i:04d}' for i in range(len(populations))]
    units = [Unit(geoid, (1000. * i, 0.), population) for i, (geoid, population) in enumerate(zip(geoids, populations))]
    monkeypatch.setattr(benchmark, 'load_units', lambda *args: (units, dict(zip(geoids, populations)), {'projection': {'lon0': -74., 'lat0': 41.}}))
    physical_rows = [(), ()] + [tuple(j for j in (i-1, i+1) if 2 <= j < k+2) for i in range(2, k+2)]
    physical = PartGraph(tuple(physical_rows), tuple(range(k+2)))
    augmented_rows = list(physical_rows)
    augmented_rows[0], augmented_rows[1], augmented_rows[2] = (2,), (2,), (0, 1, 3)
    augmented = PartGraph(tuple(augmented_rows), tuple(range(k+2)))
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs: (physical, {}, {}))
    monkeypatch.setattr(benchmark, 'build_new_york_connections', lambda *args, **kwargs: (augmented, connections, {}))
    @contextmanager
    def trace(path):
        path.write_text('{"event":"terminal"}\n')
        value = SimpleNamespace(passes=[{'inner_optimizer': {'success': True, 'actual_maxiter': 1000}}], observation_ok=True)
        value.summary = lambda: {'observation_ok': True, 'passes': value.passes}
        yield value
    monkeypatch.setattr(benchmark, 'trace_optimizer', trace)
    labels = (0, 0, *range(k))
    def solve(*args, **kwargs):
        calls.append(('solve', args[1], kwargs))
        return DistrictingResult(centers=tuple(DistrictCenter(i, float(i), 0., 0.) for i in range(k)),
            assignments=dict(zip(geoids, labels)), populations={i:10 for i in range(k)},
            iterations=80, converged=False, max_population_imbalance=0)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', solve)
    def export(source, assignments, populations, output, **kwargs):
        assert kwargs['n_districts'] == k and kwargs['recorded_connections'] == connections
        output.mkdir(parents=True)
        result = {'strict_validation': {'passed': False},
            'connectivity_validation': {'passed': True, 'policy': benchmark.POLICY}}
        benchmark.write_json(output / 'map-manifest.json', result)
        return result
    monkeypatch.setattr(benchmark, 'export_state_block_maps', export)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda output, report: (output / 'index.html').write_text('map'))
    output = benchmark.SUITE / f'corrections/new-york-inner-budget-anchors-v1/states/36/districts-{k}'
    report = benchmark.run(k, output)
    assert calls == [('baseline', k), ('solve', k, {'seed': 20200955, 'max_outer_iterations': 80, 'inner_max_iterations': 1000})]
    assert report['comparison_baseline']['failed_policy_report_sha256'] == benchmark.BASELINE_REPORT_SHA256[k]
    assert report['comparison_baseline']['strict_report_path'].endswith('districts-26/benchmark.json')
    assert report['comparison_baseline']['strict_suite_job']['district_count'] == k
    assert report['comparison_baseline']['strict_preflight_reused'] is True
    assert report['completed_k26_reference']['reused_without_rerun'] is True
    assert report['completed_k26_reference']['original_pipeline_wall_seconds'] == 1900
    assert report['preservation_audit']['completed_k26_tree_byte_identical'] is True
    assert report['solver']['outer_iteration_limit_reached'] and not report['solver']['centers_converged']
    assert report['final_plan']['physical_part_components'] == [3] + [1] * (k-1)
    assert report['final_plan']['policy_part_components'] == [1] * k
    progress = json.loads((output / 'progress.json').read_text())
    assert progress['status'] == report['status'] and progress['active_phase'] is None


def _launcher_fixture(tmp_path, monkeypatch):
    output = tmp_path / 'suite'
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'OUTPUT', output)
    monkeypatch.setattr(launcher, 'state_execution_lock', lambda state: nullcontext())
    monkeypatch.setattr(benchmark, 'validate_output', lambda *args: None)
    monkeypatch.setattr(benchmark, 'load_baseline', lambda count: {'count': count})
    monkeypatch.setattr(benchmark, 'load_reference', lambda: {'code_sha256': {}, 'timed_pipeline_wall_seconds': 1900})
    monkeypatch.setattr(benchmark, 'EXTRA_CODE', ())
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {})
    starts, waits = [], []
    def popen(command, **kwargs):
        count = int(command[command.index('--district-count')+1])
        starts.append(count)
        def wait():
            waits.append(count)
            return 1 if count == 42 else 0
        return SimpleNamespace(pid=10000+count, wait=wait)
    monkeypatch.setattr(launcher.subprocess, 'Popen', popen)
    def validate(count, output, exit_code, **kwargs):
        assert len(starts) == len(waits), 'The parent must wait before validating or starting another child.'
        return {'status': 'failed' if count == 42 else 'complete_under_recorded_mixed_policy',
            'classification': 'verified_numerical_failure' if count == 42 else 'validated_complete_plan',
            'passed': True, 'benchmark_sha256': f'benchmark-{count}', 'progress_sha256': f'progress-{count}',
            'timed_pipeline_wall_seconds': 0}
    monkeypatch.setattr(launcher, 'validate_terminal_job', validate)
    return output, starts, waits


def test_launcher_is_serial_and_continues_verified_numerical_failure(tmp_path, monkeypatch):
    output, starts, waits = _launcher_fixture(tmp_path, monkeypatch)
    launcher.main()
    record = json.loads((output / 'run.json').read_text())
    assert starts == waits == [35, 42, 61]
    assert record['status'] == 'complete_with_numerical_failures'
    assert [row['pid'] for row in record['jobs']] == [10035, 10042, 10061]
    assert [row['exit_code'] for row in record['jobs']] == [0, 1, 0]
    assert record['completed_k26_reference']['reused_without_rerun'] is True
    assert all(row['terminal_validation']['passed'] for row in record['jobs'])
    assert record['finished_at'] and record['pid']
    with pytest.raises((FileExistsError, ValueError)):
        launcher.main()
    assert starts == [35, 42, 61], 'A second launch must never spawn a duplicate.'


def test_launcher_stops_on_ambiguous_terminal_child(tmp_path, monkeypatch):
    output, starts, waits = _launcher_fixture(tmp_path, monkeypatch)
    def reject(*args, **kwargs):
        raise ValueError('Terminal report missing')
    monkeypatch.setattr(launcher, 'validate_terminal_job', reject)
    with pytest.raises(ValueError, match='Terminal report missing'):
        launcher.main()
    record = json.loads((output / 'run.json').read_text())
    assert starts == waits == [35]
    assert record['status'] == 'stopped'
    assert [row['status'] for row in record['jobs']] == ['needs_inspection', 'pending', 'pending']


def test_launcher_waits_for_owned_child_after_metadata_failure(tmp_path, monkeypatch):
    output, starts, waits = _launcher_fixture(tmp_path, monkeypatch)
    original_write = launcher.write_json
    fail_once = [True]
    def write(path, data):
        if path.name == 'run.json' and any(job.get('status') == 'running' for job in data.get('jobs', [])) and fail_once[0]:
            fail_once[0] = False
            raise OSError('Forced sharing violation')
        original_write(path, data)
    monkeypatch.setattr(launcher, 'write_json', write)
    with pytest.raises(OSError, match='Forced sharing violation'):
        launcher.main()
    record = json.loads((output / 'run.json').read_text())
    assert starts == waits == [35]
    assert record['status'] == 'stopped'
    assert record['jobs'][0]['exit_code'] == 0 and record['jobs'][0]['status'] == 'needs_inspection'


def test_artifact_path_cannot_escape_child_directory(tmp_path):
    with pytest.raises(ValueError, match='escapes'):
        launcher.artifact_path(tmp_path / 'child', '../old/benchmark.json')


def _terminal_fixture(tmp_path, monkeypatch):
    output = tmp_path / 'child'
    output.mkdir()
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {})
    baseline = {'configuration': configuration(35), 'source': {'archive_sha256': 'source'},
        'recorded_connections': [{'kind': 'water'}, {'kind': 'exclave'}],
        'environment': {'python': 'fixed-python', 'packages': {'scipy': 'fixed'}},
        'artifact_sha256': {}}
    benchmark.write_json(output / 'recorded-connections.json', baseline['recorded_connections'])
    (output / 'optimizer-trace.jsonl').write_text('terminal numerical failure\n')
    baseline['artifact_sha256']['recorded-connections.json'] = benchmark.sha256(output / 'recorded-connections.json')
    optimizer = {'success': False, 'actual_maxiter': 1000, 'iterations': 1000,
        'function_evaluations': 1100, 'status': 1, 'message': 'iteration limit'}
    passes = [{'inner_optimizer': optimizer}]
    report = {'state_fips': '36', 'district_count': 35,
        'run_kind': 'new_york_inner_budget_anchors_experiment_v1', 'policy': benchmark.POLICY,
        'status': 'failed', 'finished_at': 'terminal', 'active_phase': None,
        'solver_progress': passes, 'configuration': benchmark.configuration_for_experiment(baseline),
        'comparison_baseline': {'failed_policy_report_sha256': benchmark.BASELINE_REPORT_SHA256[35]},
        'completed_k26_reference': {'report_sha256': benchmark.K26_REPORT_SHA256, 'reused_without_rerun': True},
        'source': baseline['source'], 'recorded_connections': baseline['recorded_connections'],
        'environment': baseline['environment'], 'code_sha256': {},
        'preservation_audit': {**{key: True for key in launcher.PRESERVATION_FLAGS}, 'protected_file_count': 0},
        'artifact_sha256': {name: benchmark.sha256(output / name) for name in ('recorded-connections.json', 'optimizer-trace.jsonl')},
        'optimizer_trace': {'observation_ok': True, 'telemetry_errors': [], 'passes': passes},
        'timed_pipeline_wall_seconds': 20., 'failed_phase': 'solve',
        'error': 'DistrictingOptimizationError: iteration limit',
        'optimizer_failure': {'plan_returned': False, 'balance_pass': 1, 'iterations': 1000,
            'function_evaluations': 1100, 'status': 1, 'message': 'iteration limit'}}
    progress = {'active_phase': None, 'status': 'failed', 'district_count': 35, 'solver_progress': passes}
    benchmark.write_json(output / 'preserved-file-inventory.json', {})
    benchmark.write_json(output / 'benchmark.json', report)
    benchmark.write_json(output / 'progress.json', progress)
    return output, baseline, report, progress


def test_terminal_validator_accepts_only_verified_numerical_failure(tmp_path, monkeypatch):
    output, baseline, _, _ = _terminal_fixture(tmp_path, monkeypatch)
    result = launcher.validate_terminal_job(35, output, 1, baseline=baseline, code={}, inventory={})
    assert result['passed'] and result['classification'] == 'verified_numerical_failure'
    assert result['benchmark_sha256'] == benchmark.sha256(output / 'benchmark.json')
    with pytest.raises(ValueError, match='operational or ambiguous'):
        launcher.validate_terminal_job(35, output, 0, baseline=baseline, code={}, inventory={})


@pytest.mark.parametrize('mutation,match', [
    ('telemetry', 'trace is incomplete'), ('operational', 'operational or ambiguous'),
    ('wrong_budget', 'changed settings'), ('preservation', 'preservation audit'),
    ('unfinished_progress', 'same terminal attempt'), ('artifact', 'artifact hash mismatch'),
])
def test_terminal_validator_stops_ambiguous_or_changed_evidence(mutation, match, tmp_path, monkeypatch):
    output, baseline, report, progress = _terminal_fixture(tmp_path, monkeypatch)
    if mutation == 'telemetry':
        report['optimizer_trace']['observation_ok'] = False
    elif mutation == 'operational':
        report['failed_phase'] = 'map_export'
    elif mutation == 'wrong_budget':
        report['configuration']['inner_max_iterations'] = 2000
    elif mutation == 'preservation':
        report['preservation_audit']['completed_k26_tree_byte_identical'] = False
    elif mutation == 'unfinished_progress':
        progress['active_phase'] = 'solve'
    elif mutation == 'artifact':
        (output / 'optimizer-trace.jsonl').write_text('changed')
    benchmark.write_json(output / 'benchmark.json', report)
    benchmark.write_json(output / 'progress.json', progress)
    with pytest.raises(ValueError, match=match):
        launcher.validate_terminal_job(35, output, 1, baseline=baseline, code={}, inventory={})


def test_terminal_validator_accepts_complete_only_after_independent_audits(tmp_path, monkeypatch):
    output, baseline, report, progress = _terminal_fixture(tmp_path, monkeypatch)
    report.update(status='complete_under_recorded_mixed_policy', failed_phase=None)
    progress['status'] = report['status']
    report['solver_progress'][0]['inner_optimizer']['success'] = True
    report.pop('optimizer_failure')
    manifest = {'connectivity_validation': {'policy': benchmark.POLICY, 'passed': True,
        'source_coverage_preserved_exactly': True, 'source_geometry_modified': False}}
    report['maps'] = manifest
    report['final_plan'] = {'all_districts_policy_connected': True, 'policy_part_components': [1]*35,
        'all_blocks_assigned_once': True, 'population_sum_matches_source': True, 'total_population': 20201249}
    for name in ('initial-solver-result.json', 'after-repair-result.json', 'solver-result.json',
                 'move-audit.json', 'maps/map-manifest.json', 'index.html'):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        benchmark.write_json(path, manifest if name == 'maps/map-manifest.json' else {})
        report['artifact_sha256'][name] = benchmark.sha256(path)
    benchmark.write_json(output / 'benchmark.json', report)
    benchmark.write_json(output / 'progress.json', progress)
    result = launcher.validate_terminal_job(35, output, 0, baseline=baseline, code={}, inventory={})
    assert result['classification'] == 'validated_complete_plan'
    report['final_plan']['policy_part_components'][0] = 2
    benchmark.write_json(output / 'benchmark.json', report)
    with pytest.raises(ValueError, match='acceptance audit'):
        launcher.validate_terminal_job(35, output, 0, baseline=baseline, code={}, inventory={})


@pytest.mark.parametrize('k', [35, 42, 61])
def test_changed_baseline_report_is_rejected_before_work(k, tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    path = benchmark.baseline_directory(k) / 'benchmark.json'
    path.parent.mkdir(parents=True)
    path.write_text('{"status":"tampered"}')
    with pytest.raises(ValueError, match='baseline report changed'):
        benchmark.load_baseline(k)


def test_changed_completed_reference_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    path = benchmark.reference_directory() / 'benchmark.json'
    path.parent.mkdir(parents=True)
    path.write_text('{"status":"changed"}')
    with pytest.raises(ValueError, match='K26 reference report changed'):
        benchmark.load_reference()


@pytest.mark.parametrize('k', [35, 42, 61])
def test_strict_manifest_reuse_resolves_existing_report_before_output(k, tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path / 'suite')
    benchmark.SUITE.mkdir()
    strict_path = benchmark.SUITE / 'states/36/districts-26/benchmark.json'
    strict_path.parent.mkdir(parents=True)
    benchmark.write_json(strict_path, {'state_fips': '36', 'district_count': 26, 'status': 'unsupported_topology'})
    benchmark.write_json(benchmark.SUITE / 'suite.json', {'states': [{'state_fips': '36', 'jobs': [
        {'district_count': count, 'status': 'unsupported_topology',
         'topology_report': 'states/36/districts-26/benchmark.json'} for count in benchmark.COUNTS]}]})
    # The historical strict batch deliberately wrote no separate reports for
    # these counts: the manifest reused one source-level topology rejection.
    assert not (benchmark.SUITE / f'states/36/districts-{k}/benchmark.json').exists()
    evidence = benchmark.load_strict_baseline(k)
    assert evidence['strict_suite_job']['district_count'] == k
    assert evidence['strict_preflight_reused'] is True
    assert evidence['strict_report_sha256'] == benchmark.sha256(strict_path)
    assert evidence['strict_report_path'].endswith('districts-26/benchmark.json')
    strict_path.unlink()
    monkeypatch.setattr(benchmark, 'load_baseline', lambda count: {})
    monkeypatch.setattr(benchmark, 'load_reference', lambda: {})
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    output = benchmark.SUITE / f'corrections/new-york-inner-budget-anchors-v1/states/36/districts-{k}'
    with pytest.raises(FileNotFoundError):
        benchmark.run(k, output)
    assert not output.exists(), 'Missing referenced strict evidence must fail before child output creation.'
