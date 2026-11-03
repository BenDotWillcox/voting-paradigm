"""New York attempts preserve old evidence and require independent connectivity.

Small synthetic sources exercise orchestration and failure paths; adapter and
exporter tests separately validate source geometry and recorded-link endpoints.
"""
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from districting import DistrictCenter, DistrictingOptimizationError, DistrictingResult, Unit
from districting import algorithm
from districting.part_connectivity import PartGraph
from scripts import benchmark_new_york_budget as benchmark


@pytest.mark.parametrize('relative,count', [
    ('states/36/districts-26', 26),
    ('policies/hawaii-water-v1/states/15/districts-2', 26),
    ('corrections/new-york-inner-budget-v1/states/36/districts-35', 26),
    ('corrections/new-york-inner-budget-v1/states/36/districts-26/nested', 26),
    ('corrections/new-york-inner-budget-v1/states/36/../../../island-water-v1', 26),
])
def test_output_cannot_target_original_or_wrong_anchor(relative: str, count: int) -> None:
    with pytest.raises(ValueError, match='matching new K26 run'):
        benchmark.validate_output((benchmark.SUITE / relative).resolve(), count)


def test_old_attempt_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'corrections/new-york-inner-budget-v1/states/36/districts-26'
    output.mkdir(parents=True)
    original = b'{"status":"failed","reason":"preserved evidence"}'
    (output / 'benchmark.json').write_bytes(original)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(26, output)
    assert (output / 'benchmark.json').read_bytes() == original


@pytest.mark.parametrize('count', [26])
def test_supported_anchor_uses_new_york_lock(count: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    locks = []
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: locks.append(state) or nullcontext())
    calls = []
    monkeypatch.setattr(benchmark, '_run_locked', lambda count, output, moves: calls.append((count, output, moves)) or {'count': count})
    output = tmp_path / f'corrections/new-york-inner-budget-v1/states/36/districts-{count}'
    assert benchmark.run(count, output) == {'count': count}
    assert locks == ['36']
    assert calls == [(count, output.resolve(), 1000)]



def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    monkeypatch.setattr(benchmark, 'EXTRA_CODE', ())
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    required = [suite / 'states/36/districts-26/benchmark.json', suite / 'diagnostics/new-york/diagnosis.json',
        tmp_path / '.cache/state-block-benchmark/source/36/tl_2020_36_tabblock20.zip']
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('original evidence')
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {path.relative_to(tmp_path).as_posix(): benchmark.sha256(path) for path in required})
    source_hash = benchmark.sha256(required[-1])
    monkeypatch.setattr(benchmark, 'prepare_source', lambda *args: (tmp_path / 'source.shp', {'archive_sha256': source_hash}))
    populations = [0, 0] + [10] * 26
    geoids = [f'36001000100{i:04d}' for i in range(len(populations))]
    units = [Unit(geoid, (1000. * i, 0.), population) for i, (geoid, population) in enumerate(zip(geoids, populations))]
    monkeypatch.setattr(benchmark, 'load_units', lambda *args: (units, dict(zip(geoids, populations)), {'projection': {'lon0': -85., 'lat0': 38.}}))
    physical_rows = [(), ()] + [tuple(j for j in (i-1, i+1) if 2 <= j < 28) for i in range(2, 28)]
    physical = PartGraph(tuple(physical_rows), tuple(range(28)))
    augmented_rows = list(physical_rows)
    augmented_rows[0], augmented_rows[1] = (2,), (2,)
    augmented_rows[2] = (0, 1, 3)
    augmented = PartGraph(tuple(augmented_rows), tuple(range(28)))
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs: (physical, {}, {}))
    connections = ({'id': 'ny-liberty-test', 'kind': 'recorded-water-connection', 'part_nodes': [0, 2]},
                   {'id': 'ny-ellis-test', 'kind': 'recorded-exclave-connection', 'part_nodes': [1, 2]})
    monkeypatch.setattr(benchmark, 'build_new_york_connections', lambda *args, **kwargs: (augmented, connections, {}))
    labels = (0, 0, *range(26))
    baseline = {
        'status': 'failed', 'configuration': {
            'seed': benchmark.SEED, 'max_outer_iterations': 80, 'max_rebalance_moves': 1000,
            'center_tolerance_m': 1e-4, 'inner_max_iterations': 300,
            'inner_optimization': {'max_line_search_steps': 100},
        }, 'code_sha256': {}, 'timed_pipeline_wall_seconds': 126.4,
        'solver_progress': [{'inner_optimizer': {'success': False, 'iterations': 300}}],
        'optimizer_failure': {'iterations': 300, 'plan_returned': False},
        'recorded_connections': list(connections), 'artifact_sha256': {},
    }
    old_connections = tmp_path / 'preserved-connections.json'
    benchmark.write_json(old_connections, {'policy': benchmark.POLICY, 'connections': list(connections), 'source_sha256': source_hash})
    baseline['artifact_sha256']['recorded-connections.json'] = benchmark.sha256(old_connections)
    monkeypatch.setattr(benchmark, 'load_baseline', lambda: baseline)
    output = suite / 'corrections/new-york-inner-budget-v1/states/36/districts-26'
    return output, units, geoids, populations, labels, physical, augmented, required


def _successful_solver(monkeypatch: pytest.MonkeyPatch, geoids, labels) -> None:
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
        centers=tuple(DistrictCenter(i, float(i), 0., 0.) for i in range(26)),
        assignments=dict(zip(geoids, labels)), populations={i: 10 for i in range(26)},
        iterations=1, converged=True, max_population_imbalance=0))


def _export_success(source, assignments, populations, output, **kwargs):
    assert kwargs['state_fips'] == '36'
    assert [link['kind'] for link in kwargs['recorded_connections']] == ['recorded-water-connection', 'recorded-exclave-connection']
    assert 'water_connections' not in kwargs
    output.mkdir(parents=True)
    manifest = {'strict_validation': {'passed': False, 'district_polygon_components': [3] + [1]*25},
        'connectivity_validation': {'passed': True, 'policy': benchmark.POLICY, 'district_component_counts': [1]*26}}
    (output / 'map-manifest.json').write_text(json.dumps(manifest))
    return manifest


def test_full_attempt_distinguishes_physical_and_policy_connectivity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _, geoids, _, labels, _, _, required = _fixture(tmp_path, monkeypatch)
    original = {path: path.read_bytes() for path in required}
    _successful_solver(monkeypatch, geoids, labels)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', _export_success)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda output, report: (output / 'index.html').write_text('connected under recorded exclave policy'))
    report = benchmark.run(26, output)
    assert report['status'] == 'complete_under_recorded_mixed_policy'
    assert report['final_plan']['physical_part_components'] == [3] + [1]*25
    assert report['final_plan']['policy_part_components'] == [1]*26
    assert not report['final_plan']['all_districts_physically_part_connected']
    assert report['final_plan']['all_districts_policy_connected']
    assert report['final_plan']['total_population'] == 260
    assert report['final_plan']['district_populations'] == [10]*26
    assert report['solver']['all_inner_optimizer_passes_succeeded']
    assert not report['maps']['strict_validation']['passed']
    assert report['maps']['connectivity_validation']['passed']
    assert report['comparison_baseline']['strict_solver_ran'] is False
    assert report['preservation_audit']['prior_policy_and_correction_evidence_byte_identical']
    saved = json.loads((output / 'solver-result.json').read_text())
    assert saved['assignments'] == dict(zip(geoids, labels))
    assert 'recorded_connections_sha256' in saved['provenance']
    assert all(path.read_bytes() == data for path, data in original.items())


def test_unsuccessful_optimizer_is_persisted_without_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, *_ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(algorithm, 'minimize', lambda *args, **kwargs: OptimizeResult(
        x=np.zeros(26), fun=0., jac=np.zeros(26), success=False, status=2,
        message='forced line-search failure', nit=0, nfev=21))
    monkeypatch.setattr(benchmark, 'export_state_block_maps', lambda *args, **kwargs: pytest.fail('Must not export failed optimizer output'))
    with pytest.raises(DistrictingOptimizationError, match='forced line-search failure'):
        benchmark.run(26, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and report['failed_phase'] == 'solve'
    assert report['optimizer_failure']['plan_returned'] is False
    assert report['optimizer_failure']['balance_pass'] == 1
    assert report['solver_progress'][0]['inner_optimizer']['success'] is False
    assert report['preservation_audit']['all_original_strict_files_byte_identical']
    assert 'final_plan' not in report
    assert not (output / 'solver-result.json').exists()
    assert not (output / 'index.html').exists()
    assert json.loads((output / 'progress.json').read_text())['status'] == 'failed'


def test_polygon_failure_cannot_become_a_completed_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _, geoids, _, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    def reject(*args, **kwargs):
        raise ValueError('Independent polygon connectivity failed')
    monkeypatch.setattr(benchmark, 'export_state_block_maps', reject)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda *args: pytest.fail('Failed polygon validation cannot get a completed viewer'))
    with pytest.raises(ValueError, match='Independent polygon connectivity failed'):
        benchmark.run(26, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'independent_polygon_validation_and_map_export'
    assert (output / 'solver-result.json').exists(), 'Retain failed assignments for diagnosis'
    assert report['final_plan']['all_districts_policy_connected'], 'Graph success alone must not imply completed geometry'
    assert not (output / 'index.html').exists()


def test_success_for_another_connection_policy_is_not_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _, geoids, _, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    def wrong_policy(*args, **kwargs):
        manifest = _export_success(*args, **kwargs)
        manifest['connectivity_validation']['policy'] = 'shared_edges_plus_recorded_water_connections'
        return manifest
    monkeypatch.setattr(benchmark, 'export_state_block_maps', wrong_policy)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda *args: pytest.fail('Wrong policy must not get a viewer'))
    with pytest.raises(ValueError, match='Independent polygon and recorded-connection validation failed'):
        benchmark.run(26, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'independent_polygon_validation_and_map_export'


def test_outer_limit_and_center_convergence_remain_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _, geoids, _, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: DistrictingResult(
        centers=tuple(DistrictCenter(i, float(i), 0., 0.) for i in range(26)),
        assignments=dict(zip(geoids, labels)), populations={i: 10 for i in range(26)},
        iterations=benchmark.OUTER_ITERATION_LIMIT, converged=False, max_population_imbalance=0))
    monkeypatch.setattr(benchmark, 'export_state_block_maps', _export_success)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda output, report: (output / 'index.html').write_text('validated policy map'))
    report = benchmark.run(26, output)
    assert report['status'] == 'complete_under_recorded_mixed_policy'
    assert report['solver']['outer_iteration_limit_reached']
    assert not report['solver']['centers_converged']
    assert report['solver']['all_inner_optimizer_passes_succeeded']


def test_disconnected_augmented_source_fails_before_solving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _, _, _, _, physical, _, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'build_new_york_connections', lambda *args, **kwargs: (physical, (), {}))
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Disconnected policy graph must not solve'))
    with pytest.raises(ValueError, match='one connected source graph'):
        benchmark.run(26, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'prepare_recorded_mixed_connections'
    assert not (output / 'initial-solver-result.json').exists()


def test_viewer_distinguishes_water_and_exclave_connections(tmp_path: Path) -> None:
    benchmark.write_viewer(tmp_path, {'district_count': 26,
        'input': {'projection': {'lon0': -85, 'lat0': 38}},
        'final_plan': {'max_absolute_deviation_percent': .001}})
    page = (tmp_path / 'index.html').read_text()
    assert 'recorded water-and-exclave policy' in page
    assert 'Liberty uses a recorded water link; Ellis uses an exclave link across New Jersey land and water' in page
    assert '../districts-61/' not in page
    assert '../../../../../policies/new-york-links-v1/' in page
    assert '1,000' in page
    assert '../../../../../diagnostics/new-york/' in page
    assert '__RESULT_SUMMARY__' not in page


def test_configuration_changes_only_inner_budget_without_mutating_baseline() -> None:
    original = {'configuration': {'seed': benchmark.SEED, 'max_outer_iterations': 80,
        'max_rebalance_moves': 1000, 'center_tolerance_m': 1e-4, 'inner_max_iterations': 300,
        'inner_optimization': {'max_line_search_steps': 100, 'sentinel_tolerance': 1e-12},
        'connection_policy': 'unchanged'}}
    changed = benchmark.configuration_for_experiment(original)
    assert changed['inner_max_iterations'] == 1000
    assert original['configuration']['inner_max_iterations'] == 300
    changed['inner_max_iterations'] = 300
    assert changed == original['configuration']


@pytest.mark.parametrize('count,moves', [(35, 1000), (42, 1000), (61, 1000), (26, 10)])
def test_rejects_extra_anchors_or_changed_postprocessing(count, moves, tmp_path) -> None:
    with pytest.raises(ValueError, match='controlled experiment requires'):
        benchmark.run(count, tmp_path, max_moves=moves)


def test_exact_solver_arguments_are_preserved_except_inner_budget(tmp_path, monkeypatch) -> None:
    output, _, geoids, _, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    solver = benchmark.balanced_power_diagram
    calls = []
    def capture(*args, **kwargs):
        calls.append(kwargs)
        return solver(*args, **kwargs)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', capture)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', _export_success)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda output, report: (output / 'index.html').write_text('map'))
    report = benchmark.run(26, output)
    assert calls == [{'seed': benchmark.SEED, 'max_outer_iterations': 80, 'inner_max_iterations': 1000}]
    assert report['preservation_audit']['original_failed_policy_tree_byte_identical']
    assert report['preservation_audit']['recorded_connections_byte_identical']
    assert report['optimizer_trace']['observation_ok']
    assert report['artifact_sha256']['optimizer-trace.jsonl'] == benchmark.sha256(output / 'optimizer-trace.jsonl')


def test_changed_recorded_link_stops_before_solver(tmp_path, monkeypatch) -> None:
    output, *_, augmented, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'build_new_york_connections', lambda *args, **kwargs: (augmented, ({'id':'changed'},), {}))
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Changed links must not solve'))
    with pytest.raises(ValueError, match='connections differ from'):
        benchmark.run(26, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['failed_phase'] == 'prepare_recorded_mixed_connections'


def test_trace_failure_is_not_silently_a_success(tmp_path, monkeypatch) -> None:
    output, _, geoids, _, labels, *_ = _fixture(tmp_path, monkeypatch)
    _successful_solver(monkeypatch, geoids, labels)
    original = benchmark.trace_optimizer
    @contextmanager
    def broken_trace(path):
        with original(path) as trace:
            trace.observation_ok = False
            yield trace
    monkeypatch.setattr(benchmark, 'trace_optimizer', broken_trace)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', lambda *args, **kwargs: pytest.fail('Failed diagnostics cannot get completed output'))
    with pytest.raises(ValueError, match='diagnostics were not recorded'):
        benchmark.run(26, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed' and not report['optimizer_trace']['observation_ok']


def test_inventory_covers_old_policy_tree_reports_and_originals(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / 'suite'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    baseline = benchmark.baseline_directory()
    baseline.mkdir(parents=True)
    original = tmp_path / 'old-strict.json'
    original.write_text('strict')
    benchmark.write_json(baseline / 'preserved-file-inventory.json', {'old-strict.json': benchmark.sha256(original)})
    (baseline / 'benchmark.json').write_text('failed')
    screenshot = suite / 'policies/new-york-links-v1/screenshot.png'
    screenshot.write_bytes(b'original image')
    report = tmp_path / 'prompts/new-york-links-benchmark.md'
    report.parent.mkdir()
    report.write_text('failed comparison')
    newer = suite / 'corrections/new-york-inner-budget-v1/progress.json'
    newer.parent.mkdir(parents=True)
    newer.write_text('new')
    before = benchmark.protected_inventory()
    assert original.relative_to(tmp_path).as_posix() in before
    assert screenshot.relative_to(tmp_path).as_posix() in before
    assert report.relative_to(tmp_path).as_posix() in before
    assert newer.relative_to(tmp_path).as_posix() not in before
    report.write_text('changed')
    assert benchmark.protected_inventory() != before


def _pinned_baseline_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path / 'suite')
    baseline = benchmark.baseline_directory()
    baseline.mkdir(parents=True)
    # One content hash, distinct paths: the historical inventory count is an
    # explicit safeguard, not a reason for these unit fixtures to be large.
    original = {}
    for i in range(1052):
        path = tmp_path / f'protected-{i}.json'
        path.write_text('preserved')
        original[path.name] = benchmark.sha256(path)
    source = {}
    for i in range(23):
        path = tmp_path / f'frozen-{i}.py'
        path.write_text('# unchanged numerical pipeline')
        source[path.name] = benchmark.sha256(path)
    report = {'status': 'failed', 'failed_phase': 'solve', 'district_count': 26,
        'optimizer_failure': {'iterations': 300, 'balance_pass': 2, 'plan_returned': False},
        'configuration': {'inner_max_iterations': 300}, 'code_sha256': source,
        'environment': {'python': benchmark.sys.version,
                        'packages': {name: benchmark.version(name) for name in ('numpy', 'scipy', 'pyshp', 'shapely')}}}
    benchmark.write_json(baseline / 'benchmark.json', report)
    benchmark.write_json(baseline / 'preserved-file-inventory.json', original)
    monkeypatch.setattr(benchmark, 'BASELINE_REPORT_SHA256', benchmark.sha256(baseline / 'benchmark.json'))
    monkeypatch.setattr(benchmark, 'BASELINE_INVENTORY_SHA256', benchmark.sha256(baseline / 'preserved-file-inventory.json'))
    return report, baseline


def test_preflight_requires_all_frozen_source_and_original_evidence(tmp_path, monkeypatch) -> None:
    report, _ = _pinned_baseline_fixture(tmp_path, monkeypatch)
    assert benchmark.load_baseline() == report
    (tmp_path / 'frozen-22.py').write_text('# changed')
    with pytest.raises(ValueError, match='Frozen baseline code changed'):
        benchmark.load_baseline()


def test_preflight_rejects_changed_original_evidence(tmp_path, monkeypatch) -> None:
    _pinned_baseline_fixture(tmp_path, monkeypatch)
    (tmp_path / 'protected-1051.json').write_text('changed')
    with pytest.raises(ValueError, match='Original protected evidence changed'):
        benchmark.load_baseline()


def test_preflight_rejects_changed_baseline_report_and_dependency_version(tmp_path, monkeypatch) -> None:
    report, baseline = _pinned_baseline_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'version', lambda name: 'changed-package-version')
    with pytest.raises(ValueError, match='package versions differ'):
        benchmark.load_baseline()
    report['configuration']['inner_max_iterations'] = 1000
    benchmark.write_json(baseline / 'benchmark.json', report)
    with pytest.raises(ValueError, match='baseline report changed'):
        benchmark.load_baseline()
