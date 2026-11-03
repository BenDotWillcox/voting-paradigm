"""Inspect Hawaii source topology and proposed island forests without solving plans.

All physical adjacency remains exact. Connection distances are diagnostic:
candidate endpoints minimize a per-pair local equirectangular boundary distance;
the displayed length is the spherical great-circle distance of those endpoints.
This avoids one statewide plane across Hawaii's 24-degree longitude extent,
but is not an ellipsoidal or certified globally shortest geodesic calculation.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import shapefile
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import Point, mapping, shape
from shapely.ops import nearest_points

from scripts.benchmark_kansas_blocks import Measurements
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import load_units, prepare_source, sha256

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'diagnostics/hawaii'
EARTH_RADIUS_M = 6_371_000.0


def great_circle_m(first: list[float], second: list[float]) -> float:
    """Stable haversine distance, retaining wraparound longitude behavior."""
    lon1, lat1, lon2, lat2 = map(math.radians, [*first, *second])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*EARTH_RADIUS_M*math.asin(math.sqrt(min(1.0, max(0.0, h))))


def rooted_forest(populations: list[int], links: list[dict[str, Any]], minimum: float) -> dict[str, Any]:
    """The RI rooted Kruskal policy; no merge of two groups already holding roots."""
    if minimum <= 0 or not math.isfinite(minimum) or any(p < 0 for p in populations):
        raise ValueError('Expected nonnegative populations and positive finite minimum.')
    roots = {i for i, population in enumerate(populations) if population >= minimum}
    if not roots:
        raise ValueError('No eligible source root.')
    parents = list(range(len(populations)))
    root_of = [i if i in roots else None for i in parents]
    def find(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    selected = []
    for link in sorted(links, key=lambda row: (row['distance_m'], *row['component_ids'])):
        if link['distance_m'] <= 0:
            continue
        a, b = map(find, link['component_ids'])
        if a == b or (root_of[a] is not None and root_of[b] is not None):
            continue
        parents[b] = a
        root_of[a] = root_of[a] if root_of[a] is not None else root_of[b]
        selected.append(link['id'])
    if any(root_of[find(i)] is None for i in range(len(populations))):
        raise ValueError('At least one small component cannot reach a root.')
    groups = []
    for root in sorted(roots):
        members = [i for i in range(len(populations)) if root_of[find(i)] == root]
        groups.append({'root_component_id': root, 'component_ids': members,
                       'population': sum(populations[i] for i in members)})
    assert len(selected) == len(populations)-len(roots)
    return {'root_component_ids': sorted(roots), 'selected_link_ids': selected, 'groups': groups}


def population_allocation_bound(populations: list[int], districts: int) -> dict[str, Any]:
    """Optimistic minimax bound over positive integer seats per disconnected group.

Within each group, perfectly divisible population is assumed. A real whole-block
connected partition can only have at least this maximum deviation, never less.
"""
    if districts < 1 or not populations or any(p < 0 for p in populations) or sum(populations) <= 0:
        raise ValueError('Expected nonnegative groups with positive total and districts.')
    if len(populations) > districts:
        return {'feasible_seat_allocation': False, 'reason': 'More physical groups than districts.',
                'minimum_required_districts': len(populations)}
    ideal = sum(populations)/districts
    dp: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, ())}
    for population in populations:
        next_dp = {}
        for used, (prior, counts) in dp.items():
            for seats in range(1, districts-used+1):
                entry = (max(prior, abs(population/seats-ideal)/ideal), (*counts, seats))
                if used+seats not in next_dp or entry < next_dp[used+seats]:
                    next_dp[used+seats] = entry
        dp = next_dp
    deviation, allocation = dp[districts]
    return {'feasible_seat_allocation': True, 'best_max_deviation_pct': 100*deviation,
            'seat_counts': list(allocation), 'group_ideal_seats': [p/ideal for p in populations],
            'ideal_population': ideal, 'within_one_percent_necessary_test': deviation <= .01,
            'is_constructed_plan': False,
            'interpretation': 'Optimistic necessary bound; ignores indivisible blocks and internal geometry.'}


def components(adjacency: tuple[tuple[int, ...], ...]) -> tuple[list[list[int]], list[int]]:
    seen, groups = set(), []
    for start in range(len(adjacency)):
        if start in seen:
            continue
        seen.add(start)
        pending, members = [start], []
        while pending:
            current = pending.pop()
            members.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        groups.append(sorted(members))
    groups.sort(key=lambda group: (-len(group), group[0]))
    membership = [-1]*len(adjacency)
    for i, members in enumerate(groups):
        for member in members:
            membership[member] = i
    return groups, membership


def inventory() -> dict[str, str]:
    paths = [SUITE/'suite.json', ROOT/'.cache/state-block-benchmark/source/15/tl_2020_15_tabblock20.zip']
    paths.extend(path for path in (SUITE/'states/15').rglob('*') if path.is_file())
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(paths)}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def geographic_label(point: Point) -> tuple[str, str]:
    # Coordinates are descriptive labels only; no external outline joins affect topology.
    locations = [('Oʻahu', -157.97,21.47), ('Hawaiʻi Island', -155.5,19.6), ('Maui / Kahoʻolawe coverage', -156.33,20.8),
                 ('Kauaʻi', -159.53,22.07), ('Molokaʻi', -157.0,21.14), ('Lānaʻi', -156.92,20.83),
                 ('Niʻihau / Lehua', -160.15,21.90), ('Kahoʻolawe', -156.6,20.55),
                 ('Kaʻula', -160.54,21.66), ('Nihoa', -161.92,23.06), ('Mokumanamana / Necker',-164.70,23.57),
                 ('French Frigate Shoals',-166.28,23.86), ('Gardner Pinnacles',-167.99,24.99),
                 ('Maro Reef',-170.63,25.51), ('Laysan',-171.73,25.78), ('Lisianski',-173.96,26.06),
                 ('Pearl and Hermes Atoll',-175.85,27.80), ('Kure Atoll',-178.30,28.42)]
    best = min(locations, key=lambda row: great_circle_m([point.x,point.y], [row[1],row[2]]))
    return best[0], 'Approximate geographic label from component bounds and nearby island coordinates; county FIPS retained separately.'


def run() -> dict[str, Any]:
    started = time.perf_counter()
    before = inventory()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    measure = Measurements()
    try:
        source, source_metadata = prepare_source('15', ROOT/'.cache/state-block-benchmark/source/15', measure)
        units, population_map, input_metadata = load_units(source, '15')
        geoids = [u.geoid for u in units]
        graph, graph_metadata, cache = load_or_build_shared_edge_part_graph(
            source, geoids, source_sha256=source_metadata['archive_sha256'],
            cache_dir=ROOT/'.cache/state-block-benchmark/graph-cache/15')
        if graph_metadata['interior_overlap_pair_count']:
            raise ValueError('Source parts overlap.')
        by_geoid = {}
        with shapefile.Reader(str(source)) as reader:
            for row in reader.iterShapeRecords():
                geometry = shape(row.shape.__geo_interface__)
                by_geoid[str(row.record['GEOID20'])] = (geometry, row.record.as_dict())
        parts, records, source_part_indices = [], [], []
        for geoid in geoids:
            geometry, record = by_geoid[geoid]
            unit_parts = list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]
            parts.extend(unit_parts)
            source_part_indices.extend(range(len(unit_parts)))
            records.append(record)
        assert len(parts) == len(graph.adjacency)
        groups, membership = components(graph.adjacency)
        spanning = []
        block_groups = [[] for _ in groups]
        for unit, nodes in enumerate(graph.unit_to_parts):
            owners = {membership[node] for node in nodes}
            if len(owners) != 1:
                spanning.append({'geoid': geoids[unit], 'component_ids': sorted(owners)})
            else:
                block_groups[owners.pop()].append(unit)
        if spanning:
            raise ValueError(f'Whole blocks span physical components: {spanning}')
        component_geometries = [shapely.union_all([parts[n] for n in nodes]) for nodes in groups]
        rows = []
        for i, (members, geometry) in enumerate(zip(block_groups, component_geometries, strict=True)):
            if not geometry.is_valid or geometry.geom_type != 'Polygon':
                raise ValueError(f'Component {i} did not dissolve independently to one valid Polygon.')
            point = geometry.representative_point()
            label, basis = geographic_label(geometry.centroid)
            rows.append({'id': i, 'label': label, 'label_basis': basis,
                         'population': sum(units[u].population for u in members),
                         'block_count': len(members), 'part_count': len(groups[i]),
                         'water_only_block_count': sum(records[u]['ALAND20']==0 and records[u]['AWATER20']>0 for u in members),
                         'zero_population_block_count': sum(units[u].population==0 for u in members),
                         'bounds': list(geometry.bounds), 'representative_point': [point.x,point.y],
                         'county_fips': sorted({geoids[u][2:5] for u in members}),
                         'polygon_component_count': 1,
                         'example_geoids': [geoids[u] for u in members[:3]]})
        print(json.dumps({'components': rows}), flush=True)
        def endpoint(point: Point, component: int) -> dict[str, Any]:
            candidates = [n for n in groups[component] if parts[n].boundary.distance(point) <= 1e-9]
            if not candidates:
                raise ValueError('Candidate endpoint is not on an original source boundary.')
            node = min(candidates, key=lambda n: (geoids[graph.part_to_unit[n]], source_part_indices[n]))
            return {'geoid': geoids[graph.part_to_unit[node]], 'part_node': node,
                    'part_index': source_part_indices[node], 'coordinate': [point.x,point.y],
                    'source_boundary_error_degrees': parts[node].boundary.distance(point)}
        links = []
        for a in range(len(groups)):
            for b in range(a+1, len(groups)):
                bounds = shapely.total_bounds([component_geometries[a], component_geometries[b]])
                lon0, lat0 = (bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2
                ys = EARTH_RADIUS_M*math.pi/180
                xs = ys*math.cos(math.radians(lat0))
                projected = [affine_transform(component_geometries[i], [xs,0,0,ys,-lon0*xs,-lat0*ys]) for i in (a,b)]
                p,q = nearest_points(projected[0].boundary, projected[1].boundary)
                ends = [endpoint(Point(point.x/xs+lon0,point.y/ys+lat0), component)
                        for point,component in ((p,a),(q,b))]
                distance = great_circle_m(ends[0]['coordinate'], ends[1]['coordinate'])
                links.append({'id': f'hi-candidate-{a:02d}-{b:02d}', 'component_ids': [a,b],
                              'distance_m': distance, 'planar_candidate_distance_m': p.distance(q),
                              'endpoints': ends, 'selected_k': [],
                              'projection': {'kind': 'per-pair-bbox-centered-equirectangular',
                                             'lon0': lon0, 'lat0': lat0}})
        suite = json.loads((SUITE/'suite.json').read_text(encoding='utf-8'))
        state = next(state for state in suite['states'] if state['state_fips']=='15')
        anchors = {job['district_count']: job['house_sizes'] for job in state['jobs']}
        populations = [row['population'] for row in rows]
        plans = []
        for k in sorted(set(anchors)|{8,10}):
            ideal = sum(populations)/k
            forest = rooted_forest(populations, links, .99*ideal)
            bound = population_allocation_bound([group['population'] for group in forest['groups']], k)
            plan = {'district_count': k, 'house_sizes': anchors.get(k, []), 'hypothetical': k not in anchors,
                    'ideal_population': ideal, 'minimum_root_population': .99*ideal,
                    **forest, 'population_bound': bound, 'actual_district_plan_generated': False,
                    'augmented_component_count': len(forest['groups']),
                    'augmented_graph_connected': len(forest['groups'])==1}
            plans.append(plan)
            for link in links:
                if link['id'] in forest['selected_link_ids']:
                    link['selected_k'].append(k)
        features = []
        for row, geometry in zip(rows, component_geometries, strict=True):
            simplified = geometry.simplify(.0005, preserve_topology=True)
            features.append({'type': 'Feature', 'properties': {'component_id': row['id'], **row},
                             'geometry': mapping(simplified)})
        write_json(OUTPUT/'components.geojson', {'type':'FeatureCollection','features':features})
        write_json(OUTPUT/'links.geojson', {'type':'FeatureCollection','features':[
            {'type':'Feature','properties': {'id': link['id'], 'component_a': link['component_ids'][0],
             'component_b': link['component_ids'][1], 'distance_m': link['distance_m'],
             'selected_k': link['selected_k']}, 'geometry': {'type':'LineString',
             'coordinates':[endpoint['coordinate'] for endpoint in link['endpoints']]}} for link in links]})
        after = inventory()
        if before != after:
            raise ValueError('Original strict evidence or archive changed.')
        write_json(OUTPUT/'preserved-file-inventory.json', before)
        report = {'schema_version': 1, 'state': 'Hawaii', 'state_fips':'15',
                  'status':'diagnostic_complete_no_district_plans_generated',
                  'total_population':sum(populations), 'block_count':len(units), 'part_count':len(parts),
                  'physical_component_count':len(rows), 'original_whole_block_component_count':17,
                  'source':source_metadata, 'input':input_metadata, 'part_graph':graph_metadata, 'part_graph_cache':cache,
                  'components':rows, 'links':links, 'plans':plans,
                  'blocks_spanning_components':spanning,
                  'source_coverage_notes': [
                      'Maui and Kahoʻolawe belong to one physical part component because retained census water coverage already connects them.',
                      'Point [-156.60,20.55] on Kahoʻolawe is covered by zero-population land block 150099800001001 in component 2.',
                      'Niʻihau and Lehua are also within the same water-inclusive source component.',
                      'All 949 water-only source blocks remain present; source components are census coverage components, not just land islands.'
                  ],
                  'limitations': [
                      'A connected proposed augmented graph does not prove a balanced whole-block district partition exists.',
                      'No district solver or district polygon export ran. Actual plans need whole-block balancing and independent polygon/link validation.',
                      'One recorded connection can serve only one district: both endpoint blocks must belong to that same district.',
                      'Hypothetical K8/K10 bounds are mathematical necessary limits on any plan under this forest, not achieved district populations.',
                      'Candidate distances use a spherical diagnostic approximation; they are not certified ellipsoidal geodesic minima.'
                  ],
                  'strict_feasibility': {'positive_population_component_count':sum(p>0 for p in populations),
                                        'minimum_required_districts':len(rows),
                                        'reason':'Every physical source component, including zero-population coverage, needs its own district under strict connectivity.'},
                  'distance_model': {'candidate_search':'Per-pair local equirectangular nearest boundary points.',
                                     'reported_length':'Spherical great-circle length between candidate endpoints.',
                                     'earth_radius_m':EARTH_RADIUS_M, 'certified_geodesic_minimum':False,
                                     'all_endpoints_verified_on_original_source_parts':True,
                                     'meaning':'Gaps between included census coverage, not coastline distance, bridges or ferry routes.'},
                  'policy': {'name':'undersized-component-rooted-nearest-boundary-forest-v1',
                             'minimum_population_fraction':.99, 'root_to_root_connections':False,
                             'root_eligibility_fixed_before_attachment':True,
                             'source_geometry_modified':False,
                             'adapter_status':'Hawaii diagnostic only; production RI adapter is unchanged and remains RI-only.'},
                  'map_simplification_degrees':.0005, 'independent_dissolved_polygon_check_passed':True,
                  'preservation':{'original_strict_files_byte_identical':True,'national_suite_byte_identical':True,
                                  'source_archive_byte_identical':True},
                  'code_sha256':{str(Path(__file__).relative_to(ROOT)).replace('\\','/'):sha256(Path(__file__)),
                                'scripts/district_block_part_graph.py':sha256(ROOT/'scripts/district_block_part_graph.py'),
                                'scripts/district_block_island_links.py':sha256(ROOT/'scripts/district_block_island_links.py')},
                  'artifact_sha256':{name:sha256(OUTPUT/name) for name in ('components.geojson','links.geojson','preserved-file-inventory.json')},
                  'elapsed_seconds':time.perf_counter()-started}
        write_json(OUTPUT/'diagnosis.json', report)
        print(json.dumps({'plans':plans, 'elapsed_seconds':report['elapsed_seconds']}), flush=True)
        return report
    finally:
        measure.close()


if __name__ == '__main__':
    run()
