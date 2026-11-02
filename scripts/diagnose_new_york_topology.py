"""Diagnose exact New York polygon components and recorded-link feasibility.

Read-only with respect to historical runs and numerical/policy code. This does
not solve district plans. Approximate visual simplification is separate from
exact topology and exact source part endpoints used for every candidate.
"""
from __future__ import annotations

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
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import nearest_points

from scripts.benchmark_kansas_blocks import Measurements
from scripts.diagnose_hawaii_topology import components, great_circle_m
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import load_units, prepare_source, sha256
from scripts.hawaii_population_links import population_allocation_bound, select_population_aware_forest
from scripts.state_block_execution_lock import state_execution_lock

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'diagnostics/new-york'
EARTH_RADIUS_M = 6_371_000.0


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def inventory() -> dict[str, str]:
    paths = [SUITE/'suite.json', ROOT/'.cache/state-block-benchmark/source/36/tl_2020_36_tabblock20.zip']
    paths.extend(path for path in (SUITE/'states/36').rglob('*') if path.is_file())
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(paths)}


def run() -> dict[str, Any]:
    with state_execution_lock('36'):
        return _run_locked()


def _run_locked() -> dict[str, Any]:
    started = time.perf_counter()
    before = inventory()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT/'diagnosis.json').exists():
        raise FileExistsError('Refusing to overwrite a completed diagnosis.')
    write_json(OUTPUT/'preserved-file-inventory.json', before)
    measure = Measurements()
    try:
        source, source_metadata = prepare_source('36', ROOT/'.cache/state-block-benchmark/source/36', measure)
        units, population_map, input_metadata = load_units(source, '36')
        geoids = [u.geoid for u in units]
        print('Building or validating exact polygon-part graph.', flush=True)
        graph, graph_metadata, cache = load_or_build_shared_edge_part_graph(
            source, geoids, source_sha256=source_metadata['archive_sha256'],
            cache_dir=ROOT/'.cache/state-block-benchmark/graph-cache/36')
        if graph_metadata['interior_overlap_pair_count']:
            raise ValueError('Source parts overlap.')
        groups, membership = components(graph.adjacency)
        print(json.dumps({'part_component_sizes':list(map(len,groups))}), flush=True)
        by_geoid = {}
        with shapefile.Reader(str(source)) as reader:
            for item in reader.iterShapeRecords():
                geoid = str(item.record['GEOID20'])
                if geoid in by_geoid:
                    raise ValueError('Duplicate source GEOID.')
                by_geoid[geoid] = (shape(item.shape.__geo_interface__), item.record.as_dict())
        if set(by_geoid) != set(geoids):
            raise ValueError('Source graph population ordering mismatch.')
        parts, records, source_part_indices = [], [], []
        for unit, geoid in enumerate(geoids):
            geometry, record = by_geoid[geoid]
            unit_parts = list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]
            nodes = tuple(range(len(parts),len(parts)+len(unit_parts)))
            if tuple(graph.unit_to_parts[unit]) != nodes:
                raise ValueError('Source part order differs from cached part graph.')
            if any(graph.part_to_unit[node] != unit for node in nodes):
                raise ValueError('Source part ownership differs from cached part graph.')
            parts.extend(unit_parts)
            source_part_indices.extend(range(len(unit_parts)))
            records.append(record)
        del by_geoid
        if len(parts) != len(graph.adjacency):
            raise ValueError('Source part count mismatch.')
        spanning, block_groups = [], [[] for _ in groups]
        for unit, nodes in enumerate(graph.unit_to_parts):
            owners = {membership[node] for node in nodes}
            if len(owners) != 1:
                spanning.append({'geoid': geoids[unit], 'population':units[unit].population,'component_ids':sorted(owners)})
            else:
                block_groups[owners.pop()].append(unit)
        rows = []
        for i,members in enumerate(block_groups):
            bounds = list(map(float, shapely.total_bounds([parts[n] for n in groups[i]])))
            rows.append({'id':i,'label': 'Main New York coverage' if i==0 else f'Detached New York component {i}',
                'population':sum(units[u].population for u in members),'block_count':len(members),
                'part_count':len(groups[i]),'water_only_block_count':sum(records[u]['ALAND20']==0 and records[u]['AWATER20']>0 for u in members),
                'zero_population_block_count':sum(units[u].population==0 for u in members),
                'land_area_m2':sum(records[u]['ALAND20'] for u in members),'water_area_m2':sum(records[u]['AWATER20'] for u in members),
                'bounds':bounds,'county_fips':sorted({geoids[u][2:5] for u in members}),
                'example_geoids':[geoids[u] for u in members[:5]],
                'population_definition':'Whole-block population, only blocks exclusively owned by this physical component.'})
        write_json(OUTPUT/'initial-components.json',{'components':rows,'blocks_spanning_components':spanning})
        print(json.dumps({'components':rows,'blocks_spanning_components':spanning}),flush=True)
        if any(row['population'] > 0 for row in spanning):
            raise ValueError('Positive-population cross-component whole-block ownership needs explicit treatment; see initial-components.json.')
        if sum(row['population'] for row in rows) != input_metadata['total_population']:
            raise ValueError('Component populations do not partition source.')
        print('Dissolving exact source component polygons.',flush=True)
        component_geometries = []
        for i,nodes in enumerate(groups):
            # Parts have verified nonoverlapping interiors and exact edge coverage.
            geometry = shapely.coverage_union_all([parts[n] for n in nodes])
            if not geometry.is_valid or geometry.geom_type != 'Polygon':
                raise ValueError(f'Component {i} does not dissolve to a valid single Polygon: {geometry.geom_type}.')
            component_geometries.append(geometry)
            point = geometry.representative_point()
            rows[i].update(representative_point=[point.x,point.y],polygon_component_count=1)
        def endpoint(point: Point, component: int) -> dict[str, Any]:
            candidates = [n for n in groups[component] if parts[n].boundary.distance(point) <= 1e-9]
            if not candidates:
                raise ValueError('Candidate endpoint is not on an original source boundary.')
            node = min(candidates,key=lambda n:(geoids[graph.part_to_unit[n]],source_part_indices[n]))
            vertices=shapely.get_coordinates(parts[node].boundary)
            distances=np.hypot(vertices[:,0]-point.x,vertices[:,1]-point.y)
            nearest=int(np.argmin(distances))
            if distances[nearest] <= 1e-9:
                point=Point(vertices[nearest])
                method='Exact original boundary vertex, within inverse-projection roundoff tolerance.'
            else:
                point=nearest_points(parts[node].boundary,point)[0]
                method='Nearest point on unchanged original boundary segment after inverse projection.'
            return {'geoid':geoids[graph.part_to_unit[node]],'part_node':node,'part_index':source_part_indices[node],
                'coordinate':[point.x,point.y],'source_boundary_error_degrees':parts[node].boundary.distance(point),
                'endpoint_recovery':method}
        links = []
        for a in range(len(groups)):
            for b in range(a+1,len(groups)):
                pair_bounds=shapely.total_bounds([component_geometries[a],component_geometries[b]])
                lon0,lat0=(pair_bounds[0]+pair_bounds[2])/2,(pair_bounds[1]+pair_bounds[3])/2
                ys=EARTH_RADIUS_M*math.pi/180
                xs=ys*math.cos(math.radians(lat0))
                projected=[affine_transform(component_geometries[i],[xs,0,0,ys,-lon0*xs,-lat0*ys]) for i in (a,b)]
                p,q=nearest_points(projected[0].boundary,projected[1].boundary)
                ends=[endpoint(Point(point.x/xs+lon0,point.y/ys+lat0),component) for point,component in ((p,a),(q,b))]
                line=LineString([end['coordinate'] for end in ends])
                touching=component_geometries[a].intersects(component_geometries[b])
                distance=great_circle_m(ends[0]['coordinate'],ends[1]['coordinate'])
                intervening=[i for i,g in enumerate(component_geometries) if i not in (a,b) and line.relate(g)[0] != 'F']
                own_lengths={i:line.intersection(component_geometries[i]).difference(component_geometries[i].boundary).length for i in (a,b)}
                own_interior=[i for i,length in own_lengths.items() if length > 1e-10]
                links.append({'id':f'ny-candidate-{a:02d}-{b:02d}','component_ids':[a,b],
                    'distance_m':distance,'planar_candidate_distance_m':p.distance(q),'endpoints':ends,
                    'selected_k':[],'classification':'point_contact' if touching else 'positive_gap',
                    'source_boundaries_intersect':touching,'exact_geographic_distance_degrees':component_geometries[a].distance(component_geometries[b]),
                    'intervening_component_ids':intervening,'endpoint_component_interior_crossings':own_interior,
                    'endpoint_interior_intersection_length_degrees':own_lengths,
                    'computed_line_intersection_roundoff_tolerance_degrees':1e-10,
                    'eligible_positive_gap':not touching and distance>0 and not intervening and not own_interior,
                    'projection':{'kind':'per-pair-bbox-centered-equirectangular','lon0':lon0,'lat0':lat0}})
        write_json(OUTPUT/'candidate-links.json',links)
        print(json.dumps({'candidate_links':links}),flush=True)
        suite=json.loads((SUITE/'suite.json').read_text(encoding='utf-8'))
        state=next(state for state in suite['states'] if state['state_fips']=='36')
        anchors={job['district_count']:job['house_sizes'] for job in state['jobs']}
        populations=[row['population'] for row in rows]
        plans=[]
        for k in sorted(anchors):
            policy=select_population_aware_forest(populations,[link for link in links if link['eligible_positive_gap']],k)
            selected=policy['selected_link_ids']
            plans.append({'district_count':k,'house_sizes':anchors[k],'ideal_population':sum(populations)/k,
                'strict_population_bound':population_allocation_bound(populations,k),
                'policy_population_bound':policy['population_bound'],'selected_link_ids':selected,
                'augmented_component_count':len(policy['groups']),'policy':policy,'actual_district_plan_generated':False})
            for link in links:
                if link['id'] in selected:
                    link['selected_k'].append(k)
        augmented_validations={}
        for plan in plans:
            key=tuple(plan['selected_link_ids'])
            if key not in augmented_validations:
                augmented=[set(row) for row in graph.adjacency]
                pairs=[]
                for link in links:
                    if link['id'] in key:
                        a,b=[end['part_node'] for end in link['endpoints']]
                        augmented[a].add(b)
                        augmented[b].add(a)
                        pairs.append([a,b])
                augmented_groups,_=components(tuple(tuple(sorted(row)) for row in augmented))
                augmented_validations[key]={'independent_full_graph_traversal':True,
                    'node_count':len(graph.adjacency),'physical_component_count':len(groups),
                    'augmented_component_count':len(augmented_groups),'component_sizes':list(map(len,augmented_groups)),
                    'inserted_part_edge_pairs':pairs,'all_source_parts_reached':len(augmented_groups)==1,
                    'physical_adjacency_modified':False}
                if len(augmented_groups)!=len(plan['policy']['groups']):
                    raise ValueError('Augmented graph traversal disagrees with policy groups.')
            plan['augmented_graph_validation']=augmented_validations[key]
        # Replace the pre-selection progress snapshot with the final annotations.
        write_json(OUTPUT/'candidate-links.json',links)
        features=[]
        for row,geometry in zip(rows,component_geometries,strict=True):
            # Detached components retain source vertices. National extent uses display-only simplification.
            simplified=geometry.simplify(.00025,preserve_topology=True) if row['id']==0 else geometry
            features.append({'type':'Feature','properties':{'component_id':row['id'],**row},'geometry':mapping(simplified)})
        write_json(OUTPUT/'components.geojson',{'type':'FeatureCollection','features':features})
        write_json(OUTPUT/'candidates.geojson',{'type':'FeatureCollection','features':[
            {'type':'Feature','properties':{key:link[key] for key in ('id','component_ids','distance_m','selected_k','classification','eligible_positive_gap')},
             'geometry':{'type':'LineString','coordinates':[end['coordinate'] for end in link['endpoints']]}} for link in links]})
        # Exact detached blocks plus nearest endpoint neighbors for inspection.
        detail_nodes=set(n for group in groups[1:] for n in group)
        for link in links:
            for end in link['endpoints']:
                node=end['part_node']
                detail_nodes.add(node)
                detail_nodes.update(graph.adjacency[node])
        detail=[]
        for node in sorted(detail_nodes):
            unit=graph.part_to_unit[node]
            detail.append({'type':'Feature','properties':{'geoid':geoids[unit],'part_node':node,
                'part_index':source_part_indices[node],'component_id':membership[node],
                'population':units[unit].population,'land_area_m2':records[unit]['ALAND20'],'water_area_m2':records[unit]['AWATER20']},
                'geometry':mapping(parts[node])})
        write_json(OUTPUT/'detail-blocks.geojson',{'type':'FeatureCollection','features':detail})
        originals=[]
        baseline=json.loads((SUITE/'states/36/districts-26/benchmark.json').read_text(encoding='utf-8'))
        for job in state['jobs']:
            k=job['district_count']
            path=SUITE/f'states/36/districts-{k}/benchmark.json'
            old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
            originals.append({'district_count':k,'house_sizes':anchors[k],
                'status':old['status'] if old else job['status'],
                'unsupported_reason':old['unsupported_reason'] if old else baseline['unsupported_reason'],
                'source_components':baseline['source_components'],
                'elapsed_seconds':old['timed_pipeline_wall_seconds'] if old else None,
                'path':path.relative_to(SUITE).as_posix() if old else None,
                'individual_report_exists':old is not None,
                'reused_topology_exception':old is None,
                'suite_job':job})
        after=inventory()
        if before!=after:
            raise ValueError('Historical evidence or source archive changed.')
        report={'schema_version':1,'state':'New York','state_fips':'36','status':'diagnostic_complete_no_district_plans_generated',
            'total_population':sum(populations),'block_count':len(units),'part_count':len(parts),
            'physical_component_count':len(rows),'original_whole_block_component_count':originals[0]['unsupported_reason']['component_count'],
            'source':source_metadata,'input':input_metadata,'part_graph':graph_metadata,'part_graph_cache':cache,
            'components':rows,'links':links,'plans':plans,'original_runs':originals,'blocks_spanning_components':spanning,
            'population_assignment_ambiguity': {'positive_population_blocks_spanning_components': sum(row['population'] > 0 for row in spanning), 'zero_population_blocks_spanning_components': sum(row['population'] == 0 for row in spanning), 'area_weighted_population_estimates_used': False},
            'strict_feasibility':{'positive_population_component_count':sum(p>0 for p in populations),'minimum_required_districts':len(rows),
                'interpretation':'Every physical source component requires one or more districts under exact shared-edge connectivity; population bounds assume divisible population and ignore whole-block/internal geometry.'},
            'policy':{'name':'population-aware-rooted-boundary-forest-v1','population_tolerance':.01,
                'source_geometry_modified':False,'adapter_status':'Analytical selector reused unchanged; New York benchmark adapter not implemented; no district plans generated.'},
            'distance_model':{'candidate_search':'Per-pair bounding-box-centered equirectangular nearest boundary points.',
                'reported_length':'Spherical great-circle distance between candidate endpoints.','earth_radius_m':EARTH_RADIUS_M,
                'certified_geodesic_minimum':False,'all_endpoints_verified_on_original_source_parts':True,
                'meaning':'Distances between included census-coverage boundaries, not shoreline distances, bridges, or ferry routes.'},
            'independent_dissolved_polygon_check_passed':True,'map_simplification_degrees':.00025,
            'limitations':['Connected augmented source graph does not guarantee a balanced whole-block connected district partition.',
                'A recorded connection supports a district only if both exact endpoint blocks share that district.',
                'No optimizer, repair, district polygon validation, or district maps ran in this diagnosis.',
                'Positive gap does not by itself establish that its path is exclusively water; geography requires separately attributed context.'],
            'preservation':{'original_strict_files_byte_identical':True,'national_suite_byte_identical':True,'source_archive_byte_identical':True,'preserved_file_count':len(before)},
            'code_sha256':{name:sha256(ROOT/name) for name in ('scripts/diagnose_new_york_topology.py','scripts/district_block_part_graph.py','scripts/hawaii_population_links.py')},
            'artifact_sha256':{name:sha256(OUTPUT/name) for name in ('components.geojson','candidates.geojson','candidate-links.json','detail-blocks.geojson','preserved-file-inventory.json')},
            'elapsed_seconds':time.perf_counter()-started}
        report['analysis_seconds']=report['elapsed_seconds']
        write_json(OUTPUT/'diagnosis.json',report)
        print(json.dumps({'links':links,'plans':plans,'elapsed_seconds':report['elapsed_seconds']}),flush=True)
        return report
    finally:
        measure.close()


if __name__=='__main__':
    run()
