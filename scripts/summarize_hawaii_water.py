"""Build an evidence-linked comparison of terminal Hawaii water-policy runs.

Input benchmarks, strict results and generated maps remain read-only. This
summary is deliberately separate from the historical national suite manifest.
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
POLICY_ROOT = SUITE / 'policies/hawaii-water-v1'
BASE_URL = 'http://127.0.0.1:8770/policies/hawaii-water-v1/'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def local_link(path: Path) -> str:
    return path.resolve().as_posix()


def load_run(k: int) -> dict[str, Any]:
    directory = POLICY_ROOT / f'states/15/districts-{k}'
    path = directory / 'benchmark.json'
    report = read_json(path)
    if report.get('status') not in ('complete_under_island_water_policy', 'complete_under_population_aware_water_policy'):
        raise ValueError(f'K{k} is not terminal and successful; no comparison was written.')
    if report['district_count'] != k or report['state_fips'] != '15':
        raise ValueError('Unexpected run identity.')
    if not report['final_plan']['all_districts_policy_connected']:
        raise ValueError('Final part graph failed the declared policy.')
    audit = report['maps']['connectivity_validation']
    if not audit['passed'] or not audit['source_coverage_preserved_exactly'] or audit['source_geometry_modified']:
        raise ValueError('Independent map validation did not preserve source coverage.')
    if not all(report['preservation_audit'][key] for key in (
        'all_original_strict_files_byte_identical', 'national_suite_byte_identical',
        'source_archive_byte_identical', 'run_code_unchanged',
    )):
        raise ValueError('Run preservation audit failed.')
    for name, expected in report['artifact_sha256'].items():
        if sha256(directory / name) != expected:
            raise ValueError(f'Artifact hash mismatch: K{k} / {name}')
    for name, expected in read_json(directory / 'preserved-file-inventory.json').items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f'Preserved strict evidence changed: {name}')
    geojson = json.loads(gzip.decompress((directory / 'maps/water-connections.geojson.gz').read_bytes()))
    connections = [feature['properties'] for feature in geojson['features']]
    for link in connections:
        used = link['used_by_district']
        if used is not None and (not 0 <= used < k or link['endpoint_districts'] != [used, used]):
            raise ValueError('A used connection does not belong wholly to one district.')
        if used is None and len(set(link['endpoint_districts'])) != 2:
            raise ValueError('An unused connection has inconsistent endpoint districts.')
    result = {key: report[key] for key in (
        'district_count', 'house_sizes', 'status', 'configuration', 'source',
        'code_sha256', 'solver', 'solver_progress', 'postprocessing', 'final_plan', 'phases',
        'timed_pipeline_wall_seconds', 'peak_process_working_set_bytes',
        'preservation_audit', 'physical_part_graph_cache', 'artifact_sha256', 'island_policy_audit',
    )}
    result.update({
        'url': BASE_URL + f'states/15/districts-{k}/',
        'benchmark_path': path.relative_to(ROOT).as_posix(), 'benchmark_sha256': sha256(path),
        'peak_process_working_set_mib': report['peak_process_working_set_bytes'] / 2**20,
        'physical_polygon_components': [d['physical_polygon_components'] for d in audit['districts']],
        'policy_polygon_components': [d['connected_components_after_links'] for d in audit['districts']],
        'strict_polygon_validation': report['maps']['strict_validation'],
        'policy_polygon_validation': audit,
        'connections': connections, 'selected_link_count': len(connections),
        'used_link_count': sum(link['used_by_district'] is not None for link in connections),
        'water_policy_record': read_json(directory / 'water-connections.json'),
        'payloads': {
            'district_outlines': report['maps']['district_outlines'],
            'water_connections': report['maps']['water_connections'],
            'load_scenarios': report['maps']['load_scenarios'],
        },
    })
    inner = [row['inner_optimizer'] for row in report['solver_progress'] if 'inner_optimizer' in row]
    failures = [item for item in inner if not item['success']]
    result['inner_optimizer_summary'] = {
        'pass_count': len(inner), 'failed_pass_count': len(failures),
        'zero_iteration_failed_pass_count': sum(item['iterations'] == 0 for item in failures),
        'failure_messages': sorted({item['message'].strip() for item in failures}),
        'reported_center_convergence_is_not_inner_optimizer_success': True,
    }
    result['population_deviation_exceeds_one_percent'] = report['final_plan']['max_absolute_deviation_percent'] > 1
    return result


def summary(validation_note: str) -> dict[str, Any]:
    runs = [load_run(k) for k in (2, 3, 4)]
    strict_path = SUITE / 'states/15/districts-2/benchmark.json'
    strict = read_json(strict_path)
    diagnosis_path = SUITE / 'diagnostics/hawaii/diagnosis.json'
    diagnosis = read_json(diagnosis_path)
    if strict['status'] != 'unsupported_topology':
        raise ValueError('Original strict status changed.')
    if len({run['source']['archive_sha256'] for run in runs}) != 1:
        raise ValueError('Runs did not use the same source archive.')
    if any(run['code_sha256'] != runs[0]['code_sha256'] for run in runs[1:]):
        raise ValueError('Runs did not use the same measured code.')
    if any(sum(run['final_plan']['district_populations']) != diagnosis['total_population'] for run in runs):
        raise ValueError('A plan does not conserve the source resident total.')
    group_counts = [len(run['island_policy_audit']['groups']) for run in runs]
    root_counts = [run['island_policy_audit']['eligible_root_count'] for run in runs]
    if group_counts != [1, 1, 1] or root_counts != [1, 1, 1]:
        raise ValueError('The comparison narrative must be reviewed for a different island-group result.')
    preflight_path = POLICY_ROOT / 'population-preflight-comparison.json'
    preflight = read_json(preflight_path)
    if (sha256(ROOT / preflight['source_terminal_report']) != preflight['source_terminal_report_sha256']
            or sha256(diagnosis_path) != preflight['original_diagnosis_sha256']
            or preflight['source_archive_sha256'] != runs[0]['source']['archive_sha256']):
        raise ValueError('Hypothetical preflight comparison provenance changed.')
    examples = [item for item in preflight['comparisons'] if item['district_count'] in (8, 10)]
    if len(examples) != 2 or any(not item['hypothetical_only'] or item['constructed_plan'] for item in examples):
        raise ValueError('The higher-count comparison must remain explicitly hypothetical.')
    conditioning_path = POLICY_ROOT / 'diagnostics/k2-conditioning.json'
    conditioning = read_json(conditioning_path)
    if (conditioning['kind'] != 'fixed_saved_center_inner_solve_only'
            or not conditioning['does_not_construct_valid_connected_plan']
            or not conditioning['does_not_modify_solver_or_benchmark']
            or sha256(POLICY_ROOT / conditioning['source_benchmark']) != runs[0]['benchmark_sha256']):
        raise ValueError('K2 conditioning evidence must refer to the preserved original benchmark and an inner-only diagnostic.')
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Hawaii only; House 435 / 574 / 692 / 1000 share three distinct plans.',
        'policy': 'shared_edges_plus_population_aware_recorded_water_connections',
        'block_count': diagnosis['block_count'], 'total_population': diagnosis['total_population'],
        'physical_component_count': diagnosis['physical_component_count'], 'runs': runs,
        'validation_note': validation_note,
        'hypothetical_preflight': {'source': preflight_path.relative_to(ROOT).as_posix(),
                                  'sha256': sha256(preflight_path), 'comparisons': examples,
                                  'limitations': preflight['limitations']},
        'k2_conditioning': {'source': conditioning_path.relative_to(ROOT).as_posix(),
                            'sha256': sha256(conditioning_path), 'record': conditioning,
                            'source_benchmark_sha256': runs[0]['benchmark_sha256']},
        'strict_baseline': {
            'status': strict['status'], 'benchmark_path': strict_path.relative_to(ROOT).as_posix(),
            'benchmark_sha256': sha256(strict_path),
            'preflight_wall_seconds': strict['timed_pipeline_wall_seconds'],
            'solver_executed': False,
            'note': 'K3 and K4 reused the source-topology exception; no strict district plans or separate solver timings exist.',
            'diagnosis_path': diagnosis_path.relative_to(ROOT).as_posix(),
            'diagnosis_sha256': sha256(diagnosis_path),
        },
        'measurement_notes': [
            'New plans ran serially in fresh processes with cached source and physical part graphs.',
            'Full pipeline includes source preparation, population-aware links, solving, repair, independent audits and export.',
            'The pipeline timer excludes process imports, the initial preservation inventory and the final report flush.',
            'Shared desktop timings are observations, not isolated hardware benchmarks.',
            'The original strict preflight rejection is not a comparable strict-solver baseline; no speedup is claimed.',
            'Component population feasibility is a necessary check, not a guarantee of achieved whole-block district balance.',
            'Selected water links are available graph edges; only same-district endpoints contribute to district connectivity.',
        ],
    }


def phase(run: dict[str, Any], *names: str) -> float:
    for name in names:
        if name in run['phases']:
            return float(run['phases'][name]['wall_seconds'])
    raise ValueError('Required phase missing: ' + ', '.join(names))


def population_text(run: dict[str, Any]) -> str:
    return ' / '.join(f'{value:,}' for value in run['final_plan']['district_populations'])


def deviation_text(run: dict[str, Any]) -> str:
    plan = run['final_plan']
    count = plan['max_absolute_deviation_people']
    return f'{plan["max_absolute_deviation_percent"]:.6f}% ({count:,.3f} {"person" if count <= 1 else "people"})'


def conditioning_text(data: dict[str, Any]) -> str:
    rows = data['k2_conditioning']['record']['results']
    original = next(row for row in rows if row['coordinate_divisor'] == 1 and row['maxls_override'] is None)
    scaled = next(row for row in rows if row['coordinate_divisor'] == 1000 and row['maxls_override'] is None)
    extended = next(row for row in rows if row['coordinate_divisor'] == 1 and row['maxls_override'] == 100)
    if original['optimizer']['success'] or not scaled['optimizer']['success'] or not extended['optimizer']['success']:
        raise ValueError('Conditioning conclusions must be reviewed for changed diagnostic outcomes.')
    return (
        f'With K2\'s saved centers fixed, the original coordinates/default line search again stopped ABNORMAL '
        f'after {original["optimizer"]["iterations"]} iterations. Expressing the same geometry in kilometers '
        f'(coordinates divided by 1,000) succeeded in {scaled["optimizer"]["iterations"]} iterations: '
        f'{", ".join(f"{value:,}" for value in scaled["district_populations"])} people, '
        f'{scaled["maximum_deviation_people"]:g} people maximum deviation. Keeping the original coordinates '
        f'and increasing the line-search limit to 100 also reached {extended["maximum_deviation_people"]:g} '
        'people deviation. This is evidence of numerical scaling and line-search sensitivity in the inner solver. '
        'It is an inner-solve diagnostic only: no corrected connected plan, full benchmark or source change was made. '
        'The next fix should nondimensionalize the inner objective and weights, report inner optimizer failure '
        'explicitly, then rerun repair and independent connectivity validation.'
    )


def markdown(data: dict[str, Any]) -> str:
    runs = data['runs']
    rows = '\n'.join(
        f'| [{r["district_count"]} districts]({r["url"]}) | {", ".join(map(str, r["house_sizes"]))} | '
        f'{population_text(r)} | {deviation_text(r)} | {r["timed_pipeline_wall_seconds"]:.2f} s | '
        f'{r["peak_process_working_set_mib"]:.1f} MiB |' for r in runs)
    timing = '\n'.join(
        f'| {r["district_count"]} | {phase(r,"prepare_population_aware_water_connections","prepare_recorded_water_connection"):.2f} s | '
        f'{phase(r,"solve"):.3f} s | {phase(r,"repair_and_rebalance"):.3f} s | '
        f'{phase(r,"independent_polygon_validation_and_map_export"):.2f} s |' for r in runs)
    connectivity = '\n'.join(
        f'| {r["district_count"]} | {r["selected_link_count"]} / {r["used_link_count"]} | '
        f'{r["physical_polygon_components"]} → {r["policy_polygon_components"]} | '
        f'{r["solver"]["outer_iterations"]} / {r["solver"]["centers_converged"]} | '
        f'{r["postprocessing"]["repair_move_count"]} / {r["postprocessing"]["rebalance_move_count"]} | '
        f'{r["postprocessing"]["stop_reason"]} |' for r in runs)
    evidence = ' · '.join(f'[K{r["district_count"]} benchmark]({local_link(ROOT / r["benchmark_path"])})' for r in runs)
    issues = '\n'.join(
        f'- **K{r["district_count"]}: {r["final_plan"]["max_absolute_deviation_percent"]:.6f}% maximum deviation.** '
        f'{r["inner_optimizer_summary"]["failed_pass_count"]}/{r["inner_optimizer_summary"]["pass_count"]} inner optimizer passes failed '
        f'({", ".join(r["inner_optimizer_summary"]["failure_messages"]) or "none"}); '
        f'{r["inner_optimizer_summary"]["zero_iteration_failed_pass_count"]} failures completed zero iterations. '
        f'Rebalancing made {r["postprocessing"]["rebalance_move_count"]} moves and stopped at `{r["postprocessing"]["stop_reason"]}`.'
        for r in runs if r['inner_optimizer_summary']['failed_pass_count'])
    poor = [f'K{r["district_count"]}' for r in runs if r['population_deviation_exceeds_one_percent']]
    warning = ('**Connectivity passes; population balance varies sharply. ' + ', '.join(poor) +
               ' exceeds 1% deviation and should not be presented as a balanced plan.**') if poor else '**Connectivity and measured population balance are reported separately below.**'
    preflight_rows = '\n'.join(
        f'| {item["district_count"]} (hypothetical) | {item["prior_nearest_only"]["population_bound"]["best_max_deviation_pct"]:.6f}% | '
        f'{item["population_aware"]["population_bound"]["best_max_deviation_pct"]:.6f}% | '
        f'{len(item["population_aware"]["groups"])} | {item["population_aware"]["population_bound"]["seat_counts"]} |'
        for item in data['hypothetical_preflight']['comparisons'])
    return f'''# Hawaii: population-aware island-water connections

{warning}

All three requested plans pass polygon-part and independent polygon connectivity **under their recorded water policy**. That terminal status does not certify population quality. All **{data['block_count']:,} blocks and {data['total_population']:,} residents** remain covered exactly. The original strict results, source archive and national manifest remain byte-identical.

[Comparison]({BASE_URL}) · [Original source diagnosis](http://127.0.0.1:8770/diagnostics/hawaii/). Maps open on the main islands; **Full northwest extent** shows retained remote coverage. Magenta dashed lines are used within a district; gray selected links are not. **Inspect connection** shows exact endpoint blocks. Neither kind is land.

| Plan | House sizes | Final populations | Maximum deviation | Full pipeline | Peak working set |
|---|---|---|---:|---:|---:|
{rows}

{issues}

K3 and K4 had no failed inner passes. K4 reaches the best possible integer-population balance; K3 is within 1⅓ people of ideal. K2's reported center convergence does not establish successful population balancing, and its local repair stop does not prove a better plan impossible.

**K2 diagnostic:** {conditioning_text(data)} [Saved diagnostic]({BASE_URL}diagnostics/k2-conditioning.json). Its timings are separate from the benchmark table.

Population balance is separate from connectivity. The new rule first identifies original components with at least **99% of one ideal district's population**. It tries small-island attachments and mergers of those larger roots, keeping the greatest number of separate groups whose populations admit whole-number district allocations within **1% of the statewide ideal**. Distance breaks ties among the feasible groupings using deterministic constrained spanning forests; this is not a globally optimal geometric network.

For K2/K3/K4, **Oʻahu is the only eligible root**. All 17 physical components therefore join one group through 16 selected connections. Oʻahu can still contain several districts; being a root does not make it one district. Larger islands can remain separate at other counts only when that group's population fits its allocated district count. The 1% group check is a necessary preflight budget, **not final-plan acceptance** or a whole-block balance guarantee.

The larger-island behavior is visible in these **preflight illustrations only; no K8/K10 district plans were run**:

| Hawaii districts | Old nearest-only necessary bound | New necessary bound | Separate groups | Allocated districts |
|---|---:|---:|---:|---|
{preflight_rows}

At K8, changing small-island attachments preserves two root groups. At K10, Oʻahu remains separate while the Hawaiʻi Island and Maui roots merge. These are optimistic bounds on the selected grouping, not achieved district deviations. The new candidate set additionally excludes connections crossing unrelated source interiors; the historical diagnostic candidate set did not. The rule prioritizes keeping feasible groups separate over attaining the lowest possible population bound.

| Districts | Water-policy preparation | Solve | Repair/balance | Independent polygon audit/export |
|---|---:|---:|---:|---:|
{timing}

Runs were serial, in fresh processes with cached source/physical graphs. Full pipeline includes preparation and all audits/export; this table lists selected phases. These are shared-desktop observations. The original strict K2 run spent **{data['strict_baseline']['preflight_wall_seconds']:.4f} seconds rejecting topology before solving**; K3/K4 reused its exception. There are no strict district plans or comparable strict-solver runtimes. With {data['physical_component_count']} physical components retained, fewer than {data['physical_component_count']} districts cannot each be physically connected under pure shared edges.

| Districts | Selected / used links | Physical → policy polygon components | Outer iterations / converged | Repair / balance moves | Stop reason |
|---|---|---|---|---|---|
{connectivity}

Each district uses only links whose two endpoint blocks belong to it; no route passes through another district. Independent unsimplified polygon validation checks this connectivity and complete coverage, separately from physical connectivity and display simplification. All water and zero-population blocks remain. Candidate endpoints minimize boundary gaps in a local plane per pair; lengths are spherical endpoint distances, not certified shortest geodesics, shoreline gaps or ferry routes.

{data['validation_note']}

Evidence: {evidence} · [Comparison JSON]({local_link(ROOT / 'prompts/hawaii-water-benchmark.json')}) · [Runner]({local_link(ROOT / 'scripts/benchmark_hawaii_water.py')}). Reports preserve code/source hashes, assignments, move audits, exact connection endpoints, population-allocation decisions and compressed payload sizes. Source archive SHA-256: `{runs[0]['source']['archive_sha256']}`.
'''


def html_page(data: dict[str, Any]) -> str:
    runs = data['runs']
    unresolved = any(r['population_deviation_exceeds_one_percent'] for r in runs)
    headline = 'Connectivity passes.<br>Population balance varies sharply.' if unresolved else 'Island connections with<br>population feasibility checked.'
    cards = ''.join(f'''<article class="card"><div class="tag">{r['district_count']} districts · House {', '.join(map(str, r['house_sizes']))}</div>
<h2>{r['final_plan']['max_absolute_deviation_percent']:.6f}%<span>maximum population deviation</span></h2><p>{population_text(r)} people</p>
<p class="muted">{r['timed_pipeline_wall_seconds']:.2f} s full pipeline · {r['peak_process_working_set_mib']:.1f} MiB peak</p>
<p class="quality{' warning' if r['inner_optimizer_summary']['failed_pass_count'] else ''}">{r['inner_optimizer_summary']['failed_pass_count']}/{r['inner_optimizer_summary']['pass_count']} inner optimizer passes failed · {r['postprocessing']['rebalance_move_count']} rebalance moves</p>
<a class="button" href="states/15/districts-{r['district_count']}/">Open {r['district_count']}-district map →</a></article>''' for r in runs)
    rows = ''.join(f'<tr><th>{r["district_count"]} districts</th><td>{deviation_text(r)}</td><td>{r["selected_link_count"]} / {r["used_link_count"]}</td><td>{escape(str(r["physical_polygon_components"]))} → {escape(str(r["policy_polygon_components"]))}</td></tr>' for r in runs)
    phases = [('Full measured pipeline', ()), ('Water-policy preparation', ('prepare_population_aware_water_connections', 'prepare_recorded_water_connection')),
              ('Numerical solve', ('solve',)), ('Repair and rebalance', ('repair_and_rebalance',)),
              ('Independent polygon audit and map export', ('independent_polygon_validation_and_map_export',))]
    timings = ''.join('<tr><th>' + name + '</th>' + ''.join(f'<td>{phase(r,*keys) if keys else r["timed_pipeline_wall_seconds"]:.3f} s</td>' for r in runs) + '</tr>' for name, keys in phases)
    evidence = ''.join(f'<a href="states/15/districts-{r["district_count"]}/benchmark.json">K{r["district_count"]} benchmark</a>' for r in runs)
    optimizer_rows = ''.join(f'<tr><th>{r["district_count"]} districts</th><td>{r["inner_optimizer_summary"]["failed_pass_count"]} / {r["inner_optimizer_summary"]["pass_count"]}</td><td>{escape(", ".join(r["inner_optimizer_summary"]["failure_messages"]) or "None")}</td><td>{r["inner_optimizer_summary"]["zero_iteration_failed_pass_count"]}</td><td>{r["postprocessing"]["rebalance_move_count"]} / {escape(r["postprocessing"]["stop_reason"])}</td></tr>' for r in runs)
    preflight_rows = ''.join(
        f'<tr><th>{item["district_count"]} (hypothetical)</th><td>{item["prior_nearest_only"]["population_bound"]["best_max_deviation_pct"]:.6f}%</td>'
        f'<td>{item["population_aware"]["population_bound"]["best_max_deviation_pct"]:.6f}%</td>'
        f'<td>{len(item["population_aware"]["groups"])}</td><td>{escape(str(item["population_aware"]["population_bound"]["seat_counts"]))}</td></tr>'
        for item in data['hypothetical_preflight']['comparisons'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hawaii · Population-aware water policy</title><style>
:root{{color-scheme:dark;--bg:#10191f;--panel:#1a252d;--text:#e9f2f5;--muted:#a6bac5;--line:#354955;--accent:#6ed5df;--water:#ff91cf}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,sans-serif}}main{{max-width:1280px;padding:36px 24px 52px;margin:auto}}h1{{font-size:clamp(28px,4vw,42px);line-height:1.15;margin:10px 0 16px}}h2{{font-size:22px;line-height:1.3;margin:12px 0}}p{{margin:10px 0 18px}}a{{color:var(--accent)}}.tag{{font:12px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--water)}}.muted,.small{{color:var(--muted)}}.small{{font-size:13px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}}.card{{background:var(--panel);padding:22px;border:1px solid var(--line);border-radius:10px}}.card h2{{font-size:30px}}.card h2 span{{display:block;font-size:14px;color:var(--muted);font-weight:400}}.button{{display:inline-block;padding:9px 16px;border:1px solid var(--accent);border-radius:5px;text-decoration:none}}.callout{{border-left:3px solid var(--water);padding:10px 18px;background:#281e2c}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0 22px}}th,td{{text-align:right;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}}th:first-child,td:first-child{{text-align:left}}thead th{{color:var(--muted);font-weight:500}}nav{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}}a:focus-visible{{outline:3px solid var(--water);outline-offset:4px}}@media(max-width:950px){{.cards{{grid-template-columns:1fr}}main{{padding:24px 16px}}}}
.quality{{color:#91e5d2;font-size:13px}}.quality.warning{{color:#ffd08f}}
</style></head><body><main><div class="tag">Hawaii · Census blocks · Population-aware water policy</div><h1>{headline}</h1><p>Three saved outputs cover all <strong>{data['block_count']:,} blocks and {data['total_population']:,} residents</strong>. Each passes part-graph and independent unsimplified polygon validation under <strong>shared edges + recorded water connections</strong>. This certifies connectivity and coverage, <strong>not population balance</strong>. Original strict results remain unchanged.</p>
<div class="cards">{cards}</div><p class="callout"><strong>The dashed connections are not land.</strong> Magenta links connect two blocks in the same district; gray selected links are unused by a district. Use <strong>Inspect connection</strong> on each map or <strong>Full northwest extent</strong> to inspect the retained remote islands. County blocks load only when requested.</p>
<h2>Population and connectivity</h2><div class="table-wrap"><table><thead><tr><th>Plan</th><th>Maximum deviation</th><th>Selected / used links</th><th>Physical → policy polygon components</th></tr></thead><tbody>{rows}</tbody></table></div><p class="small">Component lists follow district order. Physical separation is preserved and reported separately; a link contributes only if both endpoint blocks belong to the district. The independent polygon audit checks unsimplified geography, not the display outlines.</p>
<h2>Solver warnings remain visible</h2><div class="table-wrap"><table><thead><tr><th>Plan</th><th>Failed / total inner passes</th><th>Failure messages</th><th>Failed passes with zero iterations</th><th>Rebalance moves / stop</th></tr></thead><tbody>{optimizer_rows}</tbody></table></div><p class="callout">A reported stop in center movement is different from successful population balancing. These saved outputs expose the inner optimizer failures and final population deviations. A local rebalancing stop does not prove that a balanced plan is impossible.</p>
<h2>K2 diagnostic: numerical conditioning</h2><p>{escape(conditioning_text(data))}</p><p class="small"><a href="diagnostics/k2-conditioning.json">Inspect the saved fixed-center diagnostic</a>. These experiments are separate from all three measured benchmark runs above.</p>
<h2>Population-aware grouping</h2><p>An island being large enough for one district does not mean its population fits a whole number of statewide district quotas. The rule keeps the greatest number of separate large-island groups that can receive integer district allocations within a <strong>1% population band</strong>, trying small-island attachments and root mergers before comparing distance. Original components with at least 99% of one ideal district qualify as roots.</p><p><strong>At 2, 3 and 4 districts, only Oʻahu qualifies.</strong> All 17 source components therefore join one group through 16 selected connections. Oʻahu may contain several districts. At higher counts, larger islands may remain separate when their group populations fit their district allocations.</p><p class="small">The 1% band is a necessary group-feasibility preflight budget, not final-plan acceptance or a guarantee about indivisible blocks. Distance chooses among deterministic constrained spanning forests; no globally optimal geographic network is claimed. The exact allocation decisions and connection provenance are in the saved benchmarks. Lengths are spherical distances between local nearest-boundary candidates in water-inclusive census coverage, not certified shortest geodesics, shoreline gaps or ferry routes. Candidates crossing unrelated source-component interiors are excluded.</p>
<h2>Larger islands: preflight illustrations only</h2><p>No 8- or 10-district plans were generated. These values are optimistic necessary population bounds for the selected island groups, not achieved map balance.</p><div class="table-wrap"><table><thead><tr><th>Hawaii districts</th><th>Old nearest-only bound</th><th>New group bound</th><th>Separate groups</th><th>Allocated districts</th></tr></thead><tbody>{preflight_rows}</tbody></table></div><p class="small">At 8 districts, different small-island attachments retain two root groups. At 10, Oʻahu stays separate and the Hawaiʻi Island and Maui roots merge. The new candidate set also excludes crossings through unrelated source interiors, unlike the older diagnosis. Keeping the most feasible groups separate takes priority over reducing the population bound further. <a href="population-preflight-comparison.json">Inspect preflight evidence</a>.</p>
<h2>Measured runtime</h2><div class="table-wrap"><table><thead><tr><th>Stage</th><th>2 districts</th><th>3 districts</th><th>4 districts</th></tr></thead><tbody>{timings}</tbody></table></div><p class="small">New runs were serial in fresh processes with cached source and physical graphs. Full pipeline includes preparation, audits and map export; selected phases are shown. Shared-desktop measurements are not isolated benchmarks.</p>
<h2>Preserved strict baseline</h2><p>The original strict run rejected {data['physical_component_count']} disconnected source components in <strong>{data['strict_baseline']['preflight_wall_seconds']:.4f} seconds before solving</strong>. The other counts reused that exception. There is no strict population result or full solver runtime to compare against. Retaining all {data['physical_component_count']} separate components with fewer districts cannot satisfy pure shared-edge connectivity.</p><p class="small">{escape(data['validation_note'])}</p>
<nav aria-label="Evidence"><a href="comparison.json">Comparison JSON</a>{evidence}<a href="../../diagnostics/hawaii/">Original diagnosis</a><a href="../../">National results</a></nav><p class="small">Each run records source/code hashes, final assignments, move audit, population-allocation decisions, exact connections, preservation checks and compressed map payload sizes. The strict national manifest is unchanged.</p></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', default='Saved artifact hashes and preservation inventories were verified while building this comparison.')
    args = parser.parse_args()
    data = summary(args.validation_note)
    text = json.dumps(data, indent=2, allow_nan=False) + '\n'
    outputs = {
        ROOT / 'prompts/hawaii-water-benchmark.json': text,
        ROOT / 'prompts/hawaii-water-benchmark.md': markdown(data),
        POLICY_ROOT / 'comparison.json': text,
        POLICY_ROOT / 'index.html': html_page(data),
    }
    for path, content in outputs.items():
        path.write_text(content, encoding='utf-8')
    print('Wrote Hawaii comparison reports and policy index.')


if __name__ == '__main__':
    main()
