"""Small synthetic checks; never load production outputs or run a solver."""
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
import gzip
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
import shapefile
from shapely.geometry import Polygon, MultiPolygon, mapping

from scripts import summarize_florida_water as summary


def manifest():
    return {'status': 'complete', 'finished_at': '2026-10-26T12:00:00Z', 'pid': 101,
            'jobs': [{'district_count': k, 'status': summary.ACCEPTED, 'pid': 102+i,
                      'finished_at': '2026-10-26T11:00:00Z', 'exit_code': 0}
                     for i, k in enumerate(summary.COUNTS)]}


def test_complete_manifest_has_exactly_four_first_attempts():
    summary.verify_manifest(manifest())


@pytest.mark.parametrize('mutation', [
    lambda m: m.update(status='running'), lambda m: m.update(finished_at=None),
    lambda m: m['jobs'].pop(), lambda m: m['jobs'][0].update(district_count=52),
    lambda m: m['jobs'][0].update(exit_code=1), lambda m: m['jobs'][0].update(exit_code=True),
    lambda m: m['jobs'][0].update(status='failed'), lambda m: m['jobs'][0].update(finished_at=None),
    lambda m: m.update(status='complete_with_numerical_failures'),
])
def test_active_missing_or_contradictory_manifest_fails(mutation):
    data = manifest(); mutation(data)
    with pytest.raises(ValueError):
        summary.verify_manifest(data)


def test_numerical_failure_is_terminal_but_not_accepted(tmp_path):
    data = manifest(); data['status'] = 'complete_with_numerical_failures'
    data['jobs'][0].update(status='failed', exit_code=1)
    summary.verify_manifest(data)
    result = summary.verify_plan(tmp_path, {'status': 'failed', 'error': 'optimizer cap'}, {}, 28)
    assert result['accepted_plan'] is False and 'map_url' not in result


def test_stopped_queue_retains_pending_and_ambiguous_work_without_reading_it(monkeypatch):
    data = manifest(); data['status'] = 'stopped'
    data['jobs'][0].update(status='needs_inspection', error='Sharing error')
    data['jobs'][1].update(status='pending')
    summary.verify_manifest(data)
    monkeypatch.setattr(summary, 'read_json', lambda _: pytest.fail('Unaccepted report must not be read'))
    for job in data['jobs'][:2]:
        row = summary.load_run(job['district_count'], {}, job=job, manifest=data)
        assert row['map_url'] is None and row['accepted_plan'] is False


def settings(k):
    threshold = Fraction(summary.TOTAL * 99, 100 * k)
    return {'seed': 20200955, 'max_outer_iterations': 80, 'inner_max_iterations': 1000,
        'center_tolerance_m': 1e-4, 'max_rebalance_moves': 1000,
        'root_eligibility_relative_band': .01, 'group_population_preflight_tolerance': .01,
        'physical_adjacency_rule': 'polygon parts; disjoint interiors; positive-length shared boundary; F***1****',
        'connection_policy': 'population-aware-rooted-boundary-forest-v1',
        'connection_kinds': ['recorded-water-connection'],
        'minimum_district_population_exact': str(threshold),
        'minimum_district_population_for_root_classification': float(threshold),
        'inner_optimization': {'max_line_search_steps': 100,
            'failure_policy': 'raise on unsuccessful termination or nonfinite output; no completed plan returned',
            'normalization': 'population-mass and geometry-derived shifted squared costs; mean-zero weight gauge'}}


@pytest.mark.parametrize('k', summary.COUNTS)
def test_settings_use_actual_target_population(k):
    summary.verify_configuration(settings(k), k)


@pytest.mark.parametrize('key,value', [('seed', 1), ('inner_max_iterations', 300),
    ('max_outer_iterations', 81), ('center_tolerance_m', .1), ('max_rebalance_moves', 1001),
    ('connection_kinds', ['recorded-exclave-connection']),
    ('minimum_district_population_exact', '123'), ('minimum_district_population_for_root_classification', 123)])
def test_changed_settings_are_rejected(key, value):
    data = settings(37); data[key] = value
    with pytest.raises(ValueError): summary.verify_configuration(data, 37)


@pytest.mark.parametrize('k', [52, 61, True])
def test_unrequested_count_is_rejected(k):
    with pytest.raises(ValueError): summary.verify_configuration({}, k)


@pytest.mark.parametrize('filename', ['benchmark.json', 'terminal-report.json'])
@pytest.mark.parametrize('absolute', [False, True])
def test_only_selected_hashed_report_is_accepted(tmp_path, filename, absolute):
    path = tmp_path / filename; path.write_text('{}')
    job = {'terminal_validation': {'passed': True, 'report_path': str(path) if absolute else filename,
                                  'benchmark_sha256': summary.sha256(path)}}
    assert summary.selected_report_path(job, tmp_path) == path.resolve()
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError): summary.selected_report_path(job, tmp_path)


@pytest.mark.parametrize('name', ['', '../benchmark.json', 'progress.json', '../other/terminal-report.json'])
def test_report_selection_rejects_guessing_or_path_escape(tmp_path, name):
    with pytest.raises(ValueError):
        summary.selected_report_path({'terminal_validation': {'passed': True, 'report_path': name}}, tmp_path)


def test_terminal_summary_stops_before_any_child_read_while_parent_active(monkeypatch):
    reads = []
    def read(path):
        reads.append(path.name)
        return {'status': 'running'}
    monkeypatch.setattr(summary, 'read_json', read)
    with pytest.raises(ValueError): summary.summary()
    assert reads == ['run.json']


def launch_record():
    return {'script': 'scripts/run_florida_water_suite.py', 'counts': list(summary.COUNTS),
            'execution': 'serial_fresh_processes', 'output': str(summary.OUTPUT), 'launcher_pid': 100}


def test_exact_parent_and_child_and_launcher_pid_inventory():
    assert summary.recorded_process_ids(manifest(), launch_record()) == [100, 101, 102, 103, 104, 105]


@pytest.mark.parametrize('mutation', [lambda m: m.pop('pid'), lambda m: m.update(pid=True),
    lambda m: m.update(pid=-1), lambda m: m['jobs'][0].pop('pid')])
def test_invalid_or_missing_process_identity_rejected(mutation):
    data = manifest(); mutation(data)
    with pytest.raises(ValueError): summary.recorded_process_ids(data)


@pytest.mark.parametrize('key,value', [('script', 'wrong.py'), ('counts', [28]),
    ('execution', 'parallel'), ('output', 'elsewhere'), ('launcher_pid', 0)])
def test_wrong_launch_record_rejected(key, value):
    record = launch_record(); record[key] = value
    with pytest.raises(ValueError): summary.recorded_process_ids(manifest(), record)


def test_windows_query_is_exact_and_not_denied_cim_inventory(monkeypatch):
    def fake(command, **options):
        assert 'Get-Process -Id $recordedId' in command[-1]
        assert '101,102' in command[-1] and 'Cim' not in command[-1]
        assert 'NoProcessFoundForGivenId,*' in command[-1]
        assert options['check'] is True and options['timeout'] == 30
        return SimpleNamespace(stdout='[{"pid":101,"active":false},{"pid":102,"active":false}]', stderr='')
    monkeypatch.setattr(summary.subprocess, 'run', fake)
    assert len(summary.windows_pid_status([101, 102])) == 2


@pytest.mark.parametrize('stdout,stderr', [('[]', ''), ('[{"pid":101,"active":0}]', ''),
    ('[{"pid":101,"active":false}]', 'Access denied')])
def test_incomplete_or_error_process_query_fails_closed(monkeypatch, stdout, stderr):
    monkeypatch.setattr(summary.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=stdout, stderr=stderr))
    with pytest.raises(ValueError): summary.windows_pid_status([101])


def test_all_exact_processes_absent_and_state12_lock_free(monkeypatch):
    calls = []
    @contextmanager
    def lock(state):
        calls.append(state); yield
    monkeypatch.setattr(summary, 'WINDOWS', True)
    monkeypatch.setattr(summary, 'windows_pid_status', lambda pids: [{'pid': p, 'active': False} for p in pids])
    monkeypatch.setattr(summary, 'state_execution_lock', lock)
    result = summary.verify_no_active_children(manifest(), launch_record())
    assert calls == ['12'] and result['all_recorded_pids_absent'] is True


def test_active_process_blocks_lock_check(monkeypatch):
    monkeypatch.setattr(summary, 'WINDOWS', True)
    monkeypatch.setattr(summary, 'windows_pid_status', lambda _: [{'pid': 101, 'active': True}])
    monkeypatch.setattr(summary, 'state_execution_lock', lambda _: pytest.fail('Lock must not be queried yet'))
    with pytest.raises(ValueError): summary.verify_no_active_children(manifest())


def test_foreign_worker_state_lock_still_blocks(monkeypatch):
    @contextmanager
    def lock(_):
        raise RuntimeError('State lock is held')
        yield
    monkeypatch.setattr(summary, 'WINDOWS', True)
    monkeypatch.setattr(summary, 'windows_pid_status', lambda _: [])
    monkeypatch.setattr(summary, 'state_execution_lock', lock)
    with pytest.raises(RuntimeError, match='State lock'): summary.verify_no_active_children(manifest())


def prelaunch_record():
    return {'phase': 'prelaunch', 'command': 'python -m pytest', 'passed': 999, 'failed': 0,
            'elapsed_seconds': 33.13, 'recorded_at': '2026-10-26T10:00:00Z'}


@pytest.mark.parametrize('count,phase,status', [(999, 'prelaunch', None), (21, 'before launch', 'passed'),
                                              (1007, 'prelaunch', 'passed')])
def test_actual_test_counts_and_original_phase_schema(count, phase, status):
    record = prelaunch_record(); record.update(passed=count, phase=phase)
    if status: record['status'] = status
    result = summary.verify_prelaunch_tests(record, '2026-10-26T10:01:00+00:00')
    assert result['passed'] == count and result['recorded_before_launch'] is True


@pytest.mark.parametrize('key,value', [('passed', 0), ('passed', True), ('failed', 1), ('failed', False),
    ('phase', 'after launch'), ('status', 'failed'), ('command', ''), ('elapsed_seconds', -1),
    ('recorded_at', '2026-10-26T10:02:00Z'), ('recorded_at', '2026-10-26T09:00:00'), ('recorded_at', 'bad')])
def test_failed_ambiguous_or_late_test_evidence_rejected(key, value):
    record = prelaunch_record(); record[key] = value
    with pytest.raises(ValueError): summary.verify_prelaunch_tests(record, '2026-10-26T10:01:00Z')


def test_separate_serial_process_and_preparation_timing():
    data = {'preparation_wall_seconds': 5, 'serial_child_process_wall_seconds': 20,
            'elapsed_wall_seconds': 30, 'jobs': [{'process_wall_seconds': 8}, {'process_wall_seconds': 12}]}
    assert summary.execution_timing(data)['serial_child_process_wall_seconds'] == 20
    data['serial_child_process_wall_seconds'] = 30
    with pytest.raises(ValueError): summary.execution_timing(data)


def link_fixture(assigned=(0, 0)):
    endpoints = [{'geoid': '120000000000001', 'part_node': 0, 'part_index': 0, 'coordinate': [1, 0]},
                 {'geoid': '120000000000002', 'part_node': 1, 'part_index': 0, 'coordinate': [2, 0]}]
    record = {'id': 'fl-water-001', 'state_fips': '12', 'kind': 'recorded-water-connection',
              'candidate_id': 'fl-candidate-00-01', 'component_ids': [0, 1], 'endpoints': endpoints, 'distance_m': 100}
    props = {key: deepcopy(record[key]) for key in ('id', 'state_fips', 'component_ids', 'endpoints', 'distance_m')}
    props.update(endpoint_districts=list(assigned), used_by_district=assigned[0] if assigned[0] == assigned[1] else None)
    feature = {'geometry': {'type': 'LineString', 'coordinates': [[1, 0], [2, 0]]}, 'properties': props}
    assignments = dict(zip([e['geoid'] for e in endpoints], assigned))
    return record, feature, assignments


@pytest.mark.parametrize('assigned', [(0, 0), (0, 1)])
def test_water_edge_contributes_only_when_both_endpoint_blocks_share_district(assigned):
    record, feature, assignments = link_fixture(assigned)
    row = summary.verify_links([feature], [record], assignments)[0]
    assert row['used_by_district'] == (0 if assigned == (0, 0) else None)


@pytest.mark.parametrize('mutation', [lambda f: f['geometry'].update(type='Point'),
    lambda f: f['geometry']['coordinates'][0].__setitem__(0, 99),
    lambda f: f['properties'].update(used_by_district=1),
    lambda f: f['properties'].update(endpoint_districts=[0, 1]),
    lambda f: f['properties']['endpoints'][0].update(part_node=55)])
def test_link_geometry_or_owner_tampering_rejected(mutation):
    record, feature, assignments = link_fixture(); mutation(feature)
    with pytest.raises(ValueError): summary.verify_links([feature], [record], assignments)


def test_graph_traversal_does_not_connect_multipart_ownership_or_cross_district_link():
    graph, owners = ((1,), (0,), ()), (0, 1, 0)
    assert summary.independent_component_counts(graph, owners, [0, 0], 1) == [2]
    assert summary.independent_component_counts(graph, owners, [0, 0], 1, [(1, 2)]) == [1]
    assert summary.independent_component_counts(graph, owners, [0, 1], 2, [(1, 2)]) == [2, 1]


@pytest.mark.parametrize('labels,edges', [([True], []), ([1], []), ([0], [(0, 2)]), ([0], [(0, 0)])])
def test_graph_check_rejects_invalid_labels_or_endpoints(labels, edges):
    with pytest.raises(ValueError): summary.independent_component_counts(((),), (0,), labels, 1, edges)


def write_source(tmp_path, monkeypatch):
    archive = tmp_path / 'tl_2020_12_tabblock20.zip'
    base = tmp_path / archive.stem / archive.stem; base.parent.mkdir()
    blocks = [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Polygon([(2, 0), (3, 0), (3, 1), (2, 1)])]
    with shapefile.Writer(str(base)) as writer:
        writer.field('GEOID20', 'C', 15); writer.field('POP20', 'N', 10)
        for i, polygon in enumerate(blocks, 1):
            writer.poly([list(polygon.exterior.coords)[::-1]])
            writer.record(f'12000000000000{i}', i * 10)
    with zipfile.ZipFile(archive, 'w') as z:
        z.write(base.with_suffix('.dbf'), base.with_suffix('.dbf').name)
    monkeypatch.setattr(summary, 'SOURCE', archive)
    monkeypatch.setattr(summary, 'SOURCE_SHA', summary.sha256(archive))
    monkeypatch.setattr(summary, 'BLOCKS', 2); monkeypatch.setattr(summary, 'TOTAL', 30)
    return blocks, {base.with_suffix(suffix).name: summary.sha256(base.with_suffix(suffix)) for suffix in ('.shp', '.shx', '.dbf')}


def test_source_dbf_population_and_saved_full_polygon_endpoint_check(tmp_path, monkeypatch):
    blocks, hashes = write_source(tmp_path, monkeypatch)
    pops = summary.source_populations(); record, _, assignments = link_fixture()
    report = {'source': {'extracted_file_sha256': hashes}, 'water_connections': [record],
              'final_plan': {'physical_part_components': [2]}}
    features = [{'properties': {'district_id': 0}, 'geometry': mapping(MultiPolygon(blocks))}]
    check = summary.verify_saved_polygon_links(features, report, assignments, pops, 1)
    assert check['physical_components'] == [2] and check['policy_components'] == [1]
    record['endpoints'][0]['coordinate'] = [1, .5]
    with pytest.raises(ValueError, match='exact original source vertex'):
        summary.verify_saved_polygon_links(features, report, assignments, pops, 1)


def test_saved_polygon_check_cannot_use_link_across_districts(tmp_path, monkeypatch):
    blocks, hashes = write_source(tmp_path, monkeypatch)
    pops = summary.source_populations(); record, _, assignments = link_fixture((0, 1))
    report = {'source': {'extracted_file_sha256': hashes}, 'water_connections': [record],
              'final_plan': {'physical_part_components': [1, 1]}}
    features = [{'properties': {'district_id': i}, 'geometry': mapping(p)} for i, p in enumerate(blocks)]
    assert summary.verify_saved_polygon_links(features, report, assignments, pops, 2)['policy_components'] == [1, 1]
    features[0]['geometry'] = mapping(MultiPolygon([blocks[0], Polygon([(4, 0), (5, 0), (5, 1), (4, 1)])]))
    report['final_plan']['physical_part_components'] = [2, 1]
    with pytest.raises(ValueError, match='not connected'):
        summary.verify_saved_polygon_links(features, report, assignments, pops, 2)


def test_source_archive_and_population_universe_must_match(tmp_path, monkeypatch):
    write_source(tmp_path, monkeypatch)
    monkeypatch.setattr(summary, 'TOTAL', 31)
    with pytest.raises(ValueError, match='official'): summary.source_populations()
    monkeypatch.setattr(summary, 'SOURCE_SHA', '0' * 64)
    with pytest.raises(ValueError, match='archive hash'): summary.source_populations()


def test_population_verifier_uses_fractional_ideal_and_exact_source_universe():
    pops = {'a': 4, 'b': 5, 'c': 1}; assigned = {'a': 0, 'b': 1, 'c': 2}
    plan = {'district_populations': [4, 5, 1], 'district_block_counts': [1, 1, 1],
            'deviation_numerators': [2, 5, -7], 'max_absolute_deviation_people': 7/3,
            'max_absolute_deviation_percent': 70, 'total_range_people': 4}
    result = summary.verify_assignments(assigned, pops, 3, plan)
    assert result['max_absolute_deviation_people'] == 7/3
    assigned.pop('c')
    with pytest.raises(ValueError): summary.verify_assignments(assigned, pops, 3, plan)


def test_compressed_maps_are_decompressed_and_hashed(tmp_path):
    (tmp_path / 'maps').mkdir(); raw = b'{"features":[]}'
    path = tmp_path / 'maps/example.geojson.gz'; path.write_bytes(gzip.compress(raw))
    item = {'gzip_path': path.name, 'gzip_bytes': path.stat().st_size, 'raw_bytes': len(raw),
            'raw_sha256': hashlib.sha256(raw).hexdigest()}
    assert summary.verify_compressed_maps(tmp_path, {'storage': {'artifacts': [item]}}) == 1
    item['raw_sha256'] = 'bad'
    with pytest.raises(ValueError): summary.verify_compressed_maps(tmp_path, {'storage': {'artifacts': [item]}})


def failed_data():
    rows = [{'district_count': k, 'house_size': summary.ANCHORS[k], 'status': 'pending',
             'accepted_plan': False, 'map_url': 'MUST-NOT-LINK'} for k in summary.COUNTS]
    return {'runs': rows, 'status': 'stopped', 'scope': 'Florida', 'preservation': {'files_rehashed': 2},
            'execution_timing': {'preparation_wall_seconds': 0, 'serial_child_process_wall_seconds': 0, 'elapsed_wall_seconds': 1},
            'validation_note': 'Synthetic test', 'prelaunch_tests': {'record': {'passed': 999}},
            'summary_validation_tests': {'record': {'passed': 25}}, 'limitations': []}


def test_unaccepted_results_never_render_map_link_or_population_claim():
    data = failed_data()
    for output in (summary.markdown(data), summary.html(data)):
        assert 'MUST-NOT-LINK' not in output and 'no accepted map' in output.lower()
        assert 'K52' not in output and 'California' not in output


def test_safe_artifact_paths_reject_escape(tmp_path):
    assert summary.safe_child_path(tmp_path, 'maps/test.gz') == tmp_path / 'maps/test.gz'
    for name in ('../test.gz', '.', str(tmp_path.parent / 'outside.json')):
        with pytest.raises(ValueError): summary.safe_child_path(tmp_path, name)


def policy_fixture(k, monkeypatch):
    link, _, _ = link_fixture()
    link['provenance'] = {'diagnostic_evidence_sha256': {'diagnosis.json': 'digest'}}
    candidate = {key: deepcopy(link[key]) for key in ('component_ids', 'endpoints', 'distance_m')}
    monkeypatch.setattr(summary, 'sha256', lambda _: 'digest')
    monkeypatch.setattr(summary, 'PINNED_EVIDENCE_SHA256', {'diagnosis.json': 'digest'})
    report = {'water_connections': [link], 'island_policy_audit': {
        'district_count': k, 'source_population': summary.TOTAL, 'block_count': summary.BLOCKS,
        'physical_component_count': 2, 'part_count': 390182, 'augmented_component_count': 1,
        'synthetic_edge_count': 1, 'source_geometry_modified': False,
        'augmented_graph_connected': True, 'all_source_parts_reached': True,
        'target_selection_verified_against_diagnosis': True,
        'population_selection': {'district_count': k, 'ideal_population': summary.TOTAL / k,
            'minimum_root_population': float(Fraction(summary.TOTAL * 99, 100*k)),
            'eligible_root_component_ids': [0], 'selected_link_ids': ['fl-candidate-00-01'],
            'population_bound': {'maximum_deviation_percent': 0},
            'groups': [{'district_count': k, 'component_ids': [0, 1], 'population': summary.TOTAL}]}}}
    selection = deepcopy(report['island_policy_audit']['population_selection'])
    diagnosis = {'plans': [{'district_count': k, 'policy': selection,
                           'policy_population_bound': deepcopy(selection['population_bound']),
                           'augmented_component_count': 1}]}
    monkeypatch.setattr(summary, 'read_json', lambda path: [candidate] if path.name == 'candidate-links.json' else diagnosis)
    return report


@pytest.mark.parametrize('k', summary.COUNTS)
def test_actual_count_policy_uses_same_single_diagnosed_water_link(k, monkeypatch):
    summary.verify_target_policy(policy_fixture(k, monkeypatch), k)


@pytest.mark.parametrize('mutation', [
    lambda r: r['island_policy_audit'].update(district_count=52),
    lambda r: r['island_policy_audit']['population_selection'].update(district_count=28),
    lambda r: r['island_policy_audit']['population_selection'].update(ideal_population=123),
    lambda r: r['island_policy_audit']['population_selection'].update(eligible_root_component_ids=[0, 1]),
    lambda r: r['island_policy_audit']['population_selection']['groups'][0].update(district_count=28),
    lambda r: r['island_policy_audit'].update(source_geometry_modified=True),
    lambda r: r['water_connections'][0].update(kind='recorded-exclave-connection'),
    lambda r: r['water_connections'][0]['endpoints'][0].update(coordinate=[99, 99]),
    lambda r: r['island_policy_audit']['population_selection']['population_bound'].update(maximum_deviation_percent=5),
    lambda r: r['water_connections'][0]['provenance']['diagnostic_evidence_sha256'].update(other='digest'),
])
def test_policy_rejects_wrong_arithmetic_root_or_endpoints(monkeypatch, mutation):
    report = policy_fixture(37, monkeypatch); mutation(report)
    with pytest.raises(ValueError): summary.verify_target_policy(report, 37)


def numerical_failure():
    last = {'success': False, 'iterations': 1000, 'function_evaluations': 1200,
            'status': 1, 'message': 'iteration limit'}
    return {'failed_phase': 'solve', 'error': 'DistrictingOptimizationError: iteration limit',
            'solver_progress': [{'inner_optimizer': last}],
            'optimizer_failure': {'plan_returned': False, 'balance_pass': 1,
                                  **{k: v for k, v in last.items() if k != 'success'}}}


def test_numerical_failure_has_no_completed_plan():
    summary.verify_failure(numerical_failure(), 1)


@pytest.mark.parametrize('mutation', [lambda r: r.update(final_plan={}), lambda r: r.update(maps={}),
    lambda r: r.update(failed_phase='map_export'), lambda r: r.update(error='PermissionError: busy'),
    lambda r: r['optimizer_failure'].update(plan_returned=True),
    lambda r: r['optimizer_failure'].update(iterations=300),
    lambda r: r['solver_progress'][0]['inner_optimizer'].update(success=True)])
def test_operational_or_contradictory_failure_is_not_numerical_outcome(mutation):
    report = numerical_failure(); mutation(report)
    with pytest.raises(ValueError): summary.verify_failure(report, 1)


def test_trace_required_for_completed_plan(tmp_path):
    with pytest.raises(ValueError): summary.checked_trace(tmp_path, {'status': summary.ACCEPTED}, 28)
    assert summary.checked_trace(tmp_path, {'status': 'failed'}, 28) is None


def test_observed_optimizer_options_are_checked_without_original_budget_baseline(tmp_path, monkeypatch):
    (tmp_path / 'optimizer-trace.jsonl').write_text('{"event":"synthetic"}\n')
    result = {'passes': [{'optimizer': {'iterations': 450}, 'samples': [], 'at_original_budget': {},
                          'objective_improvement_after_original_budget': 1}],
              'pass_count': 1, 'all_inner_passes_succeeded': True}
    monkeypatch.setattr(summary, 'verify_trace', lambda *a, **k: deepcopy(result))
    report = {'status': summary.ACCEPTED,
              'solver': {'outer_iterations': 0, 'all_inner_optimizer_passes_succeeded': True},
              'optimizer_trace': {'passes': [{'actual_options': {'maxiter': 1000, 'gtol': 1e-6/summary.TOTAL,
                                                              'ftol': 1e-12, 'maxls': 100}}]}}
    verified = summary.checked_trace(tmp_path, report, 28)
    assert verified['maximum_inner_iterations'] == 450 and 'at_original_budget' not in verified['passes'][0]
    report['optimizer_trace']['passes'][0]['actual_options']['maxiter'] = 300
    with pytest.raises(ValueError): summary.checked_trace(tmp_path, report, 28)


def test_summary_tests_metadata_requires_separate_exact_sources(monkeypatch):
    monkeypatch.setattr(summary, 'sha256', lambda _: 'hash')
    record = {'status': 'passed', 'passed': 87, 'failed': 0, 'elapsed_seconds': 1.86, 'command': 'pytest focused',
              'source_sha256': {'scripts/summarize_florida_water.py': 'hash',
                                'scripts/tests/test_summarize_florida_water.py': 'hash'}}
    summary.verify_summary_tests(record)
    record['source_sha256']['scripts/benchmark_florida_water.py'] = 'hash'
    with pytest.raises(ValueError): summary.verify_summary_tests(record)


def test_parent_operational_stop_error_is_visible_for_unstarted_jobs(monkeypatch):
    row = summary.load_run(28, {}, job={'status': 'pending'}, manifest={'error': 'WinError 5 replacing progress'})
    assert row['failure']['error'] == 'WinError 5 replacing progress'
    data = failed_data(); data['stop_error'] = 'WinError 5 replacing progress'
    assert 'WinError 5 replacing progress' in summary.markdown(data)
    assert 'WinError 5 replacing progress' in summary.html(data)


def test_every_assignment_stage_provenance_matches_source_code_and_water_artifact():
    report = {'source': {'archive_sha256': 'source'}, 'code_sha256': {'solver.py': 'code'},
              'configuration': {'inner_max_iterations': 1000}, 'artifact_sha256': {'water-connections.json': 'water'}}
    expected = {'source_sha256': 'source', 'code_sha256': {'solver.py': 'code'},
                'configuration': {'inner_max_iterations': 1000}, 'water_connections_sha256': 'water'}
    summary.verify_assignment_provenance({'provenance': expected}, report)
    for key in expected:
        changed = deepcopy(expected); changed[key] = 'changed'
        with pytest.raises(ValueError): summary.verify_assignment_provenance({'provenance': changed}, report)


def test_move_audit_counts_and_termination_reconcile_with_budget(monkeypatch):
    monkeypatch.setattr(summary, 'verify_assignment_provenance', lambda *args: None)
    post = {'stop_reason': 'local_optimum', 'repair_move_count': 1,
            'part_repair_move_count': 0, 'rebalance_move_count': 2}
    report = {'postprocessing': post, 'configuration': {'max_rebalance_moves': 1000}}
    audit = {'stop_reason': 'local_optimum', 'repair_moves': [{}], 'part_repair_moves': [],
             'rebalance_moves': [{}, {}]}
    summary.verify_postprocessing(audit, report)
    post['rebalance_move_count'] = 3
    with pytest.raises(ValueError): summary.verify_postprocessing(audit, report)
    post['rebalance_move_count'] = 2; post['stop_reason'] = 'max_moves'; audit['stop_reason'] = 'max_moves'
    with pytest.raises(ValueError): summary.verify_postprocessing(audit, report)


def reused_pid_fixture():
    data = manifest()
    job = data['jobs'][1]
    job.update(command=[r'C:\workspace\venv\Scripts\python.exe', '-X', 'utf8', 'benchmark.py'],
               finished_at='2026-10-26T11:00:00Z',
               terminal_validation={'passed': True, 'classification': 'validated_complete_plan'})
    observed = {'pid': job['pid'], 'active': True, 'process_name': 'Code',
                'executable_path': r'C:\Programs\VS Code\Code.exe',
                'start_time_utc': '2026-10-26T11:30:00.1234567Z'}
    return data, observed


def test_exact_pid_reuse_requires_later_distinct_process_lifecycle():
    data, observed = reused_pid_fixture()
    result = summary.verified_reused_pid(observed, data, launch_record(), '2026-10-26T12:05:00Z')
    assert result['classification'] == 'pid_reused_after_verified_benchmark_exit'
    assert result['prior_benchmark_jobs'][0]['district_count'] == 37
    assert result['current_executable_path'].endswith('Code.exe')


@pytest.mark.parametrize('process_name,executable', [('chrome', r'C:\Browser\chrome.exe'),
                                                    ('notepad', r'C:\Windows\notepad.exe')])
def test_pid_reuse_rule_has_no_specific_pid_or_application_exception(process_name, executable):
    data, observed = reused_pid_fixture()
    observed.update(process_name=process_name, executable_path=executable)
    assert summary.verified_reused_pid(observed, data, None, '2026-10-26T12:05:00Z')['pid'] == observed['pid']


@pytest.mark.parametrize('change', [
    {'process_name': 'python', 'executable_path': r'C:\workspace\venv\Scripts\python.exe'},
    {'process_name': 'pythonw', 'executable_path': r'C:\other\pythonw.exe'},
    {'process_name': 'pypy3', 'executable_path': r'C:\other\pypy3.exe'},
    {'process_name': None}, {'executable_path': None}, {'start_time_utc': None},
    {'executable_path': 'Code.exe'}, {'executable_path': r'C:\Programs\other.exe'},
    {'start_time_utc': '2026-10-26T10:59:59Z'},
    {'start_time_utc': '2026-10-26T11:00:00Z'},
    {'start_time_utc': '2026-10-26T11:30:00'},
    {'start_time_utc': '2026-10-26T13:00:00Z'},
    {'start_time_utc': 'unknown'},
])
def test_active_python_or_ambiguous_identity_and_lifecycle_fail_closed(change):
    data, observed = reused_pid_fixture(); observed.update(change)
    with pytest.raises(ValueError):
        summary.verified_reused_pid(observed, data, launch_record(), '2026-10-26T12:05:00Z')


@pytest.mark.parametrize('change', [{'exit_code': None}, {'exit_code': 1}, {'status': 'running'},
    {'finished_at': None}, {'command': []}, {'command': ['unknown.exe']},
    {'terminal_validation': {'passed': False}},
    {'terminal_validation': {'passed': True, 'classification': 'unknown'}}])
def test_pid_reuse_does_not_replace_parent_wait_and_terminal_validation(change):
    data, observed = reused_pid_fixture(); data['jobs'][1].update(change)
    with pytest.raises(ValueError):
        summary.verified_reused_pid(observed, data, launch_record(), '2026-10-26T12:05:00Z')


def test_active_parent_cannot_be_bypassed_as_reused_without_its_waited_exit():
    data, observed = reused_pid_fixture(); observed['pid'] = data['pid']
    with pytest.raises(ValueError, match='parent/launcher'):
        summary.verified_reused_pid(observed, data, launch_record(), '2026-10-26T12:05:00Z')


def test_windows_query_preserves_live_image_creation_and_path(monkeypatch):
    _, observed = reused_pid_fixture()
    def query(command, **options):
        assert 'StartTime.ToUniversalTime()' in command[-1]
        assert '$observedProcess.Path' in command[-1] and '$observedProcess.ProcessName' in command[-1]
        return SimpleNamespace(stdout=json.dumps([observed]), stderr='')
    monkeypatch.setattr(summary.subprocess, 'run', query)
    assert summary.windows_pid_status([observed['pid']]) == [observed]


def test_verified_reuse_retains_live_evidence_and_still_requires_free_state_lock(monkeypatch):
    data, observed = reused_pid_fixture(); locks = []
    @contextmanager
    def lock(state):
        locks.append(state); yield
    monkeypatch.setattr(summary, 'WINDOWS', True)
    monkeypatch.setattr(summary, 'state_execution_lock', lock)
    monkeypatch.setattr(summary, 'windows_pid_status', lambda pids: [observed if pid == observed['pid']
        else {'pid': pid, 'active': False} for pid in pids])
    result = summary.verify_no_active_children(data, launch_record())
    assert locks == ['12']
    assert result['all_recorded_pids_absent'] is False
    assert result['all_recorded_benchmark_processes_exited'] is True
    assert len(result['verified_reused_pids']) == 1
    digest = hashlib.sha256(json.dumps(result['live_process_observations'], sort_keys=True,
                                       separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    assert result['live_process_observations_sha256'] == digest
