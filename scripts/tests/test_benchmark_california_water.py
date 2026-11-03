"""California first-attempt orchestration and preserved failure evidence."""
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from districting import DistrictCenter, DistrictingOptimizationError, DistrictingResult, Unit
from districting import algorithm
from districting.part_connectivity import PartGraph
from scripts import benchmark_california_water as benchmark


@pytest.mark.parametrize('relative,count', [
    ('states/06/districts-52', 52),
    ('policies/california-water-v1/states/06/districts-69', 52),
    ('policies/california-water-v1/states/06/districts-52/nested', 52),
    ('policies/california-water-v1/states/06/districts-52', 69),
])
def test_output_cannot_target_original_or_wrong_anchor(relative, count):
    with pytest.raises(ValueError, match='matching new K52 run'):
        benchmark.validate_output(benchmark.SUITE / relative, count)


def test_old_attempt_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/california-water-v1/states/06/districts-52'
    output.mkdir(parents=True)
    original = b'{"status":"failed","reason":"preserved evidence"}'
    (output / 'benchmark.json').write_bytes(original)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(52, output)
    assert (output / 'benchmark.json').read_bytes() == original


def test_state_lock_and_destination_are_rechecked(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/california-water-v1/states/06/districts-52'
    locks = []
    @contextmanager
    def competing_attempt(state):
        locks.append(state)
        output.mkdir(parents=True)
        (output / 'benchmark.json').write_text('earlier attempt completed while waiting')
        yield
    monkeypatch.setattr(benchmark, 'state_execution_lock', competing_attempt)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(52, output)
    assert locks == ['06']
    assert (output / 'benchmark.json').read_text() == 'earlier attempt completed while waiting'


@pytest.mark.parametrize('count,moves', [(69, 1000), (83, 1000), (120, 1000), (52, 10)])
def test_only_requested_anchor_and_fixed_postprocessing_allowed(count, moves, tmp_path):
    with pytest.raises(ValueError, match='California pilot requires K52'):
        benchmark.run(count, tmp_path, max_moves=moves)


def test_inventory_covers_strict_diagnosis_and_report_not_new_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / 'suite'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    paths = [suite / 'suite.json', suite / 'states/06/districts-52/benchmark.json',
        suite / 'states/06/original.log', suite / 'diagnostics/california/diagnosis.json',
        suite / 'diagnostics/california/validated-map.png',
        tmp_path / 'prompts/california-topology-diagnosis.json',
        tmp_path / '.cache/state-block-benchmark/source/06/tl_2020_06_tabblock20.zip']
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'original {index}')
    new = suite / 'policies/california-water-v1/states/06/districts-52/progress.json'
    new.parent.mkdir(parents=True)
    new.write_text('running')
    before = benchmark.protected_inventory()
    assert set(before) == {path.relative_to(tmp_path).as_posix() for path in paths}
    new.write_text('complete')
    assert benchmark.protected_inventory() == before
    paths[2].write_text('changed old evidence')
    assert benchmark.protected_inventory() != before


def _fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    monkeypatch.setattr(benchmark, 'CODE_PATHS', ())
    monkeypatch.setattr(benchmark, 'EXTRA_CODE', ())
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    required = [suite / 'states/06/districts-52/benchmark.json',
        suite / 'diagnostics/california/diagnosis.json',
        tmp_path / '.cache/state-block-benchmark/source/06/tl_2020_06_tabblock20.zip']
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('original evidence')
    required[0].write_text(json.dumps({'status': 'unsupported_topology', 'solver_progress': [],
        'timed_pipeline_wall_seconds': 192.0}))
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {
        path.relative_to(tmp_path).as_posix(): benchmark.sha256(path) for path in required})
    source_hash = benchmark.sha256(required[-1])
    monkeypatch.setattr(benchmark, 'prepare_source', lambda *args: (tmp_path / 'source.shp', {'archive_sha256': source_hash}))
    populations = [0, 0] + [10] * 52
    geoids = [f'06001000100{i:04d}' for i in range(len(populations))]
    units = [Unit(geoid, (1000. * i, 0.), population) for i, (geoid, population) in enumerate(zip(geoids, populations))]
    monkeypatch.setattr(benchmark, 'load_units', lambda *args: (units, dict(zip(geoids, populations)),
        {'projection': {'lon0': -119., 'lat0': 35.}}))
    physical_rows = [(), ()] + [tuple(j for j in (i-1, i+1) if 2 <= j < 54) for i in range(2, 54)]
    physical = PartGraph(tuple(physical_rows), tuple(range(54)))
    augmented_rows = list(physical_rows)
    augmented_rows[0], augmented_rows[1], augmented_rows[2] = (2,), (2,), (0, 1, 3)
    augmented = PartGraph(tuple(augmented_rows), tuple(range(54)))
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs: (physical, {}, {}))
    connections = ({'id': 'ca-test-0', 'kind': 'recorded-water-connection', 'part_nodes': [0, 2]},
                   {'id': 'ca-test-1', 'kind': 'recorded-water-connection', 'part_nodes': [1, 2]})
    monkeypatch.setattr(benchmark, 'build_california_connections', lambda *args, **kwargs: (augmented, connections, {}))
    labels = (0, 0, *range(52))
    output = suite / 'policies/california-water-v1/states/06/districts-52'
    return output, geoids, labels, physical, required


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
        centers=tuple(DistrictCenter(i, float(i), 0., 0.) for i in range(52)),
        assignments=dict(zip(geoids, labels)), populations={i: 10 for i in range(52)},
        iterations=80, converged=False, max_population_imbalance=0))


def _export_success(source, assignments, populations, output, **kwargs):
    assert kwargs['state_fips'] == '06'
    assert all(link['kind'] == 'recorded-water-connection' for link in kwargs['water_connections'])
    assert 'recorded_connections' not in kwargs and 'exclave_connections' not in kwargs
    output.mkdir(parents=True)
    manifest = {'strict_validation': {'passed': False, 'district_polygon_components': [3] + [1]*51},
        'connectivity_validation': {'passed': True, 'policy': benchmark.POLICY, 'district_component_counts': [1]*52}}
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
    report = benchmark.run(52, output)
    assert report['status'] == 'complete_under_island_water_policy'
    assert report['final_plan']['physical_part_components'] == [3] + [1]*51
    assert report['final_plan']['policy_part_components'] == [1]*52
    assert report['final_plan']['district_populations'] == [10]*52
    assert not report['maps']['strict_validation']['passed']
    assert report['maps']['connectivity_validation']['passed']
    assert not report['comparison_baseline']['strict_solver_ran']
    assert not report['comparison_baseline']['controlled_inner_budget_comparison']
    assert report['solver']['outer_iteration_limit_reached'] and not report['solver']['centers_converged']
    assert report['solver']['all_inner_optimizer_passes_succeeded']
    assert calls == [{'seed': 20200955, 'max_outer_iterations': 80, 'center_tol': 1e-4, 'inner_max_iterations': 1000}]
    assert all(path.read_bytes() == data for path, data in original.items())
    assert report['preservation_audit']['all_original_diagnostic_files_byte_identical']
    saved = json.loads((output / 'solver-result.json').read_text())
    assert saved['assignments'] == dict(zip(geoids, labels))
    assert 'water_connections_sha256' in saved['provenance']
    assert report['artifact_sha256']['optimizer-trace.jsonl'] == benchmark.sha256(output / 'optimizer-trace.jsonl')
    assert json.loads((output / 'progress.json').read_text())['active_phase'] is None


def test_optimizer_failure_keeps_trace_and_never_exports(tmp_path, monkeypatch):
    output, *_ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(algorithm, 'minimize', lambda *args, **kwargs: OptimizeResult(
        x=np.zeros(52), fun=0., jac=np.zeros(52), success=False, status=1,
        message='forced iteration limit', nit=1000, nfev=1010))
    monkeypatch.setattr(benchmark, 'export_state_block_maps', lambda *args, **kwargs: pytest.fail('Failed optimizer must not export'))
    with pytest.raises(DistrictingOptimizationError, match='forced iteration limit'):
        benchmark.run(52, output)
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
        benchmark.run(52, output)
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
        benchmark.run(52, output)
    assert json.loads((output / 'benchmark.json').read_text())['status'] == 'failed'


def test_disconnected_policy_source_fails_before_solving(tmp_path, monkeypatch):
    output, _, _, physical, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'build_california_connections', lambda *args, **kwargs: (physical, (), {}))
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Disconnected source must not solve'))
    with pytest.raises(ValueError, match='one connected source graph'):
        benchmark.run(52, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['failed_phase'] == 'prepare_population_aware_water_connections'


def test_preflight_failure_has_terminal_report(tmp_path, monkeypatch):
    output, *_ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: (_ for _ in ()).throw(ValueError('Missing preserved diagnosis')))
    with pytest.raises(ValueError, match='Missing preserved diagnosis'):
        benchmark.run(52, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and report['failed_phase'] == 'preserve_evidence_and_fingerprint_code'
    assert not report['preservation_audit']['preservation_snapshot_completed']


def test_source_overlap_is_rejected_before_solver(tmp_path, monkeypatch):
    output, _, _, physical, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs:
        (physical, {'interior_overlap_pair_count': 1}, {}))
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Overlapping source must not solve'))
    with pytest.raises(ValueError, match='Overlapping source interiors'):
        benchmark.run(52, output)
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
        benchmark.run(52, output)
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
    report = benchmark.run(52, output)
    saved = json.loads((output / 'benchmark.json').read_text())
    assert saved['status'] == report['status'] == 'complete_under_island_water_policy'
    assert any('sharing conflict' in error for error in saved['progress_write_errors'])


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
        benchmark.run(52, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and report['preservation_error']


def test_viewer_marks_first_run_and_physical_policy_difference(tmp_path):
    benchmark.write_viewer(tmp_path, {'district_count': 52,
        'input': {'projection': {'lon0': -119, 'lat0': 35}},
        'final_plan': {'max_absolute_deviation_percent': .005}})
    page = (tmp_path / 'index.html').read_text()
    assert 'first California solver run' in page
    assert 'Physical polygons remain separate across water' in page
    assert '1,000' in page
    assert '__RESULT_SUMMARY__' not in page
