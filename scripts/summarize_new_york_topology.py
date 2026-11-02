"""Verify and summarize New York's diagnostic; never construct district plans."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

import shapefile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '.cache/state-block-benchmark/suite-through-1000/diagnostics/new-york'
REPORT = ROOT / 'prompts/new-york-topology-diagnosis'
NPS = {
    'Ellis Island geography': 'https://www.nps.gov/elis/faqs.htm',
    'Liberty Island geography': 'https://www.nps.gov/stli/planyourvisit/frequently-asked-questions-statue-of-liberty.htm',
}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(name: str):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def run() -> None:
    diagnosis, geography = read('diagnosis.json'), read('geography-context.json')
    assert diagnosis['status'] == 'diagnostic_complete_no_district_plans_generated'
    assert geography['status'] == 'complete'
    inventory = read('preserved-file-inventory.json')
    for name, expected in inventory.items():
        assert digest(ROOT / name) == expected, name
    for name, expected in diagnosis['artifact_sha256'].items():
        assert digest(DATA / name) == expected, name
    assert digest(DATA / 'candidate-links.json') == geography['candidate_file_sha256']
    for name, expected in geography['source_archive_sha256'].items():
        assert digest(ROOT / name) == expected, name

    archive = ROOT / '.cache/state-block-benchmark/source/36/tl_2020_36_tabblock20.zip'
    count = population = zero = 0
    island_records = {}
    with zipfile.ZipFile(archive) as zipped:
        dbf = next(name for name in zipped.namelist() if name.endswith('.dbf'))
        with shapefile.Reader(dbf=zipped.open(dbf)) as reader:
            for record in reader.iterRecords(fields=['GEOID20', 'POP20', 'HOUSING20', 'ALAND20', 'AWATER20']):
                row = record.as_dict()
                count += 1
                population += row['POP20']
                zero += row['POP20'] == 0
                if row['GEOID20'] in ('360610001001000', '360610001001001', '360610005000003'):
                    island_records[row['GEOID20']] = row
    assert (count, population, zero) == (288819, 20201249, 58480)
    assert (count, population) == (diagnosis['block_count'], diagnosis['total_population'])
    assert diagnosis['physical_component_count'] == 3 and not diagnosis['blocks_spanning_components']
    assert sum(row['block_count'] for row in diagnosis['components']) == count
    assert sum(row['part_count'] for row in diagnosis['components']) == diagnosis['part_count'] == 288841
    assert sum(row['population'] for row in diagnosis['components']) == population
    for row in island_records.values():
        assert row['POP20'] == row['HOUSING20'] == 0
    assert island_records['360610005000003']['ALAND20'] == 0

    selected = {'ny-candidate-00-01', 'ny-candidate-00-02'}
    assert [row['district_count'] for row in diagnosis['plans']] == [26, 35, 42, 61]
    for plan in diagnosis['plans']:
        assert set(plan['selected_link_ids']) == selected
        assert plan['augmented_graph_validation']['component_sizes'] == [288841]
        assert plan['strict_population_bound']['best_max_deviation_pct'] == 100
        assert plan['policy_population_bound']['best_max_deviation_pct'] == 0
        assert not plan['actual_district_plan_generated']
    for link in geography['links']:
        source = next(row for row in diagnosis['links'] if row['id'] == link['candidate_id'])
        assert link['candidate_endpoints'] == [row['coordinate'] for row in source['endpoints']]
        assert link['selected_k'] == source['selected_k']
        land = sum(row['candidate_interior_length_m'] for row in link['crossed_new_jersey_blocks']
                   if row['land_area_m2'] > 0 and row['water_area_m2'] == 0)
        assert abs(land - link['outside_mapped_water_length_m']) < .001
    links = {row['candidate_id']: row for row in geography['links']}
    assert links['ny-candidate-00-01']['water_only_under_2020_census_area_water']
    assert not links['ny-candidate-00-02']['water_only_under_2020_census_area_water']
    ellis = next(row for row in geography['isolated_island_water_access'] if row['geoid'].endswith('1000'))
    assert not ellis['water_intersects_island']
    assert abs(ellis['source_boundary_length_m'] - ellis['boundary_touching_new_jersey_nonwater_m']) < .001

    result = {
        'generated_at': datetime.now(timezone.utc).isoformat(), 'status': 'diagnostic_only_no_district_plans',
        'source_population_audit': {'block_count': count, 'resident_population': population,
                                  'zero_population_block_count': zero, 'selected_source_records': island_records},
        'diagnosis': diagnosis, 'connection_geography': geography, 'historical_sources': NPS,
        'preserved_file_count_independently_verified': len(inventory),
        'evidence_sha256': {name: digest(DATA / name) for name in ('diagnosis.json', 'geography-context.json')},
        'conclusion': 'Population-aware selection resolves the source-graph obstruction with one water link and one explicitly recorded exclave link; water-only eligibility does not resolve Ellis Island.',
        'conditional_extension': 'Both zero-population island blocks can join the district containing their shared water-block endpoint. This extends any valid main-component partition without changing district populations; it does not construct such a partition.',
    }
    REPORT.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    lines = [
        '# New York topology diagnosis', '',
        '[Open the interactive diagnostic](http://127.0.0.1:8770/diagnostics/new-york/)', '',
        '**The population-aware selector resolves the graph obstruction, but a water-only policy is insufficient for Ellis Island.** '
        'Use a recorded water link for Liberty Island and an explicit exclave connection for New York’s portion of Ellis Island. '
        'No district plans were generated and no existing connectivity policy was changed.', '',
        '| Physical component | Blocks | Polygon parts | 2020 residents |',
        '|---|---:|---:|---:|',
        '| Main New York coverage | 288,817 | 288,839 | 20,201,249 |',
        '| Liberty Island | 1 | 1 | 0 |',
        '| New York portion of Ellis Island | 1 | 1 | 0 |', '',
        'All 288,819 census blocks remain included. The 12 multipart blocks stay within their respective components; '
        'there is no population allocation ambiguity between detached parts. Both isolated blocks record zero housing units as well as zero residents. '
        'They are real park/museum geography, not missing records. Zero resident population does not mean zero visitors.', '',
        'The main component includes 7,660 water-only census blocks. Shared-edge connectivity here covers the complete census geography; '
        'it is not a continuous-dry-land or road-access test. Long Island, Staten Island and Manhattan do not create additional disconnected components in this source.', '',
        '## Why these two blocks are separate', '',
        'Liberty Island is in New York’s territorial jurisdiction. Ellis Island has a split boundary: its original New York portion contains the museum’s Main Building, '
        'while most expanded land is in New Jersey. The Census geometry reflects that separation. '
        f'[National Park Service: Liberty Island]({NPS["Liberty Island geography"]}); '
        f'[National Park Service: Ellis Island]({NPS["Ellis Island geography"]}).', '',
        '## Proposed connections', '',
        '| Candidate | Total distance | Mapped water | New Jersey land | Selected |',
        '|---|---:|---:|---:|---|',
    ]
    labels = {'ny-candidate-00-01': 'Liberty → main coverage', 'ny-candidate-00-02': 'Ellis → main coverage',
              'ny-candidate-01-02': 'Liberty → Ellis'}
    for key, label in labels.items():
        row = links[key]
        lines.append(f'| {label} | {row["distance_m"]:.1f} m | {row["mapped_water_length_m"]:.1f} m | '
                     f'{row["outside_mapped_water_length_m"]:.1f} m | {"All four anchors" if key in selected else "No"} |')
    lines += ['',
        'Both selected links end on the same New York water-only block, `360610005000003`. These are distances to included census boundaries, '
        'not to a Manhattan shoreline or ferry terminal. The candidate between the islands is longer and is not selected.', '',
        'The entire boundary of the New York Ellis block is surrounded by New Jersey nonwater coverage in the 2020 data. '
        f'Its closest mapped-water gap is {ellis["minimum_distance_to_hudson_county_mapped_water_m"]:.2f} m. '
        'Thus changing the candidate’s direction cannot make a strictly water-only route leave this block in the audited geometry. '
        'The proposed direct link crosses about 25.5 m of New Jersey land, verified both against county water polygons and a land-only New Jersey census block. '
        'This is the same kind of explicit geographic exception used for Kentucky, on a much shorter land segment. No New Jersey territory or population would be assigned.', '',
        '## Population-aware feasibility', '',
        '| House size | New York districts | Ideal resident population | Proposed links | Source components after links |',
        '|---:|---:|---:|---:|---:|',
    ]
    for plan in diagnosis['plans']:
        lines.append(f'| {plan["house_sizes"][0]:,} | {plan["district_count"]} | {plan["ideal_population"]:,.3f} | 2 | 1 |')
    lines += ['',
        'The unchanged population-aware selector chooses the same two edges at every anchor. An independent full-graph traversal reaches all 288,841 polygon parts. '
        'There is only one populated component, so no large-island seat-allocation tradeoff arises.', '',
        'Under strict physical connectivity with every block assigned, each single-block island would require a zero-population district: at least 100% maximum population deviation. '
        'The policy’s grouped-population lower bound becomes 0%; this is an optimistic mathematical bound, not achieved district balance. '
        'More specifically, any valid connected partition of the main component can be extended by assigning both zero-population island blocks to the district containing their shared endpoint block, '
        'without changing population totals. The balanced partition of the main component still needs to be computed and independently validated.', '',
        '## Validation and limits', '',
        f'- Independently reread original ZIP DBF records; verified block/population totals, island records, endpoint ownership, selected links, and water/land segment reconciliation.',
        f'- Verified source/artifact checksums and all {len(inventory)} protected historical files, including the strict result, national manifest and original New York archive.',
        '- Source polygons and physical adjacency remain unchanged. Proposed links are conceptual graph edges, not roads, ferries or boundary transfers.',
        '- Exact part adjacency and polygon intersections use unsimplified 2020 geometry. Display polygons are simplified separately.',
        '- Candidate search uses an approximate per-pair projection; lengths are not certified shortest geodesics. Water classifications describe mapped 2020 geography, not navigability or current water levels.',
        '- Original strict K26 stopped before solving after 99.36 seconds; K35/K42/K61 reused its topology exception. No new district runtime, balance or compactness results exist yet.', '',
        '[Detailed topology evidence](../.cache/state-block-benchmark/suite-through-1000/diagnostics/new-york/diagnosis.json) · '
        '[Independent crossing audit](../.cache/state-block-benchmark/suite-through-1000/diagnostics/new-york/geography-context.json)', '',
    ]
    REPORT.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Verified all four anchors and wrote {REPORT.with_suffix(".md")}')


if __name__ == '__main__':
    run()
