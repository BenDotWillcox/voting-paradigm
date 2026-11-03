"""Validate and summarize the Kentucky source and cross-jurisdiction diagnosis."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.cache/state-block-benchmark/suite-through-1000/diagnostics/kentucky'
URL = 'http://127.0.0.1:8770/diagnostics/kentucky/'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    names = ('diagnosis.json', 'geography-context.json', 'missouri-connection-context.json', 'area-water-audit.json')
    diagnosis, geography, context, water = [json.loads((OUTPUT / name).read_text(encoding='utf-8')) for name in names]
    assert diagnosis['status'] == 'diagnostic_complete_no_district_plans_generated'
    for name, digest in diagnosis['artifact_sha256'].items():
        assert sha256(OUTPUT / name) == digest, name
    for name, digest in json.loads((OUTPUT / 'preserved-file-inventory.json').read_text()).items():
        assert sha256(ROOT / name) == digest, name
    assert diagnosis['physical_component_count'] == 2
    assert not diagnosis['blocks_spanning_components']
    main_component, detached = diagnosis['components']
    total = main_component['population'] + detached['population']
    assert total == diagnosis['total_population'] == 4505836
    assert main_component['block_count'] + detached['block_count'] == diagnosis['block_count'] == 132662
    assert detached['population'] == 9 and detached['block_count'] == 5
    link = diagnosis['links'][0]
    endpoints = [endpoint['coordinate'] for endpoint in link['endpoints']]
    assert endpoints == water['candidate_endpoints'] == context['candidate_endpoints']
    assert water['status'] == context['status'] == 'complete'
    assert not water['water_only_under_2020_census_area_water']
    assert math.isclose(water['mapped_water_length_m'] + water['outside_mapped_water_length_m'],
                        water['candidate_planar_length_m'], abs_tol=1e-6)
    assert math.isclose(context['missouri_interior_coverage_m'], context['candidate_planar_length_m'], abs_tol=1e-6)
    assert sha256(ROOT / water['source_archive']) == water['source_archive_sha256']
    assert sha256(Path(context['source_archive'])) == context['source_archive_sha256']
    rows = []
    for plan in diagnosis['plans']:
        k = plan['district_count']
        # Independent necessary bound: a district in the detached component
        # can have at most nine people, even with freely divisible population.
        bound = Fraction(total - detached['population'] * k, total)
        assert list((bound.numerator, bound.denominator)) == plan['strict_population_bound']['deviation_fraction']
        assert plan['augmented_graph_validation']['all_source_parts_reached']
        assert plan['augmented_graph_validation']['component_sizes'] == [diagnosis['part_count']]
        assert plan['selected_link_ids'] == [link['id']]
        assert not plan['actual_district_plan_generated']
        rows.append(f"| {', '.join(map(str, plan['house_sizes']))} | {k} | {total/k:,.3f} | {100*float(bound):.6f}% |")
    summary = {
        'status': 'diagnostic_complete_no_district_plans_generated',
        'question': 'What disconnects Kentucky, why, and can the same recorded-connection approach resolve it?',
        'components': diagnosis['components'], 'plans': diagnosis['plans'], 'candidate': link,
        'crossing_context': context, 'area_water_audit': water, 'geographic_context': geography,
        'conclusion': 'The same population-aware grouping and one recorded edge connect the source graph. The nearest edge crosses Missouri land as well as river, requiring an explicit exclave connection rather than a water-only claim. No balanced district plan has been constructed.',
        'source_hashes': {name: sha256(OUTPUT / name) for name in names},
        'original_preservation': diagnosis['preservation'],
        'independent_checks': ['Original file and diagnostic artifact hashes match.',
            'Component totals reconcile to official resident and block counts.',
            'Strict population bounds independently recomputed as 1 - 9*K/4505836.',
            'Identical candidate endpoints used in Kentucky, Missouri and area-water audits.',
            'Mapped water and outside-water lengths reconcile to the complete candidate segment.',
            'All 132669 polygon parts reachable after the selected edge, for every requested anchor.'],
    }
    (ROOT / 'prompts/kentucky-topology-diagnosis.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    text = f'''# Kentucky: a recorded connection for an exclave

**Kentucky Bend is a genuine detached piece of the state. One recorded connection resolves the source-graph obstruction, but the nearest line crosses Missouri land as well as river. It must be described as an explicit exclave connection, not a water-only link.**

[Explore the diagnostic map]({URL}). Colors show physical source components, not districts; the dashed line is hypothetical. No Kentucky district solver or district-map export ran in this diagnosis.

## What is disconnected?

| Component | Residents | Census blocks | Polygon parts |
|---|---:|---:|---:|
| Main Kentucky coverage | 4,505,827 | 132,657 | 132,664 |
| Kentucky Bend / Madrid Bend | 9 | 5 | 5 |
| Total | 4,505,836 | 132,662 | 132,669 |

The detached component lies in Fulton County. It includes **45.202351 km² of land and 24.427246 km² of water coverage**, with four zero-population blocks and two water-only blocks. All nine residents are in one of its five blocks. Nothing was discarded for having zero population. Four multipart blocks elsewhere in the state remain within their physical components; no block spans the two components. Both exact component unions are valid single polygons. The gap is positive, not a corner contact or a numerical crack.

The location matches Kentucky Bend, the peninsula whose neck joins Tennessee. Kentucky's boundary followed the Mississippi; the Kentucky Historical Society describes the river claim and the boundary survey settlement with Tennessee. This geographic explanation is supported by the [Madrid Bend historical marker](https://history.ky.gov/markers/madrid-bend); the exact populations and boundaries above are calculated from the saved 2020 Census blocks.

## What strict shared edges permit

Every retained physical component needs at least one district. A district confined to the detached component can contain at most nine residents. Therefore its deviation from the statewide ideal is at least `1 − 9 × district_count / 4,505,836`. The component-allocation calculation independently agrees with this bound:

| House size | Kentucky districts | Ideal residents per district | Unavoidable maximum deviation, at least |
|---|---:|---:|---:|
{chr(10).join(rows)}

These are necessary bounds, not constructed strict plans. They rule out near-equal population under strict shared-edge connectivity while retaining every block. More optimizer iterations cannot remove this geographic constraint.

## What a recorded connection changes

The population-aware selector used for Hawaii chooses one link at every Kentucky anchor: main block **{endpoints and link['endpoints'][0]['geoid']}** to Bend block **{link['endpoints'][1]['geoid']}**. The mainland is the sole district-sized root; the nine-person component is undersized at all four counts. An independent traversal of the augmented graph reaches all **132,669 parts** after inserting that edge. Source polygons and physical adjacency remain unchanged.

The candidate is approximately **{link['distance_m']/1000:.3f} km** long, measured between original census-coverage boundaries. It is selected by an approximate equirectangular nearest-boundary search; reported length is the spherical distance between those endpoints, not a certified shortest geodesic or a shoreline distance.

The entire gap lies within Missouri census coverage. Official [2020 New Madrid County area-water polygons]({water['source_url']}) show **{water['mapped_water_length_m']/1000:.3f} km crossing the Mississippi River in two segments**, and **{water['outside_mapped_water_length_m']/1000:.3f} km crossing Missouri land between them**. The full county layer has {water['county_area_water_feature_count']} features. The intersection audit uses exact source polygons; display context is simplified. This describes mapped 2020 geography, not current river levels, navigation or a road/ferry route. A longer curved water-only route was not searched, so this does not prove none exists.

**Recommendation:** reuse the population-aware grouping and recorded-link validation, with a clearly named **exclave connection** category for Kentucky. The link grants adjacency only between its two Kentucky endpoint blocks; it does not assign Missouri territory to a Kentucky district. A district may use it only when both endpoint blocks belong to that district.

This removes the component-population obstruction, but does not establish a balanced whole-block partition. A Kentucky adapter and fresh runs at 6, 8, 9 and 14 districts must still demonstrate population balance, repair/rebalancing behavior, and independent final polygon-plus-link connectivity. The Rhode Island and Hawaii geometry adapters are state-scoped; they were not silently applied to Kentucky.

## Verification and preserved evidence

All five protected historical files (the original Kentucky report/progress/log, national manifest and Kentucky source archive) remain byte-identical. The original six-district run stopped at source-topology preflight; the other three anchors reused that exception and did not have individual solver runs. The Missouri block archive and downloaded water archive were verified by hash. No numerical or existing policy code changed.

The final diagnostic used a warm graph cache and took {diagnosis['analysis_seconds']:.2f} seconds. This is diagnostic timing, not a district benchmark; earlier diagnostic tooling repairs and cold preparation are retained separately in [attempt notes]({URL}diagnostic-attempt-notes.json).

[Exact source audit]({URL}diagnosis.json) · [Missouri coverage audit]({URL}missouri-connection-context.json) · [Water/land intersection audit]({URL}area-water-audit.json) · [Machine-readable summary](C:/Users/benja/projects/voting_paradigm/prompts/kentucky-topology-diagnosis.json).
'''
    (ROOT / 'prompts/kentucky-topology-diagnosis.md').write_text(text, encoding='utf-8')
    print('Kentucky diagnosis validated and durable reports saved.')


if __name__ == '__main__':
    main()
