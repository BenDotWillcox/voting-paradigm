"""Verify the terminal California K52 pilot and write its separate comparison.

Historical strict/diagnostic evidence and numerical runtime sources are read
only. A strict topology exception is not an earlier solved district plan.
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
import sys
from typing import Any
import zipfile

import shapefile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.summarize_kentucky_exclave import (
    outer_termination, read_json, sha256, verify_assignments, verify_compressed_maps,
)
from scripts.summarize_new_york_budget import verify_trace

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'policies/california-water-v1'
RUN = OUTPUT / 'states/06/districts-52'
BASELINE = SUITE / 'states/06/districts-52/benchmark.json'
SOURCE = ROOT / '.cache/state-block-benchmark/source/06/tl_2020_06_tabblock20.zip'
REPORT = ROOT / 'prompts/california-water-benchmark'
URL = 'http://127.0.0.1:8770/policies/california-water-v1/'
TOTAL, BLOCKS, K = 39_538_223, 519_723, 52
SOURCE_SHA = '154ffb979e4d1f8cae4ff2676cbba9030ef39a92d4620644bc8aa7f7be2ad85f'
POLICY = 'shared_edges_plus_recorded_water_connections'


def verify_execution(process: dict[str, Any], report: dict[str, Any], progress: dict[str, Any]) -> None:
    if process.get('status') not in ('complete', 'failed') or not process.get('finished_at'):
        raise ValueError('Launcher has not recorded an exited child.')
    complete = report.get('status') == 'complete_under_island_water_policy'
    if report.get('status') not in ('complete_under_island_water_policy', 'failed'):
        raise ValueError('Benchmark is not terminal.')
    if (process.get('benchmark_status') != report['status'] or (process.get('returncode') == 0) != complete
            or process.get('status') != ('complete' if complete else 'failed')
            or type(process.get('returncode')) is not int):
        raise ValueError('Launcher and terminal benchmark disagree.')
    if progress.get('status') != report['status'] or progress.get('active_phase') is not None:
        raise ValueError('Terminal progress disagrees with benchmark.')
    if report.get('active_phase') is not None or not report.get('finished_at'):
        raise ValueError('Benchmark retains an active phase.')
    if report.get('state_fips') != '06' or report.get('district_count') != K or report.get('policy') != POLICY:
        raise ValueError('Unexpected state, district count or policy.')


def verify_configuration(configuration: dict[str, Any]) -> None:
    expected = {'seed': 20200955, 'max_outer_iterations': 80,
                'inner_max_iterations': 1000, 'center_tolerance_m': 1e-4,
                'max_rebalance_moves': 1000, 'root_eligibility_relative_band': .01,
                'group_population_preflight_tolerance': .01}
    if any(configuration.get(key) != value for key, value in expected.items()):
        raise ValueError('Pilot settings do not match the requested starting configuration.')
    if configuration.get('inner_optimization', {}).get('max_line_search_steps') != 100:
        raise ValueError('Unexpected line-search allowance.')


def source_populations() -> dict[str, int]:
    if sha256(SOURCE) != SOURCE_SHA:
        raise ValueError('California source archive hash changed.')
    with zipfile.ZipFile(SOURCE) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith('.dbf')]
        if len(names) != 1:
            raise ValueError('Expected one source DBF.')
        raw = archive.read(names[0])
    populations: dict[str, int] = {}
    with shapefile.Reader(dbf=io.BytesIO(raw)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        geoid_col, pop_col = fields.index('GEOID20'), fields.index('POP20')
        for record in reader.iterRecords():
            geoid, pop = str(record[geoid_col]), record[pop_col]
            if (geoid in populations or len(geoid) != 15 or not geoid.startswith('06')
                    or type(pop) not in (int, float) or not math.isfinite(pop) or pop < 0 or int(pop) != pop):
                raise ValueError('Invalid or duplicate California source record.')
            populations[geoid] = int(pop)
    if len(populations) != BLOCKS or sum(populations.values()) != TOTAL:
        raise ValueError('Source DBF differs from official population/block totals.')
    return populations


def verify_links(features: list[dict[str, Any]], records: list[dict[str, Any]],
                 assignments: dict[str, int]) -> list[dict[str, Any]]:
    if len(features) != len(records) or len(records) != 6:
        raise ValueError('Expected the six diagnosed water connections.')
    expected = {record['id']: record for record in records}
    if len(expected) != 6 or {feature['properties']['id'] for feature in features} != set(expected):
        raise ValueError('Exported water connection IDs differ from selected records.')
    rows = []
    for feature in features:
        p = feature['properties']
        record = expected[p['id']]
        endpoint_districts = [assignments[endpoint['geoid']] for endpoint in record['endpoints']]
        used = endpoint_districts[0] if endpoint_districts[0] == endpoint_districts[1] else None
        if (feature['geometry']['type'] != 'LineString'
                or feature['geometry']['coordinates'] != [endpoint['coordinate'] for endpoint in record['endpoints']]
                or p['endpoints'] != record['endpoints'] or p['component_ids'] != record['component_ids']
                or p['distance_m'] != record['distance_m'] or p['endpoint_districts'] != endpoint_districts
                or p['used_by_district'] != used):
            raise ValueError('Exported connection geometry or district ownership disagrees with assignments.')
        rows.append({'id': p['id'], 'component_ids': p['component_ids'], 'distance_m': p['distance_m'],
                     'endpoint_districts': endpoint_districts, 'used_by_district': used,
                     'endpoint_geoids': [endpoint['geoid'] for endpoint in record['endpoints']]})
    return rows


def verify_final(directory: Path, report: dict[str, Any], populations: dict[str, int]) -> dict[str, Any]:
    verified_stages = {}
    for stage, filename in [('initial', 'initial-solver-result.json'),
                            ('after_repair', 'after-repair-result.json'), ('final', 'solver-result.json')]:
        saved = read_json(directory / filename)
        verified_stages[stage] = verify_assignments(saved['assignments'], populations, K, report[stage + '_plan'])
        if saved['provenance']['configuration'] != report['configuration']:
            raise ValueError('Assignment provenance has different settings.')
    final = report['final_plan']
    if final['policy_part_components'] != [1] * K or not final['all_districts_policy_connected']:
        raise ValueError('Final plan failed the part graph policy audit.')
    manifest = read_json(directory / 'maps/map-manifest.json')
    if manifest != report['maps']:
        raise ValueError('Map manifest differs from the terminal benchmark.')
    audit = manifest['connectivity_validation']
    if (audit['policy'] != POLICY or not audit['passed'] or len(audit['districts']) != K
            or any(row['connected_components_after_links'] != 1 for row in audit['districts'])
            or not audit['source_coverage_preserved_exactly'] or audit['source_geometry_modified']):
        raise ValueError('Independent polygon-plus-link validation did not pass.')
    if [row['physical_polygon_components'] for row in audit['districts']] != final['physical_part_components']:
        raise ValueError('Physical part and polygon component counts disagree.')
    checked = verify_compressed_maps(directory, manifest)
    for detail in ('national', 'state', 'full'):
        features = json.loads(gzip.decompress((directory / f'maps/districts-{detail}.geojson.gz').read_bytes()))['features']
        rows = sorted(features, key=lambda feature: feature['properties']['district_id'])
        if ([feature['properties']['district_id'] for feature in rows] != list(range(K))
                or [feature['properties']['population'] for feature in rows] != final['district_populations']
                or [feature['properties']['block_count'] for feature in rows] != final['district_block_counts']):
            raise ValueError('Map district attributes disagree with source-DBF assignments.')
    features = json.loads(gzip.decompress((directory / 'maps/water-connections.geojson.gz').read_bytes()))['features']
    assignments = read_json(directory / 'solver-result.json')['assignments']
    links = verify_links(features, report['water_connections'], assignments)
    if {row['id'] for row in links if row['used_by_district'] is not None} != set(audit['used_link_ids']):
        raise ValueError('Polygon validation used-link IDs disagree with endpoint assignments.')
    return {'independent_population_checks': verified_stages, 'compressed_maps_verified': checked,
            'connectivity': audit, 'links': links, 'final_population': verified_stages['final'],
            'map_payloads': manifest['load_scenarios'], 'water_link_payload': manifest['water_connections']}


def summary(validation_note: str = '') -> dict[str, Any]:
    report, baseline = read_json(RUN / 'benchmark.json'), read_json(BASELINE)
    process = read_json(OUTPUT / 'run.json')
    verify_execution(process, report, read_json(RUN / 'progress.json'))
    verify_configuration(report['configuration'])
    expected_configuration_hash = hashlib.sha256(json.dumps(
        report['configuration'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if report.get('configuration_sha256') != expected_configuration_hash:
        raise ValueError('Recorded configuration checksum disagrees with saved settings.')
    if (baseline['status'] != 'unsupported_topology' or baseline['solver_progress']
            or baseline['source']['archive_sha256'] != SOURCE_SHA
            or report['source']['archive_sha256'] != SOURCE_SHA):
        raise ValueError('Original California topology preflight or source identity changed.')
    inventory = read_json(RUN / 'preserved-file-inventory.json')
    required = {BASELINE, SUITE / 'suite.json', SOURCE,
                SUITE / 'diagnostics/california/diagnosis.json',
                ROOT / 'prompts/california-topology-diagnosis.json'}
    for directory in (SUITE / 'states/06', SUITE / 'diagnostics/california'):
        required.update(path for path in directory.rglob('*') if path.is_file())
    if set(inventory) != {path.relative_to(ROOT).as_posix() for path in required}:
        raise ValueError('Preservation inventory does not cover the complete original evidence.')
    audit = report.get('preservation_audit', {})
    if (audit.get('protected_file_count') != len(inventory)
            or any(audit.get(key) is not True for key in (
                'all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
                'national_suite_byte_identical', 'source_archive_byte_identical', 'run_code_unchanged'))):
        raise ValueError('Runner preservation audit did not pass.')
    for relative, expected in inventory.items():
        if sha256(ROOT / relative) != expected:
            raise ValueError(f'Preserved historical evidence changed: {relative}')
    for relative, expected in report['code_sha256'].items():
        if sha256(ROOT / relative) != expected:
            raise ValueError(f'Runtime source changed: {relative}')
    for relative, expected in report['artifact_sha256'].items():
        if sha256(RUN / relative) != expected:
            raise ValueError(f'Run artifact changed: {relative}')
    trace = None
    if report.get('optimizer_trace', {}).get('passes'):
        raw = [json.loads(line) for line in (RUN / 'optimizer-trace.jsonl').read_text(encoding='utf-8').splitlines()]
        trace = verify_trace(raw, report['optimizer_trace'], k=K, total=TOTAL)
        # The shared verifier exposes iteration-300 diagnostics for NY. California
        # never had that solver baseline; omit those comparison fields here.
        for row in trace['passes']:
            for key in ('at_original_budget', 'objective_improvement_after_original_budget',
                        'max_deviation_people_at_original_budget'):
                row.pop(key, None)
    accepted = report['status'] == 'complete_under_island_water_policy'
    result = verify_final(RUN, report, source_populations()) if accepted else None
    if accepted and (trace is None or not trace['all_inner_passes_succeeded']):
        raise ValueError('An accepted plan needs a successful complete optimizer trace.')
    if accepted and trace['pass_count'] != report['solver']['outer_iterations'] + 1:
        raise ValueError('Inner-pass count does not match outer iterations plus final balance.')
    if trace:
        for entry in report['optimizer_trace']['passes']:
            options = entry['actual_options']
            if (options.get('maxiter') != 1000 or options.get('maxls') != 100
                    or options.get('ftol') != 1e-12 or options.get('gtol') != 1e-6 / TOTAL):
                raise ValueError('Observed numerical optimizer options differ from the pilot settings.')
    test_record_path = OUTPUT / 'validation-tests.json'
    test_record = read_json(test_record_path)
    if (test_record.get('status') != 'passed' or test_record.get('passed') != 715
            or test_record.get('phase') != 'before launch'):
        raise ValueError('Expected the recorded prelaunch validation result.')
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'California K52 / House 435 first actual census-block solve with population-aware recorded water links and 1000 inner iterations.',
        'status': report['status'], 'accepted_plan': accepted,
        'baseline': {'status': baseline['status'], 'benchmark_path': BASELINE.relative_to(ROOT).as_posix(),
            'benchmark_sha256': sha256(BASELINE), 'solver_was_run': False,
            'pipeline_seconds': baseline['timed_pipeline_wall_seconds'],
            'peak_process_working_set_bytes': baseline['peak_process_working_set_bytes'],
            'physical_source_components': baseline['graph']['component_count'],
            'meaning': 'Preserved strict topology preflight; no solved plan or final population-balance baseline.'},
        'run': {'benchmark_path': (RUN / 'benchmark.json').relative_to(ROOT).as_posix(),
            'benchmark_sha256': sha256(RUN / 'benchmark.json'),
            'pipeline_seconds': report['timed_pipeline_wall_seconds'],
            'solve_seconds': report.get('phases', {}).get('solve', {}).get('wall_seconds'),
            'peak_process_working_set_bytes': report['peak_process_working_set_bytes'],
            'phases': report['phases'], 'configuration': report['configuration'],
            'input': report.get('input'), 'outer_termination': outer_termination(report['solver'], report['configuration']) if accepted else None,
            'postprocessing': report.get('postprocessing'), 'error': report.get('error'),
            'optimizer_failure': report.get('optimizer_failure')},
        'execution': process, 'trace': trace, 'result': result,
        'preservation': {'files_rehashed': len(inventory), 'all_byte_identical': True},
        'validation_note': validation_note,
        'prelaunch_tests': {'path': test_record_path.relative_to(ROOT).as_posix(),
                           'sha256': sha256(test_record_path), 'record': test_record},
        'limitations': [
            'The original run stopped before optimization. This is not a controlled 300-versus-1000 iteration experiment or a completed-plan speed comparison.',
            'A successful inner optimizer, outer center convergence, final population balance, physical connectivity and recorded-link connectivity are distinct outcomes.',
            'The 1% root/group population budget selects links; it is not final district-balance acceptance.',
            'Connections preserve source polygons and populations. Open-Pacific attribution uses source-component clearance and official regional geography, not a global high-resolution shoreline certificate.',
            'Objective changes are meaningful within each pass only; intermediate trace populations are point assignments before connectivity repair.',
            'Pilot timings are from a shared desktop and include observational tracing. The original preflight built the historical block graph; the pilot uses a part graph and new policy.',
            'Map byte counts describe gzip artifacts, not browser memory or network latency. County detail loads only on request.',
        ]}


def duration(seconds: float | None) -> str:
    if seconds is None:
        return 'Not run'
    return f'{seconds / 60:.2f} min ({seconds:.3f} s)'


def markdown(data: dict[str, Any]) -> str:
    run, baseline, result, trace = data['run'], data['baseline'], data['result'], data['trace']
    pop = result['final_population'] if result else None
    lines = ['# California: recorded-water K52 pilot', '', data['scope'], '',
        f'Outcome: **{data["status"]}**. {data["preservation"]["files_rehashed"]} historical files remain byte-identical.', '',
        '| Metric | Preserved strict preflight | New water-policy pilot |',
        '|---|---:|---:|',
        f'| Pipeline runtime | {duration(baseline["pipeline_seconds"])} | {duration(run["pipeline_seconds"])} |',
        f'| Solver runtime | Not run | {duration(run["solve_seconds"])} |',
        f'| Repair and rebalancing | Not run | {duration(run["phases"].get("repair_and_rebalance", {}).get("wall_seconds"))} |',
        f'| Polygon validation and map export | Not run | {duration(run["phases"].get("independent_polygon_validation_and_map_export", {}).get("wall_seconds"))} |',
        f'| Peak process memory | {baseline["peak_process_working_set_bytes"] / 2**30:.3f} GiB | {run["peak_process_working_set_bytes"] / 2**30:.3f} GiB |',
        f'| Maximum final deviation | No plan | {str(round(pop["max_absolute_deviation_people"], 6)) + " people / " + str(round(pop["max_absolute_deviation_percent"], 9)) + "%" if pop else "No accepted plan"} |', '',
        'The earlier result stopped at a disconnected source graph. It did not test a 300-iteration solve or produce final districts.', '']
    if result:
        audit = result['connectivity']
        fragmented = [row for row in audit['districts'] if row['physical_polygon_components'] > 1]
        physical = '; '.join(f'District {row["district_id"]+1}: {row["physical_polygon_components"]} pieces' for row in fragmented)
        lines += [f'All {K} districts pass the part graph and independent unsimplified polygon-plus-link audits. {physical or "All districts are physically connected"}.',
            f'All {BLOCKS:,} source blocks and {TOTAL:,} residents are retained. The remaining {K-len(fragmented)} districts are physically connected.' if fragmented else '', '',
            '| Recorded connection | Distance | Endpoint districts | Used within district |', '|---|---:|---|---|']
        geography = read_json(SUITE / 'diagnostics/california/geography-context.json')
        names = {row['id']: row['label'].replace(' coverage', '') for row in geography['components']}
        for row in result['links']:
            lines.append(f'| {" ↔ ".join(names[x] for x in row["component_ids"])} | {row["distance_m"] / 1000:.3f} km | {" / ".join(str(x+1) for x in row["endpoint_districts"])} | {str(row["used_by_district"]+1) if row["used_by_district"] is not None else "Unused"} |')
        lines += ['', run['outer_termination']['disclosure'], '',
                  f'[Validated map]({URL}states/06/districts-52/) · [Comparison and traces]({URL})', '']
        lines += ['| Population stage | Maximum deviation |', '|---|---:|']
        for stage, values in result['independent_population_checks'].items():
            lines.append(f'| {stage.replace("_", " ")} | {values["max_absolute_deviation_people"]:.6f} people / {values["max_absolute_deviation_percent"]:.9f}% |')
        payload = result['map_payloads']
        lines += ['', f'Compressed map payload: national outlines {payload["national_state_only"]["gzip_bytes"]:,} bytes; state entry outlines + detail index {payload["state_entry_outlines_and_detail_index"]["gzip_bytes"]:,} bytes; link overlay {result["water_link_payload"]["gzip_bytes"]:,} bytes. All county detail shards total {payload["all_county_detail_shards"]["gzip_bytes"]:,} bytes and load individually on request. The largest county shard (county FIPS {payload["largest_county_detail_shard"]["county_fips"]}) is {payload["largest_county_detail_shard"]["gzip_bytes"]:,} compressed bytes.', '']
    elif run['error']:
        lines += [f'Failure: `{run["error"]}`. No accepted district map is claimed.', '']
    if trace:
        largest = max(row['optimizer']['iterations'] for row in trace['passes'])
        lines += [f'Observed {trace["pass_count"]} balancing passes, {trace["accepted_iteration_count"]:,} accepted iterations; the largest pass used **{largest} / 1,000**. Tracing bookkeeping/I/O overhead: {trace["observed_overhead_seconds"]:.3f} s.', '']
    lines += ['Validation: ' + (data['validation_note'] or 'Terminal process/report consistency, preserved/runtime hashes, trace arithmetic, and independent source-DBF and saved map checks.'), '']
    lines += [f'[Saved prelaunch test record]({URL}validation-tests.json): {data["prelaunch_tests"]["record"]["passed"]} tests passed before launch; the record checksum is retained in the comparison JSON.', '']
    lines += ['- ' + note for note in data['limitations']]
    return '\n'.join(lines) + '\n'


def html(data: dict[str, Any]) -> str:
    # Tables are rendered directly from the same verified JSON as the report.
    run, baseline, result, trace = data['run'], data['baseline'], data['result'], data['trace']
    pop = result['final_population'] if result else None
    balance = f'{pop["max_absolute_deviation_people"]:.3f} people · {pop["max_absolute_deviation_percent"]:.6f}%' if pop else 'No accepted plan'
    rows = [('Pipeline', duration(baseline['pipeline_seconds']), duration(run['pipeline_seconds'])),
            ('Solver', 'Not run', duration(run['solve_seconds'])),
            ('Repair and rebalancing', 'Not run', duration(run['phases'].get('repair_and_rebalance', {}).get('wall_seconds'))),
            ('Polygon validation and map export', 'Not run', duration(run['phases'].get('independent_polygon_validation_and_map_export', {}).get('wall_seconds'))),
            ('Peak process memory', f'{baseline["peak_process_working_set_bytes"]/2**30:.3f} GiB', f'{run["peak_process_working_set_bytes"]/2**30:.3f} GiB'),
            ('Maximum final population deviation', 'No plan', balance)]
    table = ''.join('<tr>' + ''.join(f'<td>{escape(str(v))}</td>' for v in row) + '</tr>' for row in rows)
    narrative = run['outer_termination']['disclosure'] if result else run['error'] or 'No accepted map.'
    physical = ''
    if result:
        fragmented = [row for row in result['connectivity']['districts'] if row['physical_polygon_components'] > 1]
        physical = f'<p>All {K} districts pass the graph and independent polygon-plus-link audit. '+(' '.join(f'District {row["district_id"]+1} retains {row["physical_polygon_components"]} physical pieces.' for row in fragmented) or 'All districts are physically connected.')+f' {K-len(fragmented)} districts have a single physical polygon component.</p>'
    stages = ''
    if result:
        stage_rows = ''.join(f'<tr><td>{stage.replace("_", " ")}</td><td>{values["max_absolute_deviation_people"]:.3f} people</td><td>{values["max_absolute_deviation_percent"]:.6f}%</td></tr>' for stage, values in result['independent_population_checks'].items())
        payload = result['map_payloads']
        stages = '<section><h2>Population balance through postprocessing</h2><div class="scroll"><table><thead><tr><th>Stage</th><th>Maximum deviation</th><th>Percent of ideal</th></tr></thead><tbody>'+stage_rows+'</tbody></table></div><p>Independent totals from all 519,723 source blocks and 39,538,223 residents. These stage assignments are distinct from intermediate optimizer observations.</p></section>'
        stages += f'<section><h2>Compressed map data</h2><p>National outlines: {payload["national_state_only"]["gzip_bytes"]/1024:.1f} KiB. State entry outlines and detail index: {payload["state_entry_outlines_and_detail_index"]["gzip_bytes"]/1024:.1f} KiB. Recorded-link overlay: {result["water_link_payload"]["gzip_bytes"]/1024:.1f} KiB. Full county detail totals {payload["all_county_detail_shards"]["gzip_bytes"]/2**20:.2f} MiB, split into county files loaded only on request.</p></section>'
    options = ''.join(f'<option value="{i}">Pass {row["balance_pass"]} · {row["optimizer"]["iterations"]} iterations · {"success" if row["optimizer"]["success"] else "failed"}</option>' for i, row in enumerate(trace['passes'])) if trace else ''
    charts = '<section><h2>Optimizer observations</h2><label for="pass">Balancing pass</label> <select id="pass">'+options+'</select><p id="pass-status"></p><div class="charts"><div><h3>Objective improvement within this pass</h3><svg id="objective" viewBox="0 0 540 220" role="img" aria-label="Objective improvement by accepted iteration"></svg></div><div><h3>Maximum intermediate population deviation (%)</h3><svg id="population" viewBox="0 0 540 220" role="img" aria-label="Intermediate population deviation by accepted iteration"></svg></div></div><p>These are point assignments before connectivity repair. Objective values are comparable within a pass only, and lower objective does not guarantee lower population imbalance.</p></section>' if trace else ''
    embedded = json.dumps(trace['passes'] if trace else [], allow_nan=False).replace('<', '\\u003c')
    notes = ''.join(f'<li>{escape(note)}</li>' for note in data['limitations'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>California · recorded-water K52 pilot</title><style>
:root{{color-scheme:dark;font:15px/1.55 system-ui;background:#11191f;color:#e6eef2}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1160px;margin:auto;padding:28px}}h1{{font-size:30px;margin:8px 0}}h2{{font-size:21px}}h3{{font-size:15px}}a{{color:#69d4df}}.tag{{color:#69d4df;letter-spacing:.12em;font-size:12px;text-transform:uppercase}}p{{max-width:1000px}}section{{background:#19242b;border:1px solid #31424b;border-radius:8px;padding:22px;margin:20px 0}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #31424b}}.scroll{{overflow:auto}}select{{background:#13232d;color:inherit;padding:9px;border:1px solid #47616f;border-radius:5px;max-width:100%}}.charts{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}svg{{width:100%;background:#122029;border-radius:6px}}li{{margin-bottom:10px}}.status{{color:#f6c970}}@media(max-width:740px){{main{{padding:16px}}.charts{{grid-template-columns:1fr}}h1{{font-size:25px}}section{{padding:14px}}}}a:focus-visible,select:focus-visible{{outline:3px solid #f6c970;outline-offset:3px}}
</style><main><p class="tag">Saved computation · 2020 census blocks · House 435</p><h1>California: 52-district water-policy pilot</h1><p class="status">{escape(data['status'])}</p><p>This is California’s first actual block solve with the fixed optimizer and a 1,000-iteration inner ceiling. The original strict run remains preserved and stopped before solving.</p><p>{'<a href="states/06/districts-52/">Open validated district map →</a> · ' if result else ''}<a href="../../diagnostics/california/">Original topology diagnosis</a> · <a href="comparison.json">Verified comparison JSON</a> · <a href="states/06/districts-52/benchmark.json">Benchmark evidence</a></p><section><h2>Preflight and pilot measurements</h2><div class="scroll"><table><thead><tr><th>Metric</th><th>Preserved strict preflight</th><th>New recorded-water pilot</th></tr></thead><tbody>{table}</tbody></table></div><p>The original timing ends at the source topology exception. It is not a completed-plan speed comparison or a 300-versus-1,000 optimizer test.</p></section><section><h2>Connectivity and convergence</h2>{physical}<p>{escape(narrative)}</p><p>Dashed map lines are recorded graph edges across geographically attributed Pacific gaps. Source polygons remain unchanged; endpoint ownership is checked independently.</p></section>{stages}{charts}<section><h2>Evidence and limits</h2><p>{data['preservation']['files_rehashed']} historical files independently rehashed and unchanged.</p><p>{escape(data['validation_note'])}</p><ul>{notes}</ul></section></main><script>const passes={embedded};
function plot(id,samples,value){{const svg=document.getElementById(id),NS='http://www.w3.org/2000/svg';svg.replaceChildren();const vals=samples.map(value),maxX=Math.max(1,...samples.map(s=>s.iteration)),lo=Math.min(0,...vals),hi=Math.max(...vals),span=hi-lo||1;function add(type,attrs,text){{const e=document.createElementNS(NS,type);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text)e.textContent=text;svg.appendChild(e)}}add('path',{{d:'M62 18 V182 H524',stroke:'#7c93a1',fill:'none'}});const d=samples.map((s,i)=>(i?'L':'M')+(62+s.iteration/maxX*462)+','+(182-(value(s)-lo)/span*164)).join(' ');add('path',{{d,stroke:id==='objective'?'#69d4df':'#f28bc8','stroke-width':2,fill:'none'}});for(const[f,label]of[[0,lo],[.5,lo+span/2],[1,hi]])add('text',{{x:56,y:186-f*164,'text-anchor':'end',fill:'#a5bac5','font-size':11}},Number(label).toPrecision(3));add('text',{{x:62,y:204,fill:'#a5bac5','font-size':11}},'0');add('text',{{x:524,y:204,'text-anchor':'end',fill:'#a5bac5','font-size':11}},String(maxX)+' iterations')}}
function draw(){{const p=passes[Number(document.getElementById('pass').value)];document.getElementById('pass-status').textContent=p.optimizer.iterations+' accepted iterations · '+p.optimizer.function_evaluations+' evaluations · '+p.trace_wall_seconds.toFixed(2)+' s · '+p.optimizer.message;plot('objective',p.samples,s=>s.improvement_from_initial);plot('population',p.samples,s=>s.population.max_absolute_deviation_percent)}}if(passes.length){{document.getElementById('pass').addEventListener('change',draw);draw()}}</script></html>'''


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
