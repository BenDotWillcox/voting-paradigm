"""Render West Virginia's saved balance diagnosis without running districting.

Only the new diagnostic viewer and narrative report are written. Historical
benchmarks, assignments, geometries and numerical runtime files are read-only.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / ".cache/state-block-benchmark/suite-through-1000"
DIAGNOSTICS = SUITE / "diagnostics/west-virginia"
URL = "http://127.0.0.1:8770/diagnostics/west-virginia/"
COLORS = ["#21cba8", "#ffc24a", "#8f8dff"]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stage_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "populations": plan["district_populations"],
        "max_deviation_people": plan["max_absolute_deviation_people"],
        "max_deviation_percent": plan["max_absolute_deviation_percent"],
        "components": plan.get("shared_edge_components"),
        "squared_deviation_people": plan["squared_deviation_numerator"]
        / plan["squared_deviation_denominator"],
    }


def validate_diagnosis(diagnosis: dict[str, Any], total: int) -> list[dict[str, Any]]:
    """Reject partial evidence and inconsistent measurements before publication."""
    if diagnosis.get("status") != "diagnosis_complete" or diagnosis.get("diagnostic_only") is not True:
        raise ValueError("Only a completed diagnostic report may be rendered")
    if diagnosis.get("historical_preservation", {}).get("unchanged") is not True:
        raise ValueError("Historical preservation must be verified")
    stages = diagnosis.get("stages", {})
    if set(stages) != {"initial", "repaired", "original", "probe"}:
        raise ValueError("All four audited diagnostic stages are required")

    def metrics(record: dict[str, Any]) -> int:
        pops = record.get("populations", [])
        if len(pops) != 3 or any(type(p) is not int or p < 0 for p in pops) or sum(pops) != total:
            raise ValueError("Invalid stage/trace populations")
        numerators = [3 * p - total for p in pops]
        deviation = max(map(abs, numerators)) / 3
        percent = deviation / (total / 3) * 100
        for key, expected in (("max_deviation_people", deviation), ("max_deviation_percent", percent)):
            value = record.get(key)
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0 or not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(f"Inconsistent {key}")
        squared = sum(n * n for n in numerators)
        if "squared_deviation_numerator" in record and record["squared_deviation_numerator"] != squared:
            raise ValueError("Inconsistent squared population objective")
        return squared

    for name, stage in stages.items():
        metrics(stage)
        if stage.get("accepted_map") is not (name == "original"):
            raise ValueError("A diagnostic stage must not be presented as an accepted corrected map")
        components = stage.get("components")
        if not isinstance(components, list) or len(components) != 3 or any(type(c) is not int or c < 1 for c in components):
            raise ValueError("Invalid component counts")
        passed = stage.get("strict_polygon_validation_passed")
        if type(passed) is not bool or (passed and components != [1, 1, 1]):
            raise ValueError("Strict polygon audit and graph component counts disagree")
        if name in ("original", "probe") and passed is not True:
            raise ValueError("Original final and probe endpoints require full strict polygon audits")
    probe = diagnosis.get("probe", {})
    if probe.get("accepted_map") is not False or probe.get("solver_rerun") is not False:
        raise ValueError("This renderer accepts only a diagnostic continuation without a solver rerun")
    count = probe.get("additional_moves")
    limit = probe.get("additional_move_limit")
    if type(count) is not int or type(limit) is not int or not 0 <= count <= limit or limit != 100 or probe.get("cumulative_moves") != 1000 + count:
        raise ValueError("Invalid bounded continuation move counts")
    if probe.get("strict_polygon_validation_passed") is not True or stages["probe"]["strict_polygon_validation_passed"] is not True:
        raise ValueError("A full strict polygon audit is required to display this diagnostic")
    for key in ("elapsed_seconds", "guard_calls", "guard_failed_calls", "guard_wall_seconds"):
        value = probe.get(key)
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid probe {key}")
    if probe["guard_failed_calls"] > probe["guard_calls"]:
        raise ValueError("Failed guard calls exceed total guard calls")
    if probe["elapsed_seconds"] <= 0:
        raise ValueError("Invalid probe elapsed_seconds; positive measured wall time is required")
    trace = diagnosis.get("trace", [])
    if len(trace) != 1001 + count:
        raise ValueError("The complete recorded-move trace is required")
    normalized = []
    for i, point in enumerate(trace):
        if point.get("moves") != i:
            raise ValueError("Trace moves must be contiguous from zero")
        squared = metrics(point)
        normalized.append({**point, "squared_deviation_people": squared / 9})
    for index, name in ((0, "repaired"), (1000, "original"), (1000 + count, "probe")):
        if trace[index]["populations"] != stages[name]["populations"]:
            raise ValueError("Trace endpoint does not match its saved stage")
    return normalized


def saved_context(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """Use saved original reports as the authority for historical numbers."""
    rows = []
    for count in (2, 3, 4, 5):
        report = load(SUITE / f"states/54/districts-{count}/benchmark.json")
        if report.get("status") != "complete" or report["maps"]["strict_validation"]["passed"] is not True:
            raise ValueError(f"Historical K{count} is not a validated complete map")
        rows.append({
            "district_count": count,
            "house_sizes": report["house_sizes"],
            "final_populations": report["final_plan"]["district_populations"],
            "max_deviation_people": report["final_plan"]["max_absolute_deviation_people"],
            "max_deviation_percent": report["final_plan"]["max_absolute_deviation_percent"],
            "pipeline_seconds": report["timed_pipeline_wall_seconds"],
            "peak_working_set_bytes": report["peak_process_working_set_bytes"],
            "rebalance_moves": report["rebalance_move_count"],
            "stop_reason": report["stop_reason"],
            "strict_polygon_validation_passed": report["maps"]["strict_validation"]["passed"],
            "unsuccessful_inner_passes": report["solver"]["unsuccessful_inner_passes"],
        })
    original = load(SUITE / "states/54/districts-3/benchmark.json")
    trace = validate_diagnosis(diagnosis, original["input"]["total_population"])
    stages = {
        "initial": stage_from_plan(original["initial_plan"]),
        "repaired": stage_from_plan(original["after_repair"]),
        "original": stage_from_plan(original["final_plan"]),
    }
    if "stages" in diagnosis:
        for name in stages:
            supplied = diagnosis["stages"].get(name)
            if supplied and (supplied.get("populations") != stages[name]["populations"] or supplied.get("components") != stages[name]["components"]):
                raise ValueError(f"Diagnostic {name} population disagrees with original checkpoint")
            stages[name]["strict_polygon_validation_passed"] = supplied["strict_polygon_validation_passed"]
            for key in ("polygon_components", "polygons_valid", "polygon_audit_note", "graph_polygon_component_counts_agree", "coverage_union_diagnostic", "union_method"):
                if key in supplied:
                    stages[name][key] = supplied[key]
        if "probe" in diagnosis["stages"]:
            stages["probe"] = diagnosis["stages"]["probe"]
    # A diagnostic continuation is deliberately never labelled an accepted map.
    for name, stage in stages.items():
        stage["map_file"] = f"stage-{name}.geojson"
        stage["accepted_map"] = name == "original"
        failed_fast = [str(i + 1) for i, item in enumerate(stage.get("coverage_union_diagnostic", [])) if item.get("valid") is False]
        notes = []
        if failed_fast:
            notes.append("The diagnostic fast coverage dissolve was invalid for display district(s) " + ", ".join(failed_fast) + "; the independent audit uses robust unary union of unchanged source polygons.")
        if stage.get("graph_polygon_component_counts_agree") is False:
            notes.append("Graph and polygon component counts differ at this diagnostic intermediate stage; both counts are retained.")
        if notes:
            stage["polygon_audit_note"] = " ".join(notes)
    probe = diagnosis.get("probe", {})
    return {
        "original_plans": rows,
        "stages": stages,
        "trace": trace,
        "probe": probe,
        "repair_component": diagnosis.get("repair_component", {}),
        "historical_preservation": diagnosis.get("historical_preservation", {}),
        "code_comparison": diagnosis.get("code_comparison", {}),
        "audit_history": diagnosis.get("audit_history", {}),
        "source_sha256": original["source"]["archive_sha256"],
        "total_population": original["input"]["total_population"],
        "block_count": original["input"]["block_count"],
        "original_solve_seconds": original["phases"]["solve"]["wall_seconds"],
        "original_rebalance_seconds": original["phases"]["repair_and_rebalance"]["wall_seconds"],
        "original_export_seconds": original["phases"]["geometry_validation_and_map_export"]["wall_seconds"],
    }


def formatted(value: float | int, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}"


def narrative(data: dict[str, Any]) -> str:
    stage = data["stages"]
    probe = data["probe"]
    result = [
        "# West Virginia: diagnosing the population-balance outlier",
        "",
        "The original three-district plan is a valid, strictly connected map, but its population balancing stopped at the 1,000-move budget. The initial numerical solve was already well balanced. Connectivity repair, followed by incomplete boundary rebalancing, explains the final 2.25359% deviation.",
        "",
        f"[Interactive stage maps and measured trace]({URL}) · [Original connected map](http://127.0.0.1:8770/states/54/districts-3/) · [Diagnostic evidence]({URL}diagnosis.json)",
        "",
        "| Districts / House | Maximum deviation | Pipeline | Peak memory | Balancing stop |",
        "|---|---:|---:|---:|---|",
    ]
    for row in data["original_plans"]:
        result.append(
            f"| {row['district_count']} / {', '.join(map(str, row['house_sizes']))} "
            f"| {row['max_deviation_people']:,.3f} people ({row['max_deviation_percent']:.6f}%) "
            f"| {row['pipeline_seconds']/60:.2f} min "
            f"| {row['peak_working_set_bytes']/2**20:.1f} MiB "
            f"| {row['rebalance_moves']:,} moves; {row['stop_reason']} |"
        )
    result.extend([
        "",
        f"All four original plans retain {data['block_count']:,} whole census blocks and {data['total_population']:,} residents. Each passes the saved independent strict unsimplified polygon audit. The source is connected and has no multipart blocks; no water links are involved.",
        "",
        "| Three-district stage | Populations | Maximum deviation | Graph components | Independent polygon audit |",
        "|---|---|---:|---|---|",
    ])
    names = {"initial": "Initial numerical assignment", "repaired": "After connectivity repair", "original": "Original final (1,000 moves)", "probe": "Diagnostic continuation"}
    for name, record in stage.items():
        audit = "Strict validation passed" if record["strict_polygon_validation_passed"] else "Not strict-valid (diagnostic stage)"
        if record.get("polygons_valid") is False:
            audit += "; invalid dissolved geometry"
        if "polygon_components" in record:
            audit += f"; {record['polygon_components']} components"
        result.append(f"| {names[name]} | {' / '.join(f'{p:,}' for p in record['populations'])} | {record['max_deviation_people']:,.3f} people ({record['max_deviation_percent']:.6f}%) | {record.get('components', 'See diagnostic evidence')} | {audit} |")
    for name, record in stage.items():
        if record.get("polygon_audit_note"):
            result.extend(["", f"{names[name]}: {record['polygon_audit_note']}"])
    result.extend([
        "",
        "The largest repair moves 1,753 Northern Panhandle blocks and 53,789 residents from display District 2 to District 3. That restores connectivity but creates the large imbalance. All 1,000 original balancing moves transfer population back from District 3 to District 2; the last 100 moves still transfer 1,893 residents. Stopping at the budget does not establish a local or global optimum.",
        "",
        f"The original solve took {data['original_solve_seconds']:.3f} seconds, with successful inner passes and converged centers. Connectivity repair plus rebalancing took {data['original_rebalance_seconds']:.3f} seconds; validation/export took {data['original_export_seconds']:.3f} seconds. The next step is faster exact donor-connectivity checks, followed by a larger-budget continuation of the saved connected assignment. Increasing the inner optimizer budget would target the wrong stage.",
        "",
    ])
    if "probe" in stage:
        p = stage["probe"]
        extra = probe.get("additional_moves", "Recorded")
        duration = probe.get("elapsed_seconds")
        runtime = f" in {duration:.3f} seconds" if isinstance(duration, (float, int)) else ""
        result.extend([
            f"The diagnostic continuation made **{extra} additional moves**{runtime}, reaching **{p['max_deviation_people']:,.3f} people ({p['max_deviation_percent']:.6f}%)** maximum deviation. Its stop reason is `{probe.get('stop_reason', 'see diagnosis.json')}`. This is bounded diagnostic evidence, not an accepted corrected plan or a guarantee that a larger budget alone will finish balancing. A longer correction run would need its own preserved output and full validation before acceptance.",
            "",
            f"The probe itself passed its independent unsimplified polygon audit. Its donor-connectivity guard ran {probe['guard_calls']:,} times, rejected {probe['guard_failed_calls']:,} candidates, and consumed {probe['guard_wall_seconds']:.3f} seconds. These observational measurements describe the continuation; they do not change stopping rules or the numerical objective.",
            "",
            f"Donor-connectivity checks account for **{probe['guard_wall_seconds']/probe['elapsed_seconds']*100:.2f}% of probe wall time**. The candidate performance fix is a per-district articulation-point cache, invalidated for both donor and recipient after every transfer, with regression checks that preserve exact candidate order and move traces. This has not been implemented or timed here. After validating that optimization, a longer continuation can test whether more boundary moves achieve acceptable balance; eventual success is not guaranteed.",
            "",
        ])
    result.extend([
        "The chart uses saved/replayed moves and the measured continuation. Maximum absolute deviation is the primary objective; the sum of squared population deviations breaks ties as the secondary objective in the lexicographic rule. Display geometry is simplified for inspection and is not a topology certificate.",
        "",
        "Historical runtime hashes differ from current solver/connectivity/export code. A fresh solve with current code would therefore not isolate a budget change. This diagnosis preserves the original solve and records the continuation code separately. Historical two-worker timings and the diagnostic continuation are not isolated performance benchmarks.",
        "",
        "The original K2 report records one unsuccessful inner pass under the earlier permissive optimizer handling (status 2, ABNORMAL, after 11 iterations and 107 evaluations); its subsequent six passes converged. Its final balance is exact and geometry validation passed. K3 records no unsuccessful inner passes. That legacy numerical warning is separate from this K3 postprocessing issue.",
        "",
        f"Original source archive SHA-256: `{data['source_sha256']}`. Original assignments, move audits, maps and benchmark reports remain the historical evidence; preservation and continuation provenance are recorded in the diagnostic JSON.",
        "",
    ])
    history = data.get("audit_history", {})
    if history:
        result.extend([
            "The first diagnostic audit stopped on the initial, pre-repair assignment after the fast coverage dissolve failed its validation. That attempt and its log are preserved. A geometry-only finalization audited the saved assignments with robust unary union and retained the fast-dissolve evidence; the balancing probe was not repeated. Finalization time is separate from the measured continuation.",
            "",
        ])
    return "\n".join(result)


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>West Virginia · Population balance diagnosis</title>
<style>
:root{color-scheme:dark;--bg:#0c1320;--panel:#131e30;--muted:#a4b1c7;--line:#304158;--ink:#edf4ff;--teal:#21cba8;--orange:#ffc24a;--purple:#8f8dff;--pink:#ff72bf}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1220px;margin:auto;padding:32px 24px 64px}a{color:#72d7ff;text-underline-offset:3px}nav{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;margin-bottom:28px}.eyebrow{color:var(--teal);text-transform:uppercase;letter-spacing:.13em;font-size:12px;font-weight:750}h1{font-size:clamp(30px,4vw,48px);line-height:1.13;letter-spacing:-.035em;margin:12px 0 18px;max-width:900px}h2{font-size:21px;margin:0 0 10px}p{margin:8px 0 16px}.lede{font-size:18px;max-width:950px;color:#d8e1f0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:28px 0}.card,.panel{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:20px}.card .value{font-size:30px;letter-spacing:-.02em;font-weight:700}.label,.small{color:var(--muted);font-size:13px}.card p{margin:4px 0 0}.split{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(300px,1fr);gap:18px;margin:20px 0}.panel{min-width:0;margin:18px 0}.split .panel{margin:0}.badge{display:inline-block;border:1px solid #49617f;border-radius:5px;padding:3px 8px;font:12px/1.4 ui-monospace,monospace;color:#d6e1ee}.warning{border-left:3px solid var(--orange);padding:12px 16px;background:#30291c;margin:18px 0}.controls{display:flex;gap:7px;flex-wrap:wrap;margin:16px 0}button{border:1px solid #455975;border-radius:6px;background:#17263b;color:var(--ink);padding:8px 12px;font:inherit;font-size:13px;cursor:pointer}button[aria-pressed=true]{background:#264c66;border-color:#72d7ff}button:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid var(--orange);outline-offset:3px}button:hover{background:#29405b}label{display:flex;gap:7px;align-items:center;font-size:13px;color:#cdd9ea}.map-shell{position:relative;background:#0d1727;border:1px solid var(--line);border-radius:8px;overflow:hidden}.map-shell svg{display:block;width:100%;height:520px;touch-action:none;cursor:grab}.map-shell svg:active{cursor:grabbing}.map-shell .note{position:absolute;bottom:10px;left:12px;right:12px;background:#0d1727d9;color:#c9d6ea;padding:6px 10px;font-size:12px;pointer-events:none}.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;margin:12px 0}.dot{display:inline-block;width:11px;height:11px;margin-right:5px;border-radius:2px}.trace{width:100%;height:260px;display:block}.chart-title{font-size:14px;font-weight:650;margin:20px 0 0}.chart-grid{stroke:#304158;stroke-width:1}.chart-label{fill:#acbad0;font:12px system-ui}.chart-axis{stroke:#73849e}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}th{text-align:left;color:var(--muted);font-weight:600}th,td{padding:11px 10px;border-bottom:1px solid var(--line);white-space:nowrap}td:first-child,th:first-child{padding-left:0}.focus-row{background:#21364d}code{font-size:12px;overflow-wrap:anywhere}.stage-detail{font-variant-numeric:tabular-nums}.stage-detail strong{display:block;font-size:22px;margin-bottom:6px}.stage-detail dl{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.stage-detail dt{color:var(--muted)}.stage-detail dd{margin:0;text-align:right}.explain{max-width:1050px}.explain li{margin:8px 0}.footer{font-size:12px;color:var(--muted);margin-top:24px}@media(max-width:800px){.split{grid-template-columns:1fr}.cards{grid-template-columns:1fr}.map-shell svg{height:430px}.card .value{font-size:26px}main{padding:24px 16px}}
</style></head><body><main>
<nav><a href="../../">All state benchmarks</a><a href="../../states/54/districts-3/">Original K3 map</a><a href="diagnosis.json">Diagnostic evidence</a></nav>
<div class="eyebrow">West Virginia / House 574 / 3 districts</div>
<h1>Connected districts. An unfinished balance pass.</h1>
<p class="lede">The original map passes strict shared-edge and polygon connectivity. Its population gap appears when a detached Northern Panhandle component is repaired, then shrinks through 1,000 boundary moves until the move budget ends.</p>
<div class="cards"><div class="card"><div class="label">Original final maximum deviation</div><div class="value" id="headline-deviation"></div><p class="small">Worst district's distance from the fractional ideal</p></div><div class="card"><div class="label">Residents in the largest repair</div><div class="value">53,789</div><p class="small">1,753 whole blocks, District 2 → District 3</p></div><div class="card"><div class="label">Initial numerical solve</div><div class="value" id="headline-solve"></div><p class="small">Successful inner solves; converged centers</p></div></div>
<div class="split"><section class="panel"><h2>Follow the same three districts</h2><p class="small">Switch assignment stages. The highlighted component shows the large repair; colors retain their district identity.</p><div class="controls" id="stage-buttons"></div><div class="controls"><label><input type="checkbox" id="show-repair" checked> Highlight 1,753-block repair component</label><button id="fit-map">Fit state</button><button id="zoom-in" aria-label="Zoom map in">+</button><button id="zoom-out" aria-label="Zoom map out">−</button></div><div class="map-shell"><svg id="map" viewBox="0 0 720 520" role="img" aria-label="West Virginia district assignment stages"><defs><pattern id="repair-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(30)"><line x1="0" y1="0" x2="0" y2="7" stroke="#ff72bf" stroke-width="3"/></pattern></defs><g id="map-shapes"></g><g id="map-repair"></g></svg><div class="note" id="map-note">Loading saved diagnostic geometry…</div></div><div class="legend"><span><i class="dot" style="background:#21cba8"></i>District 1</span><span><i class="dot" style="background:#ffc24a"></i>District 2</span><span><i class="dot" style="background:#8f8dff"></i>District 3</span><span><i class="dot" style="background:#ff72bf"></i>Repair component</span></div><p class="small">Drag to pan. Simplified outlines support inspection; exact source geometry and independent audits determine connectivity.</p></section>
<aside class="panel"><div class="stage-detail" id="stage-detail"></div><div class="warning" id="stage-warning"></div><h2>What changed?</h2><p>District 2 initially includes a detached component in the Northern Panhandle. Assigning those 53,789 residents to adjacent District 3 restores connectivity and creates a large imbalance.</p><p>The rebalancer then returns population along valid shared edges. All 1,000 original moves go from District 3 to District 2. The last 100 moves still transfer <strong>1,893 residents</strong>.</p><p><strong>The run stopped in postprocessing at its move limit.</strong> More inner optimizer iterations would target a stage that already succeeded.</p></aside></div>
<section class="panel"><h2>Measured balancing progress</h2><p>The horizontal axis counts boundary moves after connectivity repair. Worst deviation is the primary objective; squared deviations break ties as the secondary objective. A dashed line marks the original 1,000-move limit. The continuation is a bounded diagnostic, not a published correction.</p><div class="legend"><span><i class="dot" style="background:#21cba8"></i>Original recorded moves</span><span><i class="dot" style="background:#ff72bf"></i>Diagnostic continuation</span></div><div class="chart-title">Worst district deviation from ideal population (people)</div><svg id="deviation-chart" class="trace" role="img" aria-label="Maximum population deviation by balancing move"></svg><div id="objective-section"><div class="chart-title">Sum of squared district population deviations (people²)</div><svg id="objective-chart" class="trace" role="img" aria-label="Squared population objective by balancing move"></svg></div><p class="small" id="probe-detail"></p></section>
<section class="panel"><h2>Original West Virginia anchor plans</h2><p class="small">Each saved plan passes strict independent polygon validation. Population quality and numerical convergence are separate measurements.</p><div class="table-wrap"><table><thead><tr><th>Districts / House</th><th>Max deviation</th><th>Pipeline</th><th>Peak memory</th><th>Balancing stop</th></tr></thead><tbody id="anchor-table"></tbody></table></div></section>
<section class="panel explain"><h2>The next experiment</h2><p>First make donor-connectivity checks faster while preserving the exact candidate order and resulting move trace. A candidate implementation caches each district’s articulation points—the blocks whose removal would disconnect it—and invalidates both donor and recipient caches after every transfer. Then continue from the preserved connected K3 assignment with a larger move budget. No speedup or eventual balance is yet established; validate populations, shared edges, and unsimplified polygons before accepting a correction.</p><ul><li><strong>The diagnostic probe is not a guarantee.</strong> More moves may continue helping, encounter a local optimum, or require a different balancing strategy.</li><li><strong>Historical code differs from current code.</strong> A fresh solve would not isolate a budget change. The continuation's implementation identity is separate from the original benchmark.</li><li><strong>Legacy K2 warning.</strong> Its original report records one unsuccessful inner optimizer pass despite exact final balance and valid geometry. K3 has no failed inner passes. This warning does not explain K3's balancing limit.</li></ul><p class="small">Original runs and maps are preserved. Original batch timings included two-worker contention; the diagnostic continuation is a separate measurement. No claim of global optimality is made.</p></section>
<div class="footer">2020 Census resident population · whole census blocks · no synthetic connections · stage geometry is diagnostic · <a href="diagnosis.json">source, code and preservation evidence</a></div>
</main><script>const D=__DATA__;
const colors=['#21cba8','#ffc24a','#8f8dff'];const labels={initial:'Initial solve',repaired:'After repair',original:'Original final',probe:'Diagnostic probe'};const ns='http://www.w3.org/2000/svg';const f=(n,d=2)=>Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});const el=id=>document.getElementById(id);
el('headline-deviation').textContent=f(D.stages.original.max_deviation_percent,4)+'%';el('headline-solve').textContent=f(D.original_solve_seconds,2)+' s';
for(const r of D.original_plans){const tr=document.createElement('tr');if(r.district_count===3)tr.className='focus-row';for(const text of [r.district_count+' / '+r.house_sizes.join(', '),f(r.max_deviation_people,3)+' people ('+f(r.max_deviation_percent,6)+'%)',f(r.pipeline_seconds/60,2)+' min',f(r.peak_working_set_bytes/2**20,1)+' MiB',r.rebalance_moves.toLocaleString()+' moves; '+r.stop_reason.replaceAll('_',' ')]){const td=document.createElement('td');td.textContent=text;tr.appendChild(td)}el('anchor-table').appendChild(tr)}
function svg(tag,attrs,parent){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);parent.appendChild(e);return e}
function chart(id,key){const root=el(id),w=1060,h=260,L=90,R=24,T=20,B=46;root.setAttribute('viewBox',`0 0 ${w} ${h}`);const pts=D.trace.filter(p=>Number.isFinite(p[key]));if(!pts.length)return false;const xmax=Math.max(...pts.map(p=>p.moves)),ymax=Math.max(...pts.map(p=>p[key]))*1.04;const x=n=>L+n/xmax*(w-L-R),y=n=>h-B-n/ymax*(h-B-T);for(let i=0;i<=4;i++){const value=ymax*i/4;svg('line',{x1:L,y1:y(value),x2:w-R,y2:y(value),class:'chart-grid'},root);const t=svg('text',{x:L-10,y:y(value)+4,'text-anchor':'end',class:'chart-label'},root);t.textContent=value>=1e9?f(value/1e9,1)+'B':value>=1e6?f(value/1e6,1)+'M':f(value,0)}for(let i=0;i<=5;i++){const value=xmax*i/5;const t=svg('text',{x:x(value),y:h-20,'text-anchor':'middle',class:'chart-label'},root);t.textContent=f(value,0)}const a=svg('text',{x:w-R,y:h-2,'text-anchor':'end',class:'chart-label'},root);a.textContent='Boundary moves after repair';for(const [subset,color]of [[pts.filter(p=>p.moves<=1000),'#21cba8'],[pts.filter(p=>p.moves>=1000),'#ff72bf']]){if(subset.length){const path=subset.map((p,i)=>(i?'L':'M')+x(p.moves)+','+y(p[key])).join(' ');svg('path',{d:path,fill:'none',stroke:color,'stroke-width':3},root)}}if(xmax>=1000){svg('line',{x1:x(1000),y1:T,x2:x(1000),y2:h-B,stroke:'#bac6d7','stroke-dasharray':'5 5'},root);const t=svg('text',{x:x(1000)-6,y:T+13,'text-anchor':'end',class:'chart-label'},root);t.textContent='Original limit'}for(const p of [pts[0],pts.at(-1)]){const c=svg('circle',{cx:x(p.moves),cy:y(p[key]),r:4,fill:p.moves>1000?'#ff72bf':'#21cba8'},root);svg('title',{},c).textContent=f(p[key],2)+' at move '+p.moves}return true}
chart('deviation-chart','max_deviation_people');if(!chart('objective-chart','squared_deviation_people'))el('objective-section').hidden=true;
const probe=D.probe, ps=D.stages.probe;el('probe-detail').textContent=ps?`${probe.additional_moves} additional moves in ${f(probe.elapsed_seconds,2)} s; final maximum deviation ${f(ps.max_deviation_people,3)} people (${f(ps.max_deviation_percent,6)}%). Stop: ${probe.stop_reason.replaceAll('_',' ')}. Its strict polygon audit passed; it remains a diagnostic continuation. Donor-connectivity guard: ${f(probe.guard_calls,0)} calls, ${f(probe.guard_failed_calls,0)} rejected candidates, ${f(probe.guard_wall_seconds,2)} s. Guard time is ${f(probe.guard_wall_seconds/probe.elapsed_seconds*100,2)}% of probe wall time. Profiling overhead is included.`:'No continuation outcome has been supplied.';
let active='original',cache={},repair=null,base=[0,0,720,520],view=[...base],generation=0;const map=el('map');function setView(){map.setAttribute('viewBox',view.join(' '))}function coords(g){if(g.type==='Polygon')return g.coordinates.flat();if(g.type==='MultiPolygon')return g.coordinates.flat(2);if(g.type==='GeometryCollection')return g.geometries.flatMap(coords);return[]}
function features(j){return j.type==='FeatureCollection'?j.features:j.type==='Feature'?[j]:[{type:'Feature',geometry:j,properties:{}}]}
function drawGeometry(g,project){if(g.type==='GeometryCollection')return g.geometries.map(x=>drawGeometry(x,project)).join(' ');const polygons=g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[];return polygons.flatMap(p=>p.map(r=>r.map((pt,i)=>(i?'L':'M')+project(pt).join(',')).join(' ')+'Z')).join(' ')}
async function get(name){if(!cache[name]){const response=await fetch(name);if(!response.ok)throw Error(name+' returned '+response.status);cache[name]=await response.json()}return cache[name]}
async function select(name){active=name;const serial=++generation;document.querySelectorAll('[data-stage]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.stage===name)));const s=D.stages[name],box=el('stage-detail');box.replaceChildren();const badge=document.createElement('span');badge.className='badge';badge.textContent=name==='original'?'VALID ORIGINAL MAP':name==='probe'?'DIAGNOSTIC CONTINUATION':'DIAGNOSTIC ASSIGNMENT';box.appendChild(badge);const heading=document.createElement('h2');heading.textContent=labels[name];heading.style.marginTop='12px';box.appendChild(heading);const max=document.createElement('strong');max.textContent=f(s.max_deviation_people,3)+' people / '+f(s.max_deviation_percent,6)+'%';box.appendChild(max);const caption=document.createElement('div');caption.className='small';caption.textContent='Maximum absolute deviation from '+f(D.total_population/3,3)+' residents';box.appendChild(caption);const dl=document.createElement('dl');s.populations.forEach((p,i)=>{const dt=document.createElement('dt');dt.textContent='District '+(i+1);dt.style.color=colors[i];const dd=document.createElement('dd');dd.textContent=f(p,0);dl.append(dt,dd)});box.appendChild(dl);const c=document.createElement('p');c.className='small';c.textContent='Shared-edge component counts: '+(s.components?JSON.stringify(s.components):'See diagnostic evidence');box.appendChild(c);const audit=document.createElement('p');audit.className='small';audit.textContent='Independent polygon audit: '+(s.strict_polygon_validation_passed?'passed':'not strict-valid')+(s.polygon_components?'; components '+JSON.stringify(s.polygon_components):'')+(s.polygons_valid===false?'; dissolved geometry invalid':'')+(s.polygon_audit_note?'. '+s.polygon_audit_note:'');box.appendChild(audit);el('stage-warning').textContent=name==='original'?'All three districts pass strict graph and polygon connectivity. The 2.25359% population deviation remains unresolved.':name==='initial'?'Numerically balanced, but disconnected. These assignments are not an accepted district map.':name==='repaired'?'Whole-block graph connectivity is repaired. The independent polygon status is listed above; population balancing has not yet run.': 'This bounded continuation is diagnostic. Its displayed outline is not a newly accepted corrected map.';el('map-note').textContent='Loading '+labels[name].toLowerCase()+'…';try{const data=await get(s.map_file);if(!repair)repair=await get('repair-component.geojson');if(serial!==generation)return;const fs=features(data);const points=fs.flatMap(f=>coords(f.geometry));if(!points.length)throw Error('No polygon coordinates');const bounds=points.reduce((b,p)=>[Math.min(b[0],p[0]),Math.min(b[1],p[1]),Math.max(b[2],p[0]),Math.max(b[3],p[1])],[Infinity,Infinity,-Infinity,-Infinity]),[xmin,ymin,xmax,ymax]=bounds,isLonLat=Math.abs(xmin)<180&&Math.abs(xmax)<180&&Math.abs(ymax)<90;const cx=(xmin+xmax)/2,cy=(ymin+ymax)/2,cos=isLonLat?Math.cos(cy*Math.PI/180):1,scale=Math.min(660/((xmax-xmin)*cos),450/(ymax-ymin)),project=p=>[360+(p[0]-cx)*cos*scale,250-(p[1]-cy)*scale];el('map-shapes').replaceChildren();fs.forEach((f,i)=>{const prop=f.properties||{};let district=prop.district??prop.district_id??prop.district_index??i;if(typeof district==='string')district=Number(district);const path=svg('path',{d:drawGeometry(f.geometry,project),fill:colors[(Number.isInteger(district)?district:i)%colors.length],stroke:'#0c1320','stroke-width':.9,'vector-effect':'non-scaling-stroke','fill-rule':'evenodd'},el('map-shapes'));svg('title',{},path).textContent='District '+((Number.isInteger(district)?district:i)+1)});el('map-repair').replaceChildren();features(repair).forEach(f=>svg('path',{d:drawGeometry(f.geometry,project),fill:'url(#repair-hatch)',stroke:'#ff72bf','stroke-width':1.2,'vector-effect':'non-scaling-stroke','fill-rule':'evenodd'},el('map-repair')));el('map-repair').style.display=el('show-repair').checked?'':'none';el('map-note').textContent=labels[name]+' · display geometry only · source block populations retained';view=[...base];setView()}catch(error){if(serial===generation){el('map-note').textContent='Geometry unavailable: '+error.message;el('map-shapes').replaceChildren();el('map-repair').replaceChildren()}}}
for(const name of ['initial','repaired','original','probe'])if(D.stages[name]){const b=document.createElement('button');b.textContent=labels[name];b.dataset.stage=name;b.setAttribute('aria-pressed','false');b.onclick=()=>select(name);el('stage-buttons').appendChild(b)}
el('show-repair').onchange=()=>el('map-repair').style.display=el('show-repair').checked?'':'none';el('fit-map').onclick=()=>{view=[...base];setView()};function zoom(factor){const[x,y,w,h]=view;view=[x+w*(1-factor)/2,y+h*(1-factor)/2,w*factor,h*factor];setView()}el('zoom-in').onclick=()=>zoom(.75);el('zoom-out').onclick=()=>zoom(1.3333);map.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY>0?1.12:.89)},{passive:false});let drag=null;map.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,view:[...view]};map.setPointerCapture(e.pointerId)};map.onpointermove=e=>{if(!drag)return;const rect=map.getBoundingClientRect();view=[drag.view[0]-(e.clientX-drag.x)*drag.view[2]/rect.width,drag.view[1]-(e.clientY-drag.y)*drag.view[3]/rect.height,drag.view[2],drag.view[3]];setView()};map.onpointerup=map.onpointercancel=()=>drag=null;select('original');
</script></body></html>'''


def build(diagnosis_path: Path, output: Path, report: Path) -> None:
    data = saved_context(load(diagnosis_path))
    for stage in data["stages"].values():
        path = diagnosis_path.parent / stage["map_file"]
        if not path.is_file():
            raise FileNotFoundError(path)
    if not (diagnosis_path.parent / "repair-component.geojson").is_file():
        raise FileNotFoundError("Missing saved repair component geometry")
    # Escape the only sequence that can terminate a literal script element.
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(PAGE.replace("__DATA__", payload), encoding="utf-8")
    report.write_text(narrative(data), encoding="utf-8")
    print(json.dumps({"viewer": str(output), "report": str(report), "stages": list(data["stages"])}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnosis", type=Path, default=DIAGNOSTICS / "diagnosis.json")
    parser.add_argument("--output", type=Path, default=DIAGNOSTICS / "index.html")
    parser.add_argument("--report", type=Path, default=ROOT / "prompts/west-virginia-balance-diagnosis.md")
    args = parser.parse_args()
    build(args.diagnosis, args.output, args.report)


if __name__ == "__main__":
    main()
