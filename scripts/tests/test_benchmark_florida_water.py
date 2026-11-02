"""Florida first attempts preserve evidence and fail closed on invalid outcomes."""
from contextlib import contextmanager, nullcontext
from fractions import Fraction
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from districting import DistrictCenter, DistrictingOptimizationError, DistrictingResult, Unit
from districting import algorithm
from districting.part_connectivity import PartGraph
from scripts import benchmark_florida_water as benchmark


@pytest.mark.parametrize('count', benchmark.COUNTS)
def test_anchor_configuration_keeps_numeric_settings_fixed(count):
    configuration = benchmark.configuration_for_run(count)
    minimum = Fraction(21_538_187, count) * Fraction(99, 100)
    assert configuration['minimum_district_population_exact'] == str(minimum)
    assert configuration['minimum_district_population_for_root_classification'] == float(minimum)
    assert {key: configuration[key] for key in ('seed', 'max_outer_iterations',
        'inner_max_iterations', 'center_tolerance_m', 'max_rebalance_moves')} == {
        'seed': 20200955, 'max_outer_iterations': 80, 'inner_max_iterations': 1000,
        'center_tolerance_m': 1e-4, 'max_rebalance_moves': 1000}
    original = benchmark.configuration_for_run(28)
    assert {key for key in configuration if configuration[key] != original[key]} == (
        set() if count == 28 else {'minimum_district_population_exact',
                                  'minimum_district_population_for_root_classification'})


def test_inventory_protects_original_trees_but_excludes_new_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path / 'suite')
    paths = [benchmark.SUITE / 'suite.json', benchmark.SUITE / 'states/12/districts-28/benchmark.json',
        benchmark.SUITE / 'states/12/preserved-extra.bin',
        benchmark.SUITE / 'diagnostics/florida/diagnosis.json',
        benchmark.SUITE / 'diagnostics/florida/nested/context.json',
        tmp_path / 'prompts/florida-topology-diagnosis.json',
        tmp_path / '.cache/state-block-benchmark/source/12/tl_2020_12_tabblock20.zip']
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'original evidence')
    active = benchmark.SUITE / 'policies/florida-water-v1/run.json'
    active.parent.mkdir(parents=True)
    active.write_text('running')
    inventory = benchmark.protected_inventory()
    assert set(inventory) == {path.relative_to(tmp_path).as_posix() for path in paths}
    paths[4].write_text('changed diagnostic')
    assert benchmark.protected_inventory() != inventory


@pytest.mark.parametrize('count', benchmark.COUNTS)
def test_baseline_reuses_strict_preflight_without_inventing_a_solved_plan(count, tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    baseline = benchmark.load_strict_baseline(count)
    assert baseline['strict_report_path'].endswith('states/12/districts-28/benchmark.json')
    assert baseline['strict_preflight_reused'] is (count != 28)
    assert baseline['strict_solver_ran'] is False
    assert baseline['controlled_inner_budget_comparison'] is False
    assert baseline['strict_suite_job']['district_count'] == count
    assert baseline['strict_pipeline_wall_seconds'] == 119.7


def test_baseline_rejects_a_solved_or_misdirected_original(tmp_path, monkeypatch):
    *_, required = _fixture(tmp_path, monkeypatch)
    original = json.loads(required[0].read_text())
    original['solver_progress'] = [{'returned': True}]
    required[0].write_text(json.dumps(original))
    with pytest.raises(ValueError, match='unsolved'):
        benchmark.load_strict_baseline(28)


def _fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    required = [suite / 'states/12/districts-28/benchmark.json',
        suite / 'diagnostics/florida/diagnosis.json', suite / 'suite.json',
        tmp_path / '.cache/state-block-benchmark/source/12/tl_2020_12_tabblock20.zip']
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('original evidence')
    source_hash = benchmark.sha256(required[-1])
    source = {'archive_sha256': source_hash, 'extracted_file_sha256': {'source.shp': 'same'}}
    required[0].write_text(json.dumps({'state_fips': '12', 'district_count': 28,
        'status': 'unsupported_topology', 'solver_progress': [], 'timed_pipeline_wall_seconds': 119.7,
        'source': source}))
    required[2].write_text(json.dumps({'states': [{'state_fips': '12', 'jobs': [
        {'district_count': count, 'house_sizes': [house], 'status': 'unsupported_topology',
         ('report' if count == 28 else 'topology_report'): 'states/12/districts-28/benchmark.json'}
        for count, house in zip((28,37,45,65),(435,574,692,1000))]}]}))
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {
        path.relative_to(tmp_path).as_posix(): benchmark.sha256(path) for path in required})
    monkeypatch.setattr(benchmark, 'runtime_code', lambda: {required[1].relative_to(tmp_path).as_posix():benchmark.sha256(required[1])})
    monkeypatch.setattr(benchmark, 'prepare_source', lambda *args: (tmp_path / 'source.shp', source))
    populations = [0, 0] + [10] * 28
    geoids = [f'12001000100{i:04d}' for i in range(len(populations))]
    units = [Unit(geoid, (1000. * i, 0.), population) for i, (geoid, population) in enumerate(zip(geoids, populations))]
    monkeypatch.setattr(benchmark, 'load_units', lambda *args: (units, dict(zip(geoids, populations)),
        {'projection': {'lon0': -81., 'lat0': 28.}}))
    physical_rows = [(), ()] + [tuple(j for j in (i-1, i+1) if 2 <= j < 30) for i in range(2, 30)]
    physical = PartGraph(tuple(physical_rows), tuple(range(30)))
    augmented_rows = list(physical_rows)
    augmented_rows[0], augmented_rows[1], augmented_rows[2] = (2,), (2,), (0, 1, 3)
    augmented = PartGraph(tuple(augmented_rows), tuple(range(30)))
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs: (physical, {}, {}))
    connections = ({'id': 'fl-test-0', 'kind': 'recorded-water-connection', 'part_nodes': [0, 2]},
                   {'id': 'fl-test-1', 'kind': 'recorded-water-connection', 'part_nodes': [1, 2]})
    configuration = benchmark.configuration_for_run(28)
    metadata = {'district_count': 28, 'population_selection': {'district_count': 28,
        'ideal_population': sum(populations)/28,
        'minimum_root_population': configuration['minimum_district_population_for_root_classification'],
        'groups': [{'district_count': 28}]}}
    monkeypatch.setattr(benchmark, 'build_florida_connections', lambda *args, **kwargs: (augmented, connections, metadata))
    labels = (0, 0, *range(28))
    output = suite / 'policies/florida-water-v1/states/12/districts-28'
    return output, geoids, labels, physical, required


@pytest.mark.parametrize('relative,count', [
    ('states/12/districts-28', 28),
    ('policies/florida-water-v1/states/12/districts-37', 28),
    ('policies/florida-water-v1/states/12/districts-28/nested', 28),
    ('policies/florida-water-v1/states/12/districts-28', 99),
])
def test_output_cannot_target_original_or_wrong_anchor(relative, count):
    with pytest.raises(ValueError, match='matching new Florida water-policy anchor'):
        benchmark.validate_output(benchmark.SUITE / relative, count)


def test_old_attempt_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/florida-water-v1/states/12/districts-28'
    output.mkdir(parents=True)
    original = b'{"status":"failed","reason":"preserved evidence"}'
    (output / 'benchmark.json').write_bytes(original)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(28, output)
    assert (output / 'benchmark.json').read_bytes() == original


def test_state_lock_and_destination_are_rechecked(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/florida-water-v1/states/12/districts-28'
    locks = []
    @contextmanager
    def competing_attempt(state):
        locks.append(state)
        output.mkdir(parents=True)
        (output / 'benchmark.json').write_text('earlier attempt completed while waiting')
        yield
    monkeypatch.setattr(benchmark, 'state_execution_lock', competing_attempt)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(28, output)
    assert locks == ['12']
    assert (output / 'benchmark.json').read_text() == 'earlier attempt completed while waiting'


@pytest.mark.parametrize('count,moves', [(99, 1000), (26, 1000), (28, 10)])
def test_only_requested_anchor_and_fixed_postprocessing_allowed(count, moves, tmp_path):
    with pytest.raises(ValueError, match='Florida suite requires K28/K37/K45/K65'):
        benchmark.run(count, tmp_path, max_moves=moves)


def _successful_solver(monkeypatch, geoids, labels):
    @contextmanager
    def observe(path):
        class Trace:
            passes = [{'inner_optimizer': {'success': True, 'actual_maxiter': 1000}}]
            observation_ok = True
            def summary(self):
                return {'observation_ok': self.observation_ok, 'passes': self.passes}
        path.write_text('{"type":"terminal"}\n')
        yield Trace()
    monkeypatch.setattr(benchmark, 'trace_optimizer', observe)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: DistrictingResult(
        centers=tuple(DistrictCenter(i, float(i), 0., 0.) for i in range(28)),
        assignments=dict(zip(geoids, labels)), populations={i: 10 for i in range(28)},
        iterations=80, converged=False, max_population_imbalance=0))


def _export_success(source, assignments, populations, output, **kwargs):
    assert kwargs['state_fips'] == '12'
    assert all(link['kind'] == 'recorded-water-connection' for link in kwargs['water_connections'])
    assert 'recorded_connections' not in kwargs and 'exclave_connections' not in kwargs
    output.mkdir(parents=True)
    manifest = {'strict_validation': {'passed': False, 'district_polygon_components': [3] + [1]*27},
        'connectivity_validation': {'passed': True, 'policy': benchmark.POLICY, 'district_component_counts': [1]*28}}
    (output / 'map-manifest.json').write_text(json.dumps(manifest))
    return manifest


def _mock_viewer(monkeypatch):
    monkeypatch.setattr(benchmark, 'write_viewer', lambda output, report: (output / 'index.html').write_text('validated water-policy map'))


def test_first_attempt_preserves_evidence_and_separates_metrics(tmp_path, monkeypatch):
    output, geoids, labels, _, required = _fixture(tmp_path, monkeypatch)
    original = {path: path.read_bytes() for path in required}
    _successful_solver(monkeypatch, geoids, labels)
    solver = benchmark.balanced_power_diagram
    calls = []
    def capture(*args, **kwargs):
        calls.append(kwargs)
        return solver(*args, **kwargs)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', capture)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', _export_success)
    _mock_viewer(monkeypatch)
    report = benchmark.run(28, output)
    assert report['status'] == 'complete_under_island_water_policy'
    assert report['final_plan']['physical_part_components'] == [3] + [1]*27
    assert report['final_plan']['policy_part_components'] == [1]*28
    assert report['final_plan']['district_populations'] == [10]*28
    assert not report['maps']['strict_validation']['passed']
    assert report['maps']['connectivity_validation']['passed']
    assert not report['comparison_baseline']['strict_solver_ran']
    assert not report['comparison_baseline']['controlled_inner_budget_comparison']
    assert report['solver']['outer_iteration_limit_reached'] and not report['solver']['centers_converged']
    assert report['solver']['all_inner_optimizer_passes_succeeded']
    assert calls == [{'seed': 20200955, 'max_outer_iterations': 80, 'center_tol': 1e-4, 'inner_max_iterations': 1000}]
    assert all(path.read_bytes() == data for path, data in original.items())
    assert report['preservation_audit']['all_original_diagnostic_files_byte_identical']
    assert not report['comparison_baseline']['strict_preflight_reused']
    saved = json.loads((output / 'solver-result.json').read_text())
    assert saved['assignments'] == dict(zip(geoids, labels))
    assert 'water_connections_sha256' in saved['provenance']
    assert report['artifact_sha256']['optimizer-trace.jsonl'] == benchmark.sha256(output / 'optimizer-trace.jsonl')
    assert json.loads((output / 'progress.json').read_text())['active_phase'] is None


def test_optimizer_failure_keeps_trace_and_never_exports(tmp_path, monkeypatch):
    output, *_ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(algorithm, 'minimize', lambda *args, **kwargs: OptimizeResult(
        x=np.zeros(28), fun=0., jac=np.zeros(28), success=False, status=1,
        message='forced iteration limit', nit=1000, nfev=1010))
    monkeypatch.setattr(benchmark, 'export_state_block_maps', lambda *args, **kwargs: pytest.fail('Failed optimizer must not export'))
    with pytest.raises(DistrictingOptimizationError, match='forced iteration limit'):
        benchmark.run(28, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and report['failed_phase'] == 'solve'
    assert report['optimizer_failure']['plan_returned'] is False
    assert report['optimizer_failure']['iterations'] == 1000
    assert report['solver_progress'][0]['inner_optimizer']['success'] is False
    assert report['preservation_audit']['all_original_strict_files_byte_identical']
    assert (output / 'optimizer-trace.jsonl').is_file()
    assert not (output / 'solver-result.json').exists()
    assert not (output / 'index.html').exists()


def test_polygon_failure_keeps_failed_assignments_without_publishing(tmp_path, monkeypatch):
    output, geoids, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    def reject(*args, **kwargs):
        raise ValueError('Independent polygon connectivity failed')
    monkeypatch.setattr(benchmark, 'export_state_block_maps', reject)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda *args: pytest.fail('Failed polygon validation cannot publish'))
    with pytest.raises(ValueError, match='Independent polygon connectivity failed'):
        benchmark.run(28, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'independent_polygon_validation_and_map_export'
    assert report['final_plan']['all_districts_policy_connected']
    assert (output / 'solver-result.json').is_file()


def test_wrong_policy_is_not_accepted(tmp_path, monkeypatch):
    output, geoids, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    def wrong_policy(*args, **kwargs):
        manifest = _export_success(*args, **kwargs)
        manifest['connectivity_validation']['policy'] = 'shared_edges_plus_recorded_mixed_connections'
        return manifest
    monkeypatch.setattr(benchmark, 'export_state_block_maps', wrong_policy)
    with pytest.raises(ValueError, match='Independent polygon and water-connection validation failed'):
        benchmark.run(28, output)
    assert json.loads((output / 'benchmark.json').read_text())['status'] == 'failed'


def test_disconnected_policy_source_fails_before_solving(tmp_path, monkeypatch):
    output, _, _, physical, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'build_florida_connections', lambda *args, **kwargs: (physical, (), {'district_count': 28, 'population_selection': {'district_count': 28, 'ideal_population': 10., 'minimum_root_population': benchmark.configuration_for_run(28)['minimum_district_population_for_root_classification'], 'groups': [{'district_count': 28}]}}))
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Disconnected source must not solve'))
    with pytest.raises(ValueError, match='one connected source graph'):
        benchmark.run(28, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['failed_phase'] == 'prepare_population_aware_water_connections'


def test_preflight_failure_has_terminal_report(tmp_path, monkeypatch):
    output, *_ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: (_ for _ in ()).throw(ValueError('Missing preserved diagnosis')))
    with pytest.raises(ValueError, match='Missing preserved diagnosis'):
        benchmark.run(28, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and report['failed_phase'] == 'preserve_evidence_and_fingerprint_code'
    assert not report['preservation_audit']['preservation_snapshot_completed']


def test_source_overlap_is_rejected_before_solver(tmp_path, monkeypatch):
    output, _, _, physical, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs:
        (physical, {'interior_overlap_pair_count': 1}, {}))
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Overlapping source must not solve'))
    with pytest.raises(ValueError, match='Overlapping source interiors'):
        benchmark.run(28, output)
    assert json.loads((output / 'benchmark.json').read_text())['failed_phase'] == 'load_or_build_physical_part_graph'


def test_failed_trace_cannot_become_completed_result(tmp_path, monkeypatch):
    output, geoids, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    original = benchmark.trace_optimizer
    @contextmanager
    def broken_trace(path):
        with original(path) as trace:
            trace.observation_ok = False
            yield trace
    monkeypatch.setattr(benchmark, 'trace_optimizer', broken_trace)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', lambda *args, **kwargs: pytest.fail('Failed trace must not export'))
    with pytest.raises(ValueError, match='diagnostics were not recorded'):
        benchmark.run(28, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and report['failed_phase'] == 'solve'
    assert not report['optimizer_trace']['observation_ok']


def test_display_write_failure_cannot_suppress_terminal_report(tmp_path, monkeypatch):
    output, geoids, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', _export_success)
    _mock_viewer(monkeypatch)
    original_write = benchmark.write_json
    def denied_progress(path, data):
        if path.name == 'progress.json':
            raise PermissionError('simulated Windows reader sharing conflict')
        original_write(path, data)
    monkeypatch.setattr(benchmark, 'write_json', denied_progress)
    report = benchmark.run(28, output)
    saved = json.loads((output / 'benchmark.json').read_text())
    assert saved['status'] == report['status'] == 'complete_under_island_water_policy'
    assert any('sharing conflict' in error for error in saved['progress_write_errors'])
    assert not saved['final_progress_snapshot_written']


def test_changed_evidence_rejects_publish(tmp_path, monkeypatch):
    output, geoids, labels, _, required = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    def altered(*args, **kwargs):
        manifest = _export_success(*args, **kwargs)
        required[1].write_text('unexpectedly modified diagnosis')
        return manifest
    monkeypatch.setattr(benchmark, 'export_state_block_maps', altered)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda *args: pytest.fail('Changed evidence must not publish'))
    with pytest.raises(ValueError, match='Preserved strict artifacts or source archive changed'):
        benchmark.run(28, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and report['preservation_error']


def test_viewer_marks_first_run_and_physical_policy_difference(tmp_path):
    benchmark.write_viewer(tmp_path, {'district_count': 28,
        'input': {'projection': {'lon0': -119, 'lat0': 35}},
        'final_plan': {'max_absolute_deviation_percent': .005}})
    page = (tmp_path / 'index.html').read_text()
    assert 'Original strict preflight preserved; it did not solve a plan.' in page
    assert 'Physical polygons remain unchanged.' in page
    assert all(name not in page for name in ('California', 'K52', 'Farallons', 'Channel Islands'))
    assert '1,000' in page
    assert '__RESULT_SUMMARY__' not in page


def test_stale_population_audit_is_rejected(tmp_path, monkeypatch):
    output, *_ = _fixture(tmp_path, monkeypatch)
    original = benchmark.build_florida_connections
    def stale(*args, **kwargs):
        graph, connections, metadata = original(*args, **kwargs)
        metadata['population_selection']['district_count'] = 99
        return graph, connections, metadata
    monkeypatch.setattr(benchmark, 'build_florida_connections', stale)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Stale audit must not solve'))
    with pytest.raises(ValueError, match='preflight does not match this district count'):
        benchmark.run(28, output)


def test_terminal_replacement_conflict_retains_completed_status_without_rerun(tmp_path, monkeypatch):
    output, geoids, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', _export_success)
    _mock_viewer(monkeypatch)
    original = benchmark.write_json
    def denied_terminal(path, value):
        if path.name == 'benchmark.json' and value['status'] != 'running':
            raise PermissionError('terminal replacement held by reader')
        original(path, value)
    monkeypatch.setattr(benchmark, 'write_json', denied_terminal)
    report = benchmark.run(28, output)
    fallback = json.loads((output / 'terminal-report.json').read_text())
    assert fallback['status'] == report['status'] == 'complete_under_island_water_policy'
    assert fallback['authoritative_terminal_report'] == 'terminal-report.json'
    assert 'replacement held by reader' in fallback['terminal_report_write_error']
    assert fallback['final_progress_snapshot_written']
    assert json.loads((output / 'benchmark.json').read_text())['status'] == 'running'


def test_terminal_fallback_preserves_failed_status_and_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'write_json', lambda *args: (_ for _ in ()).throw(PermissionError('locked')))
    report = {'status': 'failed', 'error': 'optimizer reached its limit', 'optimizer_failure': {'iterations': 1000}}
    path = benchmark.write_terminal_report(tmp_path, report)
    original = path.read_bytes()
    assert json.loads(original)['status'] == 'failed'
    with pytest.raises(FileExistsError):
        benchmark.write_terminal_report(tmp_path, {'status': 'complete_under_island_water_policy'})
    assert path.read_bytes() == original
