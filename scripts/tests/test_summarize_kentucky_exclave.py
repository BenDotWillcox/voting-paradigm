"""The report verifier must reject evidence that only appears self-consistent."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import zipfile

import pytest
import shapefile

from scripts import summarize_kentucky_exclave as summary


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
        writer.record('210010001001001', 9)
        writer.record('210010001001002', 0)
    archive = tmp_path / 'source.zip'
    with zipfile.ZipFile(archive, 'w') as target:
        target.writestr('source.dbf', dbf.getvalue())
    monkeypatch.setattr(summary, 'SOURCE', archive)
    monkeypatch.setattr(summary, 'TOTAL', 9)
    monkeypatch.setattr(summary, 'BLOCKS', 2)
    assert summary.source_populations(summary.sha256(archive)) == {'210010001001001': 9, '210010001001002': 0}
    with pytest.raises(ValueError, match='source archive'):
        summary.source_populations('0' * 64)


def test_viewer_is_exclave_labeled_and_context_failure_preserves_audit() -> None:
    template = (summary.ROOT / 'scripts/assets/kentucky-block-viewer.html').read_text(encoding='utf-8')
    assert 'maps/exclave-connections.geojson' in template
    assert 'no Missouri territory or population is assigned' in template
    assert 'shared_edges_plus_recorded_exclave_connections' in template
    catch = template.split(".catch(error=>{", 1)[1].split('});', 1)[0]
    assert 'contextPromise=null' in catch
    assert 'connectivityAudit=null' not in catch
    assert 'contextVisible=' not in catch


def test_outer_limit_is_preserved_separately_from_successful_inner_solves() -> None:
    solver = {'outer_iterations': 80, 'centers_converged': False,
              'outer_iteration_limit_reached': True, 'all_inner_optimizer_passes_succeeded': True}
    termination = summary.outer_termination(solver, {'max_outer_iterations': 80})
    run = {'district_count': 14, 'accepted_plan': True, 'outer_termination': termination}
    record = summary.outer_convergence_overview([run])
    serialized = json.loads(json.dumps({'solver': solver, 'outer_termination': termination, 'overview': record}))
    assert serialized['solver']['all_inner_optimizer_passes_succeeded'] is True
    assert serialized['outer_termination']['centers_converged'] is False
    assert serialized['outer_termination']['outer_iteration_limit_reached'] is True
    assert serialized['outer_termination']['configured_max_outer_iterations'] == 80
    assert record['all_accepted_plans_center_converged'] is False
    assert record['district_counts_at_outer_limit_without_center_convergence'] == [14]
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
        'accepted_plan': True, 'house_sizes': [1000], 'district_count': 14,
        'url': 'http://example.test/k14/', 'benchmark_path': 'fixture/benchmark.json',
        'outer_termination': termination, 'inner_optimizer_pass_count': 81,
        'timed_pipeline_wall_seconds': 120.0, 'peak_working_set_mib': 1024.0,
        'phases': {'solve': {'wall_seconds': 30.0}},
        'final_plan': {'district_populations': [321846] * 6 + [321845] * 8,
                       'max_absolute_deviation_people': 4 / 7,
                       'max_absolute_deviation_percent': 800 / summary.TOTAL},
        'physical_polygon_components': [1, 1, 2] + [1] * 11,
        'policy_polygon_components': [1] * 14,
        'connection_features': [{'properties': {'used_by_district': 2}}],
        'postprocessing': {'stop_reason': 'local_optimum', 'repair_move_count': 1,
                           'part_repair_move_count': 0, 'rebalance_move_count': 2},
        'payloads': {'district_outlines': {level: {'gzip_bytes': 1024} for level in ('national', 'state', 'full')},
                     'exclave_connections': {'gzip_bytes': 1024}},
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
        assert '14-district run: The outer loop reached the 80-iteration limit without center convergence.' in output
        assert 'All 81 inner optimizer passes succeeded.' in output
        assert 'Final population balance and connectivity are assessed separately after repair/rebalancing.' in output
