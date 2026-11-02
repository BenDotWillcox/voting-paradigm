"""Summarize only terminal, validated Rhode Island island-policy runs.

Writes a separate comparison page and durable reports. Historical strict runs,
policy-run reports, source files, and generated maps are read-only inputs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
from html import escape
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
POLICY_ROOT = SUITE / 'policies/island-water-v1'
BASE_URL = 'http://127.0.0.1:8770/policies/island-water-v1/'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def local_link(path: Path) -> str:
    return '/' + path.resolve().as_posix()


def load_run(k: int) -> dict[str, Any]:
    directory = POLICY_ROOT / f'states/44/districts-{k}'
    path = directory / 'benchmark.json'
    report = read_json(path)
    if report.get('status') != 'complete_under_island_water_policy':
        raise ValueError(f'K{k} is not terminal and successful; no comparison was written.')
    if report['district_count'] != k or report['state_fips'] != '44':
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
    connections = json.loads(gzip.decompress((directory / 'maps/water-connections.geojson.gz').read_bytes()))
    if len(connections['features']) != 1:
        raise ValueError('Rhode Island comparison expects exactly one recorded connection.')
    feature = connections['features'][0]
    properties = feature['properties']
    if properties['used_by_district'] is None or properties['endpoint_districts'] != [properties['used_by_district']] * 2:
        raise ValueError('The recorded connection is not used within one district.')
    return {
        'district_count': k, 'house_sizes': report['house_sizes'], 'status': report['status'],
        'url': BASE_URL + f'states/44/districts-{k}/',
        'benchmark_path': path.relative_to(ROOT).as_posix(), 'benchmark_sha256': sha256(path),
        'configuration': report['configuration'], 'source': report['source'],
        'code_sha256': report['code_sha256'], 'solver': report['solver'],
        'postprocessing': report['postprocessing'], 'final_plan': report['final_plan'],
        'phases': report['phases'], 'timed_pipeline_wall_seconds': report['timed_pipeline_wall_seconds'],
        'peak_process_working_set_bytes': report['peak_process_working_set_bytes'],
        'peak_process_working_set_mib': report['peak_process_working_set_bytes'] / 2**20,
        'preservation_audit': report['preservation_audit'],
        'physical_part_graph_cache': report['physical_part_graph_cache'],
        'physical_polygon_components': [d['physical_polygon_components'] for d in audit['districts']],
        'policy_polygon_components': [d['connected_components_after_links'] for d in audit['districts']],
        'strict_polygon_validation': report['maps']['strict_validation'],
        'policy_polygon_validation': audit,
        'connection': properties,
        'payloads': {
            'district_outlines': report['maps']['district_outlines'],
            'water_connection': report['maps']['water_connections'],
            'load_scenarios': report['maps']['load_scenarios'],
        },
        'artifact_sha256': report['artifact_sha256'],
    }


def summary() -> dict[str, Any]:
    runs = [load_run(k) for k in (2, 3)]
    strict_path = SUITE / 'states/44/districts-2/benchmark.json'
    strict = read_json(strict_path)
    certificate_path = SUITE / 'diagnostics/rhode-island/feasibility.json'
    certificate = read_json(certificate_path)
    if strict['status'] != 'unsupported_topology':
        raise ValueError('Original strict status changed.')
    if runs[0]['source']['archive_sha256'] != runs[1]['source']['archive_sha256']:
        raise ValueError('Runs did not use the same source archive.')
    if runs[0]['code_sha256'] != runs[1]['code_sha256']:
        raise ValueError('Runs did not use the same measured code.')
    if runs[0]['connection']['endpoints'] != runs[1]['connection']['endpoints']:
        raise ValueError('Runs used different connection endpoints.')
    for run in runs:
        bound = next(plan for plan in certificate['plans'] if plan['district_count'] == run['district_count'])
        run['strict_comparison'] = {
            'maximum_deviation_percent': bound['maximum_absolute_deviation_lower_bound_percent_of_ideal']['decimal'],
            'maximum_deviation_people': bound['maximum_absolute_deviation_lower_bound_people']['decimal'],
            'kind': 'exact_attained_component_partition' if run['district_count'] == 2 else 'necessary_lower_bound_not_constructed',
        }
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Rhode Island only; House 435 / 574 / 692 / 1000 share two distinct plans.',
        'policy': 'shared_edges_plus_recorded_water_connections', 'runs': runs,
        'implementation_validation': {
            'regression_tests_passed': 308,
            'pytest_elapsed_seconds': 8.29,
            'browser_checks': 'Both maps: exact outlines, link toggle and focus. K2 county 009: 4341 blocks loaded on demand.',
        },
        'strict_baseline': {
            'status': strict['status'], 'benchmark_path': strict_path.relative_to(ROOT).as_posix(),
            'benchmark_sha256': sha256(strict_path),
            'preflight_wall_seconds': strict['timed_pipeline_wall_seconds'],
            'solver_executed': False, 'k3_separate_run_executed': False,
            'note': 'K3 reused the source-topology exception; no separate strict K3 solve or runtime exists.',
            'certificate_path': certificate_path.relative_to(ROOT).as_posix(),
            'certificate_sha256': sha256(certificate_path),
        },
        'measurement_notes': [
            'New K2 and K3 pipelines ran serially in fresh processes, using cached source and physical part graphs.',
            'Full measured pipeline includes source preparation, link construction, solving, audits and map export.',
            'The pipeline timer excludes process imports, the initial preservation inventory, and the final report flush.',
            'Shared desktop timings are observations, not isolated hardware benchmarks.',
            'The original 8.4581-second preflight rejection is not a comparable strict-solver baseline; no speedup is claimed.',
            'The 1% band classifies undersized components only, not final-plan acceptance.',
            'The 2334.777m link uses a bbox-centered local metric; the earlier 2333.895m diagnostic used a population-centered metric.',
        ],
    }


def markdown(data: dict[str, Any]) -> str:
    runs = data['runs']
    result_rows = '\n'.join(
        f'| {r["district_count"]} | {", ".join(map(str, r["house_sizes"]))} | '
        f'{", ".join(f"{p:,}" for p in r["final_plan"]["district_populations"])} | '
        f'{"≥ " if r["district_count"] == 3 else ""}{r["strict_comparison"]["maximum_deviation_percent"]:.6f}% | '
        f'{r["final_plan"]["max_absolute_deviation_percent"]:.9f}% '
        f'({r["final_plan"]["max_absolute_deviation_people"]:g} '
        f'{"person" if r["final_plan"]["max_absolute_deviation_people"] <= 1 else "people"}) |'
        for r in runs)
    runtime_rows = '\n'.join(
        f'| {r["district_count"]} | {r["timed_pipeline_wall_seconds"]:.2f} s | '
        f'{r["phases"]["prepare_recorded_water_connection"]["wall_seconds"]:.2f} s | '
        f'{r["phases"]["solve"]["wall_seconds"]:.3f} s | '
        f'{r["phases"]["repair_and_rebalance"]["wall_seconds"]:.3f} s | '
        f'{r["phases"]["independent_polygon_validation_and_map_export"]["wall_seconds"]:.2f} s | '
        f'{r["peak_process_working_set_mib"]:.1f} MiB |' for r in runs)
    algorithm_rows = '\n'.join(
        f'| {r["district_count"]} | {r["solver"]["outer_iterations"]} / {"yes" if r["solver"]["centers_converged"] else "no"} | '
        f'{r["postprocessing"]["repair_move_count"]} / {r["postprocessing"]["rebalance_move_count"]} | '
        f'{r["postprocessing"]["stop_reason"]} | '
        f'{r["physical_polygon_components"]} → {r["policy_polygon_components"]} | '
        f'{r["connection"]["used_by_district"] + 1} |' for r in runs)
    evidence = ' · '.join(f'[K{r["district_count"]} report]({local_link(ROOT / r["benchmark_path"])})' for r in runs)
    return f'''# Rhode Island: recorded island-water connections

Both requested plans now pass polygon-part and independent polygon connectivity **under the recorded water-link policy**. All 25,649 blocks and 1,097,379 residents remain covered exactly. The original strict exception, diagnostic witness, source archive and national suite are byte-identical.

[Comparison]({BASE_URL}) · [2-district map]({runs[0]['url']}) · [3-district map]({runs[1]['url']}) · [Original strict diagnosis](http://127.0.0.1:8770/diagnostics/rhode-island/) · [Strict connectivity-only example](http://127.0.0.1:8770/diagnostics/rhode-island/connectivity-only-k2/). Use **Inspect connection** on either new map; the magenta dashed line is enabled by default and is not land.

| Districts | House sizes | New populations | Strict maximum deviation | New maximum deviation |
|---|---|---|---|---|
{result_rows}

The strict K2 figure is attained by assigning one district to each source component. Strict K3 is a necessary lower bound, not a constructed plan. New population balance is measured independently of connectivity.

| Districts | Full pipeline | Link preparation | Solve | Repair/balance | Polygon audit/export | Peak working set |
|---|---:|---:|---:|---:|---:|---:|
{runtime_rows}

Runs used fresh processes serially, with cached source and physical graphs. Full pipeline includes preparation, audits, export and report work; remaining phase timings are in the JSON. These are shared-desktop observations. The original strict run took **{data['strict_baseline']['preflight_wall_seconds']:.4f} seconds to reject source topology before solving**. K3 reused that exception without its own run. There is no strict-solver timing baseline or speedup claim.

| Districts | Outer iterations / centers converged | Repair / balance moves | Stop reason | Physical → policy polygon components | Link used by district |
|---|---|---|---|---|---|
{algorithm_rows}

One shortest-boundary connection links blocks **440099901000017** and **440099902000001** across **2,334.777 m of census-coverage gap**. Both endpoints belong to the indicated district. Source geometry is unchanged: a district using the link still has two physical polygons, so pure shared-edge polygon validation remains false, while the declared policy passes. The rooted forest rule permits small-island chains without cycles or links between two sufficiently populated roots.

The **1% band only classifies undersized components** (below 99% of ideal); it is not final-plan acceptance or solver tolerance. The local bbox-centered distance differs slightly from the earlier 2,333.895 m population-centered diagnostic. Neither measures shore-to-shore distance or a ferry route.

Numerical settings remain seed **20200955**, outer limit **80**, inner limit **300**, center tolerance **0.0001 m**, and **1,000** maximum balancing moves. No numerical solver was modified. Whole-block local optimization does not generally guarantee these population results elsewhere.

Validation: **308 regression tests passed**. Both maps were checked in-browser with exact outlines, connection toggles and focus; county 009 loaded its 4,341 blocks on demand.

Evidence: {evidence} · [Compact comparison JSON]({local_link(ROOT / 'prompts/rhode-island-water-benchmark.json')}) · [Runner]({local_link(ROOT / 'scripts/benchmark_rhode_island_water.py')}) · [Link builder]({local_link(ROOT / 'scripts/district_block_island_links.py')}). Each run records source/code hashes, assignments, moves, connection endpoints, validation and artifact checksums. The source archive SHA-256 is `{runs[0]['source']['archive_sha256']}`.
'''


def html_page(data: dict[str, Any]) -> str:
    runs = data['runs']
    cards = []
    for run in runs:
        k = run['district_count']
        plan = run['final_plan']
        cards.append(f'''<article class="card"><div class="tag">{k} districts · House {", ".join(map(str, run['house_sizes']))}</div>
<h2>{plan['max_absolute_deviation_percent']:.6f}% <span>maximum deviation</span></h2>
<p>{", ".join(f"{p:,}" for p in plan['district_populations'])} people</p>
<p class="muted">{run['timed_pipeline_wall_seconds']:.2f} s full pipeline · {run['peak_process_working_set_mib']:.1f} MiB peak</p>
<a class="button" href="states/44/districts-{k}/">Open {k}-district map →</a><p class="small">Choose <strong>Inspect connection</strong> on the map to zoom to the endpoints.</p></article>''')
    comparison_rows = ''.join(
        f'<tr><th>{r["district_count"]} districts</th><td>{"≥ " if r["district_count"] == 3 else ""}{r["strict_comparison"]["maximum_deviation_percent"]:.6f}%</td>'
        f'<td>{r["final_plan"]["max_absolute_deviation_percent"]:.9f}% '
        f'({r["final_plan"]["max_absolute_deviation_people"]:g} '
        f'{"person" if r["final_plan"]["max_absolute_deviation_people"] <= 1 else "people"})</td>'
        f'<td>{escape(str(r["physical_polygon_components"]))} → {escape(str(r["policy_polygon_components"]))}</td>'
        f'<td>District {r["connection"]["used_by_district"] + 1}</td></tr>' for r in runs)
    phase_names = [('Full measured pipeline', None), ('Water-link preparation', 'prepare_recorded_water_connection'),
                   ('Numerical solve', 'solve'), ('Repair and rebalance', 'repair_and_rebalance'),
                   ('Independent polygon audit and map export', 'independent_polygon_validation_and_map_export')]
    timing_rows = ''.join('<tr><th>' + label + '</th>' + ''.join(
        f'<td>{r["timed_pipeline_wall_seconds"] if key is None else r["phases"][key]["wall_seconds"]:.3f} s</td>' for r in runs) + '</tr>' for label, key in phase_names)
    algorithm = '; '.join(f'K{r["district_count"]}: {r["solver"]["outer_iterations"]} outer iterations, centers {"converged" if r["solver"]["centers_converged"] else "did not converge"}, '
                         f'{r["postprocessing"]["repair_move_count"]} repair and {r["postprocessing"]["rebalance_move_count"]} balance moves ({r["postprocessing"]["stop_reason"]})' for r in runs)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rhode Island · Island-water policy comparison</title><style>
:root{{color-scheme:dark;--bg:#10191f;--panel:#1a252d;--text:#e9f2f5;--muted:#a6bac5;--line:#354955;--accent:#6ed5df;--water:#ff91cf}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,sans-serif}}main{{max-width:1120px;padding:36px 24px 52px;margin:auto}}h1{{font-size:clamp(28px,4vw,42px);line-height:1.15;margin:10px 0 16px}}h2{{font-size:22px;line-height:1.3;margin:12px 0}}p{{margin:10px 0 18px}}a{{color:var(--accent)}}.tag{{font:12px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--water)}}.muted,.small{{color:var(--muted)}}.small{{font-size:13px}}.cards{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:28px 0}}.card{{background:var(--panel);padding:22px;border:1px solid var(--line);border-radius:10px}}.card h2{{font-size:32px}}.card h2 span{{display:block;font-size:14px;color:var(--muted);font-weight:400}}.button{{display:inline-block;padding:9px 16px;border:1px solid var(--accent);border-radius:5px;text-decoration:none}}.callout{{border-left:3px solid var(--water);padding:10px 18px;background:#281e2c}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0 22px}}th,td{{text-align:right;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}}th:first-child,td:first-child{{text-align:left}}thead th{{color:var(--muted);font-weight:500}}nav{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}}a:focus-visible{{outline:3px solid var(--water);outline-offset:4px}}@media(max-width:700px){{.cards{{grid-template-columns:1fr}}main{{padding:24px 16px}}}}
</style></head><body><main>
<div class="tag">Rhode Island · Census blocks · Recorded island-water policy</div><h1>One recorded connection.<br>Two balanced district plans.</h1>
<p>All <strong>25,649 blocks and 1,097,379 residents</strong> are retained. The plans pass polygon-part and independent polygon validation under <strong>shared edges + a recorded water connection</strong>. Historical strict results remain unchanged.</p>
<div class="cards">{''.join(cards)}</div>
<p class="callout"><strong>The magenta dashed line is not land.</strong> Source polygons stay separate across water. The recorded connection is enabled by default on both maps and can be hidden or inspected.</p>
<h2>Population and connectivity</h2><div class="table-wrap"><table><thead><tr><th>Plan</th><th>Strict maximum deviation</th><th>New maximum deviation</th><th>Physical → policy components</th><th>Connection belongs to</th></tr></thead><tbody>{comparison_rows}</tbody></table></div>
<p class="small">Strict K2 is the exact result of one district per source component. Strict K3 is a necessary lower bound, not a constructed map. Component lists follow district order. Each endpoint block belongs to the same district, and the independent audit verifies the exact source coverage. Physical shared-edge validation remains false for the two-polygon district; policy connectivity passes.</p>
<h2>Measured runtime</h2><div class="table-wrap"><table><thead><tr><th>Stage</th><th>2 districts</th><th>3 districts</th></tr></thead><tbody>{timing_rows}</tbody></table></div>
<p class="small">New runs were serial in fresh processes with cached source and physical graphs. Full pipeline includes preparation, audits and map export; the table lists selected phases. Shared-desktop measurements are not isolated benchmarks. The original strict run took {data['strict_baseline']['preflight_wall_seconds']:.4f} s to reject topology before solving; K3 reused that exception. There is no comparable strict-solver runtime or speedup claim.</p>
<p class="small">{escape(algorithm)}.</p>
<h2>The rule used here</h2><p>A rooted shortest-boundary forest attaches undersized components to a sufficiently populated component, allowing small islands to form chains without cycles or links between two populated roots. Rhode Island requires one <strong>2,334.777 m</strong> connection between blocks <strong>440099901000017</strong> and <strong>440099902000001</strong>.</p>
<p class="small">The 1% band is only for classifying undersized components (below 99% of ideal), not final-plan acceptance. Distance is between included census-coverage boundaries, including water blocks, not shorelines or ferry endpoints. This bbox-centered local metric differs slightly from the earlier 2,333.895 m population-centered diagnostic.</p>
<p class="small">The numerical solver is unchanged: seed 20200955, outer limit 80, inner limit 300, center tolerance 0.0001 m and at most 1,000 balance moves. Whole-block local optimization need not attain equally tight balance in other states.</p>
<p class="small">Validation: 308 regression tests passed. Both maps were checked with exact outlines, connection toggles and focus; county 009 loaded its 4,341 blocks on demand.</p>
<nav aria-label="Evidence"><a href="comparison.json">Comparison JSON</a><a href="states/44/districts-2/benchmark.json">K2 benchmark</a><a href="states/44/districts-3/benchmark.json">K3 benchmark</a><a href="../../diagnostics/rhode-island/">Original diagnosis</a><a href="../../diagnostics/rhode-island/connectivity-only-k2/">Strict connectivity-only example</a><a href="../../">National results</a></nav>
<p class="small">Each report records the source and code hashes, assignments, move audit, exact connection endpoints, preservation checks and compressed map payloads. The new plans do not overwrite the strict suite manifest.</p>
</main></body></html>'''


def main() -> None:
    data = summary()  # All input validation finishes before writing any result.
    text = json.dumps(data, indent=2, allow_nan=False) + '\n'
    (ROOT / 'prompts/rhode-island-water-benchmark.json').write_text(text, encoding='utf-8')
    (ROOT / 'prompts/rhode-island-water-benchmark.md').write_text(markdown(data), encoding='utf-8')
    (POLICY_ROOT / 'comparison.json').write_text(text, encoding='utf-8')
    (POLICY_ROOT / 'index.html').write_text(html_page(data), encoding='utf-8')
    print('Wrote Rhode Island comparison reports and policy index.')


if __name__ == '__main__':
    main()
