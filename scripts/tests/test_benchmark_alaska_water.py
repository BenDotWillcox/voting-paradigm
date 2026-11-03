"""Alaska plans preserve evidence and keep geometry, policy and balance distinct."""
from contextlib import contextmanager, nullcontext
import json
import math

import pytest

from districting import DistrictCenter, DistrictingOptimizationError, DistrictingResult, Unit
from districting.part_connectivity import PartGraph
from scripts import benchmark_alaska_water as benchmark


@pytest.mark.parametrize('count', (1, 2))
def test_requested_anchors_keep_the_existing_numerical_model(count):
    config = benchmark.configuration_for_run(count)
    assert {name: config[name] for name in ('seed', 'inner_max_iterations',
        'max_outer_iterations', 'center_tolerance_m', 'max_rebalance_moves')} == {
        'seed': 20200955, 'inner_max_iterations': 1000, 'max_outer_iterations': 80,
        'center_tolerance_m': 1e-4, 'max_rebalance_moves': 1000}
    assert config['solver_projection'] == 'population-centered equirectangular from normalized source internal points'
    assert config['datum'] == 'original TIGER NAD83; longitude representation change only'


@pytest.mark.parametrize('count', (0, 3, True, 1.0, '2'))
def test_unrequested_counts_are_rejected(count):
    with pytest.raises(ValueError, match='Only Alaska K1/K2'):
        benchmark.configuration_for_run(count)


def _records():
    return [
        {'geoid': '020010001000001', 'population': 4, 'working_internal_point': [-186., 60.], 'internal_point': [174., 60.]},
        {'geoid': '020010001000002', 'population': 0, 'working_internal_point': [-180., 65.], 'internal_point': [180., 65.]},
        {'geoid': '020010001000003', 'population': 0, 'working_internal_point': [-175., 65.], 'internal_point': [-175., 65.]},
        {'geoid': '020010001000004', 'population': 5, 'working_internal_point': [-150., 60.], 'internal_point': [-150., 60.]},
    ]


def test_normalized_internal_points_retain_population_and_do_not_wrap_back():
    records = _records()
    units, projection = benchmark.units_from_records(records)
    assert [unit.geoid for unit in units] == [row['geoid'] for row in records]
    assert [unit.population for unit in units] == [4, 0, 0, 5]
    assert projection['lon0'] == -166.
    assert projection['lat0'] == 60.
    assert projection['kind'] == 'population-centered-equirectangular'
    degree_y = 6371000 * math.pi / 180
    assert units[0].centroid == pytest.approx((-20 * degree_y * .5, 0))
    assert units[-1].centroid == pytest.approx((16 * degree_y * .5, 0))
    assert units[1].centroid[1] == pytest.approx(5 * degree_y)
    assert sum(unit.population * unit.centroid[0] for unit in units) == pytest.approx(0)


@pytest.mark.parametrize('records', ([], [_records()[0], _records()[0]], [_records()[1]]))
def test_empty_duplicate_or_zero_mass_records_are_rejected(records):
    with pytest.raises(ValueError):
        benchmark.units_from_records(records)


def _graphs():
    physical = PartGraph(((1,), (0,), (3,), (2,)), (0, 1, 2, 3))
    augmented = PartGraph(((1,), (0, 2), (1, 3), (2,)), (0, 1, 2, 3))
    return physical, augmented


def test_audit_separates_policy_connectivity_and_fractional_ideal():
    physical, augmented = _graphs()
    result = benchmark.audit_plan((0, 0, 0, 1), [4, 0, 0, 5], physical, augmented, 2)
    assert result['district_populations'] == [4, 5]
    assert result['target_population'] == 4.5
    assert result['max_absolute_deviation_people'] == .5
    assert result['max_absolute_deviation_percent'] == pytest.approx(100 / 9)
    assert result['physical_part_components'] == [2, 1]
    assert result['policy_part_components'] == [1, 1]
    assert not result['all_districts_physically_connected']
    assert result['all_districts_policy_connected']
    assert result['district_block_counts'] == [3, 1]


def test_audit_does_not_use_a_link_across_district_owners():
    physical, augmented = _graphs()
    result = benchmark.audit_plan((0, 1, 0, 1), [4, 0, 0, 5], physical, augmented, 2)
    assert result['policy_part_components'] == [2, 2]
    assert not result['all_districts_policy_connected']


@pytest.mark.parametrize('labels', ((0, 0, 1), (0, 0, 0, 0), (0, 0, 0, 2), (0, False, 0, 1), (0, 0., 0, 1)))
def test_audit_rejects_missing_blocks_empty_districts_and_noninteger_labels(labels):
    physical, augmented = _graphs()
    with pytest.raises(ValueError, match='Assignments must cover'):
        benchmark.audit_plan(labels, [4, 0, 0, 5], physical, augmented, 2)


def test_k1_direct_assignment_never_invokes_the_optimizer_or_trace(tmp_path, monkeypatch):
    units, _ = benchmark.units_from_records(_records())
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *a, **k: pytest.fail('K1 must not optimize'))
    monkeypatch.setattr(benchmark, 'trace_optimizer', lambda *a, **k: pytest.fail('K1 must not trace an optimizer'))
    report = {}
    labels, centers = benchmark.solve_initial(units, 1, tmp_path, report)
    assert labels == (0, 0, 0, 0)
    assert centers == []
    assert report['solver']['optimizer_ran'] is False
    assert report['solver']['centers_converged'] is None
    assert report['solver']['inner_optimization_status'] == 'not_applicable'
    assert not (tmp_path / 'optimizer-trace.jsonl').exists()


def _trace(monkeypatch, *, ok=True, success=True, passes=True):
    @contextmanager
    def observe(path):
        class Trace:
            observation_ok = ok
            def __init__(self):
                self.passes = [{'inner_optimizer': {'success': success, 'actual_maxiter': 1000}}] if passes else []
            def summary(self):
                return {'observation_ok': self.observation_ok, 'passes': self.passes}
        path.write_text('{"type":"observation"}\n')
        yield Trace()
    monkeypatch.setattr(benchmark, 'trace_optimizer', observe)


def _result(units):
    return DistrictingResult(centers=(DistrictCenter(0, 0., 0., 0.), DistrictCenter(1, 1., 0., 0.)),
        assignments=dict(zip((unit.geoid for unit in units), (0, 0, 0, 1))),
        populations={0: 4, 1: 5}, iterations=80, converged=False, max_population_imbalance=1)


def test_k2_keeps_fixed_budgets_and_separates_outer_cap_from_inner_success(tmp_path, monkeypatch):
    units, _ = benchmark.units_from_records(_records())
    _trace(monkeypatch)
    calls = []
    def solve(actual_units, count, **kwargs):
        calls.append((actual_units, count, kwargs))
        return _result(units)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', solve)
    report = {'artifact_sha256': {}}
    labels, centers = benchmark.solve_initial(units, 2, tmp_path, report)
    assert calls == [(units, 2, {'seed': 20200955, 'max_outer_iterations': 80,
        'center_tol': 1e-4, 'inner_max_iterations': 1000})]
    assert labels == (0, 0, 0, 1)
    assert len(centers) == 2
    assert report['solver']['all_inner_optimizer_passes_succeeded']
    assert not report['solver']['centers_converged']
    assert report['solver']['outer_iteration_limit_reached']
    assert report['artifact_sha256']['optimizer-trace.jsonl'] == benchmark.sha256(tmp_path / 'optimizer-trace.jsonl')


@pytest.mark.parametrize('trace_args', ({'ok': False}, {'success': False}, {'passes': False}))
def test_unobserved_or_failed_inner_pass_cannot_be_accepted(tmp_path, monkeypatch, trace_args):
    units, _ = benchmark.units_from_records(_records())
    _trace(monkeypatch, **trace_args)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *a, **k: _result(units))
    report = {'artifact_sha256': {}}
    with pytest.raises(ValueError, match='independently observed inner passes'):
        benchmark.solve_initial(units, 2, tmp_path, report)
    assert report['optimizer_trace']
    assert 'optimizer-trace.jsonl' in report['artifact_sha256']
    assert 'solver' not in report


def _fixture(tmp_path, monkeypatch, count):
    suite = tmp_path / 'suite'
    namespace = suite / 'policies/alaska-water-v1'
    archive = tmp_path / 'source.zip'
    archive.write_bytes(b'source archive fixture')
    strict = suite / 'states/02/districts-1/benchmark.json'
    strict.parent.mkdir(parents=True)
    strict.write_text(json.dumps({'status': 'unsupported_antimeridian_topology', 'solver_progress': []}))
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    monkeypatch.setattr(benchmark, 'OUTPUT', namespace)
    monkeypatch.setattr(benchmark, 'ARCHIVE', archive)
    monkeypatch.setattr(benchmark, 'SOURCE_SHA', benchmark.sha256(archive))
    monkeypatch.setattr(benchmark, 'TOTAL', 9)
    monkeypatch.setattr(benchmark, 'BLOCKS', 4)
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda *args: nullcontext())
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda: {
        path.relative_to(tmp_path).as_posix(): benchmark.sha256(path) for path in (archive, strict)})
    monkeypatch.setattr(benchmark, 'runtime_code', lambda: {'fixture.py': 'fixed'})
    class Measure:
        def __init__(self):
            self.phases = {}
        @contextmanager
        def phase(self, name):
            try:
                yield
            finally:
                self.phases[name] = {'wall_seconds': .01}
        def close(self):
            pass
    monkeypatch.setattr(benchmark, 'Measurements', Measure)
    monkeypatch.setattr(benchmark, 'process_memory', lambda: (100, 200))
    records = _records()
    physical, augmented = _graphs()
    monkeypatch.setattr(benchmark, 'load_normalized_parts', lambda *args: (
        [None] * 4, records, (0, 1, 2, 3), (0, 0, 0, 0), {'normalized': True}))
    monkeypatch.setattr(benchmark, 'build_exact_part_graph', lambda *args: (physical, {'components': 2}))
    connections = ({'id': 'test-water', 'kind': 'recorded-water-connection', 'part_nodes': [1, 2]},)
    monkeypatch.setattr(benchmark, 'build_alaska_connections', lambda *args: (augmented, connections, {}))
    def export(parts, actual_records, owners, indices, assignments, actual_links, output, **kwargs):
        assert actual_records == records
        assert actual_links == connections
        output.mkdir(parents=True)
        (output / 'index.html').write_text('verified map fixture')
        (output / 'manifest.json').write_text('{}')
        return {'connectivity_validation': {'passed': True}, 'strict_validation': {'passed': False}}
    monkeypatch.setattr(benchmark, 'export_alaska_maps', export)
    return namespace / f'states/02/districts-{count}', records, (archive, strict)


def test_k1_pipeline_includes_zero_population_blocks_and_preserves_originals(tmp_path, monkeypatch):
    output, records, preserved = _fixture(tmp_path, monkeypatch, 1)
    before = {path: path.read_bytes() for path in preserved}
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', lambda *a, **k: pytest.fail('K1 must not optimize'))
    report = benchmark.run(1, output)
    assert report['status'] == 'complete_under_recorded_water_policy'
    assert report['final_plan']['block_count'] == 4
    assert report['final_plan']['district_populations'] == [9]
    assert report['final_plan']['physical_part_components'] == [2]
    assert report['final_plan']['policy_part_components'] == [1]
    assert report['final_plan']['max_absolute_deviation_people'] == 0
    assert report['solver']['optimizer_ran'] is False
    assert not (output / 'optimizer-trace.jsonl').exists()
    assert not report['strict_baseline']['solver_ran']
    saved = json.loads((output / 'solver-result.json').read_text())
    assert saved['assignments'] == {row['geoid']: 0 for row in records}
    assert all(path.read_bytes() == data for path, data in before.items())
    assert report['preservation_audit']['original_files_byte_identical']
    assert report['peak_process_working_set_bytes'] == 200
    assert json.loads((output / 'progress.json').read_text())['active_phase'] is None


def test_numerical_failure_keeps_trace_and_never_exports(tmp_path, monkeypatch):
    output, _, preserved = _fixture(tmp_path, monkeypatch, 2)
    before = {path: path.read_bytes() for path in preserved}
    _trace(monkeypatch, success=False)
    def fail(*args, **kwargs):
        raise DistrictingOptimizationError('iteration_limit', status=1, message='forced limit',
            iterations=1000, function_evaluations=1010)
    monkeypatch.setattr(benchmark, 'balanced_power_diagram', fail)
    monkeypatch.setattr(benchmark, 'export_alaska_maps', lambda *a, **k: pytest.fail('Failed solver must not export'))
    with pytest.raises(DistrictingOptimizationError, match='forced limit'):
        benchmark.run(2, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'solve'
    assert not report['optimizer_failure']['plan_returned']
    assert report['optimizer_trace']['passes'][0]['inner_optimizer']['success'] is False
    assert report['artifact_sha256']['optimizer-trace.jsonl'] == benchmark.sha256(output / 'optimizer-trace.jsonl')
    assert not (output / 'solver-result.json').exists()
    assert not (output / 'maps').exists()
    assert all(path.read_bytes() == data for path, data in before.items())


def test_failed_polygon_validation_is_not_a_completed_map(tmp_path, monkeypatch):
    output, _, _ = _fixture(tmp_path, monkeypatch, 1)
    monkeypatch.setattr(benchmark, 'export_alaska_maps', lambda *a, **k: {'connectivity_validation': {'passed': False}})
    with pytest.raises(ValueError, match='Independent polygon/link validation failed'):
        benchmark.run(1, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'independent_polygon_and_seam_validation_map_export'
    assert report['final_plan']['all_districts_policy_connected']
    assert not report.get('optimizer_failure')


def test_previous_attempt_and_original_directories_cannot_be_overwritten(tmp_path, monkeypatch):
    output, _, _ = _fixture(tmp_path, monkeypatch, 1)
    with pytest.raises(ValueError, match='matching new Alaska policy'):
        benchmark.validate_output(benchmark.SUITE / 'states/02/districts-1', 1)
    with pytest.raises(ValueError, match='matching new Alaska policy'):
        benchmark.validate_output(output, 2)
    output.mkdir(parents=True)
    (output / 'benchmark.json').write_text('original failed run')
    with pytest.raises(FileExistsError, match='earlier Alaska attempt'):
        benchmark.run(1, output)
    assert (output / 'benchmark.json').read_text() == 'original failed run'


def test_destination_is_rechecked_after_state_lock(tmp_path, monkeypatch):
    output, _, _ = _fixture(tmp_path, monkeypatch, 1)
    @contextmanager
    def concurrent_attempt(state):
        assert state == '02'
        output.mkdir(parents=True)
        (output / 'benchmark.json').write_text('completed while waiting')
        yield
    monkeypatch.setattr(benchmark, 'state_execution_lock', concurrent_attempt)
    with pytest.raises(FileExistsError, match='earlier Alaska attempt'):
        benchmark.run(1, output)
    assert (output / 'benchmark.json').read_text() == 'completed while waiting'


def test_terminal_report_fallback_is_explicit_and_preserves_final_evidence(tmp_path, monkeypatch):
    output, _, _ = _fixture(tmp_path, monkeypatch, 1)
    original_write = benchmark.write_json
    def fail_terminal_replace(path, value):
        if path.name == 'benchmark.json' and value.get('status') == 'complete_under_recorded_water_policy':
            raise PermissionError('simulated Windows replacement sharing violation')
        original_write(path, value)
    monkeypatch.setattr(benchmark, 'write_json', fail_terminal_replace)
    benchmark.run(1, output)
    report = json.loads((output / 'terminal-report.json').read_text())
    assert report['status'] == 'complete_under_recorded_water_policy'
    assert 'sharing violation' in report['terminal_write_error']
    assert report['active_phase'] is None
    assert report['finished_at']
    assert report['artifact_sha256']['solver-result.json'] == benchmark.sha256(output / 'solver-result.json')
    progress = json.loads((output / 'progress.json').read_text())
    assert progress['authoritative_report'] == 'terminal-report.json'
    assert progress['status'] == report['status']
