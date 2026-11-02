"""Evidence, seam, geometry and reporting checks for terminal Alaska summaries."""
from copy import deepcopy
import gzip
import hashlib
import json

import pytest
from shapely.geometry import box, mapping, shape
from shapely.affinity import translate

from districting.part_connectivity import PartGraph
from scripts import summarize_alaska_water as summary
from scripts.alaska_map_export import export_alaska_maps, wrap_geometry
from scripts.benchmark_kansas_anchors import population_metrics
from scripts.tests.test_alaska_map_export import fixture_source


def _manifest():
    return {'status': 'complete', 'finished_at': '2026-10-26T19:00:00+00:00',
        'execution': 'serial_fresh_processes', 'jobs': [
            {'district_count': k, 'status': 'complete', 'finished_at': 'done', 'exit_code': 0,
             'terminal_validation': {'status': 'complete', 'report': 'benchmark.json'}} for k in (1, 2)]}


def test_terminal_manifest_accepts_complete_and_honest_failure():
    value = _manifest()
    summary.verify_manifest(value)
    value['status'] = 'complete_with_numerical_failures'
    value['jobs'][1].update(status='verified_numerical_failure', exit_code=1)
    value['jobs'][1]['terminal_validation']['status'] = 'verified_numerical_failure'
    summary.verify_manifest(value)


@pytest.mark.parametrize('change', [
    lambda d: d.update(status='running'), lambda d: d.pop('finished_at'),
    lambda d: d['jobs'].pop(), lambda d: d['jobs'][1].update(district_count=1),
    lambda d: d['jobs'][1].update(status='running'), lambda d: d['jobs'][0].update(exit_code=1),
    lambda d: d.update(status='complete_with_numerical_failures'),
    lambda d: d['jobs'][0]['terminal_validation'].update(status='verified_numerical_failure'),
])
def test_inconsistent_or_nonterminal_manifest_rejected(change):
    value = _manifest(); change(value)
    with pytest.raises(ValueError): summary.verify_manifest(value)


def test_selected_report_does_not_choose_stale_main_report(tmp_path):
    report = {'status': 'complete_under_recorded_water_policy', 'pid': 123}
    path = tmp_path / 'terminal-report.json'
    path.write_text(json.dumps(report))
    (tmp_path / 'benchmark.json').write_text(json.dumps({'status': 'running'}))
    (tmp_path / 'progress.json').write_text(json.dumps({'status': report['status'], 'pid': 123,
        'district_count': 1, 'active_phase': None, 'authoritative_report': 'terminal-report.json'}))
    job = {'district_count': 1, 'terminal_validation': {'status': 'complete',
        'report': 'terminal-report.json', 'report_sha256': summary.sha256(path)}}
    chosen, saved = summary.selected_report(job, tmp_path)
    assert chosen == path and saved == report
    progress = json.loads((tmp_path / 'progress.json').read_text())
    progress['authoritative_report'] = 'benchmark.json'
    (tmp_path / 'progress.json').write_text(json.dumps(progress))
    with pytest.raises(ValueError, match='stale'):
        summary.selected_report(job, tmp_path)


@pytest.mark.parametrize('name', ['../outside', 'nested/../../outside', '', 'C:/outside/file.json'])
def test_artifact_paths_cannot_escape(tmp_path, name):
    with pytest.raises(ValueError): summary.safe_path(tmp_path, name)


def test_part_graph_traversal_does_not_use_shared_block_ownership():
    graph = PartGraph(((), (), ()), (0, 0, 1))
    assert summary.component_counts(graph, {'a': 0, 'b': 1}, ['a', 'b'], 2) == [2, 1]
    linked = PartGraph(((1,), (0,), ()), (0, 0, 1))
    assert summary.component_counts(linked, {'a': 0, 'b': 1}, ['a', 'b'], 2) == [1, 1]


def _pair():
    g = box(-182, 60, -178, 62)
    wrapped, audit = wrap_geometry(g)
    return {'type': 'Feature', 'geometry': mapping(g), 'properties': {'district_id': 0}}, {
        'type': 'Feature', 'geometry': mapping(wrapped), 'properties': {'district_id': 0, 'antimeridian': audit}}


def test_saved_wrapped_seam_reconstruction_passes():
    working, wrapped = _pair()
    assert summary.verify_seam_pair(working, wrapped)['inverse_reconstruction_passed']


def test_wrapped_piece_reordering_cannot_reuse_wrong_inverse_offsets():
    working, wrapped = _pair()
    coordinates = list(wrapped['geometry']['coordinates'])
    wrapped['geometry'] = {'type': 'MultiPolygon', 'coordinates': coordinates[::-1]}
    assert shape(wrapped['geometry']).equals(wrap_geometry(shape(working['geometry']))[0])
    with pytest.raises(ValueError, match='ordering/offsets'):
        summary.verify_seam_pair(working, wrapped)


@pytest.mark.parametrize('change', [
    lambda f: f['properties']['antimeridian'].update(part_offsets_from_working_degrees=[0, 360]),
    lambda f: f['properties'].update(district_id=1),
    lambda f: f.update(geometry=mapping(translate(shape(f['geometry']), yoff=.001))),
])
def test_modified_wrapped_geometry_or_offsets_rejected(change):
    working, wrapped = _pair(); change(wrapped)
    with pytest.raises(ValueError): summary.verify_seam_pair(working, wrapped)


def test_payload_rejects_changed_checksum_and_duplicate_json(tmp_path):
    raw = b'{"type":"FeatureCollection","features":[]}'
    compressed = gzip.compress(raw)
    name = 'map.geojson.gz'; (tmp_path / name).write_bytes(compressed)
    meta = {'file': name, 'gzip_bytes': len(compressed), 'raw_bytes': len(raw), 'gzip_verified': True,
        'sha256': hashlib.sha256(compressed).hexdigest(), 'raw_sha256': hashlib.sha256(raw).hexdigest()}
    assert summary.read_payload(tmp_path, name, meta)['features'] == []
    meta['raw_sha256'] = '0' * 64
    with pytest.raises(ValueError): summary.read_payload(tmp_path, name, meta)
    raw = b'{"type":"FeatureCollection","type":"FeatureCollection","features":[]}'
    compressed = gzip.compress(raw); (tmp_path / name).write_bytes(compressed)
    meta.update(gzip_bytes=len(compressed), raw_bytes=len(raw), sha256=hashlib.sha256(compressed).hexdigest(), raw_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match='Duplicate'):
        summary.read_payload(tmp_path, name, meta)


def _maps(tmp_path):
    parts, records, owners, indices, labels, links = fixture_source(seam=True)
    measured = export_alaska_maps(parts, records, owners, indices, labels, links, tmp_path / 'maps')
    population = {'total_population': 110, 'block_count': 2, 'district_populations': [110],
        'district_block_counts': [2], 'max_absolute_deviation_people': 0., 'max_absolute_deviation_percent': 0.}
    report = {'maps': measured, 'final_plan': {'physical_part_components': [2]},
              'artifact_sha256': {'maps/' + n: digest for n, digest in measured['artifact_sha256'].items()}}
    return report, (parts, records, owners, indices), labels, links, population


def test_source_county_full_geometry_link_ownership_and_all_payloads_verified(tmp_path):
    report, source, labels, links, population = _maps(tmp_path)
    verified = summary.verify_maps(tmp_path, report, source, labels, links, population)
    assert verified['all_county_blocks_verified'] == 2
    assert verified['compressed_payload_count'] == 10
    assert verified['physical_polygon_components'] == [2]
    assert verified['independent_polygon_and_link_audit']['districts'][0]['connected_components_after_links'] == 1
    assert verified['payloads']['default_map_and_links_gzip_bytes'] > 0


@pytest.mark.parametrize('change', [
    lambda report: report['maps']['map_payload_summary'].update(national_gzip_bytes=1),
    lambda report: report['final_plan'].update(physical_part_components=[1]),
    lambda report: report['maps']['artifact_sha256'].pop('manifest.json'),
])
def test_tampered_report_map_claims_rejected(tmp_path, change):
    report, source, labels, links, population = _maps(tmp_path); change(report)
    with pytest.raises(ValueError): summary.verify_maps(tmp_path, report, source, labels, links, population)


def _repin_maps(directory, report):
    """Simulate coordinated checksum tampering; geometry still has to match source."""
    manifest = json.loads((directory / 'maps/manifest.json').read_text())
    for name in manifest['payloads']:
        compressed = (directory / 'maps' / name).read_bytes(); raw = gzip.decompress(compressed)
        manifest['payloads'][name].update(gzip_bytes=len(compressed), raw_bytes=len(raw),
            sha256=hashlib.sha256(compressed).hexdigest(), raw_sha256=hashlib.sha256(raw).hexdigest())
    (directory / 'maps/manifest.json').write_text(json.dumps(manifest))
    report['maps'].update(manifest)
    for path in (directory / 'maps').rglob('*'):
        if path.is_file():
            name = path.relative_to(directory / 'maps').as_posix()
            report['maps']['artifact_sha256'][name] = summary.sha256(path)
            report['artifact_sha256']['maps/' + name] = summary.sha256(path)


@pytest.mark.parametrize('stem', ['districts-full', 'counties/001', 'connections'])
def test_rehashed_bad_geometry_cannot_be_accepted(tmp_path, stem):
    report, source, labels, links, population = _maps(tmp_path)
    path = tmp_path / f'maps/{stem}.working.geojson.gz'
    content = json.loads(gzip.decompress(path.read_bytes()))
    content['features'][0]['geometry'] = mapping(translate(shape(content['features'][0]['geometry']), yoff=.001))
    path.write_bytes(gzip.compress(json.dumps(content).encode()))
    wrapped_path = tmp_path / f'maps/{stem}.wrapped.geojson.gz'
    wrapped_content = json.loads(gzip.decompress(wrapped_path.read_bytes()))
    geometry, audit = wrap_geometry(shape(content['features'][0]['geometry']))
    wrapped_content['features'][0]['geometry'] = mapping(geometry)
    wrapped_content['features'][0]['properties']['antimeridian'] = audit
    wrapped_path.write_bytes(gzip.compress(json.dumps(wrapped_content).encode()))
    _repin_maps(tmp_path, report)
    with pytest.raises(ValueError): summary.verify_maps(tmp_path, report, source, labels, links, population)


@pytest.mark.parametrize('key,value', [('population', 51), ('district_id', 1), ('geoid', '020010001001999')])
def test_rehashed_consistent_county_properties_still_must_match_source(tmp_path, key, value):
    report, source, labels, links, population = _maps(tmp_path)
    for frame in ('working', 'wrapped'):
        path = tmp_path / f'maps/counties/001.{frame}.geojson.gz'
        content = json.loads(gzip.decompress(path.read_bytes()))
        content['features'][0]['properties'][key] = value
        path.write_bytes(gzip.compress(json.dumps(content).encode()))
    _repin_maps(tmp_path, report)
    with pytest.raises(ValueError, match='County block'):
        summary.verify_maps(tmp_path, report, source, labels, links, population)


def _move_case():
    provenance = {'source_sha256': summary.benchmark.SOURCE_SHA, 'code_sha256': {},
        'configuration': {'max_rebalance_moves': 1000}, 'water_connections_sha256': 'fixed'}
    move = {'units': [1], 'geoids': ['b'], 'source_district': 1, 'target_district': 0, 'population': 2}
    saved = {'provenance': provenance, 'stop_reason': 'local_optimum', 'repair_moves': [move],
        'part_repair_moves': [deepcopy(move)], 'rebalance_moves': []}
    report = {'district_count': 2, 'configuration': provenance['configuration'], 'code_sha256': {},
        'artifact_sha256': {'water-connections.json': 'fixed'},
        'postprocessing': {'stop_reason': 'local_optimum', 'repair_move_count': 1, 'part_repair_move_count': 1, 'rebalance_move_count': 0}}
    stages = {'initial': {'a': 0, 'b': 1, 'c': 1}, 'after_repair': {'a': 0, 'b': 0, 'c': 1}, 'final': {'a': 0, 'b': 0, 'c': 1}}
    return saved, stages, {'a': 5, 'b': 2, 'c': 5}, ['a', 'b', 'c'], report


def test_moves_replay_without_double_counting_part_repair_suffix():
    assert summary.verify_moves(*_move_case())['replayed_repair_and_rebalance']


@pytest.mark.parametrize('change', [
    lambda data: data[0]['repair_moves'][0].update(population=3),
    lambda data: data[0]['repair_moves'][0].update(source_district=True),
    lambda data: data[0]['repair_moves'][0].update(geoids=['c']),
    lambda data: data[1]['final'].update(b=1),
])
def test_corrupt_moves_or_stage_results_rejected(change):
    args = list(_move_case()); change(args)
    with pytest.raises(ValueError): summary.verify_moves(*args)


def test_k1_never_reports_optimizer_convergence(tmp_path):
    report = {'solver_progress': [], 'solver': {'kind': 'direct_all_blocks_assignment', 'optimizer_ran': False,
        'centers_converged': None, 'outer_iterations': 0, 'outer_iteration_limit_reached': False,
        'inner_optimization_status': 'not_applicable'}}
    assert summary.checked_trace(tmp_path, report, 1) is None
    report['solver']['centers_converged'] = True
    with pytest.raises(ValueError): summary.checked_trace(tmp_path, report, 1)


def test_no_map_link_for_failed_or_pending_results():
    data = {'scope': 'Synthetic comparison', 'status': 'complete_with_numerical_failures',
        'source': {'block_count': 10, 'population': 100},
        'runs': [{'district_count': 1, 'house_sizes': [435, 574], 'status': 'failed',
            'accepted_plan': False, 'map_url': None, 'failure': {'error': 'Numerical failure'}},
            {'district_count': 2, 'house_sizes': [692, 1000], 'status': 'pending',
             'accepted_plan': False, 'map_url': None, 'failure': {'error': 'Pending'}}],
        'preservation': {'files_rehashed': 12}, 'prelaunch_tests': {'record': {'passed': 10}},
        'summary_tests': {'record': {'passed': 10}}, 'validation_note': 'Synthetic test', 'limits': [],
        'timing': {'parent_elapsed_seconds': 20, 'independent_summary_validation_seconds': 2}}
    html = summary.html(data); markdown = summary.markdown(data)
    assert '/maps/' not in html and '/maps/' not in markdown
    assert 'no accepted map' in html and 'No validated map.' in markdown


def test_complete_k1_k2_rendering_separates_direct_assignment_from_solver():
    payload = {key: 100 for key in ('default_map_and_links_gzip_bytes', 'national_gzip_bytes',
        'state_gzip_bytes', 'full_gzip_bytes', 'connections_gzip_bytes', 'all_county_working_gzip_bytes',
        'maximum_county_working_gzip_bytes', 'index_html_bytes', 'manifest_json_bytes')}
    runs = []
    for k in (1, 2):
        runs.append({'district_count': k, 'house_sizes': summary.benchmark.HOUSE_SIZES[k],
            'accepted_plan': True, 'status': summary.ACCEPTED, 'map_url': f'{summary.URL}states/02/districts-{k}/maps/',
            'population': {'district_populations': [11] if k == 1 else [5, 6],
                'max_absolute_deviation_people': 0. if k == 1 else .5,
                'max_absolute_deviation_percent': 0. if k == 1 else 100 / 11,
                'physical_part_components': [2] if k == 1 else [1, 2], 'policy_part_components': [1] * k},
            'pipeline_seconds': 10., 'solve_seconds': None if k == 1 else 1.,
            'direct_assignment_seconds': .01 if k == 1 else None, 'export_seconds': 5.,
            'peak_process_working_set_bytes': 2**30, 'maps': {'payloads': payload, 'compressed_payload_count': 10},
            'outer_termination': None if k == 1 else {'disclosure': 'Centers converged in 5 iterations.'},
            'optimizer_trace': None if k == 1 else {'pass_count': 6, 'maximum_inner_iterations': 10}})
    data = {'scope': 'Synthetic actual-schema rendering fixture', 'status': 'complete', 'runs': runs,
        'source': {'block_count': 2, 'population': 11}, 'preservation': {'files_rehashed': 31},
        'prelaunch_tests': {'record': {'passed': 1347}}, 'summary_tests': {'record': {'passed': 42}},
        'validation_note': 'Rendering only fixture', 'limits': [],
        'timing': {'parent_elapsed_seconds': 20, 'independent_summary_validation_seconds': 2}}
    for rendered in (summary.html(data), summary.markdown(data)):
        assert '1-district' in rendered and '2-district' in rendered
        assert '0.500' in rendered and '5' in rendered
    assert 'Direct assignment; no optimizer.' in summary.html(data)
    assert 'optimization and center convergence are not applicable' in summary.markdown(data)


def test_population_reconciliation_detects_changed_assignment_and_fractional_ideal():
    pops = {'a': 5, 'b': 6}; plan = {**population_metrics([5, 6]), 'district_block_counts': [1, 1]}
    checked = summary.verify_assignments({'a': 0, 'b': 1}, pops, 2, plan)
    assert checked['max_absolute_deviation_people'] == .5
    with pytest.raises(ValueError): summary.verify_assignments({'a': 1, 'b': 0}, pops, 2, plan)


def test_prelaunch_footer_is_required_and_hashes_must_match(tmp_path):
    path = tmp_path / 'prelaunch-tests.json'
    path.write_text(json.dumps({'exit_code': 0, 'runtime_code_sha256': {'source': 'abc'}, 'runtime_code_unchanged': True}))
    (tmp_path / 'prelaunch-tests.log').write_text('10 passed in 1.25s\n')
    # The report evidence is normally inside ROOT; use a local test root only here.
    from unittest.mock import patch
    with patch.object(summary, 'ROOT', tmp_path):
        assert summary.verify_test_record(path, code={'source': 'abc'})['record']['passed'] == 10
        with pytest.raises(ValueError): summary.verify_test_record(path, code={'source': 'changed'})
        (tmp_path / 'prelaunch-tests.log').write_text('interrupted')
        with pytest.raises(ValueError): summary.verify_test_record(path, code={'source': 'abc'})


def test_shared_strict_preflight_does_not_require_unstarted_count_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(summary.benchmark, 'SUITE', tmp_path)
    directory = tmp_path / 'states/02/districts-1'; directory.mkdir(parents=True)
    path = directory / 'benchmark.json'
    path.write_text(json.dumps({'state_fips': '02', 'district_count': 1,
        'status': 'unsupported_antimeridian_topology', 'solver_progress': [],
        'source': {'archive_sha256': summary.benchmark.SOURCE_SHA}}))
    jobs = [{'district_count': k, 'house_sizes': summary.benchmark.HOUSE_SIZES[k],
        'status': 'unsupported_antimeridian_topology',
        'report' if k == 1 else 'topology_report': 'states/02/districts-1/benchmark.json'} for k in (1, 2)]
    national = {'states': [{'state_fips': '02', 'status': 'unsupported_topology', 'jobs': jobs}]}
    (tmp_path / 'suite.json').write_text(json.dumps(national))
    verified = summary.verify_strict_baselines()
    assert verified[1]['shared_state_preflight_reused_without_launching_solver']
    assert verified[0]['sha256'] == verified[1]['sha256']
    assert not (tmp_path / 'states/02/districts-2').exists()
    jobs[1]['status'] = 'complete'
    (tmp_path / 'suite.json').write_text(json.dumps(national))
    with pytest.raises(ValueError): summary.verify_strict_baselines()


def test_checkpoint_preserves_bindings_and_payload_without_implicit_resume(tmp_path):
    binding = {'source_archive_sha256': 'fixed', 'selected_terminal_report_sha256': {'2': 'report'}}
    payload = {'accepted_plan': True, 'district_count': 2, 'population': [5, 6]}
    path = summary.write_checkpoint(tmp_path, 'verified.json', payload, binding, stage='verified_for_test')
    saved = json.loads(path.read_text())
    assert saved['payload'] == payload and saved['binding'] == binding
    assert saved['automatic_resume_supported'] is False
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    assert saved['payload_sha256'] == hashlib.sha256(encoded).hexdigest()
    with pytest.raises(FileExistsError):
        summary.write_checkpoint(tmp_path, 'verified.json', payload, binding, stage='no_overwrite')
