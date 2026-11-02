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
from scripts import benchmark_new_york_links as benchmark


@pytest.mark.parametrize('relative,count', [
    ('states/36/districts-26', 26),
    ('policies/hawaii-water-v1/states/15/districts-2', 26),
    ('policies/new-york-links-v1/states/36/districts-35', 26),
    ('policies/new-york-links-v1/states/36/districts-26/nested', 26),
    ('policies/new-york-links-v1/states/36/../../../island-water-v1', 26),
])
def test_output_cannot_target_original_or_wrong_anchor(relative: str, count: int) -> None:
    with pytest.raises(ValueError, match='matching new run'):
        benchmark.validate_output((benchmark.SUITE / relative).resolve(), count)


def test_old_attempt_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/new-york-links-v1/states/36/districts-26'
    output.mkdir(parents=True)
    original = b'{"status":"failed","reason":"preserved evidence"}'
    (output / 'benchmark.json').write_bytes(original)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(26, output)
    assert (output / 'benchmark.json').read_bytes() == original


@pytest.mark.parametrize('count', [26, 35, 42, 61])
def test_supported_anchor_uses_new_york_lock(count: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    locks = []
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: locks.append(state) or nullcontext())
    calls = []
    monkeypatch.setattr(benchmark, '_run_locked', lambda count, output, moves: calls.append((count, output, moves)) or {'count': count})
    output = tmp_path / f'policies/new-york-links-v1/states/36/districts-{count}'
    assert benchmark.run(count, output) == {'count': count}
    assert locks == ['36']
    assert calls == [(count, output.resolve(), 1000)]


def test_protection_includes_strict_diagnostics_and_prior_policies_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    directories = ('states/36', 'states/21', 'states/44', 'states/15',
        'diagnostics/new-york', 'diagnostics/kentucky', 'diagnostics/rhode-island', 'diagnostics/hawaii',
        'policies/island-water-v1', 'policies/hawaii-water-v1', 'policies/kentucky-exclave-v1',
        'corrections/hawaii-optimizer-v1', 'corrections/part-connectivity-v1')
    paths = [suite / 'suite.json', suite / 'diagnostics/new-york/diagnosis.json', suite / 'states/36/districts-26/benchmark.json',
        *(tmp_path / f'.cache/state-block-benchmark/source/{state}/tl_2020_{state}_tabblock20.zip' for state in ('36', '21', '44', '15')),
        *(suite / directory / 'preserved-map.geojson.gz' for directory in directories),
        *(tmp_path / 'prompts' / name for name in ('hawaii-water-benchmark.md', 'rhode-island-water-benchmark.json',
          'kentucky-exclave-benchmark.md', 'new-york-topology-diagnosis.md', 'maryland-virginia-geometry-diagnosis.md'))]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'original {index}')
    active = suite / 'policies/new-york-links-v1/states/36/districts-26/progress.json'
    active.parent.mkdir(parents=True)
    active.write_text('running')
    before = benchmark.protected_inventory()
    assert set(before) == {path.relative_to(tmp_path).as_posix() for path in paths}
    active.write_text('complete')
    assert benchmark.protected_inventory() == before
    prior = suite / 'policies/kentucky-exclave-v1/preserved-map.geojson.gz'
    prior.write_text('changed old evidence')
    assert benchmark.protected_inventory() != before


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    monkeypatch.setattr(benchmark, 'CODE_PATHS', ())
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
    output = suite / 'policies/new-york-links-v1/states/36/districts-26'
    return output, units, geoids, populations, labels, physical, augmented, required


def _successful_solver(monkeypatch: pytest.MonkeyPatch, geoids, labels) -> None:
    @contextmanager
    def observe(progress):
        progress.append({'inner_optimizer': {'success': True}})
        yield
    monkeypatch.setattr(benchmark, 'observe_solver', observe)
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
    assert '../districts-61/' in page
    assert '../../../../../diagnostics/new-york/' in page
    assert '__RESULT_SUMMARY__' not in page
