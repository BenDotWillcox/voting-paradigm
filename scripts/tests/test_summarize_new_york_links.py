"""The report verifier must reject evidence that only appears self-consistent."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import copy
import zipfile

import pytest
import shapefile

from scripts import summarize_new_york_links as summary


def plan() -> dict:
    return {
        'district_populations': [4, 14], 'district_block_counts': [1, 2],
        'deviation_numerators': [-10, 10], 'max_absolute_deviation_people': 5,
        'max_absolute_deviation_percent': 500 / 9, 'total_range_people': 10,
    }


def test_assignment_audit_recomputes_from_keyed_source_population() -> None:
    result = summary.verify_assignments({'b': 1, 'a': 0, 'c': 1}, {'a': 4, 'b': 5, 'c': 9}, 2, plan())
    assert result['district_populations'] == [4, 14]
    assert result['total_population'] == 18
    assert result['max_absolute_deviation_people'] == 5


@pytest.mark.parametrize('assignments', [
    {'a': 0, 'b': 1},
    {'a': 0, 'b': 1, 'outside': 1},
    {'a': 0, 'b': True, 'c': 1},
    {'a': 0, 'b': 2, 'c': 1},
])
def test_assignment_audit_rejects_missing_foreign_or_invalid_labels(assignments: dict) -> None:
    with pytest.raises(ValueError):
        summary.verify_assignments(assignments, {'a': 4, 'b': 5, 'c': 9}, 2, plan())


def test_assignment_audit_rejects_wrong_totals_even_when_report_balance_matches_itself() -> None:
    wrong = {**plan(), 'district_populations': [9, 9], 'deviation_numerators': [0, 0],
             'max_absolute_deviation_people': 0, 'max_absolute_deviation_percent': 0, 'total_range_people': 0}
    with pytest.raises(ValueError, match='source-DBF totals'):
        summary.verify_assignments({'a': 0, 'b': 1, 'c': 1}, {'a': 4, 'b': 5, 'c': 9}, 2, wrong)


def test_json_reader_rejects_duplicate_assignment_geoids(tmp_path) -> None:
    path = tmp_path / 'assignments.json'
    path.write_text('{"assignments":{"a":0,"a":1}}')
    with pytest.raises(ValueError, match='Duplicate JSON key'):
        summary.read_json(path)


def test_compressed_map_verifier_checks_decompressed_content_hash(tmp_path) -> None:
    maps = tmp_path / 'maps'
    maps.mkdir()
    raw = b'{"type":"FeatureCollection","features":[]}'
    compressed = gzip.compress(raw)
    (maps / 'map.geojson.gz').write_bytes(compressed)
    item = {'gzip_path': 'map.geojson.gz', 'gzip_bytes': len(compressed), 'raw_bytes': len(raw),
            'raw_sha256': hashlib.sha256(raw).hexdigest()}
    manifest = {'storage': {'artifacts': [item]}}
    assert summary.verify_compressed_maps(tmp_path, manifest) == 1
    item['raw_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='Compressed map verification failed'):
        summary.verify_compressed_maps(tmp_path, manifest)


def test_source_population_reader_uses_original_dbf_and_checks_archive_hash(tmp_path, monkeypatch) -> None:
    dbf = io.BytesIO()
    with shapefile.Writer(dbf=dbf) as writer:
        writer.field('GEOID20', 'C', 15)
        writer.field('POP20', 'N', 10)
        writer.record('360010001001001', 9)
        writer.record('360010001001002', 0)
    archive = tmp_path / 'source.zip'
    with zipfile.ZipFile(archive, 'w') as target:
        target.writestr('source.dbf', dbf.getvalue())
    monkeypatch.setattr(summary, 'SOURCE', archive)
    monkeypatch.setattr(summary, 'TOTAL', 9)
    monkeypatch.setattr(summary, 'BLOCKS', 2)
    assert summary.source_populations(summary.sha256(archive)) == {'360010001001001': 9, '360010001001002': 0}
    with pytest.raises(ValueError, match='source archive'):
        summary.source_populations('0' * 64)


def test_viewer_is_exclave_labeled_and_context_failure_preserves_audit() -> None:
    template = (summary.ROOT / 'scripts/assets/new-york-block-viewer.html').read_text(encoding='utf-8')
    assert 'maps/recorded-connections.geojson' in template
    assert 'no New Jersey territory or population is assigned' in template
    assert 'shared_edges_plus_recorded_mixed_connections' in template
    catch = template.split(".catch(error=>{", 1)[1].split('});', 1)[0]
    assert 'contextPromise=null' in catch
    assert 'connectivityAudit=null' not in catch
    assert 'contextVisible=' not in catch
    assert "'ny-candidate-00-02'" in template
    assert 'Liberty · water link' in template and 'Ellis · exclave link' in template
    assert 'recorded-water-connection' in template and 'recorded-exclave-connection' in template
    assert 'diagnostics/new-york/' in template
    assert 'Kentucky' not in template and 'Missouri' not in template


def connection_fixture() -> tuple[dict, dict, dict, dict]:
    records, features = [], []
    receiving = '360610005000003'
    assignments = {receiving: 4, '360610001001001': 4, '360610001001000': 4}
    for link_id, kind, island, water in (
        ('ny-water-liberty-001', 'recorded-water-connection', '360610001001001', True),
        ('ny-exclave-ellis-001', 'recorded-exclave-connection', '360610001001000', False),
    ):
        record = {
            'id': link_id, 'kind': kind, 'policy': 'new-york-harbor-recorded-mixed-v1',
            'component_ids': [0, 1 if water else 2], 'distance_m': 795 if water else 852,
            'endpoints': [{'geoid': receiving, 'coordinate': [-74.03, 40.69]},
                          {'geoid': island, 'coordinate': [-74.04, 40.70]}],
            'geographic_context': {'water_only': water, 'crossed_state': 'New Jersey',
                                   'mapped_water_length_m': 795 if water else 826.5,
                                   'mapped_land_length_m': 0 if water else 25.5},
            'provenance': {'source_archive_sha256': 'source'},
        }
        records.append(record)
        features.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [e['coordinate'] for e in record['endpoints']]},
                         'properties': {**copy.deepcopy(record), 'endpoint_districts': [4, 4], 'used_by_district': 4}})
    source = {'policy': summary.POLICY, 'source_sha256': 'source', 'connections': records}
    report = {'source': {'archive_sha256': 'source'}, 'recorded_connections': copy.deepcopy(records),
              'recorded_policy_audit': {'policy': 'new-york-harbor-recorded-mixed-v1'}}
    return {'type': 'FeatureCollection', 'features': features}, source, report, assignments


def test_both_typed_links_match_saved_records_and_same_district_assignments() -> None:
    summary.verify_connections(*connection_fixture())


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'swap_kind', 'foreign_endpoint',
                                      'cross_district', 'wrong_geometry', 'erased_land', 'changed_provenance'])
def test_mixed_connection_verifier_rejects_unapproved_or_misclassified_links(mutation: str) -> None:
    collection, source, report, assignments = connection_fixture()
    p = collection['features'][1]['properties']
    if mutation == 'missing':
        collection['features'].pop()
    elif mutation == 'duplicate':
        collection['features'][1] = copy.deepcopy(collection['features'][0])
    elif mutation == 'swap_kind':
        p['kind'] = 'recorded-water-connection'
    elif mutation == 'foreign_endpoint':
        p['endpoints'][0]['geoid'] = '340179801001001'
    elif mutation == 'cross_district':
        assignments['360610001001000'] = 5
    elif mutation == 'wrong_geometry':
        collection['features'][1]['geometry']['coordinates'][0] = [-74.02, 40.70]
    elif mutation == 'erased_land':
        p['geographic_context']['mapped_land_length_m'] = 0
    elif mutation == 'changed_provenance':
        p['provenance']['source_archive_sha256'] = 'other'
    with pytest.raises(ValueError):
        summary.verify_connections(collection, source, report, assignments)


def test_nonterminal_run_cannot_be_summarized_as_completed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(summary, 'OUTPUT', tmp_path)
    directory = tmp_path / 'states/36/districts-26'
    directory.mkdir(parents=True)
    (directory / 'benchmark.json').write_text(json.dumps({
        'state_fips': '36', 'district_count': 26, 'policy': summary.POLICY, 'status': 'running',
    }))
    with pytest.raises(ValueError, match='not terminal'):
        summary.load_run(26, {})


def execution_fixture(tmp_path, monkeypatch) -> tuple[list[dict], dict]:
    monkeypatch.setattr(summary, 'OUTPUT', tmp_path)
    monkeypatch.setattr(summary, 'ROOT', tmp_path)
    runs = [{
        'district_count': k, 'accepted_plan': k == 35,
        'status': 'complete_under_recorded_mixed_policy' if k == 35 else 'failed',
        'benchmark_sha256': f'report-{k}', 'code_sha256': {'algorithm.py': 'fixed'},
    } for k in summary.COUNTS]
    jobs = [{**run, 'exit_code': 0 if run['accepted_plan'] else 1, 'finished_at': 'finished'} for run in runs]
    original = {'status': 'stopped', 'finished_at': 'finished', 'elapsed_wall_seconds': 130,
                'code_sha256': {'algorithm.py': 'fixed'},
                'jobs': [jobs[0], *[{'district_count': k, 'status': 'pending'} for k in (35, 42, 61)]]}
    original_path = tmp_path / 'run.json'
    original_path.write_text(json.dumps(original))
    supplement = {
        'status': 'complete', 'finished_at': 'finished', 'elapsed_wall_seconds': 900,
        'attempt_kind': 'deferred_first_attempts',
        'original_run_manifest': {'sha256': summary.sha256(original_path)},
        'original_code_sha256': original['code_sha256'],
        'original_attempt_preserved_byte_identically': True,
        'preserved_original_attempt_inventory': {'run.json': summary.sha256(original_path)},
        'jobs': [{**job, 'attempt_kind': 'deferred_first_attempt', 'terminal_validation': {
            'passed': True, 'preservation_verified': True, 'code_unchanged': True,
            'classification': 'complete' if job['accepted_plan'] else 'numerical_failure',
        }} for job in jobs[1:]],
    }
    (tmp_path / 'supplemental-first-attempts.json').write_text(json.dumps(supplement))
    return runs, supplement


def test_reconcile_preserves_original_failure_and_records_deferred_first_attempts(tmp_path, monkeypatch) -> None:
    runs, _ = execution_fixture(tmp_path, monkeypatch)
    before = (tmp_path / 'run.json').read_bytes()
    result = summary.reconcile_execution(runs)
    assert [job['execution_source'] for job in result['jobs']] == ['original_suite'] + ['deferred_first_attempt'] * 3
    assert result['jobs'][0]['status'] == 'failed'
    assert result['jobs'][1]['status'] == 'complete_under_recorded_mixed_policy'
    assert result['original_elapsed_wall_seconds'] == 130
    assert result['supplemental_elapsed_wall_seconds'] == 900
    assert (tmp_path / 'run.json').read_bytes() == before


@pytest.mark.parametrize('mutation', ['running', 'wrong_original_hash', 'wrong_code', 'repeated_count',
                                     'missing_job', 'wrong_report_hash', 'failed_exit_zero', 'unchecked_terminal'])
def test_reconciliation_rejects_incomplete_or_ambiguous_execution(tmp_path, monkeypatch, mutation: str) -> None:
    runs, supplement = execution_fixture(tmp_path, monkeypatch)
    if mutation == 'running':
        supplement['status'] = 'running'
    elif mutation == 'wrong_original_hash':
        supplement['original_run_manifest']['sha256'] = 'wrong'
    elif mutation == 'wrong_code':
        supplement['original_code_sha256']['algorithm.py'] = 'changed'
    elif mutation == 'repeated_count':
        supplement['jobs'][1]['district_count'] = 35
    elif mutation == 'missing_job':
        supplement['jobs'].pop()
    elif mutation == 'wrong_report_hash':
        supplement['jobs'][0]['benchmark_sha256'] = 'changed'
    elif mutation == 'failed_exit_zero':
        supplement['jobs'][1]['exit_code'] = 0
    elif mutation == 'unchecked_terminal':
        supplement['jobs'][0]['terminal_validation']['passed'] = False
    (tmp_path / 'supplemental-first-attempts.json').write_text(json.dumps(supplement))
    with pytest.raises(ValueError):
        summary.reconcile_execution(runs)


def test_inner_cap_failure_does_not_fabricate_population_or_outer_convergence() -> None:
    result = summary.failure_details({
        'failed_phase': 'solve', 'error': 'iteration limit',
        'configuration': {'inner_max_iterations': 300, 'max_outer_iterations': 80},
        'optimizer_failure': {'balance_pass': 2, 'iterations': 300, 'message': 'ITERATIONS REACHED LIMIT'},
        'solver_progress': [{'inner_optimizer': {'success': True}}, {'inner_optimizer': {'success': False}}],
    })
    assert result['accepted_district_plan'] is False
    assert result['accepted_completed_map'] is False
    assert result['successful_inner_pass_count'] == result['failed_inner_pass_count'] == 1
    assert 'inner-optimizer failure, separate from the outer' in result['disclosure']
    assert 'Final population balance and district connectivity are unavailable' in result['disclosure']
    assert 'final_plan' not in result and 'centers_converged' not in result


def test_source_connection_viewer_is_explicitly_not_a_district_plan() -> None:
    text = summary.source_connections_html({'complete_plan_count': 0})
    assert 'None of the four attempts produced a validated district plan.' in text
    assert 'Recorded source connections, not a district plan.' in text
    assert 'no district plan is shown' in text
    assert 'Ellis land crossing' in text
    assert "candidate_id==='ny-candidate-00-02'" in text
    assert '__D3_SCRIPTS__' not in text and '__PLAN_STATUS__' not in text


def test_failed_attempt_rendering_shows_measured_cost_but_no_plan_metrics() -> None:
    report = {
        'failed_phase': 'solve', 'error': 'iteration limit',
        'configuration': {'inner_max_iterations': 300},
        'optimizer_failure': {'balance_pass': 2, 'iterations': 300, 'message': 'ITERATIONS REACHED LIMIT'},
    }
    run = {
        'district_count': 26, 'house_sizes': [435], 'accepted_plan': False,
        'failure_details': summary.failure_details(report),
        'timed_pipeline_wall_seconds': 126.41, 'peak_working_set_mib': 1053.9,
        'phases': {'solve': {'wall_seconds': 27.52}}, 'benchmark_path': 'states/36/districts-26/benchmark.json',
        'error': 'iteration limit', 'failed_phase': 'solve',
    }
    data = {
        'runs': [run], 'complete_plan_count': 0, 'failed_plan_count': 1,
        'outer_convergence': summary.outer_convergence_overview([run]),
        'strict_baseline': {'preflight_wall_seconds': 50},
        'validation_note': 'Synthetic failure renderer fixture.', 'measurement_notes': [],
        'preserved_historical_file_count': 1, 'crossing_audit': {'path': 'diagnostic.json'},
    }
    for output in (summary.html(data), summary.markdown(data)):
        assert 'No accepted plan' in output
        assert '126.41' in output
        assert 'inner weight optimizer failed on balance pass 2 after 300 iterations' in output
        assert 'Final population balance and district connectivity are unavailable' in output
        assert 'connections/' in output
    assert 'No completed district map payloads were generated' in summary.html(data)
    assert '<a href="states/36/districts-26/">' not in summary.html(data)
    assert 'Not evaluated' in summary.html(data)
    for output in (summary.html(data), summary.markdown(data)):
        assert 'No final assignment coverage, population balance, compressed district map or district-connectivity validation is claimed' in output
        assert 'recomputed final district totals from saved assignments' not in output
    assert 'Failed-attempt time ends at the failed phase' in summary.html(data)


def source_policy_fixture() -> tuple[dict, dict, dict]:
    _, source, report, _ = connection_fixture()
    report['district_count'] = 26
    report['physical_part_graph'] = {
        'component_count': 3, 'node_count': 288841, 'block_count': summary.BLOCKS,
        'source_coordinates_modified': False, 'synthetic_ownership_edges': False, 'edge_count': 712458,
    }
    report['recorded_policy_audit'].update({
        'district_count': 26, 'state_fips': '36', 'source_geometry_modified': False,
        'synthetic_ownership_edges': False, 'physical_component_count': 3,
        'augmented_component_count': 1, 'augmented_graph_connected': True,
        'synthetic_edge_count': 2, 'block_count': summary.BLOCKS, 'source_population': summary.TOTAL,
        'part_count': 288841, 'physical_edge_count': 712458, 'augmented_edge_count': 712460,
        'connection_kind_counts': {'recorded-water-connection': 1, 'recorded-exclave-connection': 1},
        'provenance': {'source_archive_sha256': 'source'},
        'components': [{'component_id': 0, 'population': summary.TOTAL, 'block_count': summary.BLOCKS - 2},
                       {'component_id': 1, 'population': 0, 'block_count': 1},
                       {'component_id': 2, 'population': 0, 'block_count': 1}],
    })
    return source, report, {'360610005000003': 0, '360610001001000': 0, '360610001001001': 0}


def test_source_policy_is_verified_even_when_no_district_assignments_exist() -> None:
    result = summary.verify_source_policy(*source_policy_fixture())
    assert result['physical_component_count'] == 3
    assert result['augmented_component_count'] == 1
    assert result['endpoint_populations_independently_verified_zero'] is True
    assert 'not final district connectivity' in result['validation_scope']


@pytest.mark.parametrize('mutation', ['report_record_mismatch', 'unconnected_augmented', 'wrong_type_counts',
                                     'wrong_physical_count', 'extra_edge', 'populated_endpoint', 'geometry_modified'])
def test_source_policy_verifier_rejects_inconsistent_preflight_evidence(mutation: str) -> None:
    source, report, populations = source_policy_fixture()
    audit = report['recorded_policy_audit']
    if mutation == 'report_record_mismatch':
        report['recorded_connections'][0]['distance_m'] += 1
    elif mutation == 'unconnected_augmented':
        audit['augmented_component_count'] = 2
    elif mutation == 'wrong_type_counts':
        audit['connection_kind_counts'] = {'recorded-water-connection': 2}
    elif mutation == 'wrong_physical_count':
        report['physical_part_graph']['component_count'] = 2
    elif mutation == 'extra_edge':
        audit['augmented_edge_count'] += 1
    elif mutation == 'populated_endpoint':
        populations['360610001001000'] = 5
    elif mutation == 'geometry_modified':
        audit['source_geometry_modified'] = True
    with pytest.raises(ValueError):
        summary.verify_source_policy(source, report, populations)


def test_outer_limit_is_preserved_separately_from_successful_inner_solves() -> None:
    solver = {'outer_iterations': 80, 'centers_converged': False,
              'outer_iteration_limit_reached': True, 'all_inner_optimizer_passes_succeeded': True}
    termination = summary.outer_termination(solver, {'max_outer_iterations': 80})
    run = {'district_count': 61, 'accepted_plan': True, 'outer_termination': termination}
    record = summary.outer_convergence_overview([run])
    serialized = json.loads(json.dumps({'solver': solver, 'outer_termination': termination, 'overview': record}))
    assert serialized['solver']['all_inner_optimizer_passes_succeeded'] is True
    assert serialized['outer_termination']['centers_converged'] is False
    assert serialized['outer_termination']['outer_iteration_limit_reached'] is True
    assert serialized['outer_termination']['configured_max_outer_iterations'] == 80
    assert record['all_accepted_plans_center_converged'] is False
    assert record['district_counts_at_outer_limit_without_center_convergence'] == [61]
    assert '80-iteration limit without center convergence' in record['disclosures'][0]


def test_center_convergence_at_last_iteration_is_not_misclassified_as_unconverged() -> None:
    termination = summary.outer_termination(
        {'outer_iterations': 80, 'centers_converged': True, 'outer_iteration_limit_reached': True},
        {'max_outer_iterations': 80},
    )
    overview = summary.outer_convergence_overview([
        {'district_count': 6, 'accepted_plan': True, 'outer_termination': termination},
    ])
    assert termination['status'] == 'center_tolerance_met'
    assert overview['all_accepted_plans_center_converged'] is True
    assert overview['disclosures'] == []


def test_outer_iteration_metadata_must_match_configured_limit() -> None:
    with pytest.raises(ValueError, match='outer-iteration'):
        summary.outer_termination(
            {'outer_iterations': 80, 'centers_converged': False, 'outer_iteration_limit_reached': False},
            {'max_outer_iterations': 80},
        )


def test_markdown_and_html_prominently_disclose_outer_limit_despite_valid_final_plan() -> None:
    termination = summary.outer_termination(
        {'outer_iterations': 80, 'centers_converged': False, 'outer_iteration_limit_reached': True},
        {'max_outer_iterations': 80},
    )
    run = {
        'accepted_plan': True, 'house_sizes': [1000], 'district_count': 61,
        'url': 'http://example.test/k14/', 'benchmark_path': 'fixture/benchmark.json',
        'outer_termination': termination, 'inner_optimizer_pass_count': 81,
        'timed_pipeline_wall_seconds': 120.0, 'peak_working_set_mib': 1024.0,
        'phases': {'solve': {'wall_seconds': 30.0}},
        'final_plan': {'district_populations': [321846] * 6 + [321845] * 8,
                       'max_absolute_deviation_people': 4 / 7,
                       'max_absolute_deviation_percent': 800 / summary.TOTAL},
        'physical_polygon_components': [1, 1, 2] + [1] * 11,
        'policy_polygon_components': [1] * 14,
        'connection_features': [{'properties': {'kind': 'recorded-water-connection', 'used_by_district': 2}}, {'properties': {'kind': 'recorded-exclave-connection', 'used_by_district': 2}}],
        'postprocessing': {'stop_reason': 'local_optimum', 'repair_move_count': 1,
                           'part_repair_move_count': 0, 'rebalance_move_count': 2},
        'payloads': {'district_outlines': {level: {'gzip_bytes': 1024} for level in ('national', 'state', 'full')},
                     'recorded_connections': {'gzip_bytes': 1024}},
    }
    data = {
        'runs': [run], 'complete_plan_count': 1, 'failed_plan_count': 0,
        'outer_convergence': summary.outer_convergence_overview([run]),
        'crossing_audit': {'path': 'fixture/crossing.json', 'record': {
            'candidate_planar_length_m': 5144.857, 'mapped_water_length_m': 1804.885,
            'outside_mapped_water_length_m': 3339.972}},
        'strict_baseline': {'preflight_wall_seconds': 66.1568065},
        'preserved_historical_file_count': 1, 'validation_note': 'Synthetic renderer fixture.',
        'measurement_notes': [],
    }
    for output in (summary.markdown(data), summary.html(data)):
        assert 'Outer convergence caveat' in output
        assert '61-district run: The outer loop reached the 80-iteration limit without center convergence.' in output
        assert 'All 81 inner optimizer passes succeeded.' in output
        assert 'Final population balance and connectivity are assessed separately after repair/rebalancing.' in output
