"""Compare a validated Hawaii K2 optimizer correction with its immutable run.

No benchmark, source map, diagnostic, or historical comparison is edited.
Successful output requires terminal validation and an intact preservation audit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
from html import escape
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OLD_ROOT = SUITE / 'policies/hawaii-water-v1'
OUTPUT = SUITE / 'corrections/hawaii-optimizer-v1'
BASE_URL = 'http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/'
OLD_URL = 'http://127.0.0.1:8770/policies/hawaii-water-v1/states/15/districts-2/'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def load_run(directory: Path, *, corrected: bool, district_count: int = 2) -> dict[str, Any]:
    path = directory / 'benchmark.json'
    report = read_json(path)
    if report.get('status') != 'complete_under_island_water_policy':
        raise ValueError(f'{directory.name} has no successful terminal connectivity result.')
    if report['district_count'] != district_count or report['state_fips'] != '15':
        raise ValueError(f'Only Hawaii K{district_count} belongs in this comparison.')
    if not report['final_plan']['all_districts_policy_connected']:
        raise ValueError('Saved part graph did not pass declared connectivity.')
    audit = report['maps']['connectivity_validation']
    if not audit['passed'] or not audit['source_coverage_preserved_exactly'] or audit['source_geometry_modified']:
        raise ValueError('Saved independent polygon validation failed.')
    for name, expected in report['artifact_sha256'].items():
        if sha256(directory / name) != expected:
            raise ValueError(f'Artifact changed: {directory.name}/{name}')
    for item in report['maps']['storage']['artifacts']:
        compressed = (directory / 'maps' / item['gzip_path']).read_bytes()
        raw = gzip.decompress(compressed)
        if (len(compressed) != item['gzip_bytes'] or len(raw) != item['raw_bytes']
                or hashlib.sha256(raw).hexdigest() != item['raw_sha256']):
            raise ValueError(f'Compressed map artifact failed verification: {item["gzip_path"]}')
    inventory = read_json(directory / 'preserved-file-inventory.json')
    for name, expected in inventory.items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f'Preserved evidence changed: {name}')
    inner = [item['inner_optimizer'] for item in report['solver_progress'] if 'inner_optimizer' in item]
    failed = [item for item in inner if not item['success']]
    if corrected:
        required_flags = ('all_original_strict_files_byte_identical', 'national_suite_byte_identical',
                          'source_archive_byte_identical', 'run_code_unchanged',
                          'all_original_water_policy_files_byte_identical', 'original_run_bytes_verified')
        if not all(report['preservation_audit'][key] for key in required_flags):
            raise ValueError('The corrected run did not preserve all original evidence.')
        required_files = [path for path in OLD_ROOT.rglob('*') if path.is_file()]
        required_files.extend(path for path in (SUITE / 'states/15').rglob('*') if path.is_file())
        required_files.extend((ROOT / 'prompts/hawaii-water-benchmark.md', ROOT / 'prompts/hawaii-water-benchmark.json'))
        if any(path.relative_to(ROOT).as_posix() not in inventory for path in required_files):
            raise ValueError('Correction inventory omitted original policy results, reports or strict files.')
        if not report['solver']['all_inner_optimizer_passes_succeeded'] or failed or not inner:
            raise ValueError('The corrected run did not demonstrate successful inner optimizer passes.')
    water_geojson = json.loads(gzip.decompress((directory / 'maps/water-connections.geojson.gz').read_bytes()))
    links = [item['properties'] for item in water_geojson['features']]
    for link in links:
        used = link['used_by_district']
        if used is not None and link['endpoint_districts'] != [used, used]:
            raise ValueError('A used water link does not belong to a single district.')
    result = {key: report[key] for key in (
        'status', 'run_kind', 'configuration', 'source', 'input', 'solver', 'solver_progress',
        'postprocessing', 'initial_plan', 'after_repair_plan', 'final_plan', 'phases',
        'timed_pipeline_wall_seconds', 'peak_process_working_set_bytes', 'code_sha256',
        'island_policy_audit', 'physical_part_graph_cache', 'preservation_audit',
    )}
    result.update({
        'label': 'Corrected optimizer' if corrected else 'Original water-policy run',
        'url': (BASE_URL if corrected else 'http://127.0.0.1:8770/policies/hawaii-water-v1/')
               + f'states/15/districts-{district_count}/',
        'benchmark_path': path.relative_to(ROOT).as_posix(), 'benchmark_sha256': sha256(path),
        'water_connections_sha256': sha256(directory / 'water-connections.json'),
        'working_set_mib': report['peak_process_working_set_bytes'] / 2**20,
        'physical_polygon_components': [item['physical_polygon_components'] for item in audit['districts']],
        'policy_polygon_components': [item['connected_components_after_links'] for item in audit['districts']],
        'connections': links, 'selected_connection_count': len(links),
        'used_connection_count': sum(item['used_by_district'] is not None for item in links),
        'inner_optimizer': {'pass_count': len(inner), 'failed_pass_count': len(failed),
                            'iterations': sum(item['iterations'] for item in inner),
                            'failure_messages': sorted({item['message'].strip() for item in failed})},
        'payloads': {'district_outlines': report['maps']['district_outlines'],
                     'water_connections': report['maps']['water_connections'],
                     'load_scenarios': report['maps']['load_scenarios']},
        'compressed_artifacts_verified': len(report['maps']['storage']['artifacts']),
        'preserved_file_count_verified': len(inventory),
    })
    if corrected:
        result['comparison_baseline'] = report['comparison_baseline']
        result['preserved_baseline_code'] = report['preserved_baseline_code']
    return result


def summary(validation_note: str) -> dict[str, Any]:
    old = load_run(OLD_ROOT / 'states/15/districts-2', corrected=False)
    new = load_run(OUTPUT / 'states/15/districts-2', corrected=True)
    if old['source']['archive_sha256'] != new['source']['archive_sha256']:
        raise ValueError('Source archive differs between runs.')
    if old['water_connections_sha256'] != new['water_connections_sha256']:
        raise ValueError('The optimizer correction changed the recorded water policy.')
    if (new['comparison_baseline']['benchmark_path'] != old['benchmark_path']
            or new['comparison_baseline']['benchmark_sha256'] != old['benchmark_sha256']
            or new['comparison_baseline']['water_connections_sha256'] != old['water_connections_sha256']):
        raise ValueError('The corrected run did not identify the exact preserved baseline.')
    for name in ('districting/algorithm.py', 'scripts/benchmark_hawaii_water.py'):
        snapshot = new['preserved_baseline_code'][name]
        if sha256(ROOT / snapshot['path']) != snapshot['sha256'] or snapshot['sha256'] != old['code_sha256'][name]:
            raise ValueError(f'Preserved original source code does not match the original benchmark: {name}')
    if (old['input']['block_count'] != new['input']['block_count']
            or old['input']['total_population'] != new['input']['total_population']):
        raise ValueError('Source universe differs between runs.')
    for key in ('seed', 'max_outer_iterations', 'inner_max_iterations', 'center_tolerance_m', 'max_rebalance_moves'):
        if old['configuration'][key] != new['configuration'][key]:
            raise ValueError(f'Comparison requires the same recorded setting: {key}')
    changed = {name: {'old': old['code_sha256'][name], 'new': new['code_sha256'][name]}
               for name in old['code_sha256'].keys() & new['code_sha256'].keys()
               if old['code_sha256'][name] != new['code_sha256'][name]}
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Hawaii K2 only; full fresh-process correction under the unchanged recorded water policy.',
        'original': old, 'corrected': new, 'changed_existing_code_hashes': changed,
        'validation_note': validation_note,
        'comparison_invariants': {
            'source_archive_identical': True, 'source_block_and_population_totals_identical': True,
            'water_connection_record_byte_identical': True,
            'seed_and_recorded_iteration_limits_identical': True,
            'all_original_water_policy_files_preserved': True,
            'original_strict_results_and_diagnostics_preserved': True,
            'original_algorithm_and_benchmark_code_snapshots_verified': True,
        },
        'measurement_notes': [
            'Both are complete pipelines in fresh processes on a shared desktop, with warm source and physical graph caches.',
            'Runs occurred at different times; these are observations, not isolated head-to-head hardware measurements.',
            'Full pipeline includes preparation, policy construction, solving, repair, audits and export.',
            'Only the new run uses corrected numerical code; code hashes are deliberately different and recorded.',
            'The prior fixed-center diagnostic was not a connected plan or full benchmark and is not used as the runtime baseline.',
            'Physical shared-edge connectivity and connectivity through recorded water links remain separate metrics.',
        ],
    }


def pops(run: dict[str, Any]) -> str:
    return ' / '.join(f'{value:,}' for value in run['final_plan']['district_populations'])


def deviation(run: dict[str, Any]) -> str:
    plan = run['final_plan']
    count = plan['max_absolute_deviation_people']
    return f'{plan["max_absolute_deviation_percent"]:.9f}% ({count:,.3f} {"person" if count <= 1 else "people"})'


def balance_note(run: dict[str, Any]) -> str:
    bound = run['final_plan']['integer_population_lower_bound']
    if bound['reached']:
        return 'This reaches the best possible integer-population balance.'
    people = bound['max_deviation_numerator'] / bound['deviation_denominator']
    return (f'Local rebalancing stopped short of the {people:g}-person integer-population lower bound. '
            'That bound ignores indivisible blocks; the local stop does not establish a global optimum.')


def phase_rows(data: dict[str, Any]) -> list[tuple[str, float, float]]:
    old, new = data['original'], data['corrected']
    keys = list(dict.fromkeys([*old['phases'], *new['phases']]))
    return [(key, old['phases'].get(key, {}).get('wall_seconds', 0),
             new['phases'].get(key, {}).get('wall_seconds', 0)) for key in keys]


def markdown(data: dict[str, Any]) -> str:
    old, new = data['original'], data['corrected']
    rows = '\n'.join(f'| {run["label"]} | {pops(run)} | {deviation(run)} | '
                     f'{run["timed_pipeline_wall_seconds"]:.2f} s | {run["working_set_mib"]:.1f} MiB | '
                     f'{run["inner_optimizer"]["failed_pass_count"]}/{run["inner_optimizer"]["pass_count"]} |'
                     for run in (old, new))
    timing = '\n'.join(f'| {name.replace("_", " ")} | {before:.3f} s | {after:.3f} s |'
                       for name, before, after in phase_rows(data))
    connectivity = '\n'.join(f'| {run["label"]} | {run["selected_connection_count"]}/{run["used_connection_count"]} | '
                             f'{run["physical_polygon_components"]} → {run["policy_polygon_components"]} | '
                             f'{run["postprocessing"]["repair_move_count"]}/{run["postprocessing"]["rebalance_move_count"]} | '
                             f'{run["postprocessing"]["stop_reason"]} |' for run in (old, new))
    return f'''# Hawaii K2: numerical optimizer correction

The rerun passes every inner optimizer call, polygon-part connectivity and independent unsimplified polygon validation under the **unchanged recorded water policy**. Final maximum population deviation is **{deviation(new)}**. {balance_note(new)}

[Comparison]({BASE_URL}) · [Corrected map]({new['url']}) · [Preserved original map]({old['url']}) · [Original three-plan comparison](http://127.0.0.1:8770/policies/hawaii-water-v1/).

| Run | Final populations | Maximum deviation | Full pipeline | Peak working set | Failed / total inner passes |
|---|---|---|---:|---:|---:|
{rows}

The original inner optimizer stopped `ABNORMAL` without advancing, despite reported convergence of center movement. The correction removes irrelevant per-block distance offsets, normalizes remaining squared costs and population mass, and subtracts a common offset from the weights. Zero-population units remain assigned but do not set the population objective's scale. Public centers and weights retain their original units. The line-search limit is also raised to **100**; unsuccessful or nonfinite optimizer output now raises an explicit failure instead of returning a completed plan.

Source, seed, outer/inner iteration budgets and exact water-connection records are retained. Old/new code hashes differ deliberately and are recorded. The earlier fixed-center diagnostic is not used as a full-runtime or connected-plan baseline.

| Run | Selected / used links | Physical → policy polygon components | Repair / rebalance moves | Stop |
|---|---|---|---|---|
{connectivity}

All **{new['input']['block_count']:,} census blocks and {new['input']['total_population']:,} residents** remain covered exactly. No source polygons or water connections changed. A selected connection counts within a district only if both endpoint blocks belong to it; the map distinguishes used magenta links from unused gray links. Physical separation across water remains reported separately from policy connectivity.

| Phase | Original | Corrected |
|---|---:|---:|
{timing}

Both pipelines used fresh processes and warm source/physical-graph caches, running serially on the shared desktop at different times. Timings include preparation, policy construction, solving, repair, independent audits and export. They are not isolated hardware comparisons. Process imports, initial preservation inventories and final report flushes are outside the pipeline timer.

{data['validation_note']}

Verification checked all {old['compressed_artifacts_verified'] + new['compressed_artifacts_verified']} compressed map artifacts against their recorded decompressed hashes. The new preservation inventory covers {new['preserved_file_count_verified']} files, including the entire prior Hawaii policy output, its saved reports and diagnostics, original strict results, national manifest and source archive. They remain byte-identical. Snapshots of the [original algorithm]({BASE_URL}baseline-code/districting/algorithm.py) and [original benchmark runner]({BASE_URL}baseline-code/scripts/benchmark_hawaii_water.py) also match the original benchmark's code hashes.

Evidence: [Original benchmark]({(ROOT / old['benchmark_path']).as_posix()}) · [Corrected benchmark]({(ROOT / new['benchmark_path']).as_posix()}) · [Comparison JSON]({(ROOT / 'prompts/hawaii-optimizer-fix.json').as_posix()}).
'''


def html_page(data: dict[str, Any]) -> str:
    old, new = data['original'], data['corrected']
    populations = new['final_plan']['district_populations']
    gap = max(populations) - min(populations)
    cards = ''.join(f'''<article class="card"><div class="tag">{escape(run['label'])}</div>
<h2>{run['final_plan']['max_absolute_deviation_percent']:.6f}%<span>maximum population deviation</span></h2>
<p>{pops(run)} people</p><p class="muted">{run['timed_pipeline_wall_seconds']:.2f} s full pipeline · {run['working_set_mib']:.1f} MiB peak</p>
<p>{run['inner_optimizer']['failed_pass_count']}/{run['inner_optimizer']['pass_count']} inner optimizer passes failed</p>
<a class="button" href="{run['url']}">Open {'corrected' if run is new else 'preserved original'} map →</a></article>''' for run in (old, new))
    times = ''.join(f'<tr><th>{escape(name.replace("_", " "))}</th><td>{before:.3f} s</td><td>{after:.3f} s</td></tr>' for name, before, after in phase_rows(data))
    rows = ''.join(f'<tr><th>{escape(run["label"])}</th><td>{run["selected_connection_count"]}/{run["used_connection_count"]}</td>'
                   f'<td>{escape(str(run["physical_polygon_components"]))} → {escape(str(run["policy_polygon_components"]))}</td>'
                   f'<td>{run["postprocessing"]["repair_move_count"]}/{run["postprocessing"]["rebalance_move_count"]}</td></tr>' for run in (old, new))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hawaii K2 · Optimizer correction</title><style>
:root{{color-scheme:dark;--bg:#10191f;--panel:#1a252d;--text:#e9f2f5;--muted:#a6bac5;--line:#354955;--accent:#6ed5df;--water:#ff91cf}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,sans-serif}}main{{max-width:1180px;padding:36px 24px 52px;margin:auto}}h1{{font-size:clamp(28px,4vw,42px);line-height:1.15;margin:10px 0 16px}}h2{{font-size:22px;line-height:1.3;margin:12px 0}}p{{margin:10px 0 18px}}a{{color:var(--accent)}}.tag{{font:12px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--water)}}.muted,.small{{color:var(--muted)}}.small{{font-size:13px}}.cards{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:28px 0}}.card{{background:var(--panel);padding:22px;border:1px solid var(--line);border-radius:10px}}.card h2{{font-size:32px}}.card h2 span{{display:block;font-size:14px;color:var(--muted);font-weight:400}}.button{{display:inline-block;padding:9px 16px;border:1px solid var(--accent);border-radius:5px;text-decoration:none}}.callout{{border-left:3px solid var(--water);padding:10px 18px;background:#281e2c}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0 22px}}th,td{{text-align:right;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}}th:first-child,td:first-child{{text-align:left}}thead th{{color:var(--muted);font-weight:500}}nav{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}}a:focus-visible{{outline:3px solid var(--water);outline-offset:4px}}@media(max-width:750px){{.cards{{grid-template-columns:1fr}}main{{padding:24px 16px}}}}
</style></head><body><main><div class="tag">Hawaii · Two districts · Preserved benchmark comparison</div><h1>Two districts.<br>{gap:,} people apart.</h1><p>The complete rerun passes every inner optimizer call and independent connectivity validation. It covers all <strong>{new['input']['block_count']:,} blocks and {new['input']['total_population']:,} residents</strong>. Final maximum deviation is <strong>{deviation(new)}</strong>. Original strict and water-policy runs remain unchanged.</p>
<div class="cards">{cards}</div><p class="small">{escape(balance_note(new))}</p><p class="callout">Water connections are byte-identical between runs. The polygons remain physically separate across water; the dashed lines represent declared graph connections, not added land. The new assignment may use different links within each district.</p>
<h2>Connectivity and postprocessing</h2><div class="table-wrap"><table><thead><tr><th>Run</th><th>Selected / used links</th><th>Physical → policy components</th><th>Repair / balance moves</th></tr></thead><tbody>{rows}</tbody></table></div><p class="small">Each used connection has both endpoint blocks in its district. Unsimplified polygon validation checks complete source coverage and district connectivity independently of the optimizer and display simplification.</p>
<h2>What changed</h2><p>The original inner population-balancing optimizer stopped <code>ABNORMAL</code> without advancing, even though center movement was reported converged. The correction removes irrelevant per-block distance offsets, normalizes remaining squared costs and population mass, and subtracts a common offset from the weights. Public centers and weights retain their original units. Zero-population blocks remain assigned but do not determine the population objective's scale.</p><p>The line-search limit is also raised to <strong>100</strong>, and unsuccessful or nonfinite optimizer output raises an explicit failure. Seed, outer/inner iteration budgets, source data and exact connections are unchanged; old and new code hashes are recorded.</p>
<h2>Measured runtime</h2><div class="table-wrap"><table><thead><tr><th>Phase</th><th>Original</th><th>Corrected</th></tr></thead><tbody>{times}</tbody></table></div><p class="small">Both are complete fresh-process pipelines using warm source and physical-graph caches. Runs occurred serially at different times on a shared desktop; they are not isolated hardware comparisons. The earlier fixed-center diagnostic was not a connected plan or full benchmark and is not used as this baseline. The pipeline timer excludes imports, the initial preservation inventory and final report flush.</p>
<h2>Verified preservation</h2><p>The entire previous Hawaii water-policy output—including reports and diagnostics—remains byte-identical, as do the original strict results, national manifest and source archive. The new inventory verifies {new['preserved_file_count_verified']} preserved files. All {old['compressed_artifacts_verified'] + new['compressed_artifacts_verified']} compressed map artifacts in this comparison match their decompressed hashes.</p><p class="small">Saved copies of the <a href="baseline-code/districting/algorithm.py">original algorithm</a> and <a href="baseline-code/scripts/benchmark_hawaii_water.py">original benchmark runner</a> match the original report's code hashes.</p><p class="small">{escape(data['validation_note'])}</p>
<nav aria-label="Evidence"><a href="comparison.json">Comparison JSON</a><a href="states/15/districts-2/benchmark.json">Corrected benchmark</a><a href="{OLD_URL}benchmark.json">Original benchmark</a><a href="../../policies/hawaii-water-v1/">Original three-plan comparison</a><a href="../../diagnostics/hawaii/">Original source diagnosis</a></nav></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', default='Saved benchmark, map and preservation hashes were verified while generating this comparison.')
    args = parser.parse_args()
    data = summary(args.validation_note)
    raw = json.dumps(data, indent=2, allow_nan=False) + '\n'
    outputs = {ROOT / 'prompts/hawaii-optimizer-fix.json': raw,
               ROOT / 'prompts/hawaii-optimizer-fix.md': markdown(data),
               OUTPUT / 'comparison.json': raw, OUTPUT / 'index.html': html_page(data)}
    for path, content in outputs.items():
        path.write_text(content, encoding='utf-8')
    print('Wrote the Hawaii K2 optimizer comparison and durable reports.')


if __name__ == '__main__':
    main()
