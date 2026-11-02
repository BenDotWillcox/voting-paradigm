"""Independently verify and summarize terminal New York mixed-link plans.

Reads original and new benchmark evidence without changing it. Population
validation uses the source archive's DBF directly, not benchmark aggregates.
Only the new policy comparison page/JSON and its durable reports are written.
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
from pathlib import Path
import re
from typing import Any
import zipfile

import shapefile


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'policies/new-york-links-v1'
SOURCE = ROOT / '.cache/state-block-benchmark/source/36/tl_2020_36_tabblock20.zip'
REPORT = ROOT / 'prompts/new-york-links-benchmark'
BASE_URL = 'http://127.0.0.1:8770/policies/new-york-links-v1/'
POLICY = 'shared_edges_plus_recorded_mixed_connections'
COUNTS = (26, 35, 42, 61)
TOTAL = 20201249
BLOCKS = 288819


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_pairs)


def source_populations(expected_sha256: str) -> dict[str, int]:
    """Read the original DBF directly, with an independently checked universe."""
    if sha256(SOURCE) != expected_sha256:
        raise ValueError('New York source archive does not match the measured run.')
    with zipfile.ZipFile(SOURCE) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith('.dbf')]
        if len(candidates) != 1:
            raise ValueError('Expected one source DBF in the New York archive.')
        raw = archive.read(candidates[0])
    populations: dict[str, int] = {}
    with shapefile.Reader(dbf=io.BytesIO(raw)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        geoid_column, population_column = fields.index('GEOID20'), fields.index('POP20')
        for record in reader.iterRecords():
            geoid, value = str(record[geoid_column]), record[population_column]
            if geoid in populations or len(geoid) != 15 or not geoid.startswith('36'):
                raise ValueError('Duplicate or non-New York GEOID in the source DBF.')
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or int(value) != value:
                raise ValueError(f'Invalid source population: {geoid}')
            populations[geoid] = int(value)
    if len(populations) != BLOCKS or sum(populations.values()) != TOTAL:
        raise ValueError('Source DBF does not match independent official block/resident totals.')
    return populations


def verify_assignments(
    assignments: dict[str, int], populations: dict[str, int], k: int,
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Recompute final district population and block counts by source GEOID."""
    if set(assignments) != set(populations):
        raise ValueError('Final assignment GEOIDs do not match the source exactly once.')
    totals, counts = [0] * k, [0] * k
    for geoid, district in assignments.items():
        if type(district) is not int or not 0 <= district < k:
            raise ValueError('Invalid district label in final assignments.')
        totals[district] += populations[geoid]
        counts[district] += 1
    if not all(counts) or totals != plan['district_populations'] or counts != plan['district_block_counts']:
        raise ValueError('Independent source-DBF totals differ from the final report.')
    total = sum(populations.values())
    numerators = [value * k - total for value in totals]
    maximum = max(map(abs, numerators))
    if plan['deviation_numerators'] != numerators:
        raise ValueError('Final report deviation numerators are inconsistent.')
    for name, actual in (
        ('max_absolute_deviation_people', maximum / k),
        ('max_absolute_deviation_percent', maximum * 100 / total),
        ('total_range_people', max(totals) - min(totals)),
    ):
        if not math.isclose(float(plan[name]), actual, abs_tol=1e-10, rel_tol=1e-12):
            raise ValueError(f'Independent balance calculation disagrees: {name}')
    return {
        'source': 'Original source archive DBF GEOID20/POP20, read independently of runner aggregation',
        'all_source_geoids_assigned_exactly_once': True,
        'block_count': len(assignments), 'total_population': total,
        'district_populations': totals, 'district_block_counts': counts,
        'deviation_numerators': numerators, 'deviation_denominator': k,
        'max_absolute_deviation_people': maximum / k,
        'max_absolute_deviation_percent': maximum * 100 / total,
    }


def verify_compressed_maps(directory: Path, manifest: dict[str, Any]) -> int:
    for item in manifest['storage']['artifacts']:
        compressed = (directory / 'maps' / item['gzip_path']).read_bytes()
        raw = gzip.decompress(compressed)
        if (len(compressed) != item['gzip_bytes'] or len(raw) != item['raw_bytes']
                or hashlib.sha256(raw).hexdigest() != item['raw_sha256']):
            raise ValueError(f'Compressed map verification failed: {directory.name}/{item["gzip_path"]}')
    return len(manifest['storage']['artifacts'])


def outer_termination(solver: dict[str, Any], configuration: dict[str, Any]) -> dict[str, Any]:
    """Keep center convergence distinct from successful inner weight solves."""
    iterations, limit = solver['outer_iterations'], configuration['max_outer_iterations']
    converged, reached_limit = solver['centers_converged'], solver['outer_iteration_limit_reached']
    if (type(iterations) is not int or type(limit) is not int or not 0 <= iterations <= limit
            or limit <= 0 or type(converged) is not bool or type(reached_limit) is not bool
            or reached_limit != (iterations >= limit)):
        raise ValueError('Inconsistent outer-iteration termination metadata.')
    if converged:
        status = 'center_tolerance_met'
        disclosure = f'The outer loop met its center-convergence tolerance after {iterations} iterations.'
        if reached_limit:
            disclosure += f' This occurred at the configured {limit}-iteration limit.'
    elif reached_limit:
        status = 'outer_iteration_limit_without_center_convergence'
        disclosure = f'The outer loop reached the {limit}-iteration limit without center convergence.'
    else:
        status = 'stopped_without_center_convergence'
        disclosure = f'The outer loop stopped after {iterations} iterations without center convergence.'
    disclosure += (' Successful inner optimizer passes do not establish outer convergence. '
                   'Final population balance and connectivity are assessed separately after repair/rebalancing.')
    return {
        'status': status, 'outer_iterations': iterations, 'configured_max_outer_iterations': limit,
        'centers_converged': converged, 'outer_iteration_limit_reached': reached_limit,
        'disclosure': disclosure,
    }


def outer_convergence_overview(runs: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, Any]:
    accepted = [run for run in runs if run['accepted_plan']]
    unconverged = [run for run in accepted if not run['outer_termination']['centers_converged']]
    return {
        'accepted_plan_count': len(accepted),
        'center_converged_plan_count': len(accepted) - len(unconverged),
        'all_accepted_plans_center_converged': bool(accepted) and not unconverged,
        'district_counts_without_center_convergence': [run['district_count'] for run in unconverged],
        'district_counts_at_outer_limit_without_center_convergence': [
            run['district_count'] for run in unconverged
            if run['outer_termination']['outer_iteration_limit_reached']
        ],
        'disclosures': [f'{run["district_count"]}-district run: {run["outer_termination"]["disclosure"]}'
                        for run in unconverged],
    }


def failure_details(report: dict[str, Any]) -> dict[str, Any]:
    """Retain the failed stage and optimizer evidence without inventing a plan."""
    passes = [row['inner_optimizer'] for row in report.get('solver_progress', []) if 'inner_optimizer' in row]
    failure = report.get('optimizer_failure')
    if failure:
        disclosure = (
            f"The inner weight optimizer failed on balance pass {failure['balance_pass']} after "
            f"{failure['iterations']} iterations: {failure['message']}. "
            f"Its configured inner iteration limit was {report['configuration']['inner_max_iterations']}. "
            "This is an inner-optimizer failure, separate from the outer center-convergence limit. "
        )
    else:
        disclosure = f"The attempt failed during {report.get('failed_phase')}: {report.get('error')}. "
    disclosure += (
        'No validated district plan or completed map is accepted from this attempt. '
        'Final population balance and district connectivity are unavailable; failure time and peak process memory are still measured.'
    )
    return {
        'disclosure': disclosure, 'failed_phase': report.get('failed_phase'),
        'optimizer_failure': failure, 'solver_progress': report.get('solver_progress', []),
        'successful_inner_pass_count': sum(row.get('success') is True for row in passes),
        'failed_inner_pass_count': sum(row.get('success') is False for row in passes),
        'accepted_district_plan': False, 'accepted_completed_map': False,
    }


def verify_connections(
    collection: dict[str, Any], source_record: dict[str, Any], report: dict[str, Any],
    assignments: dict[str, int],
) -> None:
    """Check both authorized records and their district ownership independently."""
    expected = {
        'ny-water-liberty-001': ('recorded-water-connection', '360610001001001', True),
        'ny-exclave-ellis-001': ('recorded-exclave-connection', '360610001001000', False),
    }
    features, records = collection['features'], source_record['connections']
    if (len(features) != 2 or len(records) != 2
            or {f['properties']['id'] for f in features} != set(expected)
            or {r['id'] for r in records} != set(expected)):
        raise ValueError('New York must retain exactly the Liberty water and Ellis exclave links.')
    if (source_record['policy'] != POLICY
            or source_record['source_sha256'] != report['source']['archive_sha256']
            or records != report['recorded_connections']):
        raise ValueError('Saved connection provenance differs from the measured run.')
    by_id = {record['id']: record for record in records}
    for feature in features:
        p = feature['properties']
        source = by_id[p['id']]
        kind, island_geoid, water_only = expected[p['id']]
        if (p.get('kind') != kind or p.get('policy') != 'new-york-harbor-recorded-mixed-v1'
                or p.get('policy') != report['recorded_policy_audit']['policy']):
            raise ValueError('Liberty water / Ellis exclave classification was changed.')
        for key in ('kind', 'policy', 'component_ids', 'distance_m', 'endpoints', 'geographic_context', 'provenance'):
            if p.get(key) != source.get(key):
                raise ValueError(f'Exported connection differs from its source record: {key}')
        if ({e['geoid'] for e in p['endpoints']} != {island_geoid, '360610005000003'}
                or feature['geometry'] != {'type': 'LineString', 'coordinates': [e['coordinate'] for e in p['endpoints']]}):
            raise ValueError('Recorded link geometry or source endpoint identity changed.')
        labels = [assignments[e['geoid']] for e in p['endpoints']]
        used = p['used_by_district']
        if labels != p['endpoint_districts'] or type(used) is not int or labels != [used, used]:
            raise ValueError('Recorded endpoints do not belong to the same district in saved assignments.')
        context = p['geographic_context']
        if context['water_only'] is not water_only or context['crossed_state'] != 'New Jersey':
            raise ValueError('Recorded surface classification is inconsistent.')
        if (not math.isfinite(context['mapped_water_length_m']) or context['mapped_water_length_m'] <= 0
                or not math.isfinite(context['mapped_land_length_m']) or context['mapped_land_length_m'] < 0
                or (water_only and context['mapped_land_length_m'] > .01)
                or (not water_only and context['mapped_land_length_m'] <= 0)):
            raise ValueError('Recorded water and land lengths are inconsistent.')


def verify_source_policy(source_record: dict[str, Any], report: dict[str, Any], populations: dict[str, int]) -> dict[str, Any]:
    """Check source-level policy evidence independently of any district solve."""
    records = source_record['connections']
    audit, physical = report['recorded_policy_audit'], report['physical_part_graph']
    expected = {
        'ny-water-liberty-001': ('recorded-water-connection', '360610001001001', [0, 1], True),
        'ny-exclave-ellis-001': ('recorded-exclave-connection', '360610001001000', [0, 2], False),
    }
    if (source_record['policy'] != POLICY or source_record['source_sha256'] != report['source']['archive_sha256']
            or records != report['recorded_connections'] or len(records) != 2
            or {r['id'] for r in records} != set(expected)):
        raise ValueError('Saved source records differ from the authorized measured connections.')
    if (audit['policy'] != 'new-york-harbor-recorded-mixed-v1' or audit['district_count'] != report['district_count']
            or audit['state_fips'] != '36' or audit['source_geometry_modified'] is not False
            or audit['synthetic_ownership_edges'] is not False or audit['physical_component_count'] != 3
            or audit['augmented_component_count'] != 1 or audit['augmented_graph_connected'] is not True
            or audit['synthetic_edge_count'] != 2 or audit['block_count'] != BLOCKS
            or audit['source_population'] != TOTAL or audit['part_count'] != 288841
            or audit['connection_kind_counts'] != {'recorded-water-connection': 1, 'recorded-exclave-connection': 1}):
        raise ValueError('Saved source connectivity audit does not establish three physical components joined by two typed links.')
    if (physical['component_count'] != 3 or physical['node_count'] != audit['part_count']
            or physical['block_count'] != BLOCKS or physical['source_coordinates_modified'] is not False
            or physical['synthetic_ownership_edges'] is not False
            or audit['physical_edge_count'] != physical['edge_count']
            or audit['augmented_edge_count'] != physical['edge_count'] + 2):
        raise ValueError('Physical and augmented source graph counts are inconsistent.')
    if audit['provenance']['source_archive_sha256'] != report['source']['archive_sha256']:
        raise ValueError('Source policy provenance differs from the measured archive.')
    for record in records:
        kind, island, components, water_only = expected[record['id']]
        if (record['kind'] != kind or record['component_ids'] != components
                or record['policy'] != audit['policy']
                or {e['geoid'] for e in record['endpoints']} != {island, '360610005000003'}
                or record['provenance'] != audit['provenance']
                or record['geographic_context']['water_only'] is not water_only
                or record['geographic_context']['crossed_state'] != 'New Jersey'):
            raise ValueError('Source link identity, surface classification or provenance is inconsistent.')
        if any(populations.get(e['geoid']) != 0 for e in record['endpoints']):
            raise ValueError('The original DBF does not confirm zero population at the source endpoint blocks.')
        context = record['geographic_context']
        if (not math.isfinite(context['mapped_water_length_m']) or context['mapped_water_length_m'] <= 0
                or not math.isfinite(context['mapped_land_length_m']) or context['mapped_land_length_m'] < 0
                or (water_only and context['mapped_land_length_m'] > .01)
                or (not water_only and context['mapped_land_length_m'] <= 0)):
            raise ValueError('Source connection water/land lengths do not support their classifications.')
    if [(c['component_id'], c['population'], c['block_count']) for c in audit['components']] != [(0, TOTAL, BLOCKS - 2), (1, 0, 1), (2, 0, 1)]:
        raise ValueError('Source component population or block coverage is inconsistent.')
    return {'source_records_match_report': True, 'physical_component_count': 3,
            'augmented_component_count': 1, 'recorded_water_link_count': 1, 'recorded_exclave_link_count': 1,
            'source_geometry_modified': False, 'endpoint_populations_independently_verified_zero': True,
            'validation_scope': 'Saved source graph audit, immutable typed records and original DBF endpoints; not final district connectivity.'}


def load_run(k: int, populations: dict[str, int]) -> tuple[dict[str, Any], dict[str, str]]:
    directory = OUTPUT / f'states/36/districts-{k}'
    path = directory / 'benchmark.json'
    report = read_json(path)
    if report['state_fips'] != '36' or report['district_count'] != k or report['policy'] != POLICY:
        raise ValueError('Unexpected run identity or connectivity policy.')
    if report['status'] not in ('complete_under_recorded_mixed_policy', 'failed'):
        raise ValueError(f'K{k} is not terminal; no final comparison was written.')
    inventory = read_json(directory / 'preserved-file-inventory.json')
    required_flags = (
        'all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
        'national_suite_byte_identical', 'source_archive_byte_identical',
        'prior_policy_and_correction_evidence_byte_identical', 'run_code_unchanged',
    )
    if not all(report['preservation_audit'].get(key) is True for key in required_flags):
        raise ValueError(f'K{k} did not preserve historical evidence and measured code.')
    for name, expected in report['artifact_sha256'].items():
        if sha256(directory / name) != expected:
            raise ValueError(f'K{k} artifact changed: {name}')
    result = {key: report[key] for key in (
        'status', 'district_count', 'house_sizes', 'run_kind', 'configuration', 'source', 'code_sha256',
        'phases', 'timed_pipeline_wall_seconds', 'peak_process_working_set_bytes', 'preservation_audit',
        'started_at', 'finished_at',
    )}
    result.update({
        'url': BASE_URL + f'states/36/districts-{k}/',
        'benchmark_path': path.relative_to(ROOT).as_posix(), 'benchmark_sha256': sha256(path),
        'peak_working_set_mib': report['peak_process_working_set_bytes'] / 2**20,
    })
    source_record = read_json(directory / 'recorded-connections.json')
    result['source_connection_verification'] = verify_source_policy(source_record, report, populations)
    if report['status'] == 'failed':
        result.update({key: report.get(key) for key in ('error', 'failed_phase', 'optimizer_failure')})
        result['accepted_plan'] = False
        result['failure_details'] = failure_details(report)
        result['recorded_policy_audit'] = report.get('recorded_policy_audit')
        result['recorded_connections'] = report.get('recorded_connections', [])
        return result, inventory
    manifest = read_json(directory / 'maps/map-manifest.json')
    if manifest != report['maps']:
        raise ValueError('Saved map manifest differs from the benchmark report.')
    audit = manifest['connectivity_validation']
    if (audit['policy'] != POLICY or not audit['passed'] or not audit['source_coverage_preserved_exactly']
            or audit['source_geometry_modified'] or not report['final_plan']['all_districts_policy_connected']):
        raise ValueError('Independent mixed-link validation or exact source preservation failed.')
    if report['final_plan']['policy_part_components'] != [1] * k:
        raise ValueError('A completed district is disconnected in the augmented part graph.')
    if ([row['district_id'] for row in audit['districts']] != list(range(k))
            or any(row['connected_components_after_links'] != 1 for row in audit['districts'])):
        raise ValueError('A completed district failed independent polygon connectivity.')
    inner = [row['inner_optimizer'] for row in report['solver_progress'] if 'inner_optimizer' in row]
    if not inner or not all(row['success'] for row in inner) or not report['solver']['all_inner_optimizer_passes_succeeded']:
        raise ValueError('A completed plan contains an unsuccessful optimizer pass.')
    final = read_json(directory / 'solver-result.json')
    independent = verify_assignments(final['assignments'], populations, k, report['final_plan'])
    map_count = verify_compressed_maps(directory, manifest)
    outlines = json.loads(gzip.decompress((directory / 'maps/districts-national.geojson.gz').read_bytes()))
    properties = sorted((feature['properties'] for feature in outlines['features']), key=lambda row: row['district_id'])
    if ([row['district_id'] for row in properties] != list(range(k))
            or [row['population'] for row in properties] != independent['district_populations']
            or [row['block_count'] for row in properties] != independent['district_block_counts']):
        raise ValueError('Delivered map properties differ from independently recomputed district totals.')
    links = json.loads(gzip.decompress((directory / 'maps/recorded-connections.geojson.gz').read_bytes()))
    verify_connections(links, source_record, report, final['assignments'])
    result.update({
        'accepted_plan': True, 'input': report['input'], 'solver': report['solver'],
        'outer_termination': outer_termination(report['solver'], report['configuration']),
        'initial_plan': report['initial_plan'], 'after_repair_plan': report['after_repair_plan'],
        'final_plan': report['final_plan'], 'postprocessing': report['postprocessing'],
        'recorded_policy_audit': report['recorded_policy_audit'],
        'independent_population_audit': independent,
        'verified_compressed_map_artifact_count': map_count,
        'physical_polygon_components': [row['physical_polygon_components'] for row in audit['districts']],
        'policy_polygon_components': [row['connected_components_after_links'] for row in audit['districts']],
        'strict_polygon_validation': manifest['strict_validation'], 'policy_polygon_validation': audit,
        'connection_features': links['features'], 'recorded_connections': source_record['connections'],
        'selected_connection_count': len(links['features']), 'used_connection_count': sum(type(f['properties']['used_by_district']) is int for f in links['features']),
        'inner_optimizer_pass_count': len(inner), 'inner_optimizer_failed_pass_count': 0,
        'payloads': {key: manifest[key] for key in ('district_outlines', 'recorded_connections', 'load_scenarios')},
    })
    return result, inventory


def reconcile_execution(runs: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Reconcile first attempts without rewriting the stopped original manifest."""
    if len(runs) != len(COUNTS) or {run['district_count'] for run in runs} != set(COUNTS):
        raise ValueError('Every requested anchor must have one terminal benchmark.')
    original_path = OUTPUT / 'run.json'
    original = read_json(original_path)
    if original['status'] not in ('complete', 'stopped') or not original.get('finished_at'):
        raise ValueError('The original suite has not reached a terminal state.')
    original_jobs = {job['district_count']: job for job in original['jobs']}
    if len(original['jobs']) != len(COUNTS) or set(original_jobs) != set(COUNTS):
        raise ValueError('Original suite job universe differs from the requested anchors.')
    supplement_path = OUTPUT / 'supplemental-first-attempts.json'
    supplement = read_json(supplement_path) if supplement_path.is_file() else None
    supplemental_jobs: dict[int, Any] = {}
    if supplement is not None:
        if (supplement['status'] not in ('complete', 'stopped') or not supplement.get('finished_at')
                or supplement['attempt_kind'] != 'deferred_first_attempts'):
            raise ValueError('Supplemental first attempts are not terminal.')
        if supplement.get('original_attempt_preserved_byte_identically') is not True:
            raise ValueError('Supplemental execution did not verify original attempt preservation.')
        if supplement['original_run_manifest']['sha256'] != sha256(original_path):
            raise ValueError('The original suite manifest differs from the preserved supplemental reference.')
        if supplement['original_code_sha256'] != original['code_sha256']:
            raise ValueError('Supplemental attempts used a different original code snapshot.')
        supplemental_jobs = {job['district_count']: job for job in supplement['jobs']}
        if len(supplemental_jobs) != len(supplement['jobs']) or set(supplemental_jobs) != {35, 42, 61}:
            raise ValueError('Supplemental first attempts do not match the three unstarted anchors.')
        for name, expected in supplement['preserved_original_attempt_inventory'].items():
            if sha256(ROOT / name) != expected:
                raise ValueError(f'Original attempt evidence changed: {name}')
    jobs = []
    for run in runs:
        k = run['district_count']
        job = original_jobs[k]
        source = 'original_suite'
        if k in supplemental_jobs:
            if job['status'] != 'pending' or 'pid' in job or 'started_at' in job:
                raise ValueError('A supplemental entry would retry an already started original attempt.')
            job, source = supplemental_jobs[k], 'deferred_first_attempt'
            validation = job.get('terminal_validation', {})
            expected_classification = 'complete' if run['accepted_plan'] else 'numerical_failure'
            if (job.get('attempt_kind') != 'deferred_first_attempt'
                    or validation.get('passed') is not True or validation.get('preservation_verified') is not True
                    or validation.get('code_unchanged') is not True
                    or validation.get('classification') != expected_classification):
                raise ValueError('Supplemental terminal validation does not establish the saved outcome.')
        if (job['status'] != run['status'] or job.get('benchmark_sha256') != run['benchmark_sha256']
                or not job.get('finished_at') or type(job.get('exit_code')) is not int):
            raise ValueError('Terminal child metadata does not match its saved benchmark.')
        if (job['exit_code'] == 0) != run['accepted_plan']:
            raise ValueError('Child exit code and accepted-plan status disagree.')
        if any(original['code_sha256'].get(name) != digest for name, digest in run['code_sha256'].items()):
            raise ValueError('A benchmark used code outside the preserved original snapshot.')
        jobs.append({**job, 'execution_source': source})
    return {
        'original_manifest_path': original_path.as_posix(), 'original_manifest_sha256': sha256(original_path),
        'original_status': original['status'], 'original_elapsed_wall_seconds': original['elapsed_wall_seconds'],
        'supplemental_manifest_path': supplement_path.as_posix() if supplement else None,
        'supplemental_manifest_sha256': sha256(supplement_path) if supplement else None,
        'supplemental_status': supplement['status'] if supplement else None,
        'supplemental_elapsed_wall_seconds': supplement['elapsed_wall_seconds'] if supplement else None,
        'all_requested_attempts_terminal': True, 'original_manifest_preserved': True,
        'no_prior_attempt_retried': True, 'jobs': jobs,
        'note': 'A terminal attempt may be failed. Supplemental jobs are first attempts for originally unstarted anchors; the failed original attempt is retained without retry.',
    }


def summary(validation_note: str) -> dict[str, Any]:
    identities = [read_json(OUTPUT / f'states/36/districts-{k}/benchmark.json') for k in COUNTS]
    if len({report['source']['archive_sha256'] for report in identities}) != 1:
        raise ValueError('Plans used different source archives.')
    populations = source_populations(identities[0]['source']['archive_sha256'])
    runs, inventories = zip(*(load_run(k, populations) for k in COUNTS), strict=True)
    execution = reconcile_execution(runs)
    merged: dict[str, str] = {}
    for inventory in inventories:
        for name, expected in inventory.items():
            if name in merged and merged[name] != expected:
                raise ValueError('Runs disagree about protected evidence identity.')
            merged[name] = expected
    for name, expected in merged.items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f'Preserved evidence changed: {name}')
    complete = [run for run in runs if run['accepted_plan']]
    if any(run['code_sha256'] != runs[0]['code_sha256'] for run in runs[1:]):
        raise ValueError('Runs did not use the same frozen code.')
    changing_keys = {'minimum_district_population_for_root_classification', 'minimum_district_population_exact'}
    settings = [{name: value for name, value in run['configuration'].items() if name not in changing_keys} for run in runs]
    if any(configuration != settings[0] for configuration in settings[1:]):
        raise ValueError('Optimizer or policy settings changed between district counts.')
    recorded = [run['recorded_connections'] for run in runs if run.get('recorded_connections')]
    if not recorded or any(records != recorded[0] for records in recorded[1:]):
        raise ValueError('Attempt connection records are unavailable or inconsistent.')
    if complete:
        if any(run['recorded_connections'] != complete[0]['recorded_connections'] for run in complete[1:]):
            raise ValueError('The immutable connection record changed between district counts.')
        first = {f['properties']['id']: f for f in complete[0]['connection_features']}
        for run in complete[1:]:
            for candidate in run['connection_features']:
                reference = first[candidate['properties']['id']]
                if candidate['geometry'] != reference['geometry'] or candidate['properties']['endpoints'] != reference['properties']['endpoints']:
                    raise ValueError('Connection geometry or source endpoint identity changed.')
    strict_path = SUITE / 'states/36/districts-26/benchmark.json'
    strict = read_json(strict_path)
    if strict['status'] != 'unsupported_topology':
        raise ValueError('Original strict topology exception changed.')
    water_path = SUITE / 'diagnostics/new-york/geography-context.json'
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'New York K26/K35/K42/K61 for House sizes 435/574/692/1000; recorded Liberty water and Ellis exclave links.',
        'policy': POLICY, 'total_population': TOTAL, 'block_count': BLOCKS,
        'runs': list(runs), 'complete_plan_count': len(complete), 'failed_plan_count': len(runs) - len(complete),
        'execution_audit': execution, 'recorded_connections': recorded[0],
        'source_connections_url': BASE_URL + 'connections/',
        'outer_convergence': outer_convergence_overview(runs),
        'validation_note': validation_note, 'preserved_historical_file_count': len(merged),
        'source_population_audit': {'archive': SOURCE.relative_to(ROOT).as_posix(),
            'archive_sha256': identities[0]['source']['archive_sha256'], 'all_source_dbf_geoids_unique': True,
            'source_block_count': len(populations), 'source_population': sum(populations.values())},
        'same_recorded_connection_across_completed_plans': bool(complete),
        'strict_baseline': {'status': strict['status'], 'benchmark_path': strict_path.relative_to(ROOT).as_posix(),
            'benchmark_sha256': sha256(strict_path), 'preflight_wall_seconds': strict['timed_pipeline_wall_seconds'],
            'solver_executed': False, 'district_plan_exists': False,
            'note': 'K35/K42/K61 reused the K26 source-topology rejection. No prior strict solver runtimes or population results exist.'},
        'crossing_audit': {'path': water_path.relative_to(ROOT).as_posix(), 'sha256': sha256(water_path),
            'record': read_json(water_path)},
        'measurement_notes': [
            'New plans run serially in fresh processes with cached source and part graphs; shared-desktop timings are observations, not isolated hardware comparisons.',
            'For accepted plans, pipeline time includes source and link preparation, solving, repair/rebalance, independent polygon validation, map export, viewer generation and preservation checks. For failed attempts it measures only work through the failed phase plus failure cleanup/preservation; unexecuted repair or export phases are not included.',
            'Process imports, initial preservation inventory and final report flush are outside the pipeline timer.',
            'Strict topology rejection happened before solving; it is not a before/after solver-performance baseline.',
            'Physical shared-edge connectivity and policy connectivity are separate. Liberty uses a water link; Ellis uses an explicit exclave link over New Jersey land and water. No New Jersey area or population is assigned.',
            'Only accepted-plan population deviations are independently recomputed from source DBF and final assignments. Failed attempts have no accepted final balance or district-connectivity measurement. Local whole-block balancing does not establish global optimality.',
            'Successful inner optimizer passes, outer center convergence, final postprocessed population balance and policy connectivity are independent outcomes. Outer iteration-limit cases are disclosed explicitly.',
            'Compressed payloads measure saved map bytes, not browser memory or latency. New Jersey diagnostic context loads only on connection/harbor inspection and is separate from the map export sizes.',
        ],
    }


def seconds(run: dict[str, Any], phase: str) -> float | None:
    item = run['phases'].get(phase)
    return float(item['wall_seconds']) if item else None


def display(value: float | None, digits: int = 2) -> str:
    return '—' if value is None else f'{value:,.{digits}f}'


def table_cells(run: dict[str, Any]) -> list[str]:
    final = run.get('final_plan', {})
    return [
        ' / '.join(str(value) for value in run['house_sizes']), str(run['district_count']),
        f'{final["max_absolute_deviation_people"]:,.3f}' if final else 'No accepted plan',
        f'{final["max_absolute_deviation_percent"]:.6f}%' if final else '—',
        display(run['timed_pipeline_wall_seconds']), display(seconds(run, 'solve'), 3),
        display(run['peak_working_set_mib'], 1),
        f'{run["district_count"]}/{run["district_count"]}' if run['accepted_plan'] else 'Not evaluated',
    ]


def connection_ownership(run: dict[str, Any]) -> str:
    labels = {'recorded-water-connection': 'Liberty water link', 'recorded-exclave-connection': 'Ellis exclave link'}
    return '; '.join(f"{labels[f['properties']['kind']]}: District {f['properties']['used_by_district'] + 1}"
                     for f in run['connection_features'])


def validation_scope(data: dict[str, Any]) -> str:
    text = ('Independently read the original DBF, checked official source totals and zero-population endpoint blocks, '
            'matched both typed connection records and provenance to each report, checked the saved source graph audits '
            '(three physical components, two recorded links, one augmented component), '
            f'and verified {data["preserved_historical_file_count"]} preserved historical file hashes. ')
    accepted, failed = data['complete_plan_count'], data['failed_plan_count']
    if accepted:
        text += (f'For {accepted} accepted plans, additionally verified exact final GEOID assignment coverage, '
                 'recomputed final populations, checked compressed-map sizes/content hashes, same-district endpoints '
                 'and final policy graph/polygon audits. ')
    if failed:
        text += (f'For {failed} failed attempts, checked recorded failure and execution evidence. '
                 'No final assignment coverage, population balance, compressed district map or district-connectivity '
                 'validation is claimed for those attempts.')
    return text


def markdown(data: dict[str, Any]) -> str:
    rows = ['| House size | Districts | Max deviation (people) | Max deviation (%) | Pipeline (s) | Solve (s) | Peak MiB | Policy-connected |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    rows += ['| ' + ' | '.join(table_cells(run)) + ' |' for run in data['runs']]
    text = [
        '# New York recorded harbor links benchmark', '',
        f'{data["complete_plan_count"]} accepted plans; {data["failed_plan_count"]} failed attempts. '
        f'The independently checked input has {BLOCKS:,} source blocks and {TOTAL:,} residents.', '',
        '[Open comparison and maps](' + BASE_URL + ')', '', *rows, '',
        '[Inspect the recorded source connections](' + BASE_URL + 'connections/). This source map does not assign district labels.', '',
        *['**Outer convergence caveat:** ' + note + '\n' for note in data['outer_convergence']['disclosures']],
        '## Two explicit geographic connections', '',
        'Liberty Island uses a recorded 795 m water connection. New York’s Ellis Island block uses a recorded 852 m exclave connection: '
        'about 827 m of mapped harbor water and 26 m of New Jersey land. Both island blocks have zero resident population and connect to the '
        'same New York water block. The records grant graph adjacency only; no New Jersey territory or population is assigned and no source '
        'geometry changes. Each link contributes only when its endpoint blocks belong to the same district. Physical and policy connectivity remain distinct.', '',
    ]
    for run in data['runs']:
        k = run['district_count']
        text += [f'### {k} districts', '']
        if not run['accepted_plan']:
            text += [run['failure_details']['disclosure'], '',
                     f'[Preserved failed report]({(ROOT / run["benchmark_path"]).as_posix()}) · '
                     '[Source connections map](' + BASE_URL + 'connections/)', '']
            continue
        text += [
            f'[Map]({run["url"]}) · [Saved benchmark]({(ROOT / run["benchmark_path"]).as_posix()})', '',
            'District population range: ' + f'{min(run["final_plan"]["district_populations"]):,}–{max(run["final_plan"]["district_populations"]):,}. '
            'Full population and block-count arrays are in the machine-readable comparison.', '',
            f'Physical polygon components by district: {run["physical_polygon_components"]}. '
            f'Components after eligible recorded links: {run["policy_polygon_components"]}. '
            + connection_ownership(run) + '. Endpoint ownership is independently checked against final assignments.', '',
            f'All {run["inner_optimizer_pass_count"]} inner optimizer passes succeeded. '
            f'{run["outer_termination"]["disclosure"]}', '',
            f'Postprocessing stopped at `{run["postprocessing"]["stop_reason"]}`. '
            f'Repair / part-repair / rebalance moves: {run["postprocessing"]["repair_move_count"]} / '
            f'{run["postprocessing"]["part_repair_move_count"]} / {run["postprocessing"]["rebalance_move_count"]}.', '',
            'Compressed district outlines: ' + ' / '.join(
                f'{level}: {run["payloads"]["district_outlines"][level]["gzip_bytes"]/1024:.1f} KiB'
                for level in ('national', 'state', 'full')) + '. '
            f'Recorded links: {run["payloads"]["recorded_connections"]["gzip_bytes"]:,} bytes.', '',
        ]
    text += ['## Strict baseline and interpretation', '',
        'The preserved strict K26 attempt stopped at source-topology preflight after '
        f'{data["strict_baseline"]["preflight_wall_seconds"]:.7f} seconds. '
        'K35/K42/K61 reused that exception. No prior strict solver runtimes or solved populations exist; this is not a before/after solver speed comparison.', '',
        '## Validation and timing limits', '',
        validation_scope(data), '',
        data['validation_note'], '', *['- ' + note for note in data['measurement_notes']], '',
        '[Water / land audit](' + (ROOT / data['crossing_audit']['path']).as_posix() + ') · '
        '[Original diagnosis](http://127.0.0.1:8770/diagnostics/new-york/) · '
        '[Machine-readable comparison](' + REPORT.with_suffix('.json').as_posix() + ')', '',
    ]
    execution = data.get('execution_audit')
    if execution:
        text += ['## Attempt history', '',
                 f'Original suite: `{execution["original_status"]}`, {execution["original_elapsed_wall_seconds"]:.3f} s. '
                 'Its manifest and first attempted plan remain preserved.', '']
        if execution['supplemental_status']:
            text += [f'Supplemental first attempts: `{execution["supplemental_status"]}`, '
                     f'{execution["supplemental_elapsed_wall_seconds"]:.3f} s. '
                     'These attempted previously unstarted district counts with unchanged code and settings; they did not retry K26.', '']
        text += [execution['note'], '']
    return '\n'.join(text)


def html(data: dict[str, Any]) -> str:
    metric_rows = ''.join('<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in table_cells(run)) + '</tr>' for run in data['runs'])
    cards, payload_rows = '', ''
    for run in data['runs']:
        k = run['district_count']
        if not run['accepted_plan']:
            cards += f'<article><div class="eyebrow">House {" / ".join(str(x) for x in run["house_sizes"])}</div><h2>{k} districts · failed</h2><p>{escape(run["failure_details"]["disclosure"])}</p><p><a href="states/36/districts-{k}/benchmark.json">Preserved failure report</a> · <a href="connections/">Recorded source connections map</a></p><p class="note">{run["timed_pipeline_wall_seconds"]:.2f} s measured attempt; {run["peak_working_set_mib"]:.1f} MiB peak process working set. No completed district map.</p></article>'
            continue
        final, p = run['final_plan'], run['payloads']
        cards += f'''<article><div class="eyebrow">House {' / '.join(str(x) for x in run['house_sizes'])}</div>
<h2><a href="states/36/districts-{k}/">{k} districts →</a></h2><p class="large">{final['max_absolute_deviation_people']:,.3f} <small>people from ideal, maximum</small></p>
<p class="muted">{final['max_absolute_deviation_percent']:.6f}% deviation · {run['timed_pipeline_wall_seconds']:.2f} s full pipeline</p>
<p>Population range: {min(final['district_populations']):,}–{max(final['district_populations']):,}.</p>
<p>{escape(connection_ownership(run))}.</p>
<p class="note">Physical polygon pieces: {escape(str(run['physical_polygon_components']))}. All {k} districts pass policy graph and independent polygon checks.</p>
<p class="note">All {run['inner_optimizer_pass_count']} inner optimizer passes succeeded. {escape(run['outer_termination']['disclosure'])}</p>
<p class="note">Postprocessing stopped at {escape(run['postprocessing']['stop_reason'])}.</p></article>'''
        payload_rows += '<tr><td>' + str(k) + '</td>' + ''.join(
            f'<td>{p["district_outlines"][level]["gzip_bytes"]/1024:,.1f} KiB</td>' for level in ('national', 'state', 'full')) + f'<td>{p["recorded_connections"]["gzip_bytes"]:,} B</td></tr>'
    convergence_notice = ''.join('<div class="callout"><strong>Outer convergence caveat.</strong> ' + escape(note) + '</div>' for note in data['outer_convergence']['disclosures'])
    if not payload_rows:
        payload_rows = '<tr><td colspan="5">No completed district map payloads were generated. The source-connections map remains available.</td></tr>'
    execution = data.get('execution_audit')
    history = ''
    if execution:
        history = f'<h2>Preserved attempt history</h2><p>Original suite: {escape(execution["original_status"])} after {execution["original_elapsed_wall_seconds"]:.2f} s. Its original manifest is unchanged.</p>'
        if execution['supplemental_status']:
            history += f'<p>Supplemental first attempts: {escape(execution["supplemental_status"])} after {execution["supplemental_elapsed_wall_seconds"]:.2f} s. Previously unstarted counts were attempted serially with unchanged code and settings. K26 was not retried.</p>'
        history += '<p class="note">' + escape(execution['note']) + '</p>'
    connectivity_outcome = (
        'Each accepted plan passes both the augmented polygon-part graph and an independent dissolved-polygon check '
        'that requires same-district link endpoints. Local whole-block rebalancing does not establish a global population optimum.'
        if data['complete_plan_count'] else
        'The source-level audit joins three physical components into one augmented graph, but the optimizer returned no validated district plans. '
        'Final population balance and district connectivity were not evaluated; source-graph connectivity alone does not establish a valid district partition.'
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>New York · Recorded harbor plans</title><style>
:root{{color-scheme:dark;--bg:#111b24;--panel:#192832;--ink:#edf4f4;--muted:#a5bdc9;--line:#344d5b;--accent:#72ddd4;--amber:#ffcc7d}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,sans-serif}}main{{max-width:1260px;margin:auto;padding:28px 32px 45px}}a{{color:var(--accent)}}h1{{font-size:36px;line-height:1.15;margin:10px 0 15px}}h2{{font-size:20px;margin:8px 0 12px}}p{{margin:0 0 14px}}.eyebrow{{font:11px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-top:18px}}.muted,.note{{color:var(--muted)}}.note{{font-size:12px;overflow-wrap:anywhere}}.callout{{border-left:3px solid var(--amber);padding:16px 20px;background:#2b2c29;margin:22px 0}}.callout strong{{color:var(--amber)}}.cards{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:24px 0}}article{{background:var(--panel);border:1px solid var(--line);padding:17px 20px}}article .eyebrow{{margin-top:0}}.large{{font-size:28px;font-variant-numeric:tabular-nums}}.large small{{font-size:12px;color:var(--muted)}}.table-wrap{{overflow:auto;margin:16px 0 25px}}table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th{{font-size:10px;color:var(--muted);text-transform:uppercase}}th:first-child,td:first-child{{text-align:left}}footer{{border-top:1px solid var(--line);padding-top:20px;margin-top:25px}}@media(max-width:760px){{main{{padding:20px}}h1{{font-size:28px}}.cards{{grid-template-columns:1fr}}}}</style></head><body><main>
<a href="../../">← National benchmark results</a><p class="eyebrow">New York / 2020 census blocks / Recorded harbor links</p>
<h1>Two explicit connections. Four district-count anchors.</h1>
<p class="muted">{data['complete_plan_count']} accepted plans · {data['failed_plan_count']} failed attempts. Verified source: {BLOCKS:,} New York blocks and {TOTAL:,} residents. Population balance, physical geometry, and connectivity under recorded links are separate outcomes.</p>
<div class="callout"><strong>Liberty and Ellis remain physically separate.</strong> Liberty’s 795 m link is mapped water-only. Ellis’s 852 m exclave link crosses about 827 m of water and 26 m of New Jersey land. Neither link assigns New Jersey territory or population to New York districts. <a href="../../diagnostics/new-york/">Inspect the original diagnosis</a>.</div>
<p><a href="connections/">Open the recorded source connections map →</a> <span class="note">Shows the approved links and unchanged source blocks, without district labels.</span></p>
<div class="table-wrap"><table><thead><tr><th>House size</th><th>Districts</th><th>Max deviation, people</th><th>Max deviation, %</th><th>Pipeline, s</th><th>Solve, s</th><th>Peak MiB</th><th>Policy-connected</th></tr></thead><tbody>{metric_rows}</tbody></table></div>
{convergence_notice}
<p class="note">Maximum deviation is available only for accepted plans and uses the fractional statewide ideal. Accepted-plan pipeline time includes preparation, solve, repair/rebalance, validation and export. Failed-attempt time ends at the failed phase plus cleanup/preservation; later phases did not run. Serial shared-desktop observations are not isolated hardware comparisons.</p>
<div class="cards">{cards}</div>
{history}
<h2>What changed from strict connectivity?</h2><p>The original strict run stopped before solving because New York has three source components: the main coverage and two zero-population island blocks. Its {data['strict_baseline']['preflight_wall_seconds']:.2f}-second preflight rejection was reused at the other district counts. There are no strict solved populations or solver timings for a before/after comparison.</p>
<p class="muted">{connectivity_outcome}</p>
<h2>Compressed map payloads</h2><div class="table-wrap"><table><thead><tr><th>Districts</th><th>National outlines</th><th>State outlines</th><th>Exact outlines</th><th>Recorded links</th></tr></thead><tbody>{payload_rows}</tbody></table></div>
<p class="note">Saved gzip bytes, not latency or browser memory. County blocks load only on request. New Jersey land/water context and exact endpoint blocks load on harbor inspection; those diagnostic resources are separate from these export sizes.</p>
<footer><p><a href="comparison.json">Validated comparison JSON</a> · <a href="../../diagnostics/new-york/geography-context.json">Water / land audit</a> · <a href="../../states/36/districts-26/benchmark.json">Preserved strict exception</a></p>
<p class="note">{escape(validation_scope(data))} {escape(data['validation_note'])}</p></footer></main></body></html>'''


def source_connections_html(data: dict[str, Any]) -> str:
    template = (ROOT / 'scripts/assets/new-york-recorded-connections-viewer.html').read_text(encoding='utf-8')
    # Reuse the existing local D3 dependencies, without changing the frozen viewer.
    saved_viewer = (ROOT / 'scripts/assets/new-york-block-viewer.html').read_text(encoding='utf-8')
    scripts = re.findall(r'<script>([\s\S]*?)</script>', saved_viewer)
    if len(scripts) != 3:
        raise ValueError('Expected the two local D3 libraries and the frozen viewer program.')
    libraries = '\n'.join('<script>' + script + '</script>' for script in scripts[:2])
    count = data['complete_plan_count']
    status = ('None of the four attempts produced a validated district plan.' if not count else
              f'{count} accepted district plans are linked from the comparison page; this map shows source connectivity only.')
    return template.replace('__D3_SCRIPTS__', libraries).replace('__PLAN_STATUS__', escape(status))


def write_outputs(data: dict[str, Any]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    connection_page = source_connections_html(data)
    connections = OUTPUT / 'connections'
    connections.mkdir(exist_ok=True)
    (connections / 'recorded-connections.json').write_text(json.dumps({
        'policy': POLICY, 'map_kind': 'source_connections_no_district_plan',
        'source_sha256': data['source_population_audit']['archive_sha256'],
        'connections': data['recorded_connections'],
    }, indent=2) + '\n', encoding='utf-8')
    (connections / 'index.html').write_text(connection_page, encoding='utf-8')
    encoded = json.dumps(data, indent=2) + '\n'
    (OUTPUT / 'comparison.json').write_text(encoded, encoding='utf-8')
    (OUTPUT / 'index.html').write_text(html(data), encoding='utf-8')
    REPORT.with_suffix('.json').write_text(encoded, encoding='utf-8')
    REPORT.with_suffix('.md').write_text(markdown(data), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', default='Saved evidence verified by the summary generator; browser checks are reported separately.')
    args = parser.parse_args()
    result = summary(args.validation_note)
    write_outputs(result)
    print(f'{result["complete_plan_count"]} complete / {result["failed_plan_count"]} failed; wrote {REPORT.with_suffix(".md")}')
