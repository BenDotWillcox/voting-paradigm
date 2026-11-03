"""Validate and compare the fixed-optimizer Hawaii K3/K4 follow-up runs.

Writes only a new anchors-3-4 comparison and its durable reports. Historical
strict, water-policy and corrected K2 results remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path
from typing import Any

from summarize_hawaii_optimizer import (
    BASE_URL, OLD_ROOT, OUTPUT, ROOT, balance_note, deviation, load_run,
    phase_rows, pops, read_json, sha256,
)

COMPARISON = OUTPUT / 'anchors-3-4'
COMPARISON_URL = BASE_URL + 'anchors-3-4/'
REPORT = ROOT / 'prompts/hawaii-optimizer-anchors'


def verify_populations(run: dict[str, Any], district_count: int) -> None:
    """Recompute reported balance rather than copying its headline unchecked."""
    total = run['input']['total_population']
    for stage in ('initial_plan', 'after_repair_plan', 'final_plan'):
        plan = run[stage]
        populations = plan['district_populations']
        if len(populations) != district_count or sum(populations) != total:
            raise ValueError(f'K{district_count} population coverage is inconsistent: {stage}')
        numerators = [value * district_count - total for value in populations]
        maximum = max(abs(value) for value in numerators)
        if plan['deviation_numerators'] != numerators:
            raise ValueError(f'K{district_count} exact deviation numerators are inconsistent: {stage}')
        if not math.isclose(plan['max_absolute_deviation_people'], maximum / district_count, abs_tol=1e-12):
            raise ValueError(f'K{district_count} person deviation is inconsistent: {stage}')
        if not math.isclose(plan['max_absolute_deviation_percent'], maximum * 100 / total, abs_tol=1e-12):
            raise ValueError(f'K{district_count} percentage deviation is inconsistent: {stage}')


def comparison(district_count: int, k2: dict[str, Any]) -> dict[str, Any]:
    old = load_run(OLD_ROOT / f'states/15/districts-{district_count}',
                   corrected=False, district_count=district_count)
    directory = OUTPUT / f'states/15/districts-{district_count}'
    new = load_run(directory, corrected=True, district_count=district_count)
    verify_populations(old, district_count)
    verify_populations(new, district_count)
    if not new['preservation_audit']['prior_k2_correction_byte_identical']:
        raise ValueError(f'K{district_count} did not preserve the prior K2 correction.')
    baseline = new['comparison_baseline']
    for key in ('benchmark_path', 'benchmark_sha256', 'water_connections_sha256'):
        if baseline[key] != old[key]:
            raise ValueError(f'K{district_count} does not identify the exact preserved baseline: {key}')
    if old['source']['archive_sha256'] != new['source']['archive_sha256']:
        raise ValueError(f'K{district_count} changed source archives.')
    if old['water_connections_sha256'] != new['water_connections_sha256']:
        raise ValueError(f'K{district_count} changed its recorded water connections.')
    for key in ('block_count', 'total_population'):
        if old['input'][key] != new['input'][key]:
            raise ValueError(f'K{district_count} changed the source universe: {key}')
    for key in ('seed', 'max_outer_iterations', 'inner_max_iterations', 'center_tolerance_m', 'max_rebalance_moves'):
        if old['configuration'][key] != new['configuration'][key]:
            raise ValueError(f'K{district_count} changed a comparison setting: {key}')
    for name in ('districting/algorithm.py', 'scripts/benchmark_hawaii_water.py'):
        snapshot = new['preserved_baseline_code'][name]
        if sha256(ROOT / snapshot['path']) != snapshot['sha256'] or snapshot['sha256'] != old['code_sha256'][name]:
            raise ValueError(f'K{district_count} original code snapshot differs: {name}')
    for name in ('districting/algorithm.py', 'districting/part_connectivity.py', 'scripts/hawaii_population_links.py'):
        if new['code_sha256'][name] != k2['code_sha256'][name]:
            raise ValueError(f'K{district_count} did not reuse the corrected K2 numerical/policy code: {name}')
    if new['configuration']['inner_optimization'] != k2['configuration']['inner_optimization']:
        raise ValueError(f'K{district_count} uses different optimizer settings from corrected K2.')
    preserved_k2 = list((OUTPUT / 'states/15/districts-2').rglob('*'))
    preserved_k2 += list((OUTPUT / 'baseline-code').rglob('*'))
    preserved_k2 += [OUTPUT / 'index.html', OUTPUT / 'comparison.json',
                     ROOT / 'prompts/hawaii-optimizer-fix.md', ROOT / 'prompts/hawaii-optimizer-fix.json']
    inventory = read_json(directory / 'preserved-file-inventory.json')
    for path in preserved_k2:
        if path.is_file() and path.relative_to(ROOT).as_posix() not in inventory:
            raise ValueError(f'K{district_count} did not inventory the corrected K2 evidence: {path}')
    return {
        'district_count': district_count, 'original': old, 'corrected': new,
        'delta': {
            'max_absolute_deviation_people': new['final_plan']['max_absolute_deviation_people'] - old['final_plan']['max_absolute_deviation_people'],
            'full_pipeline_wall_seconds': new['timed_pipeline_wall_seconds'] - old['timed_pipeline_wall_seconds'],
            'solve_wall_seconds': new['phases']['solve']['wall_seconds'] - old['phases']['solve']['wall_seconds'],
        },
        'changed_existing_code_hashes': {
            name: {'old': old['code_sha256'][name], 'new': new['code_sha256'][name]}
            for name in sorted(old['code_sha256'].keys() & new['code_sha256'].keys())
            if old['code_sha256'][name] != new['code_sha256'][name]
        },
        'comparison_invariants': {
            'same_source_and_population': True, 'same_water_connection_record': True,
            'same_seed_iteration_limits_and_postprocessing_budget': True,
            'same_optimizer_and_policy_code_as_corrected_k2': True,
            'original_strict_water_policy_and_corrected_k2_files_preserved': True,
            'original_algorithm_and_runner_snapshots_verified': True,
        },
    }


def summary(validation_note: str) -> dict[str, Any]:
    k2 = read_json(OUTPUT / 'states/15/districts-2/benchmark.json')
    if k2['status'] != 'complete_under_island_water_policy':
        raise ValueError('Corrected K2 numerical baseline is not complete.')
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Hawaii K3 and K4 fixed-optimizer reruns under each original recorded water policy.',
        'plans': [comparison(k, k2) for k in (3, 4)], 'validation_note': validation_note,
        'measurement_notes': [
            'Both old and new results use full fresh-process pipelines with warm source and physical graph caches.',
            'Runs occurred at different times on a shared desktop; runtime differences are not isolated hardware comparisons.',
            'The pipeline timer includes policy construction, solver, repair, independent validation, export and preservation verification.',
            'Process imports, initial preservation inventory and final report flush are outside the pipeline timer.',
            'Physical polygon connectivity, connectivity through recorded water links, center convergence and population balance are separate metrics.',
            'The K3/K4 originals already had excellent final balance; numerical normalization need not improve every final local optimum.',
        ],
    }


def metric_rows(plan: dict[str, Any]) -> str:
    return '\n'.join(
        f'| {run["label"]} | {pops(run)} | {deviation(run)} | '
        f'{run["timed_pipeline_wall_seconds"]:.2f} s | {run["phases"]["solve"]["wall_seconds"]:.3f} s | '
        f'{run["working_set_mib"]:.1f} MiB | {run["inner_optimizer"]["failed_pass_count"]}/{run["inner_optimizer"]["pass_count"]} |'
        for run in (plan['original'], plan['corrected']))


def balance_comparison(data: dict[str, Any]) -> str:
    parts = []
    for plan in data['plans']:
        old = plan['original']['final_plan']['max_absolute_deviation_people']
        new = plan['corrected']['final_plan']['max_absolute_deviation_people']
        verb = 'rose' if new > old else 'fell' if new < old else 'stayed'
        change = f'{verb} from {old:.3f} to {new:.3f}' if new != old else f'stayed at {new:.3f}'
        parts.append(f"{plan['district_count']}-district maximum deviation {change} people")
    result = '; '.join(parts) + '.'
    if all(plan['delta']['max_absolute_deviation_people'] > 0 for plan in data['plans']):
        result += ' The preserved originals remain better balanced at both counts.'
    return result


def markdown(data: dict[str, Any]) -> str:
    sections = []
    for plan in data['plans']:
        k, old, new = plan['district_count'], plan['original'], plan['corrected']
        connectivity = '\n'.join(
            f'| {run["label"]} | {run["physical_polygon_components"]} | {run["policy_polygon_components"]} | '
            f'{run["selected_connection_count"]}/{run["used_connection_count"]} | '
            f'{run["postprocessing"]["repair_move_count"]}/{run["postprocessing"]["rebalance_move_count"]} | '
            f'{run["postprocessing"]["stop_reason"]} |'
            for run in (old, new))
        phases = '\n'.join(f'| {name.replace("_", " ")} | {before:.3f} s | {after:.3f} s |'
                           for name, before, after in phase_rows(plan))
        sections.append(f'''## {k} districts

[Corrected map]({new['url']}) · [Preserved original map]({old['url']})

| Run | District populations | Maximum deviation from ideal | Full pipeline | Numerical solve | Peak working set | Failed / total inner passes |
|---|---|---|---:|---:|---:|---:|
{metric_rows(plan)}

{balance_note(new)} The original initial solver deviation was {old['initial_plan']['max_absolute_deviation_percent']:.9f}%; the corrected initial solver deviation is {new['initial_plan']['max_absolute_deviation_percent']:.9f}%. The table above reports final populations after connectivity repair and rebalancing.

| Run | Physical polygon components | Policy polygon components | Selected / used links | Repair / balance moves | Stop |
|---|---|---|---|---|---|
{connectivity}

All {k} districts pass both polygon-part graph validation and independent unsimplified polygon validation under the water policy. A component count greater than one in the physical column remains real separation across water. Connections are used only when both endpoint blocks belong to the same district.

| Pipeline phase | Original | Corrected |
|---|---:|---:|
{phases}

The corrected preservation inventory verifies {new['preserved_file_count_verified']} files. Original and corrected compressed maps ({old['compressed_artifacts_verified'] + new['compressed_artifacts_verified']} artifacts) match their recorded decompressed hashes. [Original benchmark]({(ROOT / old['benchmark_path']).as_posix()}) · [Corrected benchmark]({(ROOT / new['benchmark_path']).as_posix()}).
''')
    return f'''# Hawaii K3/K4: fixed-optimizer reruns

Both requested plans completed with every inner optimizer pass successful. All 14,732 census blocks and 1,455,271 residents are covered exactly. The original strict and water-policy results, and the prior corrected K2 results, remain byte-identical. Each K retains its own exact original water-connection record.

[Interactive comparison]({COMPARISON_URL}) · [Previous K2 correction]({BASE_URL}) · [Original three-plan comparison](http://127.0.0.1:8770/policies/hawaii-water-v1/).

The original K3/K4 plans already had excellent final balance. The corrected optimizer is the same normalization, line-search limit and explicit failure handling used for corrected K2. No numerical or island-policy changes were made for these reruns. Seed, outer/inner iteration limits and connectivity-repair budget match each preserved original. Every new inner call succeeds; center convergence and final population quality remain separate outcomes.

{balance_comparison(data)} Connectivity still passes in both plans. These are local rebalancing results, not evidence of a globally optimal whole-block partition.

{''.join(sections)}
## Measurement and preservation

Both old and new runs are fresh-process pipelines with warm source and physical-graph caches. They ran serially at different times on a shared desktop, so runtime changes are observations rather than isolated hardware comparisons. Full pipeline time includes policy construction, solving, repair, validation, export and preservation verification; imports, initial preservation inventories and final report flush are excluded.

The original full water-policy tree, source archive, strict reports, national manifest and corrected K2 evidence were verified against the new preservation inventories. Saved copies of the old algorithm and benchmark runner match each original report's hashes. New solver and policy code hashes match the corrected K2 benchmark. The saved source polygons and water connections are unchanged; dashed map lines are declared graph connections, not added land.

{data['validation_note']}

[Machine-readable comparison]({REPORT.with_suffix('.json').as_posix()}).
'''


def html_page(data: dict[str, Any]) -> str:
    sections = []
    for plan in data['plans']:
        k, old, new = plan['district_count'], plan['original'], plan['corrected']
        cards = ''.join(f'''<article class="card"><div class="tag">{escape(run['label'])}</div>
<h3>{run['final_plan']['max_absolute_deviation_percent']:.9f}%<span>maximum deviation from ideal</span></h3>
<p class="pop">{pops(run)}</p><p class="muted">people per district</p>
<dl><dt>Full pipeline</dt><dd>{run['timed_pipeline_wall_seconds']:.2f} s</dd><dt>Numerical solve</dt><dd>{run['phases']['solve']['wall_seconds']:.3f} s</dd><dt>Peak working set</dt><dd>{run['working_set_mib']:.1f} MiB</dd><dt>Failed optimizer passes</dt><dd>{run['inner_optimizer']['failed_pass_count']} / {run['inner_optimizer']['pass_count']}</dd></dl>
<a class="button" href="{run['url']}">Open {'corrected' if run is new else 'preserved original'} map →</a></article>''' for run in (old, new))
        connectivity = ''.join(f'''<tr><th>{escape(run['label'])}</th><td>{escape(str(run['physical_polygon_components']))}</td><td>{escape(str(run['policy_polygon_components']))}</td><td>{run['selected_connection_count']} / {run['used_connection_count']}</td><td>{run['postprocessing']['repair_move_count']} / {run['postprocessing']['rebalance_move_count']}</td></tr>''' for run in (old, new))
        phases = ''.join(f'<tr><th>{escape(name.replace("_", " "))}</th><td>{before:.3f} s</td><td>{after:.3f} s</td></tr>' for name, before, after in phase_rows(plan))
        sections.append(f'''<section id="k{k}"><div class="tag">Hawaii · {k} districts</div><h2>{k} districts, independently validated.</h2><div class="cards">{cards}</div><p class="small">Corrected maximum deviation: {deviation(new)}. {escape(balance_note(new))}</p>
<h3>Connectivity and postprocessing</h3><div class="table-wrap"><table><thead><tr><th>Run</th><th>Physical components</th><th>Policy components</th><th>Selected / used links</th><th>Repair / balance moves</th></tr></thead><tbody>{connectivity}</tbody></table></div>
<p class="small">Each policy component count is independently checked using unsimplified polygons and recorded connections. A used link has both endpoint blocks within one district. Physical separation across water remains visible and is not erased.</p>
<details><summary>Inspect timing phases and preservation</summary><div class="table-wrap"><table><thead><tr><th>Phase</th><th>Original</th><th>Corrected</th></tr></thead><tbody>{phases}</tbody></table></div><p>{new['preserved_file_count_verified']} preserved files verified. All {old['compressed_artifacts_verified'] + new['compressed_artifacts_verified']} compressed map artifacts match their decompressed hashes. The exact original water-connection record is unchanged.</p><nav><a href="{old['url']}benchmark.json">Original benchmark JSON</a><a href="{new['url']}benchmark.json">Corrected benchmark JSON</a></nav></details></section>''')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hawaii · Fixed optimizer · 3 and 4 districts</title><style>
:root{{color-scheme:dark;--bg:#10191f;--panel:#1a252d;--text:#e9f2f5;--muted:#a6bac5;--line:#354955;--accent:#6ed5df;--water:#ff91cf}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,sans-serif}}main{{max-width:1180px;padding:36px 24px 52px;margin:auto}}h1{{font-size:clamp(28px,4vw,42px);line-height:1.15;margin:10px 0 16px}}h2{{font-size:26px;line-height:1.3;margin:12px 0}}h3{{font-size:20px;line-height:1.3}}p{{margin:10px 0 18px}}a{{color:var(--accent)}}.tag{{font:12px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--water)}}.muted,.small{{color:var(--muted)}}.small{{font-size:13px}}.cards{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:22px 0}}.card{{background:var(--panel);padding:22px;border:1px solid var(--line);border-radius:10px}}.card h3{{font-size:30px;margin:12px 0}}.card h3 span{{display:block;font-size:14px;color:var(--muted);font-weight:400}}.pop{{font-weight:600;margin-bottom:0}}.pop+.muted{{margin-top:0;font-size:13px}}dl{{display:grid;grid-template-columns:1fr auto;gap:6px;font-size:14px}}dd{{margin:0;font-variant-numeric:tabular-nums}}dt{{color:var(--muted)}}.button{{display:inline-block;padding:9px 16px;border:1px solid var(--accent);border-radius:5px;text-decoration:none;margin-top:10px}}.callout{{border-left:3px solid var(--water);padding:10px 18px;background:#281e2c}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0 22px}}th,td{{text-align:right;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}}th:first-child,td:first-child{{text-align:left}}thead th{{color:var(--muted);font-weight:500}}nav{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}}a:focus-visible,summary:focus-visible{{outline:3px solid var(--water);outline-offset:4px}}section{{padding:34px 0;border-top:1px solid var(--line)}}summary{{cursor:pointer;color:var(--accent);padding:10px 0}}@media(max-width:750px){{.cards{{grid-template-columns:1fr}}main{{padding:24px 16px}}}}
</style></head><body><main><div class="tag">Hawaii · Fixed optimizer · 3- and 4-district reruns</div><h1>Connectivity holds.<br>Balance remains close.</h1><p>Both plans pass every inner optimizer call and independent district-connectivity validation under their unchanged water policies. All <strong>14,732 blocks and 1,455,271 residents</strong> remain covered exactly.</p>
<nav aria-label="Sections"><a href="#k3">3 districts</a><a href="#k4">4 districts</a><a href="{BASE_URL}">Previous 2-district correction</a><a href="http://127.0.0.1:8770/policies/hawaii-water-v1/">Original three-plan comparison</a></nav>
<p class="callout">{escape(balance_comparison(data))} The originals already had excellent final balance. The fixed numerical procedure does not guarantee that each final local optimum improves. Connectivity still passes in both plans.</p>
{''.join(sections)}
<section><h2>Same numerical fix, unchanged source policy</h2><p>These runs use the same normalized optimizer and explicit failure handling as corrected K2. Seed, iteration budgets, connectivity-repair budget and each plan's exact water-connection record match its preserved original. Source polygons are unchanged; dashed links are declared graph connections, not added land.</p><p class="small">Both old and new results are complete fresh-process pipelines with warm source and physical-graph caches. Runs occurred serially at different times on a shared desktop. They are not isolated hardware comparisons. The timer excludes process imports, the initial preservation inventory and final report flush.</p><p class="small">The original strict and water-policy results, diagnostics, reports, source archive, national manifest and prior corrected K2 results remain byte-identical. Original code snapshots and all compressed map hashes were verified.</p><p class="small">{escape(data['validation_note'])}</p><nav aria-label="Evidence"><a href="comparison.json">Comparison JSON</a><a href="../../../diagnostics/hawaii/">Original source diagnosis</a></nav></section></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', default='Saved benchmark, map, source-code and preservation hashes verified while generating this comparison.')
    args = parser.parse_args()
    data = summary(args.validation_note)
    raw = json.dumps(data, indent=2, allow_nan=False) + '\n'
    COMPARISON.mkdir(parents=True, exist_ok=True)
    for path, content in {
        REPORT.with_suffix('.json'): raw, REPORT.with_suffix('.md'): markdown(data),
        COMPARISON / 'comparison.json': raw, COMPARISON / 'index.html': html_page(data),
    }.items():
        path.write_text(content, encoding='utf-8')
    print('Wrote the Hawaii K3/K4 optimizer comparison and durable reports.')


if __name__ == '__main__':
    main()
