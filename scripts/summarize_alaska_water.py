"""Independently verify terminal Alaska plans without modifying their evidence.

Only the new comparison and durable reports are written. The strict historical
antimeridian preflight is not a solved-plan performance or balance baseline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
from html import escape
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import zipfile

import numpy as np
import shapefile
import shapely
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import benchmark_alaska_water as benchmark
from scripts.alaska_geometry import load_normalized_parts, build_exact_part_graph
from scripts.alaska_recorded_links import build_alaska_connections
from scripts.alaska_map_export import validate_full_polygons, wrap_geometry, _parts
from scripts.summarize_kentucky_exclave import (
    read_json, unique_pairs, sha256, verify_assignments, outer_termination,
)
from scripts.summarize_new_york_budget import finite, verify_trace
from scripts.summarize_florida_water import windows_pid_status
from scripts.state_block_execution_lock import state_execution_lock

OUTPUT = benchmark.OUTPUT
REPORT = ROOT / 'prompts/alaska-water-benchmark'
URL = 'http://127.0.0.1:8770/policies/alaska-water-v1/'
COUNTS = (1, 2)
ACCEPTED = 'complete_under_recorded_water_policy'
TERMINAL = ('complete', 'complete_with_numerical_failures', 'stopped')


def safe_path(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('Artifact paths must be nonempty relative paths.')
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()) or path == directory.resolve():
        raise ValueError('Artifact path escapes its evidence directory.')
    return path


def verify_manifest(manifest: dict) -> None:
    jobs = manifest.get('jobs', [])
    if (manifest.get('status') not in TERMINAL or not manifest.get('finished_at')
            or manifest.get('execution') != 'serial_fresh_processes'
            or len(jobs) != 2 or [j.get('district_count') for j in jobs] != list(COUNTS)):
        raise ValueError('Expected the terminal serial Alaska K1/K2 execution record.')
    for job in jobs:
        status = job.get('status')
        if status in ('complete', 'verified_numerical_failure'):
            validation = job.get('terminal_validation', {})
            if (type(job.get('exit_code')) is not int or not job.get('finished_at')
                    or validation.get('status') != status
                    or (job['exit_code'] == 0) != (status == 'complete')):
                raise ValueError('Child exit and parent-selected terminal validation disagree.')
        elif manifest['status'] != 'stopped' or status not in ('pending', 'needs_inspection'):
            raise ValueError('Execution record still contains an active or invalid job.')
    statuses = [j['status'] for j in jobs]
    if manifest['status'] == 'complete' and statuses != ['complete', 'complete']:
        raise ValueError('Complete execution record contains an unaccepted plan.')
    if manifest['status'] == 'complete_with_numerical_failures' and (
            'verified_numerical_failure' not in statuses
            or any(s not in ('complete', 'verified_numerical_failure') for s in statuses)):
        raise ValueError('Numerical-failure execution status contradicts its child outcomes.')


def selected_report(job: dict, directory: Path) -> tuple[Path, dict]:
    validation = job.get('terminal_validation', {})
    if validation.get('status') not in ('complete', 'verified_numerical_failure'):
        raise ValueError('Only explicitly selected and validated terminal reports are accepted.')
    if validation.get('report') not in ('benchmark.json', 'terminal-report.json'):
        raise ValueError('Parent did not select a recognized terminal report.')
    path = safe_path(directory, validation['report'])
    if sha256(path) != validation.get('report_sha256'):
        raise ValueError('Parent-selected terminal report checksum changed.')
    report = read_json(path)
    progress = read_json(directory / 'progress.json')
    if (progress.get('status') != report.get('status') or progress.get('active_phase') is not None
            or progress.get('authoritative_report') != path.name
            or progress.get('district_count') != job['district_count']
            or progress.get('pid') != report.get('pid')):
        raise ValueError('Final progress is stale or contradicts the selected report; inspect before publication.')
    return path, report


def check_processes(manifest: dict, launch: dict, reports: list[dict]) -> dict:
    command = launch.get('command')
    if (not isinstance(command, list) or not command
            or not any(isinstance(value, str) and Path(value).resolve() == (ROOT / 'scripts/run_alaska_water_suite.py').resolve() for value in command)
            or not launch.get('launched_at')):
        raise ValueError('Launch record does not identify this Alaska batch.')
    records = [manifest, launch, *manifest['jobs'], *reports]
    pids = [r[key] for r in records for key in ('pid', 'launcher_pid', 'child_pid', 'supervisor_pid') if key in r]
    if (type(manifest.get('pid')) is not int or type(launch.get('launcher_pid')) is not int
            or any(type(p) is not int or not 0 < p <= 2**31 - 1 for p in pids)):
        raise ValueError('Execution evidence is missing valid recorded process identities.')
    pids = sorted(set(pids))
    if os.name == 'nt':
        observations = windows_pid_status(pids)
    else:
        observations = []
        for pid in pids:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                observations.append({'pid': pid, 'active': False})
            else:
                observations.append({'pid': pid, 'active': True})
    if any(r['active'] for r in observations):
        raise ValueError('A recorded PID is still active or reused; independent lifecycle inspection is required.')
    exited = read_json(OUTPUT / 'process-exit.json')
    if (exited.get('launcher_pid') != launch['launcher_pid'] or type(exited.get('exit_code')) is not int
            or (exited['exit_code'] == 0) != (manifest['status'] != 'stopped') or not exited.get('finished_at')):
        raise ValueError('Supervisor did not confirm the parent launcher terminal exit.')
    return {'all_recorded_processes_exited': True, 'recorded_pids': pids, 'parent_exit_record': exited,
            'observed_at': datetime.now(timezone.utc).isoformat(), 'observations': observations,
            'state02_lock_acquired_and_held_during_validation': True,
            'scope': 'Recorded launcher, parent, direct child and benchmark PIDs plus the state02 OS lock; no full-system process inventory claimed.'}


def source_populations() -> dict[str, int]:
    if sha256(benchmark.ARCHIVE) != benchmark.SOURCE_SHA:
        raise ValueError('Alaska source archive identity changed.')
    with zipfile.ZipFile(benchmark.ARCHIVE) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.dbf')]
        if len(names) != 1:
            raise ValueError('Expected exactly one original Alaska DBF.')
        data = archive.read(names[0])
    result = {}
    with shapefile.Reader(dbf=io.BytesIO(data)) as reader:
        columns = [f[0] for f in reader.fields[1:]]
        gi, pi = columns.index('GEOID20'), columns.index('POP20')
        for row in reader.iterRecords():
            geoid, pop = str(row[gi]), row[pi]
            if geoid in result or len(geoid) != 15 or not geoid.startswith('02') or not geoid.isdigit():
                raise ValueError('Source DBF contains duplicate or invalid Alaska GEOIDs.')
            if isinstance(pop, bool) or not isinstance(pop, (int, float)) or not math.isfinite(pop) or int(pop) != pop or pop < 0:
                raise ValueError('Source DBF population is not a nonnegative integer.')
            result[geoid] = int(pop)
    if len(result) != benchmark.BLOCKS or sum(result.values()) != benchmark.TOTAL:
        raise ValueError('Alaska source DBF differs from official block/population totals.')
    return result


def component_counts(graph, assignments: dict, geoids: list[str], k: int) -> list[int]:
    """Independent induced-subgraph traversal; shared ownership creates no edge."""
    labels = [assignments[geoids[owner]] for owner in graph.part_to_unit]
    counts, seen = [0] * k, set()
    for start, label in enumerate(labels):
        if start in seen:
            continue
        counts[label] += 1
        pending = [start]
        seen.add(start)
        while pending:
            node = pending.pop()
            for neighbor in graph.adjacency[node]:
                if neighbor not in seen and labels[neighbor] == label:
                    seen.add(neighbor)
                    pending.append(neighbor)
    return counts


def verify_provenance(saved: dict, report: dict) -> None:
    expected = {'source_sha256': benchmark.SOURCE_SHA, 'code_sha256': report['code_sha256'],
                'configuration': report['configuration'],
                'water_connections_sha256': report['artifact_sha256']['water-connections.json']}
    if saved.get('provenance') != expected:
        raise ValueError('Saved assignment/move provenance differs from measured source, code or policy.')


def verify_moves(saved: dict, stages: dict, populations: dict, geoids: list[str], report: dict) -> dict:
    verify_provenance(saved, report)
    post = report['postprocessing']
    if saved.get('stop_reason') != post['stop_reason'] or post['stop_reason'] not in ('local_optimum', 'max_moves'):
        raise ValueError('Postprocessing termination differs from the move audit.')
    for kind in ('repair', 'part_repair', 'rebalance'):
        if type(post.get(kind + '_move_count')) is not int or post[kind + '_move_count'] != len(saved[kind + '_moves']):
            raise ValueError('Postprocessing move counts differ from the audit.')
    suffix = saved['part_repair_moves']
    if suffix and saved['repair_moves'][-len(suffix):] != suffix:
        raise ValueError('Polygon-part repairs must be the recorded suffix of all repair moves.')
    limit = report['configuration']['max_rebalance_moves']
    if not 0 <= len(saved['rebalance_moves']) <= limit or post['stop_reason'] == 'max_moves' and len(saved['rebalance_moves']) != limit:
        raise ValueError('Postprocessing budget and stop reason disagree.')
    labels = dict(stages['initial'])
    for kind, expected in (('repair', stages['after_repair']), ('rebalance', stages['final'])):
        for move in saved[kind + '_moves']:
            ids = move['units']
            if (not ids or len(set(ids)) != len(ids)
                    or any(type(i) is not int or not 0 <= i < len(geoids) for i in ids)
                    or move['geoids'] != [geoids[i] for i in ids]
                    or move['source_district'] == move['target_district']
                    or type(move['source_district']) is not int or type(move['population']) is not int
                    or type(move['target_district']) is not int
                    or not 0 <= move['target_district'] < report['district_count']
                    or any(labels[geoids[i]] != move['source_district'] for i in ids)
                    or sum(populations[geoids[i]] for i in ids) != move['population']):
                raise ValueError('A move has invalid population, identities or source ownership.')
            for i in ids:
                labels[geoids[i]] = move['target_district']
        if labels != expected:
            raise ValueError('Replayed moves do not reproduce the saved assignment stage.')
    return {'replayed_repair_and_rebalance': True, **post}


def verify_artifacts(directory: Path, report: dict) -> None:
    if not report.get('artifact_sha256'):
        raise ValueError('Terminal report does not pin any artifacts.')
    for name, digest in report['artifact_sha256'].items():
        if sha256(safe_path(directory, name)) != digest:
            raise ValueError(f'Measured artifact checksum changed: {name}')


def read_payload(directory: Path, name: str, metadata: dict) -> dict:
    compressed = safe_path(directory, name).read_bytes()
    raw = gzip.decompress(compressed)
    if (metadata.get('file') != name or len(compressed) != metadata.get('gzip_bytes')
            or len(raw) != metadata.get('raw_bytes')
            or hashlib.sha256(compressed).hexdigest() != metadata.get('sha256')
            or hashlib.sha256(raw).hexdigest() != metadata.get('raw_sha256')
            or metadata.get('gzip_verified') is not True):
        raise ValueError('Saved compressed payload differs from its measured bytes/checksums.')
    result = json.loads(raw, object_pairs_hook=unique_pairs)
    if result.get('type') != 'FeatureCollection' or not isinstance(result.get('features'), list):
        raise ValueError('Map payload is not a GeoJSON feature collection.')
    return result


def verify_seam_pair(working: dict, wrapped: dict) -> dict:
    geometry, actual = shape(working['geometry']), shape(wrapped['geometry'])
    expected, audit = wrap_geometry(geometry)
    properties = dict(wrapped['properties'])
    if properties.pop('antimeridian', None) != audit or properties != working['properties']:
        raise ValueError('Wrapped attributes or seam offsets disagree with the working feature.')
    if not actual.is_valid or not actual.equals(expected):
        raise ValueError('Saved wrapped geometry differs from the independently wrapped working feature.')
    kind = 'polygon' if geometry.geom_type in ('Polygon', 'MultiPolygon') else 'line'
    pieces = _parts(actual, kind)
    offsets = audit['part_offsets_from_working_degrees']
    if len(pieces) != len(offsets):
        raise ValueError('Saved seam offsets do not cover every displayed fragment.')
    restored = unary_union([translate(p, xoff=-offset) if offset else p for p, offset in zip(pieces, offsets, strict=True)])
    if kind == 'polygon':
        same = geometry.symmetric_difference(restored).is_empty
    else:
        same = geometry.hausdorff_distance(restored) <= 1e-10 and abs(geometry.length - restored.length) <= 1e-10
    if not same:
        raise ValueError('Saved wrapped fragment ordering/offsets fail inverse reconstruction.')
    for piece in pieces:
        rings = [piece.coords] if kind == 'line' else [piece.exterior.coords, *[r.coords for r in piece.interiors]]
        for ring in rings:
            points = np.asarray(ring)
            if np.any(points[:, 0] < -180) or np.any(points[:, 0] > 180) or np.any(np.abs(np.diff(points[:, 0])) > 180):
                raise ValueError('Saved wrapped artifact has a world-spanning segment.')
    return audit


def verify_maps(directory: Path, report: dict, source: tuple, assignments: dict, connections: list,
                population_check: dict) -> dict:
    parts, records, owners, indices = source[:4]
    full, audit, link_collection = validate_full_polygons(parts, records, owners, indices, assignments, connections)
    manifest = read_json(directory / 'maps/manifest.json')
    measured = report['maps']
    if any(measured.get(key) != value for key, value in manifest.items() if key != 'elapsed_seconds'):
        raise ValueError('Saved map manifest disagrees with the terminal export report.')
    if (manifest.get('status') != 'validated_complete_map' or manifest.get('connectivity_validation') != audit
            or manifest.get('total_population') != population_check['total_population']
            or manifest.get('block_count') != population_check['block_count']
            or manifest.get('district_populations') != population_check['district_populations']
            or manifest.get('max_absolute_deviation_people') != population_check['max_absolute_deviation_people']
            or manifest.get('max_absolute_deviation_percent') != population_check['max_absolute_deviation_percent']):
        raise ValueError('Fresh unsimplified geometry/population validation disagrees with the map manifest.')
    physical = [row['physical_polygon_components'] for row in audit['districts']]
    if (physical != report['final_plan']['physical_part_components']
            or manifest['physical_validation']['district_component_counts'] != physical
            or manifest['physical_validation']['all_districts_physically_connected'] != all(n == 1 for n in physical)):
        raise ValueError('Polygon and graph connectivity counts disagree.')
    expected_names = {f'{stem}.{frame}.geojson.gz' for stem in ('districts-full', 'districts-state', 'districts-national', 'connections') for frame in ('working', 'wrapped')}
    counties = sorted({r['geoid'][2:5] for r in records})
    expected_names.update(f'counties/{county}.{frame}.geojson.gz' for county in counties for frame in ('working', 'wrapped'))
    if set(manifest['payloads']) != expected_names:
        raise ValueError('Expected exactly every district level, connection and county frame payload.')
    actual_files = {p.relative_to(directory / 'maps').as_posix() for p in (directory / 'maps').rglob('*') if p.is_file()}
    if actual_files != expected_names | {'manifest.json', 'index.html'}:
        raise ValueError('Map artifact universe differs from the accepted export.')
    if set(measured['artifact_sha256']) != actual_files:
        raise ValueError('Map export artifact checksum universe is incomplete.')
    for name, digest in measured['artifact_sha256'].items():
        if sha256(safe_path(directory / 'maps', name)) != digest or report['artifact_sha256'].get('maps/' + name) != digest:
            raise ValueError('Map checksums differ between saved bytes, exporter and pipeline.')
    def pair(stem):
        first, second = [read_payload(directory / 'maps', f'{stem}.{frame}.geojson.gz', manifest['payloads'][f'{stem}.{frame}.geojson.gz']) for frame in ('working', 'wrapped')]
        if len(first['features']) != len(second['features']):
            raise ValueError('Working/wrapped feature counts disagree.')
        audits = [verify_seam_pair(a, b) for a, b in zip(first['features'], second['features'], strict=True)]
        return first['features'], audits
    compact_seams = []
    for stem, tolerance in (('districts-full', 0), ('districts-state', .002), ('districts-national', .015)):
        features, seams = pair(stem)
        if len(features) != len(full):
            raise ValueError('District map feature count differs from the accepted plan.')
        for d, feature in enumerate(features):
            expected_geometry = full[d].simplify(tolerance, preserve_topology=True) if tolerance else full[d]
            if not shape(feature['geometry']).equals(expected_geometry) or feature['properties'] != manifest['districts'][d]:
                raise ValueError('Saved district geometry/attributes differ from the source assignment.')
            if feature['properties']['population'] != population_check['district_populations'][d] or feature['properties']['block_count'] != population_check['district_block_counts'][d]:
                raise ValueError('Map attributes differ from source DBF totals.')
            if stem == 'districts-full':
                compact_seams.append({'artifact': stem, 'id': d, **seams[d]})
    features, seams = pair('connections')
    if len(features) != len(link_collection['features']):
        raise ValueError('Map omits a recorded connection.')
    for saved, expected, seam in zip(features, link_collection['features'], seams, strict=True):
        if not shape(saved['geometry']).equals(shape(expected['geometry'])) or saved['properties'] != expected['properties']:
            raise ValueError('Saved connection geometry or same-district endpoint use changed.')
        compact_seams.append({'artifact': 'connections', 'id': expected['properties']['id'], **seam})
    if manifest['seam_validation'] != {'passed': True, 'full_and_link_reconstruction_audits': compact_seams, 'display_cuts_count_as_physical_components': False}:
        raise ValueError('Saved full-map/link seam audit disagrees with reconstructed artifacts.')
    by_owner = [[] for _ in records]
    for part, owner in zip(parts, owners, strict=True):
        by_owner[owner].append(part)
    seen, county_records = set(), []
    for county in counties:
        features, _ = pair('counties/' + county)
        expected_units = [i for i, r in enumerate(records) if r['geoid'][2:5] == county]
        if len(features) != len(expected_units):
            raise ValueError('County payload block count differs from source.')
        for feature, unit in zip(features, expected_units, strict=True):
            record = records[unit]
            expected_geometry = by_owner[unit][0] if len(by_owner[unit]) == 1 else MultiPolygon(by_owner[unit])
            expected_properties = {'geoid': record['geoid'], 'population': record['population'],
                'district_id': assignments[record['geoid']], 'land_area_m2': record['land_area_m2'], 'water_area_m2': record['water_area_m2']}
            if not shape(feature['geometry']).equals(expected_geometry) or feature['properties'] != expected_properties or record['geoid'] in seen:
                raise ValueError('County block geometry/population/assignment differs from source or is duplicated.')
            seen.add(record['geoid'])
        county_records.append({'county_fips': county, 'block_count': len(expected_units),
            'population': sum(records[i]['population'] for i in expected_units),
            'working_file': f'counties/{county}.working.geojson.gz', 'wrapped_file': f'counties/{county}.wrapped.geojson.gz'})
    if seen != set(assignments) or manifest['counties'] != county_records:
        raise ValueError('County payloads do not cover the full source block universe.')
    sizes = {name: item['gzip_bytes'] for name, item in manifest['payloads'].items()}
    payloads = {'national_gzip_bytes': sizes['districts-national.working.geojson.gz'],
        'state_gzip_bytes': sizes['districts-state.working.geojson.gz'], 'full_gzip_bytes': sizes['districts-full.working.geojson.gz'],
        'connections_gzip_bytes': sizes['connections.working.geojson.gz'],
        'all_county_working_gzip_bytes': sum(size for name, size in sizes.items() if name.startswith('counties/') and '.working.' in name),
        'maximum_county_working_gzip_bytes': max(size for name, size in sizes.items() if name.startswith('counties/') and '.working.' in name)}
    if measured['map_payload_summary'] != payloads:
        raise ValueError('Map load-size summary differs from verified compressed payloads.')
    payloads.update(default_map_and_links_gzip_bytes=payloads['national_gzip_bytes'] + payloads['connections_gzip_bytes'],
        index_html_bytes=(directory / 'maps/index.html').stat().st_size, manifest_json_bytes=(directory / 'maps/manifest.json').stat().st_size,
        wrapped_national_gzip_bytes=sizes['districts-national.wrapped.geojson.gz'],
        note='Geometry gzip bytes; HTML and manifest listed separately. County detail is loaded on demand; the whole state block payload is not needed for the initial view.')
    return {'independent_polygon_and_link_audit': audit, 'physical_polygon_components': physical,
            'compressed_payload_count': len(expected_names), 'all_county_blocks_verified': len(seen),
            'working_and_wrapped_seams_verified': True, 'payloads': payloads}


def checked_trace(directory: Path, report: dict, k: int) -> dict | None:
    if k == 1:
        if report.get('optimizer_trace') or report.get('solver_progress') or (directory / 'optimizer-trace.jsonl').exists():
            raise ValueError('The direct K1 assignment unexpectedly ran an optimizer.')
        if report.get('solver') != {'kind': 'direct_all_blocks_assignment', 'optimizer_ran': False,
                'centers_converged': None, 'outer_iterations': 0, 'outer_iteration_limit_reached': False,
                'inner_optimization_status': 'not_applicable'}:
            raise ValueError('K1 solver metadata must identify direct assignment with no convergence claim.')
        return None
    trace_path = directory / 'optimizer-trace.jsonl'
    rows = [json.loads(line, object_pairs_hook=unique_pairs) for line in trace_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    result = verify_trace(rows, report['optimizer_trace'], k=k, total=benchmark.TOTAL)
    if report['solver_progress'] != report['optimizer_trace']['passes']:
        raise ValueError('Solver progress and optimizer trace summary disagree.')
    for entry in report['optimizer_trace']['passes']:
        if entry['actual_options'] != {'maxiter': 1000, 'gtol': 1e-6 / benchmark.TOTAL, 'ftol': 1e-12, 'maxls': 100}:
            raise ValueError('Observed inner optimizer options differ from the authorized settings.')
    if report['status'] == ACCEPTED:
        if (not result['all_inner_passes_succeeded'] or result['pass_count'] != report['solver']['outer_iterations'] + 1
                or report['solver'].get('optimizer_ran') is not True or report['solver'].get('all_inner_optimizer_passes_succeeded') is not True):
            raise ValueError('Accepted K2 plan lacks successful complete inner optimizer evidence.')
    else:
        failure, last = report.get('optimizer_failure', {}), report['solver_progress'][-1]['inner_optimizer']
        if (last['success'] is not False or failure.get('plan_returned') is not False
                or any(failure.get(key) != last[key] for key in ('iterations', 'function_evaluations', 'status', 'message'))
                or not all(p['inner_optimizer']['success'] is True for p in report['solver_progress'][:-1])):
            raise ValueError('Numerical failure report differs from its observed inner termination.')
    for row in result['passes']:
        for key in ('samples', 'at_original_budget', 'objective_improvement_after_original_budget', 'max_deviation_people_at_original_budget'):
            row.pop(key, None)
    result['maximum_inner_iterations'] = max(p['optimizer']['iterations'] for p in result['passes'])
    return result


def verify_run(job: dict, report: dict, manifest: dict, inventory: dict, populations: dict, source: tuple, physical) -> dict:
    k = job['district_count']
    directory = OUTPUT / f'states/02/districts-{k}'
    if (report.get('state_fips') != '02' or report.get('district_count') != k or report.get('house_sizes') != benchmark.HOUSE_SIZES[k]
            or not report.get('finished_at') or report.get('active_phase') is not None
            or report.get('configuration') != benchmark.configuration_for_run(k)
            or report.get('code_sha256') != manifest['code_sha256']
            or report.get('source', {}).get('archive_sha256') != benchmark.SOURCE_SHA
            or report['source'].get('resident_population') != benchmark.TOTAL or report['source'].get('block_count') != benchmark.BLOCKS):
        raise ValueError('Terminal run identity/source/configuration differs from the authorized attempt.')
    expected_status = ACCEPTED if job['status'] == 'complete' else 'failed'
    if report.get('status') != expected_status or read_json(directory / 'preserved-file-inventory.json') != inventory:
        raise ValueError('Run outcome or original evidence inventory differs from its parent.')
    if report.get('preservation_audit', {}).get('original_files_byte_identical') is not True or report['preservation_audit'].get('run_code_unchanged') is not True:
        raise ValueError('Run preservation did not pass.')
    verify_artifacts(directory, report)
    parts, records, owners, indices = source[:4]
    augmented, connections, policy = build_alaska_connections(parts, records, owners, indices, physical, k)
    connections = list(connections)
    if report.get('water_connections') != connections or read_json(directory / 'water-connections.json') != {'source_sha256': benchmark.SOURCE_SHA, 'connections': connections}:
        raise ValueError('Saved water links differ from the independently reselected and verified source policy.')
    for key, value in policy.items():
        if key not in ('elapsed_seconds', 'source_normalization') and report['island_policy_audit'].get(key) != value:
            raise ValueError(f'Saved population-aware policy differs from independent verification: {key}')
    trace = checked_trace(directory, report, k)
    pipeline = finite(report['timed_pipeline_wall_seconds'], 'pipeline wall time')
    phases = report['phases']
    if pipeline <= 0 or any(finite(p['wall_seconds'], 'phase time') < 0 for p in phases.values()) or sum(p['wall_seconds'] for p in phases.values()) > pipeline + 1:
        raise ValueError('Measured pipeline/phase runtime is inconsistent.')
    peak = report.get('peak_process_working_set_bytes')
    if type(peak) is not int or peak <= 0:
        raise ValueError('Peak process memory must be a positive measured byte count.')
    result = {'district_count': k, 'house_sizes': benchmark.HOUSE_SIZES[k], 'status': report['status'],
        'accepted_plan': False, 'map_url': None, 'pipeline_seconds': pipeline,
        'solve_seconds': phases.get('solve', {}).get('wall_seconds'),
        'direct_assignment_seconds': phases.get('direct_assignment', {}).get('wall_seconds'),
        'export_seconds': phases.get('independent_polygon_and_seam_validation_map_export', {}).get('wall_seconds'),
        'peak_process_working_set_bytes': peak, 'process_wall_seconds': job['process_wall_seconds'],
        'phases': phases, 'optimizer_trace': trace,
        'report': job['terminal_validation']['report'], 'report_sha256': job['terminal_validation']['report_sha256'],
        'water_link_count': len(connections), 'total_water_link_distance_m': sum(c['distance_m'] for c in connections)}
    if report['status'] == 'failed':
        if (k != 2 or job['exit_code'] == 0 or report.get('failed_phase') != 'solve'
                or not str(report.get('error', '')).startswith('DistrictingOptimizationError:')
                or not report.get('optimizer_failure') or 'final_plan' in report or 'maps' in report
                or (directory / 'maps').exists()):
            raise ValueError('Attempt is not a verified numerical failure without a returned map.')
        return {**result, 'failure': {'error': report['error'], 'phase': report['failed_phase'], 'optimizer': report['optimizer_failure']}}
    geoids = [r['geoid'] for r in records]
    stages, checks = {}, {}
    for stage, filename in (('initial', 'initial-solver-result.json'), ('after_repair', 'after-repair-result.json'), ('final', 'solver-result.json')):
        saved = read_json(directory / filename)
        verify_provenance(saved, report)
        labels = saved['assignments']
        checks[stage] = verify_assignments(labels, populations, k, report[stage + '_plan'])
        a, b = component_counts(physical, labels, geoids, k), component_counts(augmented, labels, geoids, k)
        planned = report[stage + '_plan']
        if (a != planned['physical_part_components'] or b != planned['policy_part_components']
                or planned['all_districts_physically_connected'] != all(c == 1 for c in a)
                or planned['all_districts_policy_connected'] != all(c == 1 for c in b)
                or stage != 'initial' and b != [1] * k):
            raise ValueError('Independent induced part-graph connectivity differs from reported assignment stage.')
        stages[stage] = labels
        checks[stage].update(physical_part_components=a, policy_part_components=b)
    post = verify_moves(read_json(directory / 'move-audit.json'), stages, populations, geoids, report)
    map_check = verify_maps(directory, report, source, stages['final'], connections, checks['final'])
    return {**result, 'accepted_plan': True, 'map_url': f'{URL}states/02/districts-{k}/maps/',
        'population': checks['final'], 'assignment_stages': checks, 'maps': map_check,
        'postprocessing': post, 'outer_termination': outer_termination(report['solver'], report['configuration']) if k == 2 else None,
        'solver_kind': report['solver']['kind']}


def verify_test_record(path: Path, *, code: dict | None = None) -> dict:
    record = read_json(path)
    if record.get('exit_code') != 0:
        raise ValueError('Required test evidence does not record a passing test run.')
    if code is not None:
        if record.get('runtime_code_sha256') != code or record.get('runtime_code_unchanged') is not True:
            raise ValueError('Passing prelaunch tests do not match the frozen runtime files.')
        log = path.with_name('prelaunch-tests.log')
        matches = re.findall(r'(\d+) passed in ([\d.]+)s', log.read_text(encoding='utf-8'))
        if len(matches) != 1 or int(matches[0][0]) <= 0:
            raise ValueError('Prelaunch log does not contain one positive passing pytest footer.')
        record = {**record, 'passed': int(matches[0][0]), 'pytest_elapsed_seconds': float(matches[0][1]),
                  'log_sha256': sha256(log), 'passed_count_source': 'preserved prelaunch-tests.log pytest footer'}
    if code is None:
        expected = {name: sha256(ROOT / name) for name in ('scripts/summarize_alaska_water.py', 'scripts/tests/test_summarize_alaska_water.py')}
        if record.get('code_sha256') != expected:
            raise ValueError('Passing summary-only tests do not match the tested summary and test files.')
        if type(record.get('passed')) is not int or record['passed'] <= 0:
            raise ValueError('Summary-only evidence must record a positive passing test count.')
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha256(path), 'record': record}


def verify_strict_baselines() -> list[dict]:
    """State-wide preflight rejection can be shared by an unstarted count job."""
    national = read_json(benchmark.SUITE / 'suite.json')
    states = [s for s in national['states'] if s.get('state_fips') == '02']
    if len(states) != 1 or states[0].get('status') != 'unsupported_topology':
        raise ValueError('Preserved national suite does not contain the original Alaska rejection.')
    jobs = states[0]['jobs']
    if [j.get('district_count') for j in jobs] != list(COUNTS):
        raise ValueError('Original Alaska anchor jobs differ from the authorized counts.')
    rows = []
    for job in jobs:
        k = job['district_count']
        reference = job.get('report') or job.get('topology_report')
        if (job.get('status') != 'unsupported_antimeridian_topology'
                or job.get('house_sizes') != benchmark.HOUSE_SIZES[k]
                or reference != 'states/02/districts-1/benchmark.json'):
            raise ValueError('Original Alaska jobs must reference their preserved shared antimeridian preflight.')
        path = safe_path(benchmark.SUITE, reference)
        data = read_json(path)
        if (data.get('status') != 'unsupported_antimeridian_topology' or data.get('solver_progress')
                or data.get('state_fips') != '02' or data.get('district_count') != 1
                or data.get('source', {}).get('archive_sha256') != benchmark.SOURCE_SHA):
            raise ValueError('Historical strict report is not the preserved unsolved source preflight.')
        rows.append({'district_count': k, 'status': job['status'], 'report': reference,
            'sha256': sha256(path), 'solver_ran': False,
            'shared_state_preflight_reused_without_launching_solver': 'topology_report' in job})
    return rows


def write_checkpoint(directory: Path, name: str, payload: dict, binding: dict, *, stage: str) -> Path:
    """Persist verified facts for inspection; this function implements no resume."""
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    record = {'schema_version': 1, 'stage': stage, 'automatic_resume_supported': False,
        'binding': binding, 'payload_sha256': hashlib.sha256(encoded).hexdigest(), 'payload': payload}
    path = safe_path(directory, name)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    saved = read_json(path)
    restored = json.dumps(saved['payload'], sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if hashlib.sha256(restored).hexdigest() != saved['payload_sha256'] or saved['binding'] != binding:
        raise ValueError('Saved validation checkpoint failed its own checksum verification.')
    return path


def summary(validation_note: str) -> dict:
    if not isinstance(validation_note, str) or not validation_note.strip():
        raise ValueError('A truthful nonempty validation note is required.')
    started = time.perf_counter()
    manifest = read_json(OUTPUT / 'run.json')
    verify_manifest(manifest)
    launch = read_json(OUTPUT / 'launch-process.json')
    selected = {}
    for job in manifest['jobs']:
        if job['status'] in ('complete', 'verified_numerical_failure'):
            selected[job['district_count']] = selected_report(job, OUTPUT / f'states/02/districts-{job["district_count"]}')[1]
    process_check = check_processes(manifest, launch, list(selected.values()))
    checkpoint_dir = OUTPUT / 'summary-checkpoints' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    binding = {'run_manifest_sha256': sha256(OUTPUT / 'run.json'),
        'preserved_inventory_sha256': sha256(OUTPUT / 'preserved-file-inventory.json'),
        'source_archive_sha256': benchmark.SOURCE_SHA,
        'runtime_code_sha256': manifest['code_sha256'],
        'summary_code_sha256': sha256(Path(__file__)),
        'selected_terminal_report_sha256': {str(job['district_count']): job['terminal_validation']['report_sha256']
            for job in manifest['jobs'] if job['district_count'] in selected}}
    with state_execution_lock('02'):
        inventory = read_json(OUTPUT / 'preserved-file-inventory.json')
        if benchmark.protected_inventory() != inventory or benchmark.runtime_code() != manifest['code_sha256']:
            raise ValueError('Original evidence or frozen runtime differs before summary validation.')
        prelaunch = verify_test_record(OUTPUT / 'prelaunch-tests.json', code=manifest['code_sha256'])
        if prelaunch['sha256'] != manifest['prelaunch_tests_sha256']:
            raise ValueError('Parent prelaunch test record checksum changed.')
        summary_tests = verify_test_record(OUTPUT / 'summary-validation-tests.json')
        strict = verify_strict_baselines()
        write_checkpoint(checkpoint_dir, 'strict-baselines.json', {'strict_originals': strict}, binding,
            stage='verified_original_shared_preflight_evidence')
        populations = source_populations()
        source = load_normalized_parts(benchmark.ARCHIVE)
        if {r['geoid']: r['population'] for r in source[1]} != populations:
            raise ValueError('Normalized source loader differs from independent original DBF accounting.')
        physical, graph_audit = build_exact_part_graph(source[0], source[2])
        runs = []
        for job in manifest['jobs']:
            k = job['district_count']
            if k in selected:
                runs.append(verify_run(job, selected[k], manifest, inventory, populations, source, physical))
                write_checkpoint(checkpoint_dir, f'verified-run-{k}.json', runs[-1], binding,
                    stage='verified_run_pending_final_preservation_recheck')
                print(f'Independently verified Alaska K{k}; checkpoint saved.', flush=True)
            else:
                runs.append({'district_count': k, 'house_sizes': benchmark.HOUSE_SIZES[k],
                    'status': job['status'], 'accepted_plan': False, 'map_url': None,
                    'failure': {'error': manifest.get('error', 'No accepted terminal report; requires inspection.')}})
        if benchmark.protected_inventory() != inventory or benchmark.runtime_code() != manifest['code_sha256']:
            raise ValueError('Original evidence or frozen runtime changed during summary validation.')
        if read_json(OUTPUT / 'run.json') != manifest:
            raise ValueError('Parent execution record changed during summary validation.')
    data = {'schema_version': 1, 'state': 'Alaska', 'status': manifest['status'],
        'generated_at': datetime.now(timezone.utc).isoformat(), 'validation_note': validation_note,
        'scope': '2020 census blocks, K1 for House 435/574 and K2 for House 692/1000; 49 explicit water links, continuous-longitude normalization, 1,000 inner and 80 outer iterations for K2.',
        'source': {'archive_sha256': benchmark.SOURCE_SHA, 'block_count': len(populations), 'population': sum(populations.values()),
            'part_count': len(source[0]), 'physical_component_count': graph_audit['component_count']},
        'runs': runs, 'strict_originals': strict, 'process_check': process_check,
        'preservation': {'files_rehashed': len(inventory), 'all_original_files_unchanged': True, 'frozen_runtime_unchanged': True,
                         'runtime_code_sha256': manifest['code_sha256']},
        'prelaunch_tests': prelaunch, 'summary_tests': summary_tests,
        'validation_checkpoint_directory': checkpoint_dir.relative_to(ROOT).as_posix(),
        'timing': {'parent_elapsed_seconds': manifest['elapsed_wall_seconds'],
            'serial_child_process_seconds': sum(j.get('process_wall_seconds', 0) for j in manifest['jobs']),
            'independent_summary_validation_seconds': time.perf_counter() - started},
        'limits': ['K1 is a direct assignment of every block; it has no solver runtime or convergence result.',
            'The strict batch ran K1 preflight and reused its antimeridian rejection for unstarted K2; no solver ran and there is no solved strict-plan baseline.',
            'Physical shared-edge connectivity is separate from connectivity through same-district recorded links.',
            'Regional ocean evidence and Alaska source-interior checks do not certify a global land mask, foreign-land clearance or navigability.',
            'All source polygons and populations are preserved. Seam cuts affect displayed longitude representation, not physical graph connectivity.',
            'Original NAD83 source coordinates are retained; no WGS84 datum conversion or strict RFC7946 claim.',
            'The existing population-centered equirectangular solver distance model is approximate across Alaska.',
            'Pipeline timings include source reading, repeated graph/policy verification and map export; trace observation overhead is included. Independent summary time is separate.',
            'K2 inner optimizer success, outer center convergence and final whole-block population balance are separate findings.']}
    write_checkpoint(checkpoint_dir, 'validated-comparison.json', data, binding,
        stage='all_numerical_geometry_preservation_and_process_checks_passed_ready_for_rendering')
    return data


def markdown(data: dict) -> str:
    lines = ['# Alaska recorded-water benchmark', '', data['scope'], '',
        f"Status: **{data['status']}**. All {data['source']['block_count']:,} source blocks and {data['source']['population']:,} residents are retained.", '',
        '| Districts | House sizes | Result | Max population deviation | Physical components by district | Components with links |',
        '|---:|---|---|---|---|---|']
    for row in data['runs']:
        if row['accepted_plan']:
            pop = row['population']
            values = [f"[{row['district_count']}-district map]({row['map_url']})", ', '.join(map(str, row['house_sizes'])), 'Validated',
                f"{pop['max_absolute_deviation_people']:,.3f} people ({pop['max_absolute_deviation_percent']:.6f}%)",
                ', '.join(map(str, pop['physical_part_components'])), ', '.join(map(str, pop['policy_part_components']))]
        else:
            values = [str(row['district_count']), ', '.join(map(str, row['house_sizes'])), row['status'], '—', '—', '—']
        lines.append('| ' + ' | '.join(values) + ' |')
    lines += ['', '| Districts | Pipeline seconds | Solver seconds | Direct assignment seconds | Export / validation seconds | Peak GiB |',
        '|---:|---:|---:|---:|---:|---:|']
    def seconds(value):
        return '—' if value is None else f'{value:,.3f}'
    for row in data['runs']:
        lines.append('| ' + ' | '.join([str(row['district_count']), *[seconds(row.get(key)) for key in ('pipeline_seconds', 'solve_seconds', 'direct_assignment_seconds', 'export_seconds')],
            f"{row['peak_process_working_set_bytes']/2**30:.3f}" if row.get('peak_process_working_set_bytes') else '—']) + ' |')
    for row in data['runs']:
        lines += ['', f"## {row['district_count']} districts", '']
        if not row['accepted_plan']:
            lines.append('No validated map. ' + row.get('failure', {}).get('error', 'Requires inspection.'))
            continue
        pop = row['population']
        lines.append('District populations: ' + ', '.join(f'{p:,}' for p in pop['district_populations']) + '.')
        if row['district_count'] == 1:
            lines.append('Every source block is assigned directly to the one district; optimization and center convergence are not applicable.')
        else:
            lines.append(row['outer_termination']['disclosure'])
            lines.append(f"All {row['optimizer_trace']['pass_count']} inner solves succeeded; maximum {row['optimizer_trace']['maximum_inner_iterations']} iterations against the 1,000-iteration cap.")
        payload = row['maps']['payloads']
        lines.append(f"Map geometry: national {payload['national_gzip_bytes']:,} gzip bytes; state {payload['state_gzip_bytes']:,}; full {payload['full_gzip_bytes']:,}; connections {payload['connections_gzip_bytes']:,}. County detail: {payload['all_county_working_gzip_bytes']:,} bytes in total, {payload['maximum_county_working_gzip_bytes']:,} at most for one county. Initial map plus links: {payload['default_map_and_links_gzip_bytes']:,} compressed geometry bytes, plus {payload['index_html_bytes']:,} HTML and {payload['manifest_json_bytes']:,} manifest bytes.")
        lines.append(f"All {row['maps']['compressed_payload_count']} compressed payloads, every source block, full district coverage, link ownership, and wrapped seam reconstruction independently verified.")
    lines += ['', f"Serial parent elapsed time: {data['timing']['parent_elapsed_seconds']:,.3f}s. Independent summary validation: {data['timing']['independent_summary_validation_seconds']:,.3f}s; this is not added to the measured plan runtime.", '',
        f"{data['preservation']['files_rehashed']} historical files rehashed unchanged. Prelaunch tests: {data['prelaunch_tests']['record']['passed']} passed. Summary-only tests: {data['summary_tests']['record']['passed']} passed.", '',
        data['validation_note'], '', 'Limits:', '', *['- ' + note for note in data['limits']], '',
        f'[Local comparison]({URL}) · [Machine-readable comparison]({URL}comparison.json)', '']
    return '\n'.join(lines)


def html(data: dict) -> str:
    quality, timing, details = [], [], []
    for row in data['runs']:
        k = row['district_count']
        if row['accepted_plan']:
            pop = row['population']
            quality.append([f'<a href="{escape(row["map_url"], quote=True)}">{k}-district map</a>', ', '.join(map(str, row['house_sizes'])),
                f'{pop["max_absolute_deviation_people"]:,.3f} people / {pop["max_absolute_deviation_percent"]:.6f}%',
                escape(str(pop['physical_part_components'])), escape(str(pop['policy_part_components']))])
            payload = row['maps']['payloads']
            convergence = 'Direct assignment; no optimizer.' if k == 1 else row['outer_termination']['disclosure'] + f" All {row['optimizer_trace']['pass_count']} inner solves succeeded; largest used {row['optimizer_trace']['maximum_inner_iterations']} / 1,000 iterations."
            details.append(f'<section><h2>{k} districts</h2><p>Populations: {", ".join(f"{p:,}" for p in pop["district_populations"])}.</p><p>{escape(convergence)}</p><p>Initial map + 49 links: {payload["default_map_and_links_gzip_bytes"]:,} compressed geometry bytes. State detail: {payload["state_gzip_bytes"]:,}; full: {payload["full_gzip_bytes"]:,}. County blocks load on demand: largest {payload["maximum_county_working_gzip_bytes"]:,} bytes; all counties {payload["all_county_working_gzip_bytes"]:,} bytes. HTML {payload["index_html_bytes"]:,} bytes and manifest {payload["manifest_json_bytes"]:,} bytes are separate.</p><p><a href="states/02/districts-{k}/maps/">Open verified map and water links</a></p></section>')
        else:
            quality.append([str(k), ', '.join(map(str, row['house_sizes'])), escape(row['status']), '—', '—'])
            details.append(f'<section><h2>{k} districts: no accepted map</h2><p>{escape(row.get("failure", {}).get("error", "Requires inspection."))}</p></section>')
        timing.append([str(k), *['—' if row.get(key) is None else f'{row[key]:,.3f}' for key in ('pipeline_seconds', 'solve_seconds', 'direct_assignment_seconds', 'export_seconds')],
            f'{row["peak_process_working_set_bytes"]/2**30:.3f}' if row.get('peak_process_working_set_bytes') else '—'])
    def table(headers, rows):
        return '<div class="scroll"><table><thead><tr>' + ''.join('<th>' + escape(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + c + '</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></div>'
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Alaska recorded-water benchmark</title><style>:root{color-scheme:dark;font:15px/1.6 system-ui;background:#0d1822;color:#e7edf4}body{margin:0}main{max-width:1180px;margin:auto;padding:28px}h1{font-size:32px}section{background:#142433;border:1px solid #304c62;padding:20px;margin:20px 0;border-radius:8px}a{color:#62dfed}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #304c62;vertical-align:top}.scroll{overflow:auto}.tag{color:#77dfba;text-transform:uppercase;letter-spacing:.12em;font-size:12px}a:focus-visible{outline:3px solid #f6cf72;outline-offset:3px}@media(max-width:700px){main{padding:14px}section{padding:12px}h1{font-size:26px}}</style><main><p class="tag">2020 census blocks · preserved source geometry</p><h1>Alaska recorded-water benchmark</h1>''' + f'<p>{escape(data["scope"])}</p><p>Status: {escape(data["status"])}. All {data["source"]["block_count"]:,} blocks and {data["source"]["population"]:,} residents retained.</p><p><a href="comparison.json">Verified comparison JSON</a> · <a href="run.json">Execution record</a> · <a href="../../diagnostics/alaska/">Preserved topology diagnosis</a></p><section><h2>Population and connectivity</h2>' + table(['Plan', 'House sizes', 'Maximum deviation', 'Physical components by district', 'Components with recorded links'], quality) + '</section><section><h2>Measured runtime and memory</h2>' + table(['Districts', 'Pipeline s', 'Solver s', 'Direct assignment s', 'Export/validation s', 'Peak GiB'], timing) + '<p>K1 is direct assignment. K2 uses the fixed optimizer. Strict originals stopped at antimeridian preflight and are not solved-plan baselines. These fresh processes ran serially.</p></section>' + ''.join(details) + f'<section><h2>Evidence and limits</h2><p>{data["preservation"]["files_rehashed"]} historical files independently rehashed unchanged. {data["prelaunch_tests"]["record"]["passed"]} prelaunch tests and {data["summary_tests"]["record"]["passed"]} summary-only tests passed.</p><p>{escape(data["validation_note"])}</p><ul>' + ''.join('<li>' + escape(note) + '</li>' for note in data['limits']) + '</ul></section></main></html>'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', required=True)
    args = parser.parse_args()
    data = summary(args.validation_note)
    encoded = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    for path in (OUTPUT / 'comparison.json', REPORT.with_suffix('.json')):
        path.write_text(encoded, encoding='utf-8')
    REPORT.with_suffix('.md').write_text(markdown(data), encoding='utf-8')
    (OUTPUT / 'index.html').write_text(html(data), encoding='utf-8')
    print(json.dumps({'status': data['status'], 'accepted_plans': [r['district_count'] for r in data['runs'] if r['accepted_plan']],
        'report': str(REPORT.with_suffix('.md')), 'url': URL,
        'validation_seconds': data['timing']['independent_summary_validation_seconds']}), flush=True)


if __name__ == '__main__':
    main()
