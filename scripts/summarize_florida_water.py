"""Independently verify Florida's four first water-policy attempts after exit.

This writer runs only after the serial launcher exits. Failed, unstarted and
ambiguous attempts never receive an accepted-map link in the comparison.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
from html import escape
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
from typing import Any
import zipfile

import shapefile
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.summarize_kentucky_exclave import (
    unique_pairs, read_json, sha256, verify_assignments, verify_compressed_maps, outer_termination,
)
from scripts.summarize_new_york_budget import finite, verify_trace
from scripts.state_block_execution_lock import state_execution_lock
from scripts.district_block_part_graph import _identity, _read_cache

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'policies/florida-water-v1'
SOURCE = ROOT / '.cache/state-block-benchmark/source/12/tl_2020_12_tabblock20.zip'
REPORT = ROOT / 'prompts/florida-water-benchmark'
URL = 'http://127.0.0.1:8770/policies/florida-water-v1/'
COUNTS = (28, 37, 45, 65)
ANCHORS = {28: 435, 37: 574, 45: 692, 65: 1000}
TOTAL, BLOCKS = 21_538_187, 390_066
SOURCE_SHA = 'ce5d7a02e47df17dadfa9c889edb6d35a89dfb520b8669bc4d302c2c0e100418'
POLICY = 'shared_edges_plus_recorded_water_connections'
PINNED_EVIDENCE_SHA256 = {
    'diagnosis.json': '194944247f3faea9f6fefd02fe90b576bb83a8a0edfc9d50232ac434ddc32e3a',
    'candidate-links.json': 'd08f371408f62e756d573b28a11ff1bce8a1c7ecd72fa8498de2268c6b2b736f',
    'geography-context.json': '50b003eb8f380bed1daac314ded547242cdddb000b19a2a8535fdacd598b0e4e',
}
ACCEPTED = 'complete_under_island_water_policy'
TERMINAL = ('complete', 'complete_with_numerical_failures', 'stopped')
WINDOWS = os.name == 'nt'


def verify_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get('status') not in TERMINAL or not manifest.get('finished_at'):
        raise ValueError('The anchor launcher is not terminal.')
    jobs = manifest.get('jobs', [])
    if len(jobs) != 4 or {job.get('district_count') for job in jobs} != set(COUNTS):
        raise ValueError('Expected exactly the four Florida jobs.')
    for job in jobs:
        if job.get('status') in (ACCEPTED, 'failed'):
            if not job.get('finished_at') or type(job.get('exit_code')) is not int:
                raise ValueError('A terminal child needs an exit code and finish time.')
            if (job['exit_code'] == 0) != (job['status'] == ACCEPTED):
                raise ValueError('Child exit code contradicts the recorded outcome.')
        elif manifest['status'] != 'stopped' or job.get('status') not in ('pending', 'needs_inspection'):
            raise ValueError('A nonterminal child remains in a purportedly completed suite.')
    complete = all(job['status'] == ACCEPTED for job in jobs)
    if manifest['status'] == 'complete' and not complete:
        raise ValueError('Complete suite contains an unaccepted plan.')
    if manifest['status'] == 'complete_with_numerical_failures' and (complete or any(job['status'] not in (ACCEPTED, 'failed') for job in jobs)):
        raise ValueError('Numerical-failure status contradicts the child outcomes.')


def recorded_process_ids(manifest: dict[str, Any], launch: dict[str, Any] | None = None) -> list[int]:
    """Use only recorded process identities; absence is never inferred from names."""
    if 'pid' not in manifest:
        raise ValueError('Launcher PID is missing from the execution record.')
    records = [manifest, *manifest['jobs']]
    if launch is not None:
        if (launch.get('script') != 'scripts/run_florida_water_suite.py'
                or launch.get('counts') != list(COUNTS) or launch.get('execution') != 'serial_fresh_processes'
                or Path(launch.get('output', '')).resolve() != OUTPUT.resolve()
                or 'launcher_pid' not in launch):
            raise ValueError('Top-level launch record does not identify this anchor batch.')
        records.append(launch)
    for job in manifest['jobs']:
        if job.get('status') != 'pending' and not any(name in job for name in ('pid', 'launcher_pid', 'child_pid')):
            raise ValueError('A launched child has no recorded PID.')
    values = [record[name] for record in records for name in ('pid', 'launcher_pid', 'child_pid') if name in record]
    if any(type(value) is not int or not 0 < value <= 2**31 - 1 for value in values):
        raise ValueError('Recorded process identities must be positive integer PIDs.')
    return sorted(set(values))


def windows_pid_status(pids: list[int]) -> list[dict[str, Any]]:
    # Get-Process -Id works without the denied Win32_Process CIM inventory.
    # Only the specific no-such-PID error means absent; every other error fails.
    command = (
        "$ErrorActionPreference='Stop'; $observed=@(); "
        "foreach ($recordedId in @(" + ','.join(str(pid) for pid in pids) + ")) { "
        "try { $observedProcess=Get-Process -Id $recordedId -ErrorAction Stop; "
        "$observedStart=$null; $observedPath=$null; "
        "try { $observedStart=$observedProcess.StartTime.ToUniversalTime().ToString('o') } catch {}; "
        "try { $observedPath=$observedProcess.Path } catch {}; "
        "$observed += @{pid=$recordedId;active=$true;process_name=$observedProcess.ProcessName;"
        "start_time_utc=$observedStart;executable_path=$observedPath} } "
        "catch { if ($_.FullyQualifiedErrorId -notlike 'NoProcessFoundForGivenId,*') { throw }; "
        "$observed += @{pid=$recordedId;active=$false} } }; "
        "ConvertTo-Json -Compress -InputObject @($observed)")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, check=True, timeout=30)
    if result.stderr.strip():
        raise ValueError('Recorded PID query produced an unexpected error.')
    rows = json.loads(result.stdout, object_pairs_hook=unique_pairs)
    if (not isinstance(rows, list) or len(rows) != len(pids)
            or any(not isinstance(row, dict) or type(row.get('pid')) is not int
                   or type(row.get('active')) is not bool
                   or set(row) != ({'pid', 'active', 'process_name', 'start_time_utc', 'executable_path'}
                                   if row.get('active') else {'pid', 'active'}) for row in rows)
            or sorted(row['pid'] for row in rows) != pids):
        raise ValueError('Recorded PID query did not account for every requested process.')
    return rows


def verified_reused_pid(observed: dict[str, Any], manifest: dict[str, Any],
                        launch: dict[str, Any] | None, observed_at: str) -> dict[str, Any]:
    """A PID is reusable; require a later, different image and a waited child exit.

    An image name alone is never sufficient. Missing Windows creation/path
    access, another Python process, or an unproved parent lifecycle fails closed.
    """
    pid = observed['pid']
    parent_pids = {manifest['pid']}
    if launch is not None:
        parent_pids.update(launch[name] for name in ('pid', 'launcher_pid', 'child_pid') if name in launch)
    if pid in parent_pids:
        raise ValueError(f'Recorded parent/launcher PID {pid} is still active; its exit is not independently proved.')
    jobs = [job for job in manifest['jobs'] if job.get('pid') == pid]
    if not jobs:
        raise ValueError(f'Active PID {pid} has no directly waited child lifecycle.')
    name, executable, started = (observed.get(key) for key in ('process_name', 'executable_path', 'start_time_utc'))
    if (any(not isinstance(value, str) or not value.strip() for value in (name, executable, started))
            or not PureWindowsPath(executable).is_absolute()
            or PureWindowsPath(executable).suffix.casefold() != '.exe'
            or PureWindowsPath(executable).stem.casefold() != name.casefold()
            or name.casefold().startswith(('python', 'pypy'))):
        raise ValueError(f'Active PID {pid} lacks an unambiguous different non-Python executable identity.')
    try:
        created = datetime.fromisoformat(started.replace('Z', '+00:00'))
        queried = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
    except (TypeError, ValueError) as error:
        raise ValueError('Process creation and observation timestamps must be valid ISO dates.') from error
    if created.utcoffset() is None or queried.utcoffset() is None or created > queried:
        raise ValueError('Process creation time must have a timezone and precede its live observation.')
    prior_jobs = []
    for job in jobs:
        validation = job.get('terminal_validation', {})
        command = job.get('command')
        if (job.get('status') not in (ACCEPTED, 'failed') or type(job.get('exit_code')) is not int
                or (job['exit_code'] == 0) != (job['status'] == ACCEPTED)
                or validation.get('passed') is not True
                or validation.get('classification') != ('validated_complete_plan' if job['status'] == ACCEPTED else 'verified_numerical_failure')
                or not isinstance(command, list) or not command or not isinstance(command[0], str)
                or not PureWindowsPath(command[0]).is_absolute()
                or not PureWindowsPath(command[0]).stem.casefold().startswith(('python', 'pypy'))
                or PureWindowsPath(command[0]) == PureWindowsPath(executable)):
            raise ValueError(f'Active PID {pid} has no validated exited Python child record.')
        try:
            finished = datetime.fromisoformat(job['finished_at'].replace('Z', '+00:00'))
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError('Recorded benchmark child finish timestamp is invalid.') from error
        if finished.utcoffset() is None or created <= finished:
            raise ValueError(f'Active PID {pid} was not created strictly after the recorded benchmark child exited.')
        prior_jobs.append({'district_count': job['district_count'], 'finished_at': job['finished_at'],
                           'exit_code': job['exit_code'], 'status': job['status'],
                           'command_executable': command[0], 'terminal_classification': validation['classification']})
    return {'pid': pid, 'classification': 'pid_reused_after_verified_benchmark_exit',
            'current_process_name': name, 'current_executable_path': executable,
            'current_start_time_utc': started, 'observed_at': observed_at, 'prior_benchmark_jobs': prior_jobs}


def verify_no_active_children(manifest: dict[str, Any], launch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check exact recorded PIDs and the state OS lock, not all system processes."""
    verify_manifest(manifest)
    pids = recorded_process_ids(manifest, launch)
    reused, observations = [], []
    observed_at = datetime.now(timezone.utc).isoformat()
    if WINDOWS:
        observations = windows_pid_status(pids)
        observed_at = datetime.now(timezone.utc).isoformat()
        active = [row['pid'] for row in observations if row['active']]
        reused = [verified_reused_pid(row, manifest, launch, observed_at) for row in observations if row['active']]
    else:
        active = []
        for pid in pids:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            active.append(pid)
    if active and not WINDOWS:
        raise ValueError(f'Recorded process PIDs are still active: {active}.')
    with state_execution_lock('12'):
        pass
    return {'recorded_pids_checked': pids, 'all_recorded_pids_absent': not active,
            'all_recorded_benchmark_processes_exited': True,
            'verified_reused_pids': reused, 'live_process_observations': observations,
            'live_process_observed_at': observed_at,
            'live_process_observations_sha256': hashlib.sha256(json.dumps(observations, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
            'florida_state_os_lock_acquired_and_released': True,
            'method': 'Get-Process -Id' if WINDOWS else 'os.kill(pid, 0)',
            'process_record_sources': ['run.json', 'launch-process.json'] if launch is not None else ['run.json'],
            'scope': 'Exact recorded parent/launcher/child PIDs plus the Florida process-owned OS lock. An active PID is excluded only with a different non-Python executable created strictly after its parent-recorded, validated child exit. No full-system command-line inventory or unrecorded-process absence is claimed.'}


def selected_report_path(job: dict[str, Any], directory: Path) -> Path:
    """Accept only the exact terminal report selected and hashed by the launcher."""
    validation = job.get('terminal_validation', {})
    if validation.get('passed') is not True:
        raise ValueError('Launcher did not validate this terminal child.')
    named = Path(validation.get('report_path', ''))
    allowed = {(directory / name).resolve() for name in ('benchmark.json', 'terminal-report.json')}
    candidates = {named.resolve()} if named.is_absolute() else {
        (base / named).resolve() for base in (directory, OUTPUT, ROOT)}
    matches = candidates & allowed
    if len(matches) != 1:
        raise ValueError('Unexpected authoritative terminal report location.')
    selected = matches.pop()
    expected = validation.get('benchmark_sha256')
    if not isinstance(expected, str) or sha256(selected) != expected:
        raise ValueError('Authoritative terminal report checksum changed.')
    return selected


def verify_configuration(configuration: dict[str, Any], k: int) -> None:
    if type(k) is not int or k not in COUNTS:
        raise ValueError('Unrequested district count.')
    expected = {'seed': 20200955, 'max_outer_iterations': 80, 'inner_max_iterations': 1000,
        'center_tolerance_m': 1e-4, 'max_rebalance_moves': 1000,
        'root_eligibility_relative_band': .01, 'group_population_preflight_tolerance': .01,
        'physical_adjacency_rule': 'polygon parts; disjoint interiors; positive-length shared boundary; F***1****',
        'connection_policy': 'population-aware-rooted-boundary-forest-v1',
        'connection_kinds': ['recorded-water-connection']}
    if any(configuration.get(key) != value for key, value in expected.items()):
        raise ValueError('Settings differ from the authorized Florida starting configuration.')
    optimization = configuration.get('inner_optimization', {})
    if (optimization.get('max_line_search_steps') != 100
            or optimization.get('failure_policy') != 'raise on unsuccessful termination or nonfinite output; no completed plan returned'
            or optimization.get('normalization') != 'population-mass and geometry-derived shifted squared costs; mean-zero weight gauge'):
        raise ValueError('Unexpected optimizer normalization, line search or failure policy.')
    threshold = Fraction(TOTAL * 99, 100 * k)
    if (configuration.get('minimum_district_population_exact') != str(threshold)
            or configuration.get('minimum_district_population_for_root_classification') != float(threshold)):
        raise ValueError('Root classification threshold does not match this anchor population.')


def source_populations() -> dict[str, int]:
    """Read original archive DBF, retaining source record order for part ownership."""
    if sha256(SOURCE) != SOURCE_SHA:
        raise ValueError('Florida source archive hash changed.')
    with zipfile.ZipFile(SOURCE) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith('.dbf')]
        if len(names) != 1:
            raise ValueError('Expected exactly one source DBF.')
        raw = archive.read(names[0])
    result: dict[str, int] = {}
    with shapefile.Reader(dbf=io.BytesIO(raw)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        geoid_col, pop_col = fields.index('GEOID20'), fields.index('POP20')
        for row in reader.iterRecords():
            geoid, value = str(row[geoid_col]), row[pop_col]
            if (geoid in result or len(geoid) != 15 or not geoid.isascii() or not geoid.isdigit()
                    or not geoid.startswith('12') or type(value) not in (int, float)
                    or not math.isfinite(value) or value < 0 or int(value) != value):
                raise ValueError('Invalid or duplicate Florida source record.')
            result[geoid] = int(value)
    if len(result) != BLOCKS or sum(result.values()) != TOTAL:
        raise ValueError('Source DBF differs from official population/block totals.')
    return result


def safe_child_path(directory: Path, name: str) -> Path:
    path = (directory / name).resolve()
    if path == directory.resolve() or not path.is_relative_to(directory.resolve()):
        raise ValueError('Artifact path escapes the expected directory.')
    return path


def verify_links(features: list[dict[str, Any]], records: list[dict[str, Any]],
                 assignments: dict[str, int]) -> list[dict[str, Any]]:
    if len(features) != 1 or len(records) != 1 or records[0]['id'] != 'fl-water-001':
        raise ValueError('Expected exactly the diagnosed Florida water connection.')
    feature, record = features[0], records[0]
    p = feature['properties']
    endpoint_districts = [assignments[endpoint['geoid']] for endpoint in record['endpoints']]
    used = endpoint_districts[0] if endpoint_districts[0] == endpoint_districts[1] else None
    if (p['id'] != record['id'] or p.get('state_fips') != '12'
            or feature['geometry']['type'] != 'LineString'
            or feature['geometry']['coordinates'] != [endpoint['coordinate'] for endpoint in record['endpoints']]
            or p['endpoints'] != record['endpoints'] or p['component_ids'] != record['component_ids']
            or p['distance_m'] != record['distance_m'] or p['endpoint_districts'] != endpoint_districts
            or p['used_by_district'] != used):
        raise ValueError('Exported water geometry or endpoint ownership disagrees with assignments.')
    return [{'id': p['id'], 'component_ids': p['component_ids'], 'distance_m': p['distance_m'],
             'endpoint_districts': endpoint_districts, 'used_by_district': used,
             'endpoint_geoids': [endpoint['geoid'] for endpoint in record['endpoints']]}]


def independent_component_counts(adjacency: Any, owners: Any, labels: list[int],
                                 k: int, links: Any = ()) -> list[int]:
    """A separate traversal: ownership sets labels but never creates an edge."""
    if any(type(label) is not int or not 0 <= label < k for label in labels):
        raise ValueError('Invalid district labels for independent graph traversal.')
    additions: dict[int, list[int]] = {}
    for a, b in links:
        if not 0 <= a < len(owners) or not 0 <= b < len(owners) or a == b:
            raise ValueError('Invalid recorded part endpoints.')
        additions.setdefault(a, []).append(b)
        additions.setdefault(b, []).append(a)
    seen, counts = bytearray(len(owners)), [0] * k
    for node in range(len(owners)):
        if seen[node]:
            continue
        district = labels[owners[node]]
        counts[district] += 1
        seen[node] = 1
        queue = [node]
        while queue:
            current = queue.pop()
            for neighbor in (*adjacency[current], *additions.get(current, ())):
                if not seen[neighbor] and labels[owners[neighbor]] == district:
                    seen[neighbor] = 1
                    queue.append(neighbor)
    return counts


def verify_final_graph(report: dict[str, Any], assignments: dict[str, int],
                       populations: dict[str, int], k: int) -> dict[str, Any]:
    geoids = list(populations)
    cache = report['physical_part_graph_cache']
    directory = ROOT / '.cache/state-block-benchmark/graph-cache/12'
    path = Path(cache['path']).resolve()
    if not path.is_relative_to(directory.resolve()) or path.suffix != '.npz':
        raise ValueError('Unexpected physical part-cache location.')
    identity = _identity(geoids, SOURCE_SHA)
    if cache['identity'] != identity:
        raise ValueError('Physical graph identity differs from verified source/code/environment.')
    # The read-only loader validates every array and payload SHA. Never rebuild.
    graph, metadata = _read_cache(path, identity)
    if metadata != report['physical_part_graph']:
        raise ValueError('Cached part graph differs from the measured source graph.')
    edges = []
    for link in report['water_connections']:
        nodes = []
        for endpoint in link['endpoints']:
            node = endpoint['part_node']
            if (type(node) is not int or not 0 <= node < len(graph.part_to_unit)
                    or geoids[graph.part_to_unit[node]] != endpoint['geoid']
                    or node != bisect_left(graph.part_to_unit, graph.part_to_unit[node]) + endpoint['part_index']):
                raise ValueError('Recorded part-node owner differs from the source graph.')
            nodes.append(node)
        edges.append(tuple(nodes))
    labels = [assignments[geoid] for geoid in geoids]
    physical = independent_component_counts(graph.adjacency, graph.part_to_unit, labels, k)
    augmented = independent_component_counts(graph.adjacency, graph.part_to_unit, labels, k, edges)
    if (physical != report['final_plan']['physical_part_components']
            or augmented != [1] * k or augmented != report['final_plan']['policy_part_components']):
        raise ValueError('Independent final part-graph traversal disagrees with the reported plan.')
    return {'physical_components': physical, 'policy_components': augmented,
            'cache_path': path.relative_to(ROOT).as_posix(), 'cache_sha256': sha256(path),
            'method': 'Read-only validated source part cache; independent per-district traversal; whole-block ownership creates no edge.'}


def verify_saved_polygon_links(full_features: list[dict[str, Any]], report: dict[str, Any],
                               assignments: dict[str, int], populations: dict[str, int], k: int) -> dict[str, Any]:
    """Recheck exact endpoint source parts against saved unsimplified polygons."""
    polygons = {}
    for feature in full_features:
        district = feature['properties']['district_id']
        geometry = shape(feature['geometry'])
        if (district in polygons or geometry.geom_type not in ('Polygon', 'MultiPolygon')
                or not geometry.is_valid or geometry.is_empty):
            raise ValueError('Invalid or duplicate full district polygon.')
        polygons[district] = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
    if set(polygons) != set(range(k)):
        raise ValueError('Full district polygon identifiers differ from this plan.')
    physical = [len(polygons[district]) for district in range(k)]
    if physical != report['final_plan']['physical_part_components']:
        raise ValueError('Actual full-polygon component counts disagree with the part graph.')
    source = SOURCE.parent / SOURCE.stem / (SOURCE.stem + '.shp')
    hashes = report['source']['extracted_file_sha256']
    for suffix in ('.shp', '.shx', '.dbf'):
        path = source.with_suffix(suffix)
        if sha256(path) != hashes[path.name]:
            raise ValueError('Extracted source geometry changed before endpoint verification.')
    record_indices = {geoid: index for index, geoid in enumerate(populations)}
    parents = [list(range(count)) for count in physical]
    def find(district: int, node: int) -> int:
        while parents[district][node] != node:
            node = parents[district][node]
        return node
    with shapefile.Reader(str(source)) as reader:
        for link in report['water_connections']:
            endpoint_components = []
            for endpoint in link['endpoints']:
                geoid = endpoint['geoid']
                raw = reader.shapeRecord(record_indices[geoid])
                if str(raw.record['GEOID20']) != geoid:
                    raise ValueError('Source endpoint record differs from DBF order.')
                geometry = shape(raw.shape.__geo_interface__)
                parts = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
                part_index = endpoint['part_index']
                if type(part_index) is not int or not 0 <= part_index < len(parts):
                    raise ValueError('Invalid endpoint source part index.')
                part = parts[part_index]
                coordinate = tuple(endpoint['coordinate'])
                if not any(coordinate == tuple(vertex) for ring in [part.exterior, *part.interiors] for vertex in ring.coords):
                    raise ValueError('Connection endpoint is not the exact original source vertex.')
                district = assignments[geoid]
                containers = [i for i, polygon in enumerate(polygons[district]) if polygon.covers(part)]
                if len(containers) != 1:
                    raise ValueError('Endpoint source part does not lie in exactly one full district component.')
                endpoint_components.append((district, containers[0]))
            (da, a), (db, b) = endpoint_components
            if da == db:
                parents[da][find(da, a)] = find(da, b)
    policy = [len({find(district, node) for node in range(len(parts))}) for district, parts in enumerate(parents)]
    if policy != [1] * k:
        raise ValueError('Saved full district polygons are not connected under their eligible water link.')
    return {'physical_components': physical, 'policy_components': policy,
            'exact_source_endpoint_vertices_verified': True,
            'source_coverage_equality': 'Independently certified by the preserved exporter audit; not recomputed by this summary.'}


def verify_assignment_provenance(saved: dict[str, Any], report: dict[str, Any]) -> None:
    expected = {'source_sha256': report['source']['archive_sha256'], 'code_sha256': report['code_sha256'],
                'configuration': report['configuration'],
                'water_connections_sha256': report['artifact_sha256']['water-connections.json']}
    if saved.get('provenance') != expected:
        raise ValueError('Assignment provenance differs from the source, code, settings or recorded water artifact.')


def verify_postprocessing(saved: dict[str, Any], report: dict[str, Any]) -> None:
    verify_assignment_provenance(saved, report)
    post = report['postprocessing']
    limit = report['configuration']['max_rebalance_moves']
    if post['stop_reason'] not in ('local_optimum', 'max_moves') or saved['stop_reason'] != post['stop_reason']:
        raise ValueError('Postprocessing termination differs from the saved move audit.')
    for kind in ('repair', 'part_repair', 'rebalance'):
        if type(post[kind + '_move_count']) is not int or post[kind + '_move_count'] != len(saved[kind + '_moves']):
            raise ValueError('Postprocessing move count differs from its saved audit.')
    moves = post['rebalance_move_count']
    if not 0 <= moves <= limit or post['stop_reason'] == 'max_moves' and moves != limit:
        raise ValueError('Postprocessing budget and termination are contradictory.')


def verify_plan(directory: Path, report: dict[str, Any], populations: dict[str, int], k: int) -> dict[str, Any]:
    if report['status'] == 'failed':
        return {'accepted_plan': False, 'failure': {'phase': report.get('failed_phase'),
                'error': report.get('error'), 'optimizer': report.get('optimizer_failure')}}
    if report['status'] != ACCEPTED:
        raise ValueError('Benchmark is not a terminal accepted or failed attempt.')
    stages = {}
    for stage, filename in (('initial', 'initial-solver-result.json'), ('after_repair', 'after-repair-result.json'), ('final', 'solver-result.json')):
        saved = read_json(directory / filename)
        stages[stage] = verify_assignments(saved['assignments'], populations, k, report[stage + '_plan'])
        verify_assignment_provenance(saved, report)
    final = report['final_plan']
    if final['policy_part_components'] != [1] * k or final['all_districts_policy_connected'] is not True:
        raise ValueError('Part graph connectivity failed.')
    assignments = read_json(directory / 'solver-result.json')['assignments']
    verify_postprocessing(read_json(directory / 'move-audit.json'), report)
    graph_check = verify_final_graph(report, assignments, populations, k)
    manifest = read_json(directory / 'maps/map-manifest.json')
    if manifest != report['maps']:
        raise ValueError('Map manifest differs from the measured report.')
    audit = manifest['connectivity_validation']
    if (audit['policy'] != POLICY or audit['passed'] is not True
            or audit['source_coverage_preserved_exactly'] is not True or audit['source_geometry_modified'] is not False
            or [row['district_id'] for row in audit['districts']] != list(range(k))
            or any(row['connected_components_after_links'] != 1 for row in audit['districts'])
            or [row['physical_polygon_components'] for row in audit['districts']] != final['physical_part_components']):
        raise ValueError('Independent polygon-plus-link connectivity disagrees with the graph audit.')
    for item in manifest['storage']['artifacts']:
        safe_child_path(directory / 'maps', item['gzip_path'])
    map_count = verify_compressed_maps(directory, manifest)
    for level in ('national', 'state', 'full'):
        features = json.loads(gzip.decompress((directory / f'maps/districts-{level}.geojson.gz').read_bytes()))['features']
        props = sorted((f['properties'] for f in features), key=lambda row: row['district_id'])
        if ([p['district_id'] for p in props] != list(range(k))
                or [p['population'] for p in props] != stages['final']['district_populations']
                or [p['block_count'] for p in props] != stages['final']['district_block_counts']):
            raise ValueError('Map district attributes disagree with source-DBF assignment totals.')
        if level == 'full':
            polygon_check = verify_saved_polygon_links(features, report, assignments, populations, k)
    features = json.loads(gzip.decompress((directory / 'maps/water-connections.geojson.gz').read_bytes()))['features']
    links = verify_links(features, report['water_connections'], assignments)
    if {row['id'] for row in links if row['used_by_district'] is not None} != set(audit['used_link_ids']):
        raise ValueError('Used water edges differ between endpoint assignments and polygon validation.')
    values = stages['final']['district_populations']
    return {'accepted_plan': True, 'independent_population_checks': stages,
            'independent_final_graph_check': graph_check, 'saved_full_polygon_recheck': polygon_check,
            'population_min': min(values), 'population_max': max(values),
            'fractional_ideal_population': TOTAL / k, 'connectivity': audit,
            'physical_polygon_components': final['physical_part_components'], 'links': links,
            'compressed_maps_verified': map_count, 'map_payloads': manifest['load_scenarios'],
            'water_link_payload': manifest['water_connections'],
            'postprocessing': report['postprocessing'],
            'outer_termination': outer_termination(report['solver'], report['configuration'])}


def verify_report_identity(report: dict[str, Any], k: int) -> None:
    if (report.get('state_fips') != '12' or report.get('district_count') != k
            or report.get('policy') != POLICY or report.get('house_sizes') != [ANCHORS[k]]
            or report.get('status') not in (ACCEPTED, 'failed') or not report.get('finished_at')
            or report.get('active_phase') is not None):
        raise ValueError('Unexpected or nonterminal Florida anchor report.')
    verify_configuration(report['configuration'], k)
    config_sha = hashlib.sha256(json.dumps(report['configuration'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if report.get('configuration_sha256') != config_sha:
        raise ValueError('Configuration checksum changed.')
    if report['source']['archive_sha256'] != SOURCE_SHA:
        raise ValueError('Source identity changed.')


def verify_target_policy(report: dict[str, Any], k: int) -> None:
    audit = report['island_policy_audit']
    selection = audit['population_selection']
    groups = selection['groups']
    if (audit['district_count'] != k or selection['district_count'] != k
            or selection['ideal_population'] != TOTAL / k
            or selection['minimum_root_population'] != float(Fraction(TOTAL * 99, 100 * k))
            or selection['eligible_root_component_ids'] != [0]
            or selection['selected_link_ids'] != ['fl-candidate-00-01']
            or len(groups) != 1 or groups[0]['district_count'] != k
            or groups[0]['component_ids'] != [0, 1] or groups[0]['population'] != TOTAL
            or audit['source_population'] != TOTAL or audit['block_count'] != BLOCKS
            or audit['physical_component_count'] != 2 or audit['part_count'] != 390182
            or audit['augmented_component_count'] != 1 or audit['synthetic_edge_count'] != 1
            or audit['source_geometry_modified'] is not False
            or audit['augmented_graph_connected'] is not True or audit['all_source_parts_reached'] is not True):
        raise ValueError('Population-aware policy audit does not match the target anchor.')
    if audit.get('target_selection_verified_against_diagnosis') is not True:
        raise ValueError('Target policy was not verified against the preserved Florida diagnosis.')
    links = report['water_connections']
    if (len(links) != 1 or links[0]['id'] != 'fl-water-001'
            or links[0]['candidate_id'] != 'fl-candidate-00-01'
            or links[0]['state_fips'] != '12' or links[0]['kind'] != 'recorded-water-connection'
            or links[0]['component_ids'] != [0, 1]):
        raise ValueError('Unexpected Florida water connection identity.')
    candidates = read_json(SUITE / 'diagnostics/florida/candidate-links.json')
    if len(candidates) != 1 or any(links[0][key] != candidates[0][key] for key in ('component_ids', 'distance_m', 'endpoints')):
        raise ValueError('Water connection endpoints or distance differ from the preserved diagnosis.')
    evidence = links[0]['provenance']['diagnostic_evidence_sha256']
    if evidence != PINNED_EVIDENCE_SHA256:
        raise ValueError('Link diagnostic evidence differs from the three immutable pinned sources.')
    for name, digest in evidence.items():
        path = safe_child_path(SUITE / 'diagnostics/florida', name)
        if sha256(path) != digest:
            raise ValueError('Pinned geographic or topology evidence changed.')
    diagnosis = read_json(SUITE / 'diagnostics/florida/diagnosis.json')
    plans = [plan for plan in diagnosis['plans'] if plan['district_count'] == k]
    if (len(plans) != 1 or plans[0]['policy'] != selection
            or plans[0]['policy_population_bound'] != selection['population_bound']
            or plans[0]['augmented_component_count'] != 1):
        raise ValueError('Complete population-aware audit differs from the preserved actual-count diagnosis.')


def checked_trace(directory: Path, report: dict[str, Any], k: int) -> dict[str, Any] | None:
    if not report.get('optimizer_trace', {}).get('passes'):
        if report['status'] == ACCEPTED:
            raise ValueError('Accepted plan has no successful optimizer trace.')
        return None
    rows = [json.loads(line, object_pairs_hook=unique_pairs) for line in (directory / 'optimizer-trace.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    result = verify_trace(rows, report['optimizer_trace'], k=k, total=TOTAL)
    for entry in report['optimizer_trace']['passes']:
        options = entry['actual_options']
        if options != {'maxiter': 1000, 'gtol': 1e-6 / TOTAL, 'ftol': 1e-12, 'maxls': 100}:
            raise ValueError('Observed optimizer options changed.')
    if report['status'] == ACCEPTED and (not result['all_inner_passes_succeeded']
            or result['pass_count'] != report['solver']['outer_iterations'] + 1
            or report['solver']['all_inner_optimizer_passes_succeeded'] is not True):
        raise ValueError('Accepted plan has incomplete or failed inner passes.')
    # Retain an inspectable pass summary without embedding every gradient sample
    # in the comparison page; the full trace remains in its immutable artifact.
    for row in result['passes']:
        for key in ('samples', 'at_original_budget', 'objective_improvement_after_original_budget', 'max_deviation_people_at_original_budget'):
            row.pop(key, None)
    result['maximum_inner_iterations'] = max(p['optimizer']['iterations'] for p in result['passes'])
    return result


def verify_failure(report: dict[str, Any], exit_code: int) -> None:
    passes = report.get('solver_progress', [])
    failure = report.get('optimizer_failure', {})
    if (exit_code == 0 or report.get('failed_phase') != 'solve'
            or not str(report.get('error', '')).startswith('DistrictingOptimizationError:')
            or failure.get('plan_returned') is not False or not passes
            or failure.get('balance_pass') != len(passes) or 'final_plan' in report or 'maps' in report):
        raise ValueError('Attempt is not a verified numerical failure.')
    last = passes[-1]['inner_optimizer']
    if (last['success'] is not False
            or any(failure.get(key) != last[key] for key in ('iterations', 'function_evaluations', 'status', 'message'))
            or not all(row['inner_optimizer']['success'] is True for row in passes[:-1])):
        raise ValueError('Numerical failure evidence contradicts the observed optimizer passes.')


def load_run(k: int, populations: dict[str, int], *, job: dict[str, Any],
             manifest: dict[str, Any]) -> dict[str, Any]:
    directory = OUTPUT / f'states/12/districts-{k}'
    if job['status'] in ('pending', 'needs_inspection'):
        return {'district_count': k, 'house_size': ANCHORS[k], 'status': job['status'],
                'accepted_plan': False, 'failure': {'error': job.get('error') or manifest.get('error') or 'No independently accepted terminal plan.'},
                'map_url': None}
    path = selected_report_path(job, directory)
    report = read_json(path)
    verify_report_identity(report, k)
    verify_target_policy(report, k)
    progress = read_json(directory / 'progress.json')
    validation = job['terminal_validation']
    expected_class = 'validated_complete_plan' if report['status'] == ACCEPTED else 'verified_numerical_failure'
    if (job['status'] != report['status'] or validation.get('classification') != expected_class
            or validation.get('progress_sha256') != sha256(directory / 'progress.json')
            or report.get('final_progress_snapshot_written') is not True
            or report.get('run_kind') != 'florida_population_aware_water_v1'
            or progress.get('solver_progress') != report['solver_progress']
            or progress.get('status') != report['status'] or progress.get('active_phase') is not None
            or progress.get('district_count') != k):
        raise ValueError('Launcher, terminal report and final progress validation disagree.')
    if path.name == 'terminal-report.json' and (report.get('authoritative_terminal_report') != 'terminal-report.json'
            or not report.get('terminal_report_write_error')):
        raise ValueError('Fallback report is not explicitly authoritative.')
    if report['comparison_baseline'] != manifest['strict_preflight_baselines'][str(k)]:
        raise ValueError('Child changed its original strict preflight reference.')
    if report['environment'] != manifest['environment'] or report['code_sha256'] != manifest['code_sha256']:
        raise ValueError('Child numerical environment or code differs from its parent.')
    duration = finite(report['timed_pipeline_wall_seconds'], 'pipeline duration')
    child_time = finite(job['process_wall_seconds'], 'child elapsed time')
    peak = report['peak_process_working_set_bytes']
    if duration < 0 or child_time < duration or type(peak) is not int or peak <= 0:
        raise ValueError('Child duration or peak memory measurement is invalid.')
    for phase in report['phases'].values():
        if finite(phase['wall_seconds'], 'phase duration') < 0:
            raise ValueError('Negative phase time.')
    flags = ['all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
             'national_suite_byte_identical', 'source_archive_byte_identical', 'run_code_unchanged']
    if any(report['preservation_audit'].get(key) is not True for key in flags) or report.get('preservation_error'):
        raise ValueError('Runner did not pass the historical preservation audit.')
    for relative, digest in report['code_sha256'].items():
        if sha256(safe_child_path(ROOT, relative)) != digest:
            raise ValueError(f'Frozen runtime changed: {relative}')
    hashes = report['artifact_sha256']
    required = {'water-connections.json', 'optimizer-trace.jsonl'}
    if report['status'] == ACCEPTED:
        required |= {'initial-solver-result.json', 'after-repair-result.json', 'solver-result.json',
                     'move-audit.json', 'maps/map-manifest.json', 'index.html'}
    if not required <= set(hashes):
        raise ValueError('Required accepted-plan or failure artifacts lack checksums.')
    for relative, digest in hashes.items():
        if sha256(safe_child_path(directory, relative)) != digest:
            raise ValueError(f'Saved benchmark artifact changed: K{k}/{relative}')
    saved_links = read_json(directory / 'water-connections.json')
    if saved_links != {'policy': POLICY, 'connections': report['water_connections'], 'source_sha256': SOURCE_SHA}:
        raise ValueError('Saved water record differs from the measured report.')
    if report['status'] == 'failed':
        verify_failure(report, job['exit_code'])
    plan = verify_plan(directory, report, populations, k)
    trace = checked_trace(directory, report, k)
    return {'district_count': k, 'house_size': ANCHORS[k], 'status': report['status'],
            'benchmark_path': path.relative_to(ROOT).as_posix(), 'benchmark_sha256': sha256(path),
            'code_sha256': report['code_sha256'], 'source_sha256': report['source']['archive_sha256'],
            'configuration': report['configuration'], 'environment': report['environment'],
            'comparison_baseline': report['comparison_baseline'],
            'pipeline_seconds': duration, 'process_wall_seconds': child_time, 'phases': report['phases'],
            'solve_seconds': report['phases'].get('solve', {}).get('wall_seconds'),
            'export_seconds': report['phases'].get('independent_polygon_validation_and_map_export', {}).get('wall_seconds'),
            'peak_process_working_set_bytes': peak, 'trace': trace,
            'water_connections': report['water_connections'], 'water_connections_sha256': sha256(directory / 'water-connections.json'),
            'island_policy_audit': report['island_policy_audit'], 'preservation_audit': report['preservation_audit'],
            'preservation_inventory': read_json(directory / 'preserved-file-inventory.json'),
            'map_url': URL + f'states/12/districts-{k}/' if plan['accepted_plan'] else None, **plan}


def execution_timing(manifest: dict[str, Any]) -> dict[str, float]:
    values = {key: finite(manifest[key], key) for key in (
        'preparation_wall_seconds', 'serial_child_process_wall_seconds', 'elapsed_wall_seconds')}
    if any(value < 0 for value in values.values()):
        raise ValueError('Execution durations must be nonnegative.')
    child_total = sum(finite(job.get('process_wall_seconds', 0), 'child elapsed time') for job in manifest['jobs'])
    if (abs(child_total - values['serial_child_process_wall_seconds']) > 1e-6
            or values['elapsed_wall_seconds'] + 1e-6 < child_total + values['preparation_wall_seconds']):
        raise ValueError('Serial child and preparation timing does not reconcile with launcher elapsed time.')
    return values


def verify_prelaunch_tests(record: dict[str, Any], started_at: str) -> dict[str, Any]:
    """Validate the original count-based test record without rewriting it."""
    if (record.get('phase') not in ('prelaunch', 'before launch')
            or record.get('status') not in (None, 'passed')
            or type(record.get('passed')) is not int or record['passed'] <= 0
            or type(record.get('failed')) is not int or record['failed'] != 0
            or not isinstance(record.get('command'), str) or not record['command'].strip()):
        raise ValueError('Saved prelaunch test counts or outcome are invalid.')
    elapsed = finite(record.get('elapsed_seconds'), 'prelaunch test elapsed time')
    if elapsed < 0:
        raise ValueError('Prelaunch test elapsed time must be nonnegative.')
    try:
        recorded = datetime.fromisoformat(record['recorded_at'].replace('Z', '+00:00'))
        launched = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError('Prelaunch test and launch timestamps must be valid ISO dates.') from error
    if recorded.utcoffset() is None or launched.utcoffset() is None or recorded > launched:
        raise ValueError('Test evidence must have a timezone and precede the batch launch.')
    return {'passed': record['passed'], 'failed': 0, 'recorded_before_launch': True,
            'recorded_at': record['recorded_at'], 'launch_started_at': started_at,
            'elapsed_seconds': elapsed}


def verify_preservation(manifest: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    path = OUTPUT / 'preserved-file-inventory.json'
    inventory = read_json(path)
    if sha256(path) != manifest['preserved_file_inventory_sha256'] or len(inventory) != manifest['protected_file_count']:
        raise ValueError('Launcher preservation inventory changed.')
    required = {p.relative_to(ROOT).as_posix() for tree in (SUITE / 'states/12', SUITE / 'diagnostics/florida')
                for p in tree.rglob('*') if p.is_file()}
    required.update(p.relative_to(ROOT).as_posix() for p in (
        SOURCE, SUITE / 'suite.json', ROOT / 'prompts/florida-topology-diagnosis.json'))
    if set(inventory) != required:
        raise ValueError('Preservation inventory differs from the entire original strict and diagnostic evidence.')
    for row in runs:
        child_inventory = row.get('preservation_inventory')
        if child_inventory is not None and (child_inventory != inventory
                or row['preservation_audit']['protected_file_count'] != len(inventory)):
            raise ValueError('Child and launcher historical inventories differ.')
    for name, digest in inventory.items():
        if sha256(safe_child_path(ROOT, name)) != digest:
            raise ValueError(f'Historical evidence changed: {name}')
    return {'files_rehashed': len(inventory), 'all_byte_identical': True,
            'strict_and_diagnostic_trees_preserved': True}


def verify_baselines(manifest: dict[str, Any]) -> dict[str, Any]:
    original = read_json(SUITE / 'states/12/districts-28/benchmark.json')
    national = read_json(SUITE / 'suite.json')
    states = [state for state in national['states'] if state['state_fips'] == '12']
    if (len(states) != 1 or original.get('status') != 'unsupported_topology'
            or original.get('solver_progress') or original.get('state_fips') != '12'
            or original.get('district_count') != 28 or original['source']['archive_sha256'] != SOURCE_SHA):
        raise ValueError('Original strict Florida preflight identity changed.')
    jobs = {job['district_count']: job for job in states[0]['jobs']}
    records = manifest['strict_preflight_baselines']
    if set(records) != {str(k) for k in COUNTS}:
        raise ValueError('Expected a strict preflight reference for every target count.')
    for k in COUNTS:
        record, job = records[str(k)], jobs[k]
        reference_key = 'report' if k == 28 else 'topology_report'
        if (job['status'] != 'unsupported_topology' or job.get(reference_key) != 'states/12/districts-28/benchmark.json'
                or record['strict_suite_job'] != job or record['strict_status'] != 'unsupported_topology'
                or record['strict_solver_ran'] is not False or record['strict_preflight_reused'] is not (k != 28)
                or record['controlled_inner_budget_comparison'] is not False
                or record['source_archive_sha256'] != SOURCE_SHA
                or record['strict_report_path'] != (SUITE / 'states/12/districts-28/benchmark.json').relative_to(ROOT).as_posix()
                or record['strict_report_sha256'] != sha256(SUITE / 'states/12/districts-28/benchmark.json')
                or record['strict_suite_sha256'] != sha256(SUITE / 'suite.json')
                or record['strict_pipeline_wall_seconds'] != original['timed_pipeline_wall_seconds']):
            raise ValueError('Strict topology exception was changed or misrepresented as a solved baseline.')
    return {'status': original['status'], 'solver_was_run': False,
            'pipeline_seconds': original['timed_pipeline_wall_seconds'],
            'peak_process_working_set_bytes': original['peak_process_working_set_bytes'],
            'physical_source_components': original['graph']['component_count'],
            'references_by_district_count': records,
            'meaning': 'One preserved K28 source-topology preflight; reused by the other three original anchors. No final plan or population-balance baseline.'}


def verify_summary_tests(record: dict[str, Any]) -> None:
    expected = {'scripts/summarize_florida_water.py', 'scripts/tests/test_summarize_florida_water.py'}
    if (record.get('status') != 'passed' or type(record.get('passed')) is not int or record['passed'] <= 0
            or type(record.get('failed')) is not int or record['failed'] != 0
            or set(record.get('source_sha256', {})) != expected
            or not isinstance(record.get('command'), str) or not record['command'].strip()
            or finite(record.get('elapsed_seconds'), 'summary test duration') < 0
            or any(sha256(ROOT / name) != digest for name, digest in record['source_sha256'].items())):
        raise ValueError('Summary validation record is invalid or its tested source changed.')


def summary(validation_note: str = '') -> dict[str, Any]:
    manifest = read_json(OUTPUT / 'run.json')
    verify_manifest(manifest)
    launch_path = OUTPUT / 'launch-process.json'
    launch_record = read_json(launch_path)
    execution_verification = verify_no_active_children(manifest, launch_record)
    execution_verification['launch_process_record_sha256'] = sha256(launch_path)
    test_path, summary_test_path = OUTPUT / 'validation-tests.json', OUTPUT / 'summary-validation-tests.json'
    test_record, summary_tests = read_json(test_path), read_json(summary_test_path)
    prelaunch_validation = verify_prelaunch_tests(test_record, launch_record['started_at'])
    if test_record.get('source_sha256') != manifest['code_sha256']:
        raise ValueError('Prelaunch tested runtime differs from the launched frozen code.')
    verify_summary_tests(summary_tests)
    baseline = verify_baselines(manifest)
    populations = source_populations()
    jobs = {job['district_count']: job for job in manifest['jobs']}
    runs = [load_run(k, populations, job=jobs[k], manifest=manifest) for k in COUNTS]
    measured = [run for run in runs if 'benchmark_path' in run]
    if measured and (len({row['water_connections_sha256'] for row in measured}) != 1
            or any(row['water_connections'] != measured[0]['water_connections'] for row in measured)):
        raise ValueError('The recorded water connection changed across Florida counts.')
    preservation = verify_preservation(manifest, runs)
    timing = execution_timing(manifest)
    for row in runs:
        row.pop('preservation_inventory', None)
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Florida K28/K37/K45/K65 for House 435/574/692/1000: first census-block solves with the population-aware recorded water policy and 1,000 inner iterations.',
            'status': manifest['status'], 'runs': runs, 'strict_preflight': baseline,
            'accepted_plan_count': sum(row['accepted_plan'] for row in runs),
            'verified_numerical_failure_count': sum(row['status'] == 'failed' for row in runs),
            'unaccepted_or_unstarted_count': sum(row['status'] in ('pending', 'needs_inspection') for row in runs),
            'execution': manifest, 'execution_verification': execution_verification,
            'stop_error': manifest.get('error'),
            'execution_timing': timing, 'preservation': preservation, 'validation_note': validation_note,
            'same_water_connection_across_measured_counts': bool(measured),
            'prelaunch_tests': {'path': test_path.relative_to(ROOT).as_posix(), 'sha256': sha256(test_path),
                               'record': test_record, 'verification': prelaunch_validation},
            'summary_validation_tests': {'path': summary_test_path.relative_to(ROOT).as_posix(),
                                         'sha256': sha256(summary_test_path), 'record': summary_tests},
            'limitations': [
                'All four targets are first water-policy attempts, run serially; the preserved strict source-topology exception did not solve a plan. This is not a controlled 300-versus-1000 iteration experiment.',
                'Successful inner solves, outer center convergence, final population balance and connectivity under recorded water links are separate outcomes.',
                'Physical polygons remain unchanged. The water connection counts only when both endpoint blocks belong to the same district; multipart ownership never creates a geometric edge.',
                'The single connection joins water-inclusive census coverage in the Dry Tortugas region to main Florida coverage. Its endpoints are not shorelines, a bridge, or a ferry route; official regional attribution is not a global high-resolution shoreline certificate.',
                'The 1% group/root preflight guides link selection; it is not a final population-balance acceptance guarantee. Local rebalancing does not establish a global optimum.',
                'Population and final part-graph traversals were recomputed; full saved polygon components and source endpoint ownership were rechecked. Statewide source-coverage equality reuses the preserved independent exporter audit.',
                'Objective improvement is comparable within each inner pass only. Trace populations are intermediate point assignments before whole-block connectivity repair.',
                'Wall timings include tracing and shared-desktop contention; peak memory is per-process OS peak working set; gzip file sizes do not measure browser memory or network latency.',
            ]}


def display_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data['runs']


def minutes(value: float | None) -> str:
    return '—' if value is None else f'{value / 60:.2f}'


def quality_cells(row: dict[str, Any]) -> list[str]:
    if not row['accepted_plan']:
        return [str(row['district_count']), row['status'], 'No accepted plan', '—', '—', '—']
    pop = row['independent_population_checks']['final']
    physical = sum(value == 1 for value in row['physical_polygon_components'])
    return [str(row['district_count']),
            f'{pop["max_absolute_deviation_people"]:.3f} people / {pop["max_absolute_deviation_percent"]:.6f}%',
            f'{row["population_min"]:,}–{row["population_max"]:,}', f'{row["district_count"]}/{row["district_count"]}',
            f'{physical}/{row["district_count"]}', str(row['trace']['maximum_inner_iterations'])]


def markdown(data: dict[str, Any]) -> str:
    lines = ['# Florida water-policy benchmark', '', data['scope'], '',
             f'Outcome: **{data["status"]}**. {data["preservation"]["files_rehashed"]} historical files independently rehashed and unchanged.',
             ('Queue stop: ' + str(data['stop_error'])) if data.get('stop_error') else '', '',
             '| Districts | Final maximum deviation | Population range | Policy connected | Physically connected | Largest inner pass |',
             '|---|---:|---:|---:|---:|---:|']
    for row in display_rows(data):
        lines.append('| ' + ' | '.join(quality_cells(row)) + ' |')
    lines += ['', '| Districts | Pipeline min | Solver min | Export/validation min | Peak GiB |', '|---|---:|---:|---:|---:|']
    for row in display_rows(data):
        lines.append('| ' + ' | '.join([str(row['district_count']), minutes(row.get('pipeline_seconds')), minutes(row.get('solve_seconds')), minutes(row.get('export_seconds')), f'{row["peak_process_working_set_bytes"]/2**30:.3f}' if row.get('peak_process_working_set_bytes') else '—']) + ' |')
    timing = data['execution_timing']
    lines += ['', f'Preparation: {timing["preparation_wall_seconds"]:.3f} s. Serial child processes: {timing["serial_child_process_wall_seconds"]/60:.2f} min. Overall launcher elapsed time, including between-run validation: {timing["elapsed_wall_seconds"]/60:.2f} min. [Execution record]({URL}run.json). All four plans are first water-policy attempts; the strict preflight did not solve a plan.', '']
    for row in display_rows(data):
        lines += [f'## House {row["house_size"]}: {row["district_count"]} districts', '']
        if not row['accepted_plan']:
            lines += [f'**{row["status"]}** — no accepted map. {row.get("failure", {})}', '']
            continue
        fragmented = [f'District {i+1}: {count} physical pieces' for i, count in enumerate(row['physical_polygon_components']) if count > 1]
        lines += [f'[Validated map]({row["map_url"]}). ' + '; '.join(fragmented) + '.', row['outer_termination']['disclosure'], '',
                  f'Connectivity postprocessing: {row["postprocessing"]["repair_move_count"]} component-repair moves, {row["postprocessing"]["part_repair_move_count"]} part-repair moves, and {row["postprocessing"]["rebalance_move_count"]}/{row["configuration"]["max_rebalance_moves"]} rebalance moves. Rebalancing stopped with **{row["postprocessing"]["stop_reason"]}**.', '',
                  '| Stage | Maximum deviation people | Maximum deviation % |', '|---|---:|---:|']
        for stage, pop in row['independent_population_checks'].items():
            lines.append(f'| {stage.replace("_", " ")} | {pop["max_absolute_deviation_people"]:.6f} | {pop["max_absolute_deviation_percent"]:.9f} |')
        payload = row['map_payloads']
        lines += ['', f'All {BLOCKS:,} blocks and {TOTAL:,} residents are assigned once. {row["compressed_maps_verified"]} compressed map artifacts verified. Gzip bytes: national {payload["national_state_only"]["gzip_bytes"]:,}; state entry {payload["state_entry_outlines_and_detail_index"]["gzip_bytes"]:,}; connections {row["water_link_payload"]["gzip_bytes"]:,}; all county shards {payload["all_county_detail_shards"]["gzip_bytes"]:,}.', '',
                  '| Link | Endpoint districts | Used within district |', '|---|---|---|']
        for link in row['links']:
            lines.append(f'| {link["id"]} | {" / ".join(str(d+1) for d in link["endpoint_districts"])} | {link["used_by_district"]+1 if link["used_by_district"] is not None else "Unused"} |')
        lines += ['', f'{row["trace"]["pass_count"]} inner passes; {row["trace"]["accepted_iteration_count"]:,} accepted iterations; all inner passes succeeded: {row["trace"]["all_inner_passes_succeeded"]}.', '']
    lines += ['Validation: ' + data['validation_note'], '',
              f'[Saved prelaunch test evidence]({URL}validation-tests.json): {data["prelaunch_tests"]["record"]["passed"]} tests passed; the checksum is retained in the comparison JSON.', '',
              f'[Summary validation evidence]({URL}summary-validation-tests.json): {data["summary_validation_tests"]["record"]["passed"]} focused checks passed; the tested summary and test-source hashes are recorded.', '',
              *['- ' + note for note in data['limitations']], '']
    return '\n'.join(lines)


def html(data: dict[str, Any]) -> str:
    def table(headers: list[str], rows: list[list[str]]) -> str:
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    rows = display_rows(data)
    quality = table(['Districts', 'Maximum final deviation', 'Population range', 'Policy connected', 'Physically connected', 'Largest inner pass'], [quality_cells(row) for row in rows])
    timing = table(['Districts', 'Pipeline min', 'Solver min', 'Export/validation min', 'Peak GiB'], [[str(r['district_count']), minutes(r.get('pipeline_seconds')), minutes(r.get('solve_seconds')), minutes(r.get('export_seconds')), f'{r["peak_process_working_set_bytes"]/2**30:.3f}' if r.get('peak_process_working_set_bytes') else '—'] for r in rows])
    sections = []
    for row in rows:
        title = f'House {row["house_size"]} · {row["district_count"]} districts'
        if not row['accepted_plan']:
            sections.append('<section><h2>'+title+'</h2><p class="status">'+escape(row['status'])+' — no accepted map</p><p>'+escape(str(row.get('failure', {})))+'</p></section>')
            continue
        poprows = [[stage.replace('_',' '), f'{p["max_absolute_deviation_people"]:.3f}', f'{p["max_absolute_deviation_percent"]:.6f}%'] for stage,p in row['independent_population_checks'].items()]
        fragmented = '; '.join(f'District {i+1} retains {count} physical pieces' for i,count in enumerate(row['physical_polygon_components']) if count>1)
        payload = row['map_payloads']
        post = row['postprocessing']
        post_note = f"Connectivity postprocessing: {post['repair_move_count']} component-repair moves, {post['part_repair_move_count']} part-repair moves; {post['rebalance_move_count']}/{row['configuration']['max_rebalance_moves']} rebalance moves, stopping with {post['stop_reason']}."
        sections.append('<section><h2>'+title+'</h2><p><a href="'+row['map_url']+'">Open validated district map →</a></p><p>'+escape(fragmented)+'.</p><p>'+escape(row['outer_termination']['disclosure'])+'</p><p>'+escape(post_note)+'</p>'+table(['Population stage','Maximum deviation people','Maximum deviation percent'],poprows)+f'<p>All {BLOCKS:,} source blocks and {TOTAL:,} residents remain assigned. The single recorded water connection is identical across independently measured counts; {sum(l["used_by_district"] is not None for l in row["links"])} links are used within districts.</p><p>Gzip map data: national {payload["national_state_only"]["gzip_bytes"]/1024:.1f} KiB; state entry {payload["state_entry_outlines_and_detail_index"]["gzip_bytes"]/1024:.1f} KiB; links {row["water_link_payload"]["gzip_bytes"]/1024:.1f} KiB. County detail totals {payload["all_county_detail_shards"]["gzip_bytes"]/2**20:.2f} MiB and loads only on explicit request.</p></section>')
    notes=''.join('<li>'+escape(note)+'</li>' for note in data['limitations'])
    stop_notice = '<p class="status">Queue stop: ' + escape(str(data['stop_error'])) + '</p>' if data.get('stop_error') else ''
    timing_summary = ''
    if timing_values := data.get('execution_timing'):
        timing_summary = f'<p>Preparation {timing_values["preparation_wall_seconds"]:.3f} s; serial child processes {timing_values["serial_child_process_wall_seconds"]/60:.2f} min; overall launcher time including checks {timing_values["elapsed_wall_seconds"]/60:.2f} min.</p>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Florida water-policy benchmark</title><style>:root{{color-scheme:dark;font:15px/1.55 system-ui;background:#11191f;color:#e6eef2}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1180px;margin:auto;padding:28px}}h1{{font-size:30px}}h2{{font-size:21px}}a{{color:#69d4df}}.tag{{color:#69d4df;letter-spacing:.1em;text-transform:uppercase;font-size:12px}}section{{background:#19242b;border:1px solid #31424b;border-radius:8px;padding:20px;margin:22px 0}}table{{border-collapse:collapse;width:100%}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #31424b;vertical-align:top}}.scroll{{overflow:auto}}.status{{color:#f6c970}}li{{margin-bottom:10px}}a:focus-visible{{outline:3px solid #f6c970;outline-offset:3px}}@media(max-width:740px){{main{{padding:16px}}h1{{font-size:25px}}section{{padding:14px}}}}</style><main><p class="tag">Saved computation · Florida · 2020 census blocks</p><h1>Florida water-policy benchmark</h1><p class="status">{escape(data['status'])}</p><p>{escape(data['scope'])}</p>{stop_notice}<p><a href="comparison.json">Verified comparison JSON</a> · <a href="run.json">Serial execution record</a> · <a href="../../diagnostics/florida/">Original topology diagnosis</a></p><section><h2>Population balance and connectivity</h2>{quality}</section><section><h2>Measured runtime and memory</h2>{timing}{timing_summary}<p>New plans ran serially. The original strict topology preflight is unsolved and is excluded from this batch timing.</p></section>{''.join(sections)}<section><h2>Evidence and limits</h2><p>{data['preservation']['files_rehashed']} historical files independently rehashed and unchanged.</p><p>{escape(data['validation_note'])}</p><ul>{notes}</ul></section></main></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', default='')
    args = parser.parse_args()
    data = summary(args.validation_note)
    serialized = json.dumps(data, indent=2, allow_nan=False) + '\n'
    (OUTPUT / 'comparison.json').write_text(serialized, encoding='utf-8')
    (OUTPUT / 'index.html').write_text(html(data), encoding='utf-8')
    REPORT.with_suffix('.json').write_text(serialized, encoding='utf-8')
    REPORT.with_suffix('.md').write_text(markdown(data), encoding='utf-8')
    print(REPORT.with_suffix('.md'))


if __name__ == '__main__':
    main()
