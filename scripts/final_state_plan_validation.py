"""Read-only, bounded final acceptance checks across saved state-plan schemas.

This module never solves, repairs, exports, or rewrites a plan. It independently
reconciles populations and exported geometry, while distinguishing historical
source-coverage/graph audits from a newly regenerated source dissolve or graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any
import zipfile

import shapefile
import shapely
from shapely.affinity import translate
from shapely.geometry import Point, shape

from scripts.district_block_sources import EXPECTED_BLOCK_COUNTS, EXPECTED_RESIDENT_POPULATIONS

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STATUSES = {
    'complete', 'complete_under_island_water_policy', 'complete_under_water_policy',
    'complete_under_recorded_water_policy', 'complete_under_exclave_policy',
    'complete_under_recorded_mixed_policy',
}


class PlanValidationError(ValueError):
    """Saved evidence does not support accepting this selected plan."""


def _policy_name(report: dict, state_fips: str) -> str:
    # Alaska's schema records its policy in configuration/connectivity audits,
    # rather than the top-level field used by the earlier state adapters.
    return report.get('policy', 'shared_edges_plus_recorded_water_connections'
                      if state_fips == '02' else 'strict_shared_edge')


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlanValidationError(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _json_bytes(data: bytes) -> Any:
    return json.loads(data, object_pairs_hook=_unique_object)


def _read(path: Path) -> Any:
    return _json_bytes(path.read_bytes())


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _signature(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def _inside(base: Path, relative: str) -> Path:
    _require(isinstance(relative, str) and bool(relative), 'Artifact path must be a nonempty string.')
    path = (base / relative).resolve()
    _require(path.is_relative_to(base.resolve()), f'Artifact path escapes its run: {relative}')
    _require(path.is_file(), f'Missing artifact: {path}')
    return path


def _integer(value, label: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f'{label} must be an integer >= {minimum}.')
    return value


def _polygon_parts(geometry) -> list:
    _require(not geometry.is_empty and geometry.is_valid
             and geometry.geom_type in ('Polygon', 'MultiPolygon'),
             'Full exported/source geometry must be nonempty, valid and polygonal.')
    return list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]


@dataclass
class _Source:
    path: Path
    sha256: str
    signature: tuple[int, int, int]
    state_fips: str
    geoids: tuple[str, ...]
    populations: dict[str, int]
    member_stem: str
    endpoint_geometries: dict[tuple[str, bool], Any] = field(default_factory=dict)

    def load_endpoint_geometries(self, geoids: set[str], *, alaska: bool) -> dict[str, Any]:
        missing = geoids - {geoid for geoid, normalized in self.endpoint_geometries if normalized == alaska}
        if missing:
            indices = {geoid: index for index, geoid in enumerate(self.geoids) if geoid in missing}
            _require(set(indices) == missing, 'A link endpoint is absent from the source DBF.')
            with zipfile.ZipFile(self.path) as archive:
                # Sorted shape indices permit forward streaming through the ZIP
                # member; no source extraction or all-state geometry load occurs.
                with archive.open(self.member_stem + '.shp') as stream:
                    with shapefile.Reader(shp=stream, shx=io.BytesIO(archive.read(self.member_stem + '.shx'))) as reader:
                        for geoid, index in sorted(indices.items(), key=lambda item: item[1]):
                            geometry = shape(reader.shape(index).__geo_interface__)
                            _polygon_parts(geometry)
                            if alaska:
                                coordinates = shapely.get_coordinates(geometry)
                                positives = coordinates[:, 0] > 0
                                _require(not bool(positives.any()) or bool(positives.all()),
                                         'Alaska source block crosses the sign boundary; whole-block normalization is ambiguous.')
                                if bool(positives.all()):
                                    geometry = translate(geometry, xoff=-360)
                            self.endpoint_geometries[geoid, alaska] = geometry
        _require(_signature(self.path) == self.signature, 'Source archive changed during endpoint validation.')
        return {geoid: self.endpoint_geometries[geoid, alaska] for geoid in geoids}


@dataclass
class ValidationContext:
    """Reuse independently verified source populations across a state's plans."""
    sources: dict[tuple[Path, str], _Source] = field(default_factory=dict)

    def source(self, path: Path, digest: str, state_fips: str) -> _Source:
        path = path.resolve()
        key = path, digest
        if key in self.sources:
            result = self.sources[key]
            _require(result.state_fips == state_fips and _signature(path) == result.signature,
                     'Previously verified source archive changed during this validation session.')
            return result
        before = _signature(path)
        _require(_sha(path) == digest, 'Source archive SHA-256 does not match the selected report.')
        populations = {}
        with zipfile.ZipFile(path) as archive:
            dbfs = [name for name in archive.namelist() if name.lower().endswith('.dbf')]
            _require(len(dbfs) == 1, 'Source archive must identify exactly one DBF.')
            stem = dbfs[0][:-4]
            with shapefile.Reader(dbf=io.BytesIO(archive.read(dbfs[0]))) as reader:
                for record in reader.iterRecords():
                    geoid, population = str(record['GEOID20']), record['POP20']
                    _require(len(geoid) == 15 and geoid.isascii() and geoid.isdigit()
                             and geoid.startswith(state_fips) and geoid not in populations,
                             'Source DBF contains duplicate or wrong-state GEOIDs.')
                    populations[geoid] = _integer(population, 'Source population')
        _require(state_fips in EXPECTED_RESIDENT_POPULATIONS and state_fips in EXPECTED_BLOCK_COUNTS,
                 f'Unknown state FIPS {state_fips}.')
        _require(len(populations) == EXPECTED_BLOCK_COUNTS[state_fips]
                 and sum(populations.values()) == EXPECTED_RESIDENT_POPULATIONS[state_fips],
                 'Source DBF disagrees with official 2020 resident population/block totals.')
        _require(_signature(path) == before, 'Source archive changed during DBF validation.')
        result = _Source(path, digest, before, state_fips, tuple(populations), populations, stem)
        self.sources[key] = result
        return result


def _payload_descriptors(maps: dict) -> dict[str, dict]:
    descriptors = {}

    def add(row):
        if not isinstance(row, dict):
            return
        name = row.get('gzip_path', row.get('file'))
        if isinstance(name, str) and name.endswith('.gz'):
            merged = descriptors.setdefault(name, {})
            for field in ('raw_bytes', 'gzip_bytes', 'raw_sha256', 'sha256'):
                if field in row:
                    _require(field not in merged or merged[field] == row[field],
                             f'Conflicting payload metadata for {name}/{field}.')
                    merged[field] = row[field]
            for field in ('logical_path', 'path'):
                if field in row:
                    merged.setdefault('raw_path', row[field])
        for value in row.values():
            if isinstance(value, dict):
                add(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        add(item)

    add(maps)
    _require(bool(descriptors), 'No compressed map payload records were found.')
    return descriptors


def _verify_payloads(maps_dir: Path, maps: dict) -> tuple[dict[str, dict], list[str]]:
    verified, legacy = {}, []
    for name, row in sorted(_payload_descriptors(maps).items()):
        path = _inside(maps_dir, name)
        _require(path.stat().st_size == row.get('gzip_bytes'), f'Compressed size mismatch: {name}')
        compressed_sha = _sha(path)
        if 'sha256' in row:
            _require(compressed_sha == row['sha256'], f'Compressed SHA-256 mismatch: {name}')
        digest, size = hashlib.sha256(), 0
        with gzip.open(path, 'rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
                size += len(chunk)
        raw_sha = digest.hexdigest()
        _require(size == row.get('raw_bytes'), f'Decompressed size mismatch: {name}')
        if 'raw_sha256' in row:
            _require(raw_sha == row['raw_sha256'], f'Decompressed SHA-256 mismatch: {name}')
        else:
            # Kansas predates compressed-only storage. Its retained raw files
            # provide an independent exact round-trip comparison.
            raw_name = row.get('raw_path', name[:-3])
            raw_path = _inside(maps_dir, raw_name)
            _require(raw_path.stat().st_size == size and _sha(raw_path) == raw_sha,
                     f'Legacy raw/gzip round-trip mismatch: {name}')
            legacy.append(name)
        verified[name] = {'gzip_bytes': path.stat().st_size, 'raw_bytes': size,
                          'gzip_sha256': compressed_sha, 'raw_sha256': raw_sha}
    return verified, legacy


def _gzip_json(directory: Path, name: str, payloads: dict) -> Any:
    _require(name in payloads, f'Geometry payload was not independently verified: {name}')
    with gzip.open(_inside(directory, name), 'rb') as stream:
        return _json_bytes(stream.read())


def _reconcile_manifest(saved: dict, embedded: dict, *, alaska: bool, checked_hashes: dict) -> dict:
    if not alaska:
        _require(saved == embedded, 'Saved map manifest differs from selected terminal report.')
        return saved
    # Alaska writes manifest.json before hashing that file and the new viewer.
    # The returned export result then adds those hashes/payload totals and a
    # later elapsed time. Only these documented post-write additions may differ.
    additions = {'artifact_sha256', 'map_payload_summary'}
    _require(set(embedded) == set(saved) | additions,
             'Alaska report/manifest fields differ beyond documented export additions.')
    _require({key: value for key, value in embedded.items() if key not in additions | {'elapsed_seconds'}}
             == {key: value for key, value in saved.items() if key != 'elapsed_seconds'},
             'Alaska report differs from saved geometry/connectivity manifest.')
    earlier, later = saved.get('elapsed_seconds'), embedded.get('elapsed_seconds')
    _require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in (earlier, later))
             and later >= earlier, 'Alaska post-write export timing is inconsistent.')
    hashes = embedded.get('artifact_sha256')
    _require(isinstance(hashes, dict) and 'manifest.json' in hashes
             and all(checked_hashes.get('maps/' + name) == digest for name, digest in hashes.items()),
             'Alaska post-write map hashes are not bound by the verified report artifacts.')
    payloads = saved['payloads']
    counties = [row['gzip_bytes'] for name, row in payloads.items()
                if name.startswith('counties/') and '.working.' in name]
    _require(bool(counties), 'Alaska map manifest has no working county payloads.')
    summary = {
        'national_gzip_bytes': payloads['districts-national.working.geojson.gz']['gzip_bytes'],
        'state_gzip_bytes': payloads['districts-state.working.geojson.gz']['gzip_bytes'],
        'full_gzip_bytes': payloads['districts-full.working.geojson.gz']['gzip_bytes'],
        'connections_gzip_bytes': payloads['connections.working.geojson.gz']['gzip_bytes'],
        'all_county_working_gzip_bytes': sum(counties),
        'maximum_county_working_gzip_bytes': max(counties),
    }
    _require(embedded.get('map_payload_summary') == summary, 'Alaska post-write payload summary differs from manifest.')
    return {**saved, 'map_payload_summary': summary}


def _validate_polygons(document, populations, block_counts) -> tuple[list, list[int]]:
    _require(document.get('type') == 'FeatureCollection', 'Full map must be a FeatureCollection.')
    geometries = {}
    for feature in document.get('features', []):
        props = feature.get('properties', {})
        district = _integer(props.get('district_id'), 'Exported district identifier')
        _require(district < len(populations) and district not in geometries,
                 'Full map has duplicate or unexpected district identifiers.')
        _integer(props.get('population'), 'Exported district population')
        _integer(props.get('block_count'), 'Exported district block count', minimum=1)
        _require(props.get('population') == populations[district]
                 and props.get('block_count') == block_counts[district],
                 f'Full map population/block count disagrees with source assignments for district {district}.')
        geometry = shape(feature['geometry'])
        _polygon_parts(geometry)
        geometries[district] = geometry
    _require(set(geometries) == set(range(len(populations))), 'Full map omits a district.')
    ordered = [geometries[district] for district in range(len(populations))]
    _require(bool(shapely.coverage_is_valid(ordered)), 'Exported district coverage is invalid.')
    return ordered, [len(_polygon_parts(geometry)) for geometry in ordered]


def _link_connectivity(links, display, assignments, source, geometries, *, state_fips, alaska):
    parts = [_polygon_parts(geometry) for geometry in geometries]
    parents = [list(range(len(district_parts))) for district_parts in parts]
    used = [[] for _ in parts]

    def root(district, part):
        while parents[district][part] != part:
            parents[district][part] = parents[district][parents[district][part]]
            part = parents[district][part]
        return part

    features = {}
    for feature in display.get('features', []):
        props = feature.get('properties', {})
        link_id = props.get('id', feature.get('id'))
        _require(isinstance(link_id, str) and link_id not in features, 'Display connection IDs are invalid or duplicated.')
        features[link_id] = feature
    _require(len(links) == len(features), 'Recorded and displayed connection counts differ.')
    endpoint_geoids = {endpoint['geoid'] for link in links for endpoint in link.get('endpoints', [])}
    source_geometry = source.load_endpoint_geometries(endpoint_geoids, alaska=alaska)
    ids, edges = set(), set()
    audit = []
    for link in links:
        link_id = link.get('id')
        _require(isinstance(link_id, str) and link_id and link_id not in ids and link_id in features,
                 'Recorded connection IDs differ from the displayed map.')
        ids.add(link_id)
        _require(link.get('state_fips') == state_fips, 'Recorded link belongs to another state.')
        _require(link.get('kind') in ('recorded-water-connection', 'recorded-exclave-connection'),
                 'Recorded link must explicitly identify water or exclave policy.')
        distance = link.get('distance_m')
        _require(type(distance) in (int, float) and math.isfinite(distance) and distance > 0,
                 'Recorded link distance must be finite and positive.')
        endpoints = link.get('endpoints')
        _require(isinstance(endpoints, list) and len(endpoints) == 2, 'A recorded link must have two endpoints.')
        feature = features[link_id]
        props = feature['properties']
        _require(props.get('endpoints') == endpoints and props.get('distance_m') == link.get('distance_m'),
                 f'Displayed link identity differs from saved link {link_id}.')
        coordinates, districts, containers, ownership = [], [], [], []
        for endpoint in endpoints:
            geoid = endpoint.get('geoid')
            _require(geoid in assignments, 'Recorded endpoint block has no final district assignment.')
            index = _integer(endpoint.get('part_index'), 'Source part index')
            block_parts = _polygon_parts(source_geometry[geoid])
            _require(index < len(block_parts), 'Recorded source part index is out of range.')
            coordinate = endpoint.get('coordinate')
            _require(isinstance(coordinate, list) and len(coordinate) == 2
                     and all(type(value) in (int, float) and math.isfinite(value) for value in coordinate),
                     'Recorded endpoint coordinates must be finite pairs.')
            source_part = block_parts[index]
            _require(source_part.boundary.distance(Point(coordinate)) <= 1e-9,
                     'Recorded endpoint is not on its exact source-part boundary.')
            district = assignments[geoid]
            matches = [i for i, polygon in enumerate(parts[district]) if polygon.covers(source_part)]
            _require(len(matches) == 1, 'Endpoint source part is not wholly owned by one exported district polygon.')
            coordinates.append(coordinate)
            districts.append(district)
            containers.append(matches[0])
            ownership.append((geoid, index))
        edge = tuple(sorted(ownership))
        _require(ownership[0] != ownership[1] and edge not in edges, 'Duplicate/self recorded connection.')
        edges.add(edge)
        _require(feature.get('geometry') == {'type': 'LineString', 'coordinates': coordinates},
                 'Displayed connection geometry differs from its exact saved endpoints.')
        _require(props.get('endpoint_districts') == districts, 'Displayed endpoint district ownership is stale.')
        active = districts[0] == districts[1]
        _require(props.get('used_by_district') == (districts[0] if active else None),
                 'Displayed connection use disagrees with endpoint ownership.')
        if active:
            district = districts[0]
            a, b = (root(district, index) for index in containers)
            parents[district][a] = b
            used[district].append(link_id)
        audit.append({'id': link_id, 'kind': link['kind'], 'endpoint_districts': districts,
                      'used_by_district': districts[0] if active else None})
    counts = [len({root(district, part) for part in range(len(parts[district]))})
              for district in range(len(parts))]
    _require(all(count == 1 for count in counts), 'Recorded links do not connect every exported district polygon.')
    return counts, used, audit


def validate_plan(
    report_path: str | Path, *, archive_path: str | Path | None = None,
    expected_report_sha256: str | None = None, expected_state_fips: str | None = None,
    expected_district_count: int | None = None, context: ValidationContext | None = None,
) -> dict[str, Any]:
    """Validate one explicitly selected terminal report without mutating inputs.

    Legacy code hashes are provenance, not a requirement to match current code.
    Source graph traversal and full source-to-district dissolves are not rerun;
    their saved audits are checked separately from independent exported checks.
    """
    report_path = Path(report_path).resolve()
    run = report_path.parent
    report_sha = _sha(report_path)
    if expected_report_sha256 is not None:
        _require(report_sha == expected_report_sha256, 'Selected terminal report hash changed.')
    report = _read(report_path)
    _require(report.get('status') in TERMINAL_STATUSES and report.get('accepted_map') is not False,
             'Selected report is not an accepted terminal plan.')
    state = report.get('state_fips', expected_state_fips)
    _require(isinstance(state, str) and len(state) == 2, 'Selected report has no valid state FIPS.')
    if expected_state_fips is not None:
        _require(state == expected_state_fips, 'Selected report has the wrong state.')
    count = _integer(report.get('district_count'), 'District count', minimum=1)
    if expected_district_count is not None:
        _require(count == expected_district_count, 'Selected report has the wrong district count.')
    source_info = report.get('source', {})
    if archive_path is None:
        archive_path = source_info.get('archive_path')
        if archive_path is None and state == '20':
            archive_path = ROOT / '.cache/kansas-block-benchmark/source/tl_2020_20_tabblock20.zip'
    _require(archive_path is not None, 'Source archive path is missing.')
    source = (context or ValidationContext()).source(Path(archive_path), source_info['archive_sha256'], state)
    hash_records = report.get('artifact_sha256', {})
    checked_hashes = {}
    for name, expected in hash_records.items():
        actual = _sha(_inside(run, name))
        _require(actual == expected, f'Historical artifact hash mismatch: {name}')
        checked_hashes[name] = actual
    checkpoint_name = report.get('artifacts', {}).get('final_checkpoint', 'solver-result.json')
    checkpoint_path = _inside(run, checkpoint_name)
    checkpoint_sha = _sha(checkpoint_path)
    _require(checkpoint_name in checked_hashes or state == '20', 'Final checkpoint lacks its recorded artifact hash.')
    checkpoint = _read(checkpoint_path)
    _require(checkpoint.get('plan_kind') not in ('initial', 'after_repair', 'repair'),
             'Selected checkpoint is not the final plan.')
    provenance = checkpoint.get('provenance', checkpoint)
    _require(provenance.get('source_sha256') == source.sha256, 'Checkpoint source identity differs from report.')
    for key in ('settings_sha256', 'code_sha256'):
        if key in provenance and key in report:
            _require(provenance[key] == report[key], f'Checkpoint/report {key} differs.')
    assignments = checkpoint.get('assignments')
    _require(isinstance(assignments, dict) and set(assignments) == set(source.populations),
             'Final assignments do not exactly cover the official source GEOIDs.')
    populations, block_counts = [0] * count, [0] * count
    for geoid, label in assignments.items():
        _integer(label, 'District label')
        _require(label < count, 'Saved district label exceeds requested district count.')
        populations[label] += source.populations[geoid]
        block_counts[label] += 1
    _require(all(block_counts), 'Final assignments contain an empty district.')
    total = sum(populations)
    final = report.get('final_plan', {})
    _require(final.get('district_populations') == populations and final.get('total_population') == total,
             'Final report populations disagree with independent source DBF reconciliation.')
    _require(final.get('district_block_counts') == block_counts,
             'Final report block counts disagree with assignments.')
    numerator = max(abs(count * value - total) for value in populations)
    deviation, percent = numerator / count, numerator / total * 100
    for key, actual in [('max_absolute_deviation_people', deviation), ('max_absolute_deviation_percent', percent)]:
        _require(type(final.get(key)) in (int, float) and math.isclose(final[key], actual, rel_tol=1e-10, abs_tol=1e-9),
                 f'Final report {key} differs from independent calculation.')
    alaska = state == '02'
    manifest_name = 'maps/manifest.json' if alaska else report.get('artifacts', {}).get('map_manifest', 'maps/map-manifest.json')
    manifest_path = _inside(run, manifest_name)
    maps = _reconcile_manifest(_read(manifest_path), report.get('maps'), alaska=alaska,
                               checked_hashes=checked_hashes)
    maps_dir = manifest_path.parent
    payloads, legacy_payloads = _verify_payloads(maps_dir, maps)
    full_name = maps['full_file'] if alaska else maps['district_outlines']['full']['gzip_path']
    geometries, physical_counts = _validate_polygons(_gzip_json(maps_dir, full_name, payloads), populations, block_counts)
    link_keys = [key for key in ('water_connections', 'exclave_connections', 'recorded_connections') if report.get(key)]
    _require(len(link_keys) <= 1, 'Selected report has ambiguous connection policies.')
    links = report[link_keys[0]] if link_keys else []
    if links:
        link_key = link_keys[0]
        connection_file = maps['connections_file'] if alaska else maps[link_key]['gzip_path']
        policy_counts, used_links, link_audit = _link_connectivity(
            links, _gzip_json(maps_dir, connection_file, payloads), assignments, source, geometries,
            state_fips=state, alaska=alaska,
        )
        saved_policy = maps.get('connectivity_validation', {})
        _require(saved_policy.get('passed') is True, 'Saved independent recorded-link audit did not pass.')
        districts = {row['district_id']: row for row in saved_policy.get('districts', [])}
        _require(set(districts) == set(range(count)), 'Saved policy audit omits districts.')
        for district in range(count):
            row = districts[district]
            _require(row.get('physical_polygon_components') == physical_counts[district]
                     and row.get('connected_components_after_links') == policy_counts[district]
                     and set(row.get('used_link_ids', [])) == set(used_links[district]),
                     'Saved policy component/link audit differs from exported geometry.')
        _require(saved_policy.get('source_coverage_preserved_exactly') is True
                 and saved_policy.get('independent_source_coverage_valid') is True
                 and saved_policy.get('independent_district_coverage_valid') is True,
                 'Saved source-coverage policy audit did not pass.')
    else:
        policy_counts, used_links, link_audit = physical_counts, [[] for _ in range(count)], []
        _require(physical_counts == [1] * count, 'A strict district has disconnected exported polygons.')
        if state != '20':
            _require(maps.get('strict_validation', {}).get('passed') is True, 'Saved strict map validation did not pass.')
    if not alaska:
        quality = maps.get('quality', {})
        _require(quality.get('source_invalid_geometries') == 0
                 and quality.get('repaired_source_area_change_square_meters') == 0
                 and quality.get('district_coverage_is_valid') is True
                 and quality.get('dissolved_geometries_valid') is True,
                 'Saved source/geometry audit reports a repair or invalid coverage.')
        saved_components = [quality.get('districts', {}).get(str(i), {}).get('polygon_components') for i in range(count)]
        _require(saved_components == physical_counts, 'Saved full polygon component counts differ.')
    else:
        _require(maps.get('seam_validation', {}).get('passed') is True
                 and maps['seam_validation'].get('display_cuts_count_as_physical_components') is False,
                 'Saved Alaska normalization/seam validation did not pass.')
        # Working-frame polygons determine physical connectivity. Wrapped map
        # cuts are display pieces; check their validity without counting them
        # as new physical islands or recomputing the historic seam transform.
        for name in payloads:
            if name.startswith('districts-') and '.wrapped.' in name:
                document = _gzip_json(maps_dir, name, payloads)
                for feature in document.get('features', []):
                    geometry = shape(feature['geometry'])
                    _polygon_parts(geometry)
                    coordinates = shapely.get_coordinates(geometry)
                    _require(bool((coordinates[:, 0] >= -180).all()) and bool((coordinates[:, 0] <= 180).all()),
                             'Wrapped Alaska display longitude falls outside [-180,180].')
    graph_fields = ('policy_part_components', 'shared_edge_part_components', 'shared_edge_components')
    graph_field = next((key for key in graph_fields if key in final), None)
    _require(graph_field is not None and final[graph_field] == [1] * count,
             'Saved final graph-connectivity audit does not pass the selected policy.')
    _require(_sha(report_path) == report_sha and _signature(source.path) == source.signature,
             'Report or source changed during validation.')
    return {
        'status': 'validated_saved_plan', 'report_path': str(report_path), 'state_fips': state,
        'district_count': count, 'report_sha256': report_sha, 'checkpoint_sha256': checkpoint_sha,
        'map_manifest_sha256': _sha(manifest_path), 'source_archive_sha256': source.sha256,
        'block_count': len(assignments), 'total_population': total, 'district_populations': populations,
        'district_block_counts': block_counts, 'max_absolute_deviation_people': deviation,
        'max_absolute_deviation_percent': percent, 'physical_polygon_components': physical_counts,
        'all_districts_physically_connected': physical_counts == [1] * count,
        'policy_components': policy_counts, 'policy': _policy_name(report, state),
        'recorded_links': link_audit, 'recorded_link_count': len(links), 'payloads': payloads,
        'map_payload_summary': maps.get('load_scenarios', maps.get('map_payload_summary', {})),
        'timed_pipeline_wall_seconds': report.get('timed_pipeline_wall_seconds'),
        'peak_process_working_set_bytes': report.get('peak_process_working_set_bytes'),
        'phases': report.get('phases', {}), 'solver': report.get('solver', {}),
        'full_end_to_end_run': report.get('full_end_to_end_run'),
        'checks': {'official_dbf_populations_recomputed': True, 'all_saved_assignments_reconciled': True,
                   'historical_artifact_hash_count': len(checked_hashes),
                   'compressed_payload_count': len(payloads), 'full_exported_geometry_independently_checked': True,
                   'recorded_endpoint_source_parts_and_district_ownership_checked': bool(links),
                   'saved_graph_audit_passed': True, 'saved_graph_audit_field': graph_field,
                   'saved_source_coverage_audit_passed': True},
        'limitations': [
            'Source adjacency and the full source-to-district dissolve were not regenerated; their saved audits were checked.',
            'County payload hashes were verified; every county feature was not reparsed to reconstruct assignments.',
            'Recorded endpoint source GEOID, local polygon part, boundary coordinate and district ownership were checked; historical global part-node numbering was not regenerated.',
            *(['Legacy Kansas report lacks historical checkpoint hashes; new measured hashes bind this audit, and retained raw/gzip map bytes were compared.'] if not hash_records else []),
            *(['Some legacy payloads lack a historical raw SHA; retained raw/gzip bytes were compared exactly.'] if legacy_payloads else []),
            *(['Alaska physical geometry was checked in its continuous working frame; saved seam reconstruction evidence and wrapped payload validity were checked without regenerating every seam cut.'] if alaska else []),
        ],
    }
