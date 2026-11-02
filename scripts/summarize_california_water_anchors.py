"""Verify California's new water-policy anchors without modifying the K52 pilot.

This writer runs only after the serial launcher exits. Failed, unstarted and
ambiguous attempts never receive an accepted-map link in the comparison.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import summarize_california_water as pilot
from scripts.summarize_kentucky_exclave import unique_pairs
from scripts.summarize_new_york_budget import finite, verify_trace
from scripts.state_block_execution_lock import state_execution_lock

SUITE = pilot.SUITE
OUTPUT = SUITE / 'policies/california-water-anchors-v1'
REFERENCE = pilot.RUN
REPORT = ROOT / 'prompts/california-water-anchor-benchmark'
URL = 'http://127.0.0.1:8770/policies/california-water-anchors-v1/'
REFERENCE_URL = 'http://127.0.0.1:8770/policies/california-water-v1/states/06/districts-52/'
COUNTS = (69, 83, 120)
ANCHORS = {52: 435, 69: 574, 83: 692, 120: 1000}
ACCEPTED = 'complete_under_island_water_policy'
TERMINAL = ('complete', 'complete_with_numerical_failures', 'stopped')
REFERENCE_SHA = 'c7ddac16236328909f6f5d3b49467ef5a5004c0324280e2b4bd8b0e899e326e8'
WINDOWS = os.name == 'nt'


def verify_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get('status') not in TERMINAL or not manifest.get('finished_at'):
        raise ValueError('The anchor launcher is not terminal.')
    jobs = manifest.get('jobs', [])
    if len(jobs) != 3 or {job.get('district_count') for job in jobs} != set(COUNTS):
        raise ValueError('Expected exactly the three new anchor jobs.')
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
        if (launch.get('script') != 'scripts/run_california_water_anchors.py'
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
        "try { $null=Get-Process -Id $recordedId -ErrorAction Stop; "
        "$observed += @{pid=$recordedId;active=$true} } "
        "catch { if ($_.FullyQualifiedErrorId -notlike 'NoProcessFoundForGivenId,*') { throw }; "
        "$observed += @{pid=$recordedId;active=$false} } }; "
        "ConvertTo-Json -Compress -InputObject @($observed)")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, check=True, timeout=30)
    if result.stderr.strip():
        raise ValueError('Recorded PID query produced an unexpected error.')
    rows = json.loads(result.stdout, object_pairs_hook=unique_pairs)
    if (not isinstance(rows, list) or len(rows) != len(pids)
            or any(not isinstance(row, dict) or set(row) != {'pid', 'active'}
                   or type(row['pid']) is not int or type(row['active']) is not bool for row in rows)
            or sorted(row['pid'] for row in rows) != pids):
        raise ValueError('Recorded PID query did not account for every requested process.')
    return rows


def verify_no_active_children(manifest: dict[str, Any], launch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check exact recorded PIDs and the state OS lock, not all system processes."""
    pids = recorded_process_ids(manifest, launch)
    if WINDOWS:
        active = [row['pid'] for row in windows_pid_status(pids) if row['active']]
    else:
        active = []
        for pid in pids:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            active.append(pid)
    if active:
        raise ValueError(f'Recorded process PIDs are still active: {active}.')
    with state_execution_lock('06'):
        pass
    return {'recorded_pids_checked': pids, 'all_recorded_pids_absent': True,
            'california_state_os_lock_acquired_and_released': True,
            'method': 'Get-Process -Id' if WINDOWS else 'os.kill(pid, 0)',
            'process_record_sources': ['run.json', 'launch-process.json'] if launch is not None else ['run.json'],
            'scope': 'Exact parent/launcher/child PIDs in the named process records plus the California process-owned OS lock. No full-system command-line inventory or unrecorded-process absence is claimed.'}


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
    if not isinstance(expected, str) or pilot.sha256(selected) != expected:
        raise ValueError('Authoritative terminal report checksum changed.')
    return selected


def verify_configuration(configuration: dict[str, Any], original: dict[str, Any], k: int) -> None:
    if k not in ANCHORS:
        raise ValueError('Unrequested district count.')
    pilot.verify_configuration(configuration)
    allowed = {'minimum_district_population_for_root_classification', 'minimum_district_population_exact'}
    changes = {key for key in configuration.keys() | original.keys() if configuration.get(key) != original.get(key)}
    if changes - allowed:
        raise ValueError('Settings other than the per-K root threshold changed from K52.')
    threshold = Fraction(pilot.TOTAL * 99, 100 * k)
    if (configuration.get('minimum_district_population_exact') != str(threshold)
            or configuration.get('minimum_district_population_for_root_classification') != float(threshold)):
        raise ValueError('Root classification threshold does not match this anchor population.')


def verify_plan(directory: Path, report: dict[str, Any], populations: dict[str, int], k: int) -> dict[str, Any]:
    if report['status'] == 'failed':
        return {'accepted_plan': False, 'failure': {'phase': report.get('failed_phase'),
                'error': report.get('error'), 'optimizer': report.get('optimizer_failure')}}
    if report['status'] != ACCEPTED:
        raise ValueError('Benchmark is not a terminal accepted or failed attempt.')
    stages = {}
    for stage, filename in (('initial', 'initial-solver-result.json'), ('after_repair', 'after-repair-result.json'), ('final', 'solver-result.json')):
        saved = pilot.read_json(directory / filename)
        stages[stage] = pilot.verify_assignments(saved['assignments'], populations, k, report[stage + '_plan'])
        if saved['provenance']['configuration'] != report['configuration']:
            raise ValueError('Assignment settings differ from the measured report.')
    final = report['final_plan']
    if final['policy_part_components'] != [1] * k or final['all_districts_policy_connected'] is not True:
        raise ValueError('Part graph connectivity failed.')
    manifest = pilot.read_json(directory / 'maps/map-manifest.json')
    if manifest != report['maps']:
        raise ValueError('Map manifest differs from the measured report.')
    audit = manifest['connectivity_validation']
    if (audit['policy'] != pilot.POLICY or audit['passed'] is not True
            or audit['source_coverage_preserved_exactly'] is not True or audit['source_geometry_modified'] is not False
            or [row['district_id'] for row in audit['districts']] != list(range(k))
            or any(row['connected_components_after_links'] != 1 for row in audit['districts'])
            or [row['physical_polygon_components'] for row in audit['districts']] != final['physical_part_components']):
        raise ValueError('Independent polygon-plus-link connectivity disagrees with the graph audit.')
    map_count = pilot.verify_compressed_maps(directory, manifest)
    for level in ('national', 'state', 'full'):
        features = json.loads(gzip.decompress((directory / f'maps/districts-{level}.geojson.gz').read_bytes()))['features']
        props = sorted((f['properties'] for f in features), key=lambda row: row['district_id'])
        if ([p['district_id'] for p in props] != list(range(k))
                or [p['population'] for p in props] != stages['final']['district_populations']
                or [p['block_count'] for p in props] != stages['final']['district_block_counts']):
            raise ValueError('Map district attributes disagree with source-DBF assignment totals.')
    features = json.loads(gzip.decompress((directory / 'maps/water-connections.geojson.gz').read_bytes()))['features']
    links = pilot.verify_links(features, report['water_connections'], pilot.read_json(directory / 'solver-result.json')['assignments'])
    if {row['id'] for row in links if row['used_by_district'] is not None} != set(audit['used_link_ids']):
        raise ValueError('Used water edges differ between endpoint assignments and polygon validation.')
    values = stages['final']['district_populations']
    return {'accepted_plan': True, 'independent_population_checks': stages,
            'population_min': min(values), 'population_max': max(values),
            'fractional_ideal_population': pilot.TOTAL / k, 'connectivity': audit,
            'physical_polygon_components': final['physical_part_components'], 'links': links,
            'compressed_maps_verified': map_count, 'map_payloads': manifest['load_scenarios'],
            'water_link_payload': manifest['water_connections'],
            'postprocessing': report['postprocessing'],
            'outer_termination': pilot.outer_termination(report['solver'], report['configuration'])}


def verify_report_identity(report: dict[str, Any], k: int, original: dict[str, Any]) -> None:
    if (report.get('state_fips') != '06' or report.get('district_count') != k
            or report.get('policy') != pilot.POLICY or report.get('house_sizes') != [ANCHORS[k]]
            or report.get('status') not in (ACCEPTED, 'failed') or not report.get('finished_at')
            or report.get('active_phase') is not None):
        raise ValueError('Unexpected or nonterminal California anchor report.')
    verify_configuration(report['configuration'], original['configuration'], k)
    config_sha = hashlib.sha256(json.dumps(report['configuration'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if report.get('configuration_sha256') != config_sha:
        raise ValueError('Configuration checksum changed.')
    if report['source']['archive_sha256'] != pilot.SOURCE_SHA or report['water_connections'] != original['water_connections']:
        raise ValueError('Source or selected water connection records changed from K52.')


def verify_target_policy(report: dict[str, Any], original: dict[str, Any], k: int) -> None:
    audit = report['island_policy_audit']
    selection = audit['population_selection']
    groups = selection['groups']
    if (audit['district_count'] != k or selection['district_count'] != k
            or selection['ideal_population'] != pilot.TOTAL / k
            or selection['minimum_root_population'] != float(Fraction(pilot.TOTAL * 99, 100 * k))
            or selection['eligible_root_component_ids'] != [0]
            or selection['selected_link_ids'] != original['island_policy_audit']['population_selection']['selected_link_ids']
            or len(groups) != 1 or groups[0]['district_count'] != k
            or groups[0]['component_ids'] != list(range(7)) or groups[0]['population'] != pilot.TOTAL
            or audit['source_geometry_modified'] is not False
            or audit['augmented_graph_connected'] is not True or audit['all_source_parts_reached'] is not True):
        raise ValueError('Population-aware policy audit does not match the target anchor.')
    if k != 52 and (audit.get('base_verification_district_count') != 52
            or audit.get('target_selection_verified_against_diagnosis') is not True
            or audit.get('connection_records_reused_unchanged') is not True):
        raise ValueError('Target policy was not verified against the preserved K52 diagnosis.')


def checked_trace(directory: Path, report: dict[str, Any], k: int) -> dict[str, Any] | None:
    if not report.get('optimizer_trace', {}).get('passes'):
        if report['status'] == ACCEPTED:
            raise ValueError('Accepted plan has no successful optimizer trace.')
        return None
    rows = [json.loads(line, object_pairs_hook=unique_pairs) for line in (directory / 'optimizer-trace.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    result = verify_trace(rows, report['optimizer_trace'], k=k, total=pilot.TOTAL)
    for entry in report['optimizer_trace']['passes']:
        options = entry['actual_options']
        if options != {'maxiter': 1000, 'gtol': 1e-6 / pilot.TOTAL, 'ftol': 1e-12, 'maxls': 100}:
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


def load_run(k: int, populations: dict[str, int], original: dict[str, Any], *, job: dict[str, Any] | None = None) -> dict[str, Any]:
    reference = job is None
    directory = REFERENCE if reference else OUTPUT / f'states/06/districts-{k}'
    if not reference and job['status'] in ('pending', 'needs_inspection'):
        return {'district_count': k, 'house_size': ANCHORS[k], 'read_only_reference': False,
                'status': job['status'], 'accepted_plan': False,
                'failure': {'error': job.get('error', 'No independently accepted terminal plan.')}, 'map_url': None}
    path = directory / 'benchmark.json' if reference else selected_report_path(job, directory)
    report = pilot.read_json(path)
    verify_report_identity(report, k, original)
    verify_target_policy(report, original, k)
    progress = pilot.read_json(directory / 'progress.json')
    if progress.get('status') != report['status'] or progress.get('active_phase') is not None:
        raise ValueError('Terminal progress differs from the measured outcome.')
    if not reference:
        validation = job['terminal_validation']
        expected_class = 'validated_complete_plan' if report['status'] == ACCEPTED else 'verified_numerical_failure'
        if (job['status'] != report['status'] or validation.get('classification') != expected_class
                or validation.get('progress_sha256') != pilot.sha256(directory / 'progress.json')
                or report.get('final_progress_snapshot_written') is not True
                or report.get('run_kind') != 'california_population_aware_water_anchors_v1'
                or progress.get('solver_progress') != report['solver_progress']):
            raise ValueError('Launcher and child terminal validation disagree.')
        if path.name == 'terminal-report.json' and (report.get('authoritative_terminal_report') != 'terminal-report.json'
                or not report.get('terminal_report_write_error')):
            raise ValueError('Fallback report is not explicitly authoritative.')
        finite(job['process_wall_seconds'], 'child elapsed time')
        if job['process_wall_seconds'] < report['timed_pipeline_wall_seconds']:
            raise ValueError('Child process duration is shorter than the measured pipeline.')
        reference_record = report['completed_k52_reference']
        if reference_record.get('report_sha256') != pilot.sha256(REFERENCE / 'benchmark.json') or reference_record.get('reused_without_rerun') is not True:
            raise ValueError('Child did not preserve the K52 reference.')
        if (report['environment'] != original['environment']
                or report['source'].get('extracted_file_sha256') != original['source'].get('extracted_file_sha256')):
            raise ValueError('Numerical environment or extracted source differs from K52.')
    flags = ['all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
             'national_suite_byte_identical', 'source_archive_byte_identical', 'run_code_unchanged']
    if not reference:
        flags += ['completed_k52_tree_byte_identical', 'water_connections_byte_identical_to_k52']
    if any(report['preservation_audit'].get(key) is not True for key in flags) or report.get('preservation_error'):
        raise ValueError('Runner did not pass the historical preservation audit.')
    if pilot.sha256(directory / 'water-connections.json') != pilot.sha256(REFERENCE / 'water-connections.json'):
        raise ValueError('Water connection artifact is not byte-identical to K52.')
    for relative, digest in report['code_sha256'].items():
        if pilot.sha256(ROOT / relative) != digest:
            raise ValueError(f'Frozen runtime changed: {relative}')
    for relative, digest in report['artifact_sha256'].items():
        if pilot.sha256(directory / relative) != digest:
            raise ValueError(f'Saved benchmark artifact changed: K{k}/{relative}')
    plan = verify_plan(directory, report, populations, k)
    trace = checked_trace(directory, report, k)
    return {'district_count': k, 'house_size': ANCHORS[k], 'read_only_reference': reference,
            'status': report['status'], 'benchmark_path': path.relative_to(ROOT).as_posix(),
            'benchmark_sha256': pilot.sha256(path), 'code_sha256': report['code_sha256'],
            'source_sha256': report['source']['archive_sha256'], 'configuration': report['configuration'],
            'pipeline_seconds': report['timed_pipeline_wall_seconds'], 'phases': report['phases'],
            'solve_seconds': report['phases'].get('solve', {}).get('wall_seconds'),
            'export_seconds': report['phases'].get('independent_polygon_validation_and_map_export', {}).get('wall_seconds'),
            'peak_process_working_set_bytes': report['peak_process_working_set_bytes'],
            'trace': trace, 'island_policy_audit': report['island_policy_audit'],
            'preservation_audit': report['preservation_audit'],
            'preservation_inventory': pilot.read_json(directory / 'preserved-file-inventory.json'),
            'map_url': (REFERENCE_URL if reference else URL + f'states/06/districts-{k}/') if plan['accepted_plan'] else None,
            **plan}


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


def verify_preservation(manifest: dict[str, Any], runs: list[dict[str, Any]], reference: dict[str, Any]) -> dict[str, Any]:
    path = OUTPUT / 'preserved-file-inventory.json'
    inventory = pilot.read_json(path)
    if (pilot.sha256(path) != manifest['preserved_file_inventory_sha256']
            or len(inventory) != manifest['protected_file_count']):
        raise ValueError('Launcher preservation inventory changed.')
    required = {p.relative_to(ROOT).as_posix() for tree in (SUITE / 'states/06', SUITE / 'diagnostics/california', pilot.OUTPUT) for p in tree.rglob('*') if p.is_file()}
    required.update(p.relative_to(ROOT).as_posix() for p in (pilot.SOURCE, SUITE / 'suite.json', ROOT / 'prompts/california-topology-diagnosis.json', pilot.REPORT.with_suffix('.md'), pilot.REPORT.with_suffix('.json')))
    if not required <= set(inventory):
        raise ValueError('Preservation inventory omits strict, diagnostic or K52 evidence.')
    merged = dict(inventory)
    for row in [reference, *runs]:
        child_inventory = row.get('preservation_inventory')
        if child_inventory is None:
            continue
        if not row['read_only_reference'] and child_inventory != inventory:
            raise ValueError('Child and launcher historical inventories differ.')
        for name, digest in child_inventory.items():
            if name in merged and merged[name] != digest:
                raise ValueError('Saved historical inventories disagree.')
            merged[name] = digest
    for name, digest in merged.items():
        if pilot.sha256(ROOT / name) != digest:
            raise ValueError(f'Historical evidence changed: {name}')
    record = manifest['completed_k52_reference']
    if record.get('report_sha256') != reference['benchmark_sha256'] or record.get('reused_without_rerun') is not True:
        raise ValueError('Launcher K52 reference identity changed.')
    return {'files_rehashed': len(merged), 'all_byte_identical': True,
            'original_k52_tree_preserved': True, 'strict_and_diagnostic_trees_preserved': True}


def summary(validation_note: str = '') -> dict[str, Any]:
    manifest = pilot.read_json(OUTPUT / 'run.json')
    verify_manifest(manifest)
    launch_path = OUTPUT / 'launch-process.json'
    launch_record = pilot.read_json(launch_path)
    execution_verification = verify_no_active_children(manifest, launch_record)
    execution_verification['launch_process_record_sha256'] = pilot.sha256(launch_path)
    # Check summary metadata before the expensive source/map verification, so
    # evidence-format problems fail immediately without repeated large reads.
    test_path = OUTPUT / 'validation-tests.json'
    test_record = pilot.read_json(test_path)
    prelaunch_validation = verify_prelaunch_tests(test_record, launch_record['started_at'])
    summary_test_path = OUTPUT / 'summary-validation-tests.json'
    summary_tests = pilot.read_json(summary_test_path)
    expected_test_sources = {'scripts/summarize_california_water_anchors.py',
                             'scripts/tests/test_summarize_california_water_anchors.py'}
    if (summary_tests.get('status') != 'passed' or type(summary_tests.get('passed')) is not int
            or summary_tests['passed'] <= 0 or set(summary_tests.get('source_sha256', {})) != expected_test_sources
            or any(pilot.sha256(ROOT / name) != digest for name, digest in summary_tests['source_sha256'].items())):
        raise ValueError('Summary validation record is missing or its tested source changed.')
    original = pilot.read_json(REFERENCE / 'benchmark.json')
    if original['status'] != ACCEPTED or pilot.sha256(REFERENCE / 'benchmark.json') != REFERENCE_SHA:
        raise ValueError('The immutable K52 reference changed.')
    pilot.verify_execution(pilot.read_json(pilot.OUTPUT / 'run.json'), original, pilot.read_json(REFERENCE / 'progress.json'))
    populations = pilot.source_populations()
    reference = load_run(52, populations, original)
    jobs = {job['district_count']: job for job in manifest['jobs']}
    runs = [load_run(k, populations, original, job=jobs[k]) for k in COUNTS]
    measured = [run for run in runs if 'benchmark_path' in run]
    if any(row['code_sha256'] != manifest['code_sha256'] for row in measured):
        raise ValueError('Children and launcher differ in frozen runtime code.')
    preservation = verify_preservation(manifest, runs, reference)
    timing = execution_timing(manifest)
    for row in [reference, *runs]:
        row.pop('preservation_inventory', None)
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'California K69/K83/K120 for House 574/692/1000 with the same recorded water policy and 1,000 inner iterations; K52 is an unchanged saved reference.',
            'status': manifest['status'], 'runs': runs, 'reference_k52': reference,
            'execution': manifest, 'execution_verification': execution_verification,
            'execution_timing': timing, 'preservation': preservation, 'validation_note': validation_note,
            'prelaunch_tests': {'path': test_path.relative_to(ROOT).as_posix(),
                               'sha256': pilot.sha256(test_path), 'record': test_record,
                               'verification': prelaunch_validation},
            'summary_validation_tests': {'path': summary_test_path.relative_to(ROOT).as_posix(),
                                         'sha256': pilot.sha256(summary_test_path), 'record': summary_tests},
            'limitations': [
                'K52 was computed earlier and is reused without rerunning. The three new anchors run serially; preparation and child timing remain separate.',
                'The preserved strict source-topology exception did not solve any plan. These are not 300-versus-1000 iteration experiments.',
                'Successful inner solves, outer center convergence, population balance and connectivity under recorded water links are separate outcomes.',
                'Physical polygons remain unchanged. A water connection counts only when both endpoint blocks belong to the same district.',
                'All six links retain the K52 records. Distances span census-coverage boundaries, not shorelines or ferry routes; open-Pacific attribution is not a global high-resolution shoreline certificate.',
                'The 1% group/root preflight guides policy selection; it is not a final population-balance acceptance guarantee.',
                'Wall timings include tracing and desktop contention; gzip file sizes do not measure browser memory or network latency.',
            ]}


def display_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [data['reference_k52'], *data['runs']]


def minutes(value: float | None) -> str:
    return '—' if value is None else f'{value / 60:.2f}'


def quality_cells(row: dict[str, Any]) -> list[str]:
    if not row['accepted_plan']:
        return [str(row['district_count']), row['status'], 'No accepted plan', '—', '—', '—']
    pop = row['independent_population_checks']['final']
    physical = sum(value == 1 for value in row['physical_polygon_components'])
    return [str(row['district_count']) + (' (prior)' if row['read_only_reference'] else ''),
            f'{pop["max_absolute_deviation_people"]:.3f} people / {pop["max_absolute_deviation_percent"]:.6f}%',
            f'{row["population_min"]:,}–{row["population_max"]:,}', f'{row["district_count"]}/{row["district_count"]}',
            f'{physical}/{row["district_count"]}', str(row['trace']['maximum_inner_iterations'])]


def markdown(data: dict[str, Any]) -> str:
    lines = ['# California water-policy anchor benchmark', '', data['scope'], '',
             f'Outcome: **{data["status"]}**. {data["preservation"]["files_rehashed"]} historical files independently rehashed and unchanged.', '',
             '| Districts | Final maximum deviation | Population range | Policy connected | Physically connected | Largest inner pass |',
             '|---|---:|---:|---:|---:|---:|']
    for row in display_rows(data):
        lines.append('| ' + ' | '.join(quality_cells(row)) + ' |')
    lines += ['', '| Districts | Pipeline min | Solver min | Export/validation min | Peak GiB |', '|---|---:|---:|---:|---:|']
    for row in display_rows(data):
        lines.append('| ' + ' | '.join([str(row['district_count']), minutes(row.get('pipeline_seconds')), minutes(row.get('solve_seconds')), minutes(row.get('export_seconds')), f'{row["peak_process_working_set_bytes"]/2**30:.3f}' if row.get('peak_process_working_set_bytes') else '—']) + ' |')
    timing = data['execution_timing']
    lines += ['', f'Preparation: {timing["preparation_wall_seconds"]:.3f} s. Serial child processes: {timing["serial_child_process_wall_seconds"]/60:.2f} min. Overall launcher elapsed time, including between-run validation: {timing["elapsed_wall_seconds"]/60:.2f} min. [Execution record]({URL}run.json). K52’s original runtime is not added to the new serial batch.', '']
    for row in display_rows(data):
        lines += [f'## House {row["house_size"]}: {row["district_count"]} districts' + (' (saved reference)' if row['read_only_reference'] else ''), '']
        if not row['accepted_plan']:
            lines += [f'**{row["status"]}** — no accepted map. {row.get("failure", {})}', '']
            continue
        fragmented = [f'District {i+1}: {count} physical pieces' for i, count in enumerate(row['physical_polygon_components']) if count > 1]
        lines += [f'[Validated map]({row["map_url"]}). ' + '; '.join(fragmented) + '.', row['outer_termination']['disclosure'], '',
                  '| Stage | Maximum deviation people | Maximum deviation % |', '|---|---:|---:|']
        for stage, pop in row['independent_population_checks'].items():
            lines.append(f'| {stage.replace("_", " ")} | {pop["max_absolute_deviation_people"]:.6f} | {pop["max_absolute_deviation_percent"]:.9f} |')
        payload = row['map_payloads']
        lines += ['', f'All {pilot.BLOCKS:,} blocks and {pilot.TOTAL:,} residents are assigned once. {row["compressed_maps_verified"]} compressed map artifacts verified. Gzip bytes: national {payload["national_state_only"]["gzip_bytes"]:,}; state entry {payload["state_entry_outlines_and_detail_index"]["gzip_bytes"]:,}; connections {row["water_link_payload"]["gzip_bytes"]:,}; all county shards {payload["all_county_detail_shards"]["gzip_bytes"]:,}.', '',
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
        title = f'House {row["house_size"]} · {row["district_count"]} districts' + (' · preserved reference' if row['read_only_reference'] else '')
        if not row['accepted_plan']:
            sections.append('<section><h2>'+title+'</h2><p class="status">'+escape(row['status'])+' — no accepted map</p><p>'+escape(str(row.get('failure', {})))+'</p></section>')
            continue
        poprows = [[stage.replace('_',' '), f'{p["max_absolute_deviation_people"]:.3f}', f'{p["max_absolute_deviation_percent"]:.6f}%'] for stage,p in row['independent_population_checks'].items()]
        fragmented = '; '.join(f'District {i+1} retains {count} physical pieces' for i,count in enumerate(row['physical_polygon_components']) if count>1)
        payload = row['map_payloads']
        sections.append('<section><h2>'+title+'</h2><p><a href="'+row['map_url']+'">Open validated district map →</a></p><p>'+escape(fragmented)+'.</p><p>'+escape(row['outer_termination']['disclosure'])+'</p>'+table(['Population stage','Maximum deviation people','Maximum deviation percent'],poprows)+f'<p>All {pilot.BLOCKS:,} source blocks and {pilot.TOTAL:,} residents remain assigned. All six water records are identical to K52; {sum(l["used_by_district"] is not None for l in row["links"])} links are used within districts.</p><p>Gzip map data: national {payload["national_state_only"]["gzip_bytes"]/1024:.1f} KiB; state entry {payload["state_entry_outlines_and_detail_index"]["gzip_bytes"]/1024:.1f} KiB; links {row["water_link_payload"]["gzip_bytes"]/1024:.1f} KiB. County detail totals {payload["all_county_detail_shards"]["gzip_bytes"]/2**20:.2f} MiB and loads only on explicit request.</p></section>')
    notes=''.join('<li>'+escape(note)+'</li>' for note in data['limitations'])
    timing_summary = ''
    if timing_values := data.get('execution_timing'):
        timing_summary = f'<p>Preparation {timing_values["preparation_wall_seconds"]:.3f} s; serial child processes {timing_values["serial_child_process_wall_seconds"]/60:.2f} min; overall launcher time including checks {timing_values["elapsed_wall_seconds"]/60:.2f} min.</p>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>California water-policy anchors</title><style>:root{{color-scheme:dark;font:15px/1.55 system-ui;background:#11191f;color:#e6eef2}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1180px;margin:auto;padding:28px}}h1{{font-size:30px}}h2{{font-size:21px}}a{{color:#69d4df}}.tag{{color:#69d4df;letter-spacing:.1em;text-transform:uppercase;font-size:12px}}section{{background:#19242b;border:1px solid #31424b;border-radius:8px;padding:20px;margin:22px 0}}table{{border-collapse:collapse;width:100%}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #31424b;vertical-align:top}}.scroll{{overflow:auto}}.status{{color:#f6c970}}li{{margin-bottom:10px}}a:focus-visible{{outline:3px solid #f6c970;outline-offset:3px}}@media(max-width:740px){{main{{padding:16px}}h1{{font-size:25px}}section{{padding:14px}}}}</style><main><p class="tag">Saved computation · California · 2020 census blocks</p><h1>California water-policy anchors</h1><p class="status">{escape(data['status'])}</p><p>{escape(data['scope'])}</p><p><a href="comparison.json">Verified comparison JSON</a> · <a href="run.json">Serial execution record</a> · <a href="../../diagnostics/california/">Original topology diagnosis</a></p><section><h2>Population balance and connectivity</h2>{quality}</section><section><h2>Measured runtime and memory</h2>{timing}{timing_summary}<p>New plans ran serially. K52’s earlier runtime is a saved reference and is excluded from this batch.</p></section>{''.join(sections)}<section><h2>Evidence and limits</h2><p>{data['preservation']['files_rehashed']} historical files independently rehashed and unchanged.</p><p>{escape(data['validation_note'])}</p><ul>{notes}</ul></section></main></html>'''


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
