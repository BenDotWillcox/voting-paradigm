"""Small source archives prove the final verifier's checks without state reruns."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

import pytest
import shapefile
import shapely
from shapely.geometry import box, mapping
from shapely.geometry.polygon import orient

from scripts import final_state_plan_validation as v


def test_alaska_schema_without_top_level_policy_is_never_labeled_strict():
    assert v._policy_name({'configuration': {'policy_adjacency': 'physical shared edges plus individually recorded water connections'}}, '02') == 'shared_edges_plus_recorded_water_connections'
    assert v._policy_name({}, '01') == 'strict_shared_edge'


def test_explicit_connection_policy_name_is_preserved():
    assert v._policy_name({'policy': 'shared_edges_plus_recorded_mixed_connections'}, '36') == 'shared_edges_plus_recorded_mixed_connections'


def write_json(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_plan(tmp_path, monkeypatch, *, linked=False, kansas=False):
    state = '20' if kansas else '01'
    geometries = [box(i, 0, i + 1, 1) for i in range(4)]
    labels, populations = [0, 0, 1, 1], [10] * 4
    if linked:
        geometries.append(box(6, 0, 7, 1))
        labels.append(1)
        populations.append(0)
    geoids = [f'{state}001000100{i:04}' for i in range(len(labels))]
    monkeypatch.setitem(v.EXPECTED_BLOCK_COUNTS, state, len(labels))
    monkeypatch.setitem(v.EXPECTED_RESIDENT_POPULATIONS, state, sum(populations))
    source = tmp_path / f'tl_2020_{state}_tabblock20'
    with shapefile.Writer(str(source)) as writer:
        writer.field('GEOID20', 'C', size=15)
        writer.field('POP20', 'N', size=10)
        for geoid, population, geometry in zip(geoids, populations, geometries, strict=True):
            writer.poly([list(orient(geometry, sign=-1).exterior.coords)])
            writer.record(geoid, population)
    archive = source.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for suffix in ('.dbf', '.shp', '.shx'):
            zipped.write(source.with_suffix(suffix), source.name + suffix)
    run = tmp_path / 'run'
    maps_dir = run / 'maps'
    maps_dir.mkdir(parents=True)
    assignments = dict(zip(geoids, labels, strict=True))
    checkpoint = {'plan_kind': 'final', 'source_sha256': digest(archive), 'assignments': assignments}
    write_json(run / 'solver-result.json', checkpoint)
    totals = [sum(p for p, label in zip(populations, labels, strict=True) if label == i) for i in range(2)]
    counts = [labels.count(i) for i in range(2)]
    full = [shapely.union_all([geometry for geometry, label in zip(geometries, labels, strict=True) if label == i]) for i in range(2)]
    component_counts = [len(g.geoms) if g.geom_type == 'MultiPolygon' else 1 for g in full]
    features = [{'type': 'Feature', 'properties': {'district_id': i, 'population': totals[i], 'block_count': counts[i]},
                 'geometry': mapping(g)} for i, g in enumerate(full)]

    def payload(name, document):
        raw = json.dumps(document).encode()
        (maps_dir / name).write_bytes(raw)
        compressed = gzip.compress(raw, mtime=0)
        (maps_dir / (name + '.gz')).write_bytes(compressed)
        return {'path': name, 'logical_path': name, 'gzip_path': name + '.gz',
                'raw_bytes': len(raw), 'gzip_bytes': len(compressed), 'raw_sha256': hashlib.sha256(raw).hexdigest()}

    outlines = payload('districts-full.geojson', {'type': 'FeatureCollection', 'features': features})
    maps = {'district_outlines': {'full': outlines},
            'storage': {'artifacts': [outlines]},
            'quality': {'source_invalid_geometries': 0, 'repaired_source_area_change_square_meters': 0,
                        'district_coverage_is_valid': True, 'dissolved_geometries_valid': True,
                        'districts': {str(i): {'polygon_components': component_counts[i]} for i in range(2)}},
            'strict_validation': {'passed': not linked}}
    report = {'status': 'complete', 'state_fips': state, 'district_count': 2,
              'source': {'archive_path': str(archive), 'archive_sha256': digest(archive)},
              'final_plan': {'district_populations': totals, 'district_block_counts': counts,
                             'total_population': sum(totals), 'max_absolute_deviation_people': 0,
                             'max_absolute_deviation_percent': 0, 'shared_edge_components': component_counts},
              'maps': maps, 'artifact_sha256': {'solver-result.json': digest(run / 'solver-result.json')}}
    if linked:
        link = {'id': 'water-001', 'state_fips': state, 'kind': 'recorded-water-connection',
                'distance_m': 2000, 'component_ids': [0, 1], 'endpoints': [
                    {'geoid': geoids[3], 'part_index': 0, 'part_node': 3, 'coordinate': [4.0, 0.5]},
                    {'geoid': geoids[4], 'part_index': 0, 'part_node': 4, 'coordinate': [6.0, 0.5]},
                ]}
        display = {'type': 'FeatureCollection', 'features': [{
            'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [e['coordinate'] for e in link['endpoints']]},
            'properties': {**link, 'endpoint_districts': [1, 1], 'used_by_district': 1},
        }]}
        descriptor = payload('water-connections.geojson', display)
        maps['water_connections'] = descriptor
        maps['storage']['artifacts'].append(descriptor)
        maps['connectivity_validation'] = {'passed': True, 'source_coverage_preserved_exactly': True,
            'independent_source_coverage_valid': True, 'independent_district_coverage_valid': True,
            'districts': [{'district_id': i, 'physical_polygon_components': component_counts[i],
                           'connected_components_after_links': 1, 'used_link_ids': ['water-001'] if i == 1 else []} for i in range(2)]}
        report.update(status='complete_under_island_water_policy', policy='shared_edges_plus_recorded_water_connections', water_connections=[link])
        report['final_plan']['policy_part_components'] = [1, 1]
    if kansas:
        report.pop('artifact_sha256')
        for descriptor in maps['storage']['artifacts']:
            descriptor.pop('raw_sha256')
        maps.pop('storage')
        maps.pop('strict_validation')
    write_json(maps_dir / 'map-manifest.json', maps)
    write_json(run / 'benchmark.json', report)
    return run / 'benchmark.json', archive


def mutate_report(path, change):
    report = json.loads(path.read_text())
    change(report)
    write_json(path, report)
    return report


def synchronize_manifest(path, report):
    write_json(path.parent / 'maps/map-manifest.json', report['maps'])
    write_json(path, report)


def test_strict_plan_reconciles_dbf_geometry_and_hashes_without_mutation(tmp_path, monkeypatch):
    report, archive = fixture_plan(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = v.validate_plan(report, expected_report_sha256=digest(report), expected_state_fips='01', expected_district_count=2)
    assert result['status'] == 'validated_saved_plan'
    assert result['district_populations'] == [20, 20]
    assert result['physical_polygon_components'] == result['policy_components'] == [1, 1]
    assert result['checks']['official_dbf_populations_recomputed'] is True
    assert result['source_archive_sha256'] == digest(archive)
    assert {p: p.read_bytes() for p in before} == before


def test_source_context_reuses_dbf_and_rejects_changed_source(tmp_path, monkeypatch):
    report, archive = fixture_plan(tmp_path, monkeypatch)
    context = v.ValidationContext()
    v.validate_plan(report, context=context)
    original = context.sources.copy()
    v.validate_plan(report, context=context)
    assert context.sources == original
    archive.write_bytes(archive.read_bytes() + b'changed')
    with pytest.raises(v.PlanValidationError, match='Previously verified source archive changed'):
        v.validate_plan(report, context=context)


def test_recorded_link_connects_actual_source_owned_polygon_parts(tmp_path, monkeypatch):
    report, _ = fixture_plan(tmp_path, monkeypatch, linked=True)
    result = v.validate_plan(report)
    assert result['physical_polygon_components'] == [1, 2]
    assert result['all_districts_physically_connected'] is False
    assert result['policy_components'] == [1, 1]
    assert result['recorded_links'][0]['endpoint_districts'] == [1, 1]
    assert result['recorded_link_count'] == 1


def test_kansas_legacy_raw_roundtrip_replaces_absent_historical_hashes(tmp_path, monkeypatch):
    report, archive = fixture_plan(tmp_path, monkeypatch, kansas=True)
    result = v.validate_plan(report, archive_path=archive, expected_state_fips='20', expected_district_count=2)
    assert result['checks']['historical_artifact_hash_count'] == 0
    assert any('Legacy Kansas' in note for note in result['limitations'])


@pytest.mark.parametrize('status', ['failed', 'running', 'unsupported_topology', 'diagnosis_complete'])
def test_nonaccepted_report_is_rejected(tmp_path, monkeypatch, status):
    report, _ = fixture_plan(tmp_path, monkeypatch)
    mutate_report(report, lambda value: value.update(status=status))
    with pytest.raises(v.PlanValidationError, match='accepted terminal'):
        v.validate_plan(report)


def test_selection_state_count_and_report_pin_are_checked(tmp_path, monkeypatch):
    report, _ = fixture_plan(tmp_path, monkeypatch)
    for options in ({'expected_state_fips': '02'}, {'expected_district_count': 3}, {'expected_report_sha256': '0' * 64}):
        with pytest.raises(v.PlanValidationError):
            v.validate_plan(report, **options)


@pytest.mark.parametrize('mutation', ['missing', 'wrong-label', 'bool-label', 'wrong-population'])
def test_checkpoint_and_population_corruption_is_detected(tmp_path, monkeypatch, mutation):
    report_path, _ = fixture_plan(tmp_path, monkeypatch)
    checkpoint_path = report_path.parent / 'solver-result.json'
    checkpoint = json.loads(checkpoint_path.read_text())
    first = next(iter(checkpoint['assignments']))
    if mutation == 'missing':
        checkpoint['assignments'].pop(first)
    elif mutation == 'wrong-label':
        checkpoint['assignments'][first] = 7
    elif mutation == 'bool-label':
        checkpoint['assignments'][first] = False
    else:
        checkpoint['assignments'][first] = 1
    write_json(checkpoint_path, checkpoint)
    # Even with a self-consistent new checkpoint hash, the source/final-report
    # reconciliation must reject bad labels, missing units or shifted totals.
    mutate_report(report_path, lambda d: d['artifact_sha256'].update({'solver-result.json': digest(checkpoint_path)}))
    with pytest.raises(v.PlanValidationError):
        v.validate_plan(report_path)


def test_historical_checkpoint_hash_cannot_be_bypassed(tmp_path, monkeypatch):
    report, _ = fixture_plan(tmp_path, monkeypatch)
    path = report.parent / 'solver-result.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(v.PlanValidationError, match='Historical artifact hash mismatch'):
        v.validate_plan(report)


def test_compressed_raw_sha_mismatch_is_rejected(tmp_path, monkeypatch):
    report_path, _ = fixture_plan(tmp_path, monkeypatch)
    report = json.loads(report_path.read_text())
    descriptor = report['maps']['district_outlines']['full']
    descriptor['raw_sha256'] = '0' * 64
    report['maps']['storage']['artifacts'][0]['raw_sha256'] = '0' * 64
    synchronize_manifest(report_path, report)
    with pytest.raises(v.PlanValidationError, match='Decompressed SHA-256 mismatch'):
        v.validate_plan(report_path)


def test_mismatched_map_manifest_is_rejected(tmp_path, monkeypatch):
    report, _ = fixture_plan(tmp_path, monkeypatch)
    write_json(report.parent / 'maps/map-manifest.json', {})
    with pytest.raises(v.PlanValidationError, match='manifest differs'):
        v.validate_plan(report)


def test_polygon_components_fail_strict_validation_independently():
    geometries = [box(0, 0, 1, 1), shapely.union_all([box(2, 0, 3, 1), box(4, 0, 5, 1)])]
    document = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'district_id': i, 'population': 20, 'block_count': 2},
         'geometry': mapping(g)} for i, g in enumerate(geometries)]}
    _, counts = v._validate_polygons(document, [20, 20], [2, 2])
    assert counts == [1, 2]


def test_invalid_polygon_rejected_without_repair():
    document = {'type': 'FeatureCollection', 'features': [{
        'type': 'Feature', 'properties': {'district_id': 0, 'population': 20, 'block_count': 2},
        'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]},
    }]}
    with pytest.raises(v.PlanValidationError, match='valid and polygonal'):
        v._validate_polygons(document, [20], [2])


def test_duplicate_json_keys_are_not_silently_accepted():
    with pytest.raises(v.PlanValidationError, match='Duplicate JSON key'):
        v._json_bytes(b'{"assignments":{"010010001000001":0,"010010001000001":1}}')


def test_artifact_paths_cannot_escape_run(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    (tmp_path / 'outside').write_text('outside')
    with pytest.raises(v.PlanValidationError, match='escapes its run'):
        v._inside(run, '../outside')


def test_wrong_source_totals_fail_even_when_archive_hash_matches(tmp_path, monkeypatch):
    report, _ = fixture_plan(tmp_path, monkeypatch)
    monkeypatch.setitem(v.EXPECTED_RESIDENT_POPULATIONS, '01', 41)
    with pytest.raises(v.PlanValidationError, match='official 2020'):
        v.validate_plan(report)


def test_alaska_endpoint_normalization_is_whole_block_and_read_only(tmp_path, monkeypatch):
    stem = tmp_path / 'tl_2020_02_tabblock20'
    geoids = ['020010001000000', '020010001000001']
    geometries = [box(170, 50, 171, 51), box(-169, 50, -168, 51)]
    with shapefile.Writer(str(stem)) as writer:
        writer.field('GEOID20', 'C', size=15)
        writer.field('POP20', 'N', size=10)
        for geoid, geometry in zip(geoids, geometries, strict=True):
            writer.poly([list(orient(geometry, sign=-1).exterior.coords)])
            writer.record(geoid, 10)
    archive = stem.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for suffix in ('.shp', '.shx', '.dbf'):
            zipped.write(stem.with_suffix(suffix), stem.name + suffix)
    original = archive.read_bytes()
    monkeypatch.setitem(v.EXPECTED_BLOCK_COUNTS, '02', 2)
    monkeypatch.setitem(v.EXPECTED_RESIDENT_POPULATIONS, '02', 20)
    source = v.ValidationContext().source(archive, digest(archive), '02')
    result = source.load_endpoint_geometries(set(geoids), alaska=True)
    assert result[geoids[0]].bounds == (-190, 50, -189, 51)
    assert result[geoids[1]].bounds == (-169, 50, -168, 51)
    assert archive.read_bytes() == original


def test_recorded_endpoint_with_wrong_local_source_part_is_rejected(tmp_path, monkeypatch):
    report_path, _ = fixture_plan(tmp_path, monkeypatch, linked=True)
    report = json.loads(report_path.read_text())
    maps_dir = report_path.parent / 'maps'
    links = deepcopy(report['water_connections'])
    links[0]['endpoints'][0]['part_index'] = 9
    document = json.loads((maps_dir / 'water-connections.geojson').read_text())
    document['features'][0]['properties']['endpoints'] = links[0]['endpoints']
    source = v.ValidationContext().source(Path(report['source']['archive_path']), report['source']['archive_sha256'], '01')
    assignments = json.loads((report_path.parent / 'solver-result.json').read_text())['assignments']
    full = json.loads((maps_dir / 'districts-full.geojson').read_text())
    geometries = [shapely.geometry.shape(feature['geometry']) for feature in full['features']]
    with pytest.raises(v.PlanValidationError, match='part index is out of range'):
        v._link_connectivity(links, document, assignments, source, geometries, state_fips='01', alaska=False)


def alaska_manifest_pair():
    names = ['districts-national.working.geojson.gz', 'districts-state.working.geojson.gz',
             'districts-full.working.geojson.gz', 'connections.working.geojson.gz',
             'counties/001.working.geojson.gz']
    saved = {'elapsed_seconds': 10.0, 'payloads': {name: {'gzip_bytes': i + 1} for i, name in enumerate(names)},
             'connectivity_validation': {'passed': True}}
    summary = {'national_gzip_bytes': 1, 'state_gzip_bytes': 2, 'full_gzip_bytes': 3,
               'connections_gzip_bytes': 4, 'all_county_working_gzip_bytes': 5,
               'maximum_county_working_gzip_bytes': 5}
    embedded = {**deepcopy(saved), 'elapsed_seconds': 10.2, 'artifact_sha256': {'manifest.json': 'checked'},
                'map_payload_summary': summary}
    return saved, embedded, {'maps/manifest.json': 'checked'}


def test_alaska_manifest_accepts_only_verified_documented_postwrite_additions():
    saved, embedded, hashes = alaska_manifest_pair()
    result = v._reconcile_manifest(saved, embedded, alaska=True, checked_hashes=hashes)
    assert result['elapsed_seconds'] == 10.0
    assert result['map_payload_summary'] == embedded['map_payload_summary']
    assert 'artifact_sha256' not in saved


@pytest.mark.parametrize('change', ['geometry', 'summary', 'hash', 'time', 'extra'])
def test_alaska_manifest_still_rejects_unexplained_or_unverified_changes(change):
    saved, embedded, hashes = alaska_manifest_pair()
    if change == 'geometry':
        embedded['connectivity_validation']['passed'] = False
    elif change == 'summary':
        embedded['map_payload_summary']['full_gzip_bytes'] = 999
    elif change == 'hash':
        embedded['artifact_sha256']['manifest.json'] = 'unverified'
    elif change == 'time':
        embedded['elapsed_seconds'] = 9.9
    else:
        embedded['extra_geometry'] = 'not an authorized post-write difference'
    with pytest.raises(v.PlanValidationError):
        v._reconcile_manifest(saved, embedded, alaska=True, checked_hashes=hashes)

