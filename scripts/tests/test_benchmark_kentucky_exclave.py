"""Kentucky attempts preserve old evidence and require independent connectivity.

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
from scripts import benchmark_kentucky_exclave as benchmark


@pytest.mark.parametrize('relative,count', [
    ('states/21/districts-6', 6),
    ('policies/hawaii-water-v1/states/15/districts-2', 6),
    ('policies/kentucky-exclave-v1/states/21/districts-8', 6),
    ('policies/kentucky-exclave-v1/states/21/districts-6/nested', 6),
    ('policies/kentucky-exclave-v1/states/21/../../../island-water-v1', 6),
])
def test_output_cannot_target_original_or_wrong_anchor(relative: str, count: int) -> None:
    with pytest.raises(ValueError, match='matching new run'):
        benchmark.validate_output((benchmark.SUITE / relative).resolve(), count)


def test_old_attempt_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/kentucky-exclave-v1/states/21/districts-6'
    output.mkdir(parents=True)
    original = b'{"status":"failed","reason":"preserved evidence"}'
    (output / 'benchmark.json').write_bytes(original)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(6, output)
    assert (output / 'benchmark.json').read_bytes() == original


@pytest.mark.parametrize('count', [6, 8, 9, 14])
def test_supported_anchor_uses_kentucky_lock(count: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    locks = []
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: locks.append(state) or nullcontext())
    calls = []
    monkeypatch.setattr(benchmark, '_run_locked', lambda count, output, moves: calls.append((count, output, moves)) or {'count': count})
    output = tmp_path / f'policies/kentucky-exclave-v1/states/21/districts-{count}'
    assert benchmark.run(count, output) == {'count': count}
    assert locks == ['21']
    assert calls == [(count, output.resolve(), 1000)]


def test_protection_includes_strict_diagnostics_and_prior_policies_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    directories = ('states/21', 'states/44', 'states/15', 'diagnostics/kentucky', 'diagnostics/rhode-island',
        'diagnostics/hawaii', 'policies/island-water-v1', 'policies/hawaii-water-v1', 'corrections/hawaii-optimizer-v1')
    paths = [suite / 'suite.json', suite / 'diagnostics/kentucky/diagnosis.json', suite / 'states/21/districts-6/benchmark.json',
        *(tmp_path / f'.cache/state-block-benchmark/source/{state}/tl_2020_{state}_tabblock20.zip' for state in ('21', '44', '15')),
        *(suite / directory / 'preserved-map.geojson.gz' for directory in directories),
        *(tmp_path / 'prompts' / name for name in ('hawaii-water-benchmark.md', 'rhode-island-water-benchmark.json', 'kentucky-topology-diagnosis.md'))]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'original {index}')
    active = suite / 'policies/kentucky-exclave-v1/states/21/districts-6/progress.json'
    active.parent.mkdir(parents=True)
    active.write_text('running')
    before = benchmark.protected_inventory()
    assert set(before) == {path.relative_to(tmp_path).as_posix() for path in paths}
    active.write_text('complete')
    assert benchmark.protected_inventory() == before
    prior = suite / 'policies/hawaii-water-v1/preserved-map.geojson.gz'
    prior.write_text('changed old evidence')
    assert benchmark.protected_inventory() != before


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    monkeypatch.setattr(benchmark, 'CODE_PATHS', ())
    monkeypatch.setattr(benchmark, 'EXTRA_CODE', ())
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    required = [suite / 'states/21/districts-6/benchmark.json', suite / 'diagnostics/kentucky/diagnosis.json',
        tmp_path / '.cache/state-block-benchmark/source/21/tl_2020_21_tabblock20.zip']
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('original evidence')
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {path.relative_to(tmp_path).as_posix(): benchmark.sha256(path) for path in required})
    source_hash = benchmark.sha256(required[-1])
    monkeypatch.setattr(benchmark, 'prepare_source', lambda *args: (tmp_path / 'source.shp', {'archive_sha256': source_hash}))
    populations = [5, 5, 10, 10, 10, 10, 10]
    geoids = [f'21001000100{i:04d}' for i in range(len(populations))]
    units = [Unit(geoid, (1000. * i, 0.), population) for i, (geoid, population) in enumerate(zip(geoids, populations))]
    monkeypatch.setattr(benchmark, 'load_units', lambda *args: (units, dict(zip(geoids, populations)), {'projection': {'lon0': -85., 'lat0': 38.}}))
    augmented = PartGraph(tuple(tuple(j for j in (i-1, i+1) if 0 <= j < 7) for i in range(7)), tuple(range(7)))
    physical = PartGraph(((), (2,), (1, 3), (2, 4), (3, 5), (4, 6), (5,)), tuple(range(7)))
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs: (physical, {}, {}))
    connection = {'id': 'ky-exclave-test', 'kind': 'recorded-exclave-connection', 'part_nodes': [0, 1]}
    monkeypatch.setattr(benchmark, 'build_kentucky_connections', lambda *args, **kwargs: (augmented, (connection,), {}))
    labels = (0, 0, 1, 2, 3, 4, 5)
    output = suite / 'policies/kentucky-exclave-v1/states/21/districts-6'
    return output, units, geoids, populations, labels, physical, augmented, required


def _successful_solver(monkeypatch: pytest.MonkeyPatch, geoids, labels) -> None:
    @contextmanager
    def observe(progress):
        progress.append({'inner_optimizer': {'success': True}})
        yield
    monkeypatch.setattr(benchmark, 'observe_solver', observe)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: DistrictingResult(
        centers=tuple(DistrictCenter(i, float(i), 0., 0.) for i in range(6)),
        assignments=dict(zip(geoids, labels)), populations={i: 10 for i in range(6)},
        iterations=1, converged=True, max_population_imbalance=0))


def _export_success(source, assignments, populations, output, **kwargs):
    assert kwargs['state_fips'] == '21'
    assert kwargs['exclave_connections'][0]['kind'] == 'recorded-exclave-connection'
    assert 'water_connections' not in kwargs
    output.mkdir(parents=True)
    manifest = {'strict_validation': {'passed': False, 'district_polygon_components': [2, 1, 1, 1, 1, 1]},
        'connectivity_validation': {'passed': True, 'policy': benchmark.POLICY, 'district_component_counts': [1]*6}}
    (output / 'map-manifest.json').write_text(json.dumps(manifest))
    return manifest


def test_full_attempt_distinguishes_physical_and_policy_connectivity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _, geoids, _, labels, _, _, required = _fixture(tmp_path, monkeypatch)
    original = {path: path.read_bytes() for path in required}
    _successful_solver(monkeypatch, geoids, labels)
    monkeypatch.setattr(benchmark, 'export_state_block_maps', _export_success)
    monkeypatch.setattr(benchmark, 'write_viewer', lambda output, report: (output / 'index.html').write_text('connected under recorded exclave policy'))
    report = benchmark.run(6, output)
    assert report['status'] == 'complete_under_exclave_policy'
    assert report['final_plan']['physical_part_components'] == [2, 1, 1, 1, 1, 1]
    assert report['final_plan']['policy_part_components'] == [1]*6
    assert not report['final_plan']['all_districts_physically_part_connected']
    assert report['final_plan']['all_districts_policy_connected']
    assert report['final_plan']['total_population'] == 60
    assert report['final_plan']['district_populations'] == [10]*6
    assert report['solver']['all_inner_optimizer_passes_succeeded']
    assert not report['maps']['strict_validation']['passed']
    assert report['maps']['connectivity_validation']['passed']
    assert report['comparison_baseline']['strict_solver_ran'] is False
    assert report['preservation_audit']['rhode_island_and_hawaii_evidence_byte_identical']
    saved = json.loads((output / 'solver-result.json').read_text())
    assert saved['assignments'] == dict(zip(geoids, labels))
    assert 'exclave_connections_sha256' in saved['provenance']
    assert all(path.read_bytes() == data for path, data in original.items())


def test_unsuccessful_optimizer_is_persisted_without_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, *_ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(algorithm, 'minimize', lambda *args, **kwargs: OptimizeResult(
        x=np.zeros(6), fun=0., jac=np.zeros(6), success=False, status=2,
        message='forced line-search failure', nit=0, nfev=21))
    monkeypatch.setattr(benchmark, 'export_state_block_maps', lambda *args, **kwargs: pytest.fail('Must not export failed optimizer output'))
    with pytest.raises(DistrictingOptimizationError, match='forced line-search failure'):
        benchmark.run(6, output)
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
        benchmark.run(6, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'independent_polygon_validation_and_map_export'
    assert (output / 'solver-result.json').exists(), 'Retain failed assignments for diagnosis'
    assert report['final_plan']['all_districts_policy_connected'], 'Graph success alone must not imply completed geometry'
    assert not (output / 'index.html').exists()


def test_disconnected_augmented_source_fails_before_solving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _, _, _, _, physical, _, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(benchmark, 'build_kentucky_connections', lambda *args, **kwargs: (physical, (), {}))
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *args, **kwargs: pytest.fail('Disconnected policy graph must not solve'))
    with pytest.raises(ValueError, match='one connected source graph'):
        benchmark.run(6, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'prepare_recorded_exclave_connection'
    assert not (output / 'initial-solver-result.json').exists()


def test_viewer_calls_connection_exclave_not_water_only(tmp_path: Path) -> None:
    benchmark.write_viewer(tmp_path, {'district_count': 6,
        'input': {'projection': {'lon0': -85, 'lat0': 38}},
        'final_plan': {'max_absolute_deviation_percent': .001}})
    page = (tmp_path / 'index.html').read_text()
    assert 'recorded exclave-link policy' in page
    assert 'conceptual link crosses Missouri land and water' in page
    assert '../districts-14/' in page
    assert '../../../../../diagnostics/kentucky/' in page
    assert '__RESULT_SUMMARY__' not in page
