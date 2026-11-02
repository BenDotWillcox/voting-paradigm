"""Independently verify and summarize terminal Kentucky exclave-policy plans.

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
from typing import Any
import zipfile

import shapefile


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'policies/kentucky-exclave-v1'
SOURCE = ROOT / '.cache/state-block-benchmark/source/21/tl_2020_21_tabblock20.zip'
REPORT = ROOT / 'prompts/kentucky-exclave-benchmark'
BASE_URL = 'http://127.0.0.1:8770/policies/kentucky-exclave-v1/'
POLICY = 'shared_edges_plus_recorded_exclave_connections'
COUNTS = (6, 8, 9, 14)
TOTAL = 4505836
BLOCKS = 132662


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
        raise ValueError('Kentucky source archive does not match the measured run.')
    with zipfile.ZipFile(SOURCE) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith('.dbf')]
        if len(candidates) != 1:
            raise ValueError('Expected one source DBF in the Kentucky archive.')
        raw = archive.read(candidates[0])
    populations: dict[str, int] = {}
    with shapefile.Reader(dbf=io.BytesIO(raw)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        geoid_column, population_column = fields.index('GEOID20'), fields.index('POP20')
        for record in reader.iterRecords():
            geoid, value = str(record[geoid_column]), record[population_column]
            if geoid in populations or len(geoid) != 15 or not geoid.startswith('21'):
                raise ValueError('Duplicate or non-Kentucky GEOID in the source DBF.')
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


def load_run(k: int, populations: dict[str, int]) -> tuple[dict[str, Any], dict[str, str]]:
    directory = OUTPUT / f'states/21/districts-{k}'
    path = directory / 'benchmark.json'
    report = read_json(path)
    if report['state_fips'] != '21' or report['district_count'] != k or report['policy'] != POLICY:
        raise ValueError('Unexpected run identity or connectivity policy.')
    if report['status'] not in ('complete_under_exclave_policy', 'failed'):
        raise ValueError(f'K{k} is not terminal; no final comparison was written.')
    inventory = read_json(directory / 'preserved-file-inventory.json')
    required_flags = (
        'all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
        'national_suite_byte_identical', 'source_archive_byte_identical',
        'rhode_island_and_hawaii_evidence_byte_identical', 'run_code_unchanged',
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
        'url': BASE_URL + f'states/21/districts-{k}/',
        'benchmark_path': path.relative_to(ROOT).as_posix(), 'benchmark_sha256': sha256(path),
        'peak_working_set_mib': report['peak_process_working_set_bytes'] / 2**20,
    })
    if report['status'] == 'failed':
        result.update({key: report.get(key) for key in ('error', 'failed_phase', 'optimizer_failure')})
        result['accepted_plan'] = False
        return result, inventory
    manifest = read_json(directory / 'maps/map-manifest.json')
    if manifest != report['maps']:
        raise ValueError('Saved map manifest differs from the benchmark report.')
    audit = manifest['connectivity_validation']
    if (audit['policy'] != POLICY or not audit['passed'] or not audit['source_coverage_preserved_exactly']
            or audit['source_geometry_modified'] or not report['final_plan']['all_districts_policy_connected']):
        raise ValueError('Independent exclave-policy validation or exact source preservation failed.')
    if any(value != 1 for value in report['final_plan']['policy_part_components']):
        raise ValueError('A completed district is disconnected in the augmented part graph.')
    if len(audit['districts']) != k or any(row['connected_components_after_links'] != 1 for row in audit['districts']):
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
    links = json.loads(gzip.decompress((directory / 'maps/exclave-connections.geojson.gz').read_bytes()))
    if len(links['features']) != 1:
        raise ValueError('Kentucky must retain exactly one recorded exclave connection.')
    source_record = read_json(directory / 'exclave-connections.json')
    if source_record['policy'] != POLICY or source_record['source_sha256'] != report['source']['archive_sha256']:
        raise ValueError('Saved connection provenance is inconsistent.')
    for feature in links['features']:
        p = feature['properties']
        endpoint_labels = [final['assignments'][endpoint['geoid']] for endpoint in p['endpoints']]
        used = p['used_by_district']
        if endpoint_labels != p['endpoint_districts']:
            raise ValueError('Exported endpoint ownership differs from final assignments.')
        if type(used) is not int or endpoint_labels != [used, used]:
            raise ValueError('The exclave link is not owned by one district at both endpoints.')
        if (p.get('policy') != source_record['connections'][0]['policy']
                or p.get('policy') != report['exclave_policy_audit']['policy']
                or p.get('kind') != 'recorded-exclave-connection'):
            raise ValueError('Exported connection is not labeled as an explicit exclave exception.')
    result.update({
        'accepted_plan': True, 'input': report['input'], 'solver': report['solver'],
        'outer_termination': outer_termination(report['solver'], report['configuration']),
        'initial_plan': report['initial_plan'], 'after_repair_plan': report['after_repair_plan'],
        'final_plan': report['final_plan'], 'postprocessing': report['postprocessing'],
        'exclave_policy_audit': report['exclave_policy_audit'],
        'independent_population_audit': independent,
        'verified_compressed_map_artifact_count': map_count,
        'physical_polygon_components': [row['physical_polygon_components'] for row in audit['districts']],
        'policy_polygon_components': [row['connected_components_after_links'] for row in audit['districts']],
        'strict_polygon_validation': manifest['strict_validation'], 'policy_polygon_validation': audit,
        'connection_features': links['features'], 'recorded_connections': source_record['connections'],
        'selected_connection_count': len(links['features']), 'used_connection_count': 1,
        'inner_optimizer_pass_count': len(inner), 'inner_optimizer_failed_pass_count': 0,
        'payloads': {key: manifest[key] for key in ('district_outlines', 'exclave_connections', 'load_scenarios')},
    })
    return result, inventory


def summary(validation_note: str) -> dict[str, Any]:
    identities = [read_json(OUTPUT / f'states/21/districts-{k}/benchmark.json') for k in COUNTS]
    if len({report['source']['archive_sha256'] for report in identities}) != 1:
        raise ValueError('Plans used different source archives.')
    populations = source_populations(identities[0]['source']['archive_sha256'])
    runs, inventories = zip(*(load_run(k, populations) for k in COUNTS), strict=True)
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
    if complete:
        if any(run['recorded_connections'] != complete[0]['recorded_connections'] for run in complete[1:]):
            raise ValueError('The immutable connection record changed between district counts.')
        first = complete[0]['connection_features'][0]
        for run in complete[1:]:
            candidate = run['connection_features'][0]
            if candidate['geometry'] != first['geometry'] or candidate['properties']['endpoints'] != first['properties']['endpoints']:
                raise ValueError('Connection geometry or source endpoint identity changed.')
    strict_path = SUITE / 'states/21/districts-6/benchmark.json'
    strict = read_json(strict_path)
    if strict['status'] != 'unsupported_topology':
        raise ValueError('Original strict topology exception changed.')
    water_path = SUITE / 'diagnostics/kentucky/area-water-audit.json'
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Kentucky K6/K8/K9/K14 for House sizes 435/574/692/1000; new recorded-exclave policy.',
        'policy': POLICY, 'total_population': TOTAL, 'block_count': BLOCKS,
        'runs': list(runs), 'complete_plan_count': len(complete), 'failed_plan_count': len(runs) - len(complete),
        'outer_convergence': outer_convergence_overview(runs),
        'validation_note': validation_note, 'preserved_historical_file_count': len(merged),
        'source_population_audit': {'archive': SOURCE.relative_to(ROOT).as_posix(),
            'archive_sha256': identities[0]['source']['archive_sha256'], 'all_source_dbf_geoids_unique': True,
            'source_block_count': len(populations), 'source_population': sum(populations.values())},
        'same_recorded_connection_across_completed_plans': True,
        'strict_baseline': {'status': strict['status'], 'benchmark_path': strict_path.relative_to(ROOT).as_posix(),
            'benchmark_sha256': sha256(strict_path), 'preflight_wall_seconds': strict['timed_pipeline_wall_seconds'],
            'solver_executed': False, 'district_plan_exists': False,
            'note': 'K8/K9/K14 reused the K6 source-topology rejection. No prior strict solver runtimes or population results exist.'},
        'crossing_audit': {'path': water_path.relative_to(ROOT).as_posix(), 'sha256': sha256(water_path),
            'record': read_json(water_path)},
        'measurement_notes': [
            'New plans run serially in fresh processes with cached source and part graphs; shared-desktop timings are observations, not isolated hardware comparisons.',
            'Full pipeline includes source preparation, link preparation, solve, repair/rebalance, independent polygon validation, map export, viewer generation and preservation checks.',
            'Process imports, initial preservation inventory and final report flush are outside the pipeline timer.',
            'Strict topology rejection happened before solving; it is not a before/after solver-performance baseline.',
            'Physical shared-edge connectivity and policy connectivity are separate. The recorded exclave connection crosses Missouri land and water; no Missouri area or population is assigned.',
            'Population deviations are independently recomputed from source DBF and final assignments. Local whole-block balancing does not establish global optimality.',
            'Successful inner optimizer passes, outer center convergence, final postprocessed population balance and policy connectivity are independent outcomes. Outer iteration-limit cases are disclosed explicitly.',
            'Compressed payloads measure saved map bytes, not browser memory or latency. Missouri diagnostic context loads only on connection/Bend inspection and is separate from the map export sizes.',
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
        f'{run["district_count"]}/{run["district_count"]}' if run['accepted_plan'] else 'Failed',
    ]


def markdown(data: dict[str, Any]) -> str:
    rows = ['| House size | Districts | Max deviation (people) | Max deviation (%) | Pipeline (s) | Solve (s) | Peak MiB | Policy-connected |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    rows += ['| ' + ' | '.join(table_cells(run)) + ' |' for run in data['runs']]
    crossing = data['crossing_audit']['record']
    text = [
        '# Kentucky recorded-exclave benchmark', '',
        f'{data["complete_plan_count"]} accepted plans; {data["failed_plan_count"]} failed attempts. '
        f'All {BLOCKS:,} source blocks and {TOTAL:,} residents were retained in every accepted plan.', '',
        '[Open comparison and maps](' + BASE_URL + ')', '', *rows, '',
        *['**Outer convergence caveat:** ' + note + '\n'
          for note in data['outer_convergence']['disclosures']],
        '## Connectivity and the geographic exception', '',
        f'The same recorded Kentucky Bend connection spans {crossing["candidate_planar_length_m"]/1000:.3f} km: '
        f'{crossing["mapped_water_length_m"]/1000:.3f} km of 2020 mapped river water and '
        f'{crossing["outside_mapped_water_length_m"]/1000:.3f} km of Missouri land. '
        'It is explicitly an exclave graph connection, not a water-only route or a change to district territory. '
        'Missouri coverage appears only as context. Physical and policy polygon counts below remain distinct.', '',
    ]
    for run in data['runs']:
        k = run['district_count']
        text += [f'### {k} districts', '']
        if not run['accepted_plan']:
            text += [f'Failed during `{run.get("failed_phase")}`: {run.get("error")}', '']
            continue
        text += [
            f'[Map]({run["url"]}) · [Saved benchmark]({(ROOT / run["benchmark_path"]).as_posix()})', '',
            'Populations: ' + ' / '.join(f'{n:,}' for n in run['final_plan']['district_populations']) + '.', '',
            f'Physical polygon components by district: {run["physical_polygon_components"]}. '
            f'Components after the recorded connection: {run["policy_polygon_components"]}. '
            f'The one link is used by District {run["connection_features"][0]["properties"]["used_by_district"] + 1}; '
            'both endpoint GEOIDs independently match that district in final assignments.', '',
            f'All {run["inner_optimizer_pass_count"]} inner optimizer passes succeeded. '
            f'{run["outer_termination"]["disclosure"]}', '',
            f'Postprocessing stopped at `{run["postprocessing"]["stop_reason"]}`. '
            f'Repair / part-repair / rebalance moves: {run["postprocessing"]["repair_move_count"]} / '
            f'{run["postprocessing"]["part_repair_move_count"]} / {run["postprocessing"]["rebalance_move_count"]}.', '',
            'Compressed district outlines: ' + ' / '.join(
                f'{level}: {run["payloads"]["district_outlines"][level]["gzip_bytes"]/1024:.1f} KiB'
                for level in ('national', 'state', 'full')) + '. '
            f'Connection: {run["payloads"]["exclave_connections"]["gzip_bytes"]:,} bytes.', '',
        ]
    text += ['## Strict baseline and interpretation', '',
        f'The preserved strict K6 attempt stopped at source-topology preflight after '
        f'{data["strict_baseline"]["preflight_wall_seconds"]:.7f} seconds. '
        'K8/K9/K14 reused that exception. There are no prior strict solved populations or solver runtimes to compare; no speedup over a strict solver is claimed.', '',
        '## Validation and timing limits', '',
        f'Independently read the original source DBF, verified unique GEOIDs and official totals, and recomputed final district totals from saved assignments. '
        f'Checked compressed-map sizes and decompressed hashes, declared policy validation, same-district endpoints, identical source connection records across K, '
        f'and {data["preserved_historical_file_count"]} preserved historical file hashes.', '',
        data['validation_note'], '',
        *['- ' + note for note in data['measurement_notes']], '',
        '[Water/land crossing audit](' + (ROOT / data['crossing_audit']['path']).as_posix() + ') · '
        '[Original diagnosis](http://127.0.0.1:8770/diagnostics/kentucky/) · '
        '[Machine-readable comparison](' + REPORT.with_suffix('.json').as_posix() + ')', '',
    ]
    return '\n'.join(text)


def html(data: dict[str, Any]) -> str:
    metric_rows = ''
    for run in data['runs']:
        cells = table_cells(run)
        metric_rows += '<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in cells) + '</tr>'
    cards = ''
    for run in data['runs']:
        k = run['district_count']
        if run['accepted_plan']:
            final = run['final_plan']
            populations = ' / '.join(f'{n:,}' for n in final['district_populations'])
            district = run['connection_features'][0]['properties']['used_by_district'] + 1
            cards += f'''<article class="card"><div class="eyebrow">House {' / '.join(str(x) for x in run['house_sizes'])}</div>
<h2><a href="states/21/districts-{k}/">{k} districts →</a></h2><p class="large">{final['max_absolute_deviation_people']:,.3f} <small>people from ideal, maximum</small></p>
<p class="muted">{final['max_absolute_deviation_percent']:.6f}% deviation · {run['timed_pipeline_wall_seconds']:.2f} s full pipeline</p>
<p class="populations">{populations}</p><p class="note">District {district} uses the recorded exclave link. Physical polygon pieces: {escape(str(run['physical_polygon_components']))}. All {k} districts pass policy graph and independent polygon checks.</p>
<p class="note">All {run['inner_optimizer_pass_count']} inner optimizer passes succeeded. {escape(run['outer_termination']['disclosure'])}</p>
<p class="note">Postprocessing stopped at {escape(run['postprocessing']['stop_reason'])}.</p></article>'''
        else:
            cards += f'<article class="card"><h2>{k} districts · failed</h2><p>{escape(run.get("error") or "Unknown failure")}</p><a href="states/21/districts-{k}/benchmark.json">Saved failure report</a></article>'
    payload_rows = ''
    for run in data['runs']:
        if not run['accepted_plan']:
            continue
        p = run['payloads']
        payload_rows += '<tr><td>' + str(run['district_count']) + '</td>' + ''.join(
            f'<td>{p["district_outlines"][level]["gzip_bytes"]/1024:,.1f} KiB</td>'
            for level in ('national', 'state', 'full')) + f'<td>{p["exclave_connections"]["gzip_bytes"]:,} B</td></tr>'
    convergence_notice = ''.join('<div class="callout"><strong>Outer convergence caveat.</strong> '
                                + escape(note) + '</div>'
                                for note in data['outer_convergence']['disclosures'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kentucky · Recorded exclave plans</title><style>
:root{{color-scheme:dark;--bg:#111b24;--panel:#192832;--ink:#edf4f4;--muted:#a5bdc9;--line:#344d5b;--accent:#72ddd4;--amber:#ffcc7d}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,sans-serif}}main{{max-width:1260px;margin:auto;padding:28px 32px 45px}}a{{color:var(--accent)}}h1{{font-size:36px;line-height:1.15;margin:10px 0 15px}}h2{{font-size:20px;margin:8px 0 12px}}p{{margin:0 0 14px}}.eyebrow{{font:11px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-top:18px}}.muted,.note{{color:var(--muted)}}.note{{font-size:12px}}.callout{{border-left:3px solid var(--amber);padding:16px 20px;background:#2b2c29;margin:22px 0}}.callout strong{{color:var(--amber)}}.cards{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:24px 0}}.card{{background:var(--panel);border:1px solid var(--line);padding:17px 20px}}.card .eyebrow{{margin-top:0}}.large{{font-size:28px;font-variant-numeric:tabular-nums}}.large small{{font-size:12px;color:var(--muted)}}.populations{{font:13px/1.7 ui-monospace,monospace;overflow-wrap:anywhere}}.table-wrap{{overflow:auto;margin:16px 0 25px}}table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th{{font-size:10px;color:var(--muted);text-transform:uppercase}}th:first-child,td:first-child{{text-align:left}}footer{{border-top:1px solid var(--line);padding-top:20px;margin-top:25px}}@media(max-width:760px){{main{{padding:20px}}h1{{font-size:28px}}.cards{{grid-template-columns:1fr}}}}</style></head><body><main>
<a href="../../">← National benchmark results</a><p class="eyebrow">Kentucky / 2020 census blocks / Recorded exclave policy</p>
<h1>One explicit connection. Four district-count anchors.</h1>
<p class="muted">{data['complete_plan_count']} accepted plans · {data['failed_plan_count']} failed attempts. Every accepted plan retains all {BLOCKS:,} Kentucky blocks and {TOTAL:,} residents. Population balance, physical geometry, and connectivity through the recorded connection are reported separately.</p>
<div class="callout"><strong>Kentucky Bend stays physically separate.</strong> The 5.145 km connection crosses about 1.805 km of mapped Mississippi River water and 3.340 km of Missouri land. It is an explicit exclave graph exception. No Missouri territory or population is assigned to Kentucky districts. <a href="../../diagnostics/kentucky/">Inspect the geographic diagnosis</a>.</div>
<div class="table-wrap"><table><thead><tr><th>House size</th><th>Districts</th><th>Max deviation, people</th><th>Max deviation, %</th><th>Pipeline, s</th><th>Solve, s</th><th>Peak MiB</th><th>Policy-connected</th></tr></thead><tbody>{metric_rows}</tbody></table></div>
{convergence_notice}
<p class="note">Maximum deviation uses the fractional statewide ideal. Full pipeline includes link preparation, solving, repair/rebalance, independent polygon validation, map export and preservation checks. Shared-desktop serial timings are not isolated hardware measurements.</p>
<div class="cards">{cards}</div>
<h2>What changed from strict connectivity?</h2><p>The original strict attempt stopped before solving because Kentucky has two separate source components, one with only 9 residents. Its {data['strict_baseline']['preflight_wall_seconds']:.2f}-second preflight rejection was reused at the other district counts. There are no prior strict district populations or solver timings for a before/after comparison.</p>
<p class="muted">The recorded connection removes that source-graph obstruction. Each accepted plan then passes both the augmented polygon-part graph and an independent dissolved-polygon check that verifies both link endpoints belong to the same district. Local whole-block rebalancing does not establish a global population optimum.</p>
<h2>Compressed map payloads</h2><div class="table-wrap"><table><thead><tr><th>Districts</th><th>National outlines</th><th>State outlines</th><th>Exact outlines</th><th>Exclave connection</th></tr></thead><tbody>{payload_rows}</tbody></table></div>
<p class="note">Saved gzip bytes, not latency or browser memory. County block detail loads on request. Missouri context loads only when inspecting the connection or Kentucky Bend and is separate from these export sizes.</p>
<footer><p><a href="comparison.json">Validated comparison JSON</a> · <a href="../../diagnostics/kentucky/area-water-audit.json">Water / land crossing audit</a> · <a href="../../states/21/districts-6/benchmark.json">Preserved strict exception</a></p>
<p class="note">Independently recomputed final district populations from the original source DBF and saved GEOID assignments; verified compressed-map hashes, endpoint ownership, identical connection records, and {data['preserved_historical_file_count']} protected historical file hashes. {escape(data['validation_note'])}</p></footer></main></body></html>'''


def write_outputs(data: dict[str, Any]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
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
