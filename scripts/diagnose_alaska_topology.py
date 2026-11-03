"""Audit an Alaska-only longitude frame and proposed island connections.

No district optimization, historical mutation, polygon repair or rounding.
The unwrapped GeoJSON is an internal diagnostic view, not an RFC 7946 export.
"""
from __future__ import annotations

import json
import math
from numbers import Integral
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import shapely
from shapely.affinity import affine_transform, translate
from shapely.geometry import LineString, Point, mapping
from shapely.ops import nearest_points

from scripts.alaska_geometry import load_normalized_parts, build_exact_part_graph
from scripts.benchmark_kansas_blocks import process_memory
from scripts.diagnose_hawaii_topology import components, great_circle_m
from scripts.district_block_sources import sha256
from scripts.hawaii_population_links import select_population_aware_forest, population_allocation_bound
from scripts.state_block_execution_lock import state_execution_lock

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'diagnostics/alaska'
ARCHIVE = ROOT / '.cache/state-block-benchmark/source/02/tl_2020_02_tabblock20.zip'
EXPECTED_SHA = '6fe96f3a8bbaf78945ee3a3897264ed74f1b72bc0cb46ffd434039729dccf493'


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def inventory() -> dict[str, str]:
    paths = [SUITE/'suite.json', ARCHIVE, ARCHIVE.with_suffix('.manifest.json')]
    paths.extend(p for p in (SUITE/'states/02').rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(set(paths))}


def single_group_forest(populations: list[int], links: list[dict], k: int) -> dict:
    """Exact one-root/no-root specialization of the existing bounded policy.

Original undersized components cannot become protected roots. With at most
one eligible root, all components must join one group. Kruskal then gives the
minimum spanning tree on these permitted candidates; no grouping enumeration
is needed. This is not a globally shortest geodesic/Steiner tree guarantee.
"""
    if (isinstance(k, bool) or not isinstance(k, Integral) or k < 1
            or not populations or any(isinstance(p, bool) or not isinstance(p, Integral) or p < 0 for p in populations)):
        raise ValueError('Invalid population or district count.')
    populations = list(map(int, populations))
    k = int(k)
    total = sum(populations)
    if total <= 0:
        raise ValueError('Invalid population or district count.')
    roots = [i for i,p in enumerate(populations) if p*k*100 >= 99*total]
    if len(roots) > 1:
        raise ValueError('Multiple eligible roots require the general population-aware search.')
    parents = list(range(len(populations)))
    def find(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    candidates, pairs, ids = [], set(), set()
    for link in links:
        if not isinstance(link, dict):
            raise ValueError('Invalid/duplicate candidate.')
        pair_values, distance, identifier = link.get('component_ids'), link.get('distance_m'), link.get('id')
        if (not isinstance(pair_values, (list, tuple)) or len(pair_values) != 2
                or any(isinstance(i, bool) or not isinstance(i, Integral) for i in pair_values)
                or isinstance(distance, bool) or not isinstance(distance, (int, float))
                or not math.isfinite(distance) or distance <= 0
                or not isinstance(identifier, str) or not identifier):
            raise ValueError('Invalid/duplicate candidate.')
        a,b = pair_values
        pair = tuple(sorted((a,b)))
        if (a == b or min(pair)<0 or max(pair)>=len(populations) or pair in pairs
                or identifier in ids):
            raise ValueError('Invalid/duplicate candidate.')
        pairs.add(pair); ids.add(identifier)
        candidates.append(link)
    selected = []
    for link in sorted(candidates, key=lambda r:(r['distance_m'],*sorted(r['component_ids']),r['id'])):
        a,b = link['component_ids']
        x,y = find(a),find(b)
        if x != y:
            parents[y] = x
            selected.append(link)
    if len({find(i) for i in range(len(populations))}) != 1:
        raise ValueError('Permitted candidates cannot connect all coverage components.')
    return {'policy':'population-aware-rooted-boundary-forest-v1',
        'implementation':'single-group Kruskal specialization; same root eligibility and grouping semantics',
        'eligible_root_component_ids':roots, 'no_individual_root_fallback':not bool(roots),
        'selected_link_ids':[r['id'] for r in selected],
        'selected_total_distance_m':math.fsum(r['distance_m'] for r in selected),
        'groups':[{'component_ids':list(range(len(populations))), 'population':total,'district_count':k}],
        'population_bound':population_allocation_bound([total],k),
        'is_constructed_plan':False}


def source_population_accounting(records: list[dict], component_rows: list[dict], spanning: list[dict]) -> dict:
    """Retain whole-block totals when multipart ownership prevents attribution."""
    source = {row['geoid']:row['population'] for row in records}
    if len(source) != len(records):
        raise ValueError('Duplicate source records in population reconciliation.')
    unresolved = {row['geoid']:row['population'] for row in spanning}
    if len(unresolved) != len(spanning) or any(geoid not in source or source[geoid] != pop for geoid,pop in unresolved.items()):
        raise ValueError('Spanning-block population differs from source records.')
    total, allocated, ambiguous = sum(source.values()), sum(row['population'] for row in component_rows), sum(unresolved.values())
    allocated_blocks = sum(row['block_count'] for row in component_rows)
    if allocated + ambiguous != total or allocated_blocks + len(spanning) != len(records):
        raise ValueError('Component and spanning-block totals do not reconcile to the source.')
    return {'source_total_population':total,'source_block_count':len(records),
            'component_attributed_population':allocated,'component_attributed_block_count':allocated_blocks,
            'unattributed_spanning_block_population':ambiguous,'spanning_block_count':len(spanning),
            'component_population_totals_complete':not bool(spanning),
            'whole_block_population_counted_once':True}


def run() -> dict:
    with state_execution_lock('02'):
        return _run()


def _run() -> dict:
    started = time.perf_counter()
    if OUTPUT.exists():
        raise FileExistsError('Refusing to replace an existing Alaska diagnosis.')
    before = inventory()
    if sha256(ARCHIVE) != EXPECTED_SHA:
        raise ValueError('Original Alaska archive identity changed.')
    OUTPUT.mkdir(parents=True)
    write_json(OUTPUT/'preserved-file-inventory.json', before)
    try:
        print('Loading and validating original and normalized Alaska polygon parts.',flush=True)
        parts, records, owners, part_indices, normalization = load_normalized_parts(ARCHIVE)
        if len(records)!=28568 or sum(r['population'] for r in records)!=733391:
            raise ValueError('Alaska block/resident totals differ from official 2020 source totals.')
        raw_parts, raw_records, raw_owners, raw_indices, _ = load_normalized_parts(ARCHIVE, normalize=False)
        if (raw_owners != owners or raw_indices != part_indices or
                [(r['geoid'],r['population']) for r in raw_records] != [(r['geoid'],r['population']) for r in records]):
            raise ValueError('Independent original-source load changed block/part identity.')
        print('Building exact shared-edge graph in the continuous Alaska frame.',flush=True)
        graph, graph_metadata = build_exact_part_graph(parts,owners)
        print('Independently comparing original-coordinate and normalized adjacency.',flush=True)
        raw_graph, raw_metadata = build_exact_part_graph(raw_parts,owners)
        if raw_graph.adjacency != graph.adjacency or raw_graph.part_to_unit != graph.part_to_unit:
            raise ValueError('Longitude translation changed adjacency/ownership; inspect before proceeding.')
        groups, membership = components(graph.adjacency)
        members_by_group = [[] for _ in groups]
        spanning=[]
        for unit,nodes in enumerate(graph.unit_to_parts):
            group_ids=sorted({membership[n] for n in nodes})
            if len(group_ids)!=1:
                spanning.append({'geoid':records[unit]['geoid'],'population':records[unit]['population'],'component_ids':group_ids})
            else:
                members_by_group[group_ids[0]].append(unit)
        rows=[]
        for i,nodes in enumerate(groups):
            units=members_by_group[i]
            rows.append({'id':i,'label':'Main Alaska census coverage' if i==0 else f'Alaska coverage component {i}',
                'population':sum(records[u]['population'] for u in units),'block_count':len(units),'part_count':len(nodes),
                'bounds':list(map(float,shapely.total_bounds([parts[n] for n in nodes]))),
                'county_fips':sorted({records[u]['geoid'][2:5] for u in units}),
                'zero_population_block_count':sum(records[u]['population']==0 for u in units),
                'water_only_block_count':sum(records[u]['land_area_m2']==0 and records[u]['water_area_m2']>0 for u in units),
                'land_area_m2':sum(records[u]['land_area_m2'] for u in units),
                'water_area_m2':sum(records[u]['water_area_m2'] for u in units),
                'example_geoids':[records[u]['geoid'] for u in units[:5]]})
        population_accounting = source_population_accounting(records, rows, spanning)
        write_json(OUTPUT/'initial-components.json',{'components':rows,'blocks_spanning_components':spanning,
                                                    'population_accounting':population_accounting})
        print(json.dumps({'component_count':len(rows),'components':rows,'spanning_blocks':spanning}),flush=True)
        print('Dissolving exact physical components and testing candidate boundary links.',flush=True)
        dissolved=[]
        for i,nodes in enumerate(groups):
            geometry=shapely.coverage_union_all([parts[n] for n in nodes])
            if not geometry.is_valid or geometry.geom_type!='Polygon':
                raise ValueError(f'Component {i} failed independent unsimplified polygon validation.')
            dissolved.append(geometry)
            p=geometry.representative_point()
            rows[i]['representative_point']=[p.x,p.y]
        tree=shapely.STRtree(parts)
        def endpoint(p: Point, component: int) -> dict:
            options=[int(n) for n in tree.query(p.buffer(1e-9).envelope)
                     if membership[int(n)]==component and parts[int(n)].boundary.distance(p)<=1e-9]
            if not options:
                raise ValueError('Candidate endpoint did not recover a source polygon part.')
            n=min(options,key=lambda n:(records[owners[n]]['geoid'],part_indices[n]))
            vertices=shapely.get_coordinates(parts[n].boundary)
            distances=np.hypot(vertices[:,0]-p.x,vertices[:,1]-p.y)
            idx=int(np.argmin(distances))
            p=Point(vertices[idx]) if distances[idx]<=1e-9 else nearest_points(parts[n].boundary,p)[0]
            raw=Point(p.x-records[owners[n]]['longitude_offset_degrees'],p.y)
            error=raw_parts[n].boundary.distance(raw)
            if error>1e-9:
                raise ValueError('Unwrapped candidate endpoint does not map to an original source boundary.')
            return {'geoid':records[owners[n]]['geoid'],'part_node':n,'part_index':part_indices[n],
                'coordinate':[p.x,p.y],'source_coordinate':[raw.x,raw.y],
                'source_boundary_error_degrees':error}
        links=[]
        for a in range(len(groups)):
            for b in range(a+1,len(groups)):
                bounds=shapely.total_bounds([dissolved[a],dissolved[b]])
                lon0,lat0=(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2
                ys=6371000*math.pi/180; xs=ys*math.cos(math.radians(lat0))
                projected=[affine_transform(dissolved[i],[xs,0,0,ys,-lon0*xs,-lat0*ys]) for i in (a,b)]
                p,q=nearest_points(projected[0].boundary,projected[1].boundary)
                ends=[endpoint(Point(p.x/xs+lon0,p.y/ys+lat0),a),endpoint(Point(q.x/xs+lon0,q.y/ys+lat0),b)]
                line=LineString([end['coordinate'] for end in ends])
                others=[i for i,g in enumerate(dissolved) if i not in (a,b) and line.relate(g)[0]!='F']
                own=[i for i in (a,b) if line.intersection(dissolved[i]).difference(dissolved[i].boundary).length>1e-10]
                touching=dissolved[a].intersects(dissolved[b])
                distance=great_circle_m(ends[0]['coordinate'],ends[1]['coordinate'])
                links.append({'id':f'ak-candidate-{a:02d}-{b:02d}','component_ids':[a,b],
                    'distance_m':distance,'endpoints':ends,'selected_k':[],
                    'eligible_positive_gap':not touching and distance>0 and not others and not own,
                    'source_boundaries_intersect':touching,'intervening_component_ids':others,
                    'endpoint_component_interior_crossings':own,
                    'classification':'geometric candidate; geographic water attribution not certified',
                    'projection':{'kind':'pair-local-equirectangular','lon0':float(lon0),'lat0':float(lat0)}})
            print(f'Candidate pairs through component {a}: {len(links)}',flush=True)
        suite=json.loads((SUITE/'suite.json').read_text(encoding='utf-8'))
        jobs=next(s for s in suite['states'] if s['state_fips']=='02')['jobs']
        pops=[r['population'] for r in rows]
        plans=[]
        for job in jobs:
            k=job['district_count']
            plan={'district_count':k,'house_sizes':job['house_sizes'],'actual_district_plan_generated':False,
                'selected_link_ids':[],
                'strict_population_bound':None if spanning else population_allocation_bound(pops,k),
                'strict_population_bound_status':'unavailable: whole-block population spans physical components' if spanning else 'available'}
            if spanning:
                plan['policy_status']='blocked: whole-block ownership spans physical components'
            else:
                permitted=[r for r in links if r['eligible_positive_gap']]
                roots=[i for i,p in enumerate(pops) if p*k*100>=99*sum(pops)]
                policy=single_group_forest(pops,permitted,k) if len(roots)<=1 else select_population_aware_forest(pops,permitted,k)
                plan.update(policy=policy,policy_status='geometric_candidate_forest',
                    selected_link_ids=policy['selected_link_ids'],augmented_component_count=len(policy['groups']),
                    policy_population_bound=policy['population_bound'])
                extra={}
                for link in links:
                    if link['id'] not in plan['selected_link_ids']:
                        continue
                    link['selected_k'].append(k)
                    x,y=[end['part_node'] for end in link['endpoints']]
                    extra.setdefault(x,[]).append(y); extra.setdefault(y,[]).append(x)
                augmented=tuple(tuple(sorted((*neighbors,*extra.get(n,[])))) for n,neighbors in enumerate(graph.adjacency))
                augmented_groups,_=components(augmented)
                if len(augmented_groups)!=len(policy['groups']):
                    raise ValueError('Independent augmented source-graph traversal failed.')
                plan['independent_augmented_graph_validation']={'component_count':len(augmented_groups),'parts_reached':sum(map(len,augmented_groups))}
            plans.append(plan)
        write_json(OUTPUT/'components.geojson',{'type':'FeatureCollection','features':[
            {'type':'Feature','properties':r,'geometry':mapping(shapely.simplify(g,.002,preserve_topology=True))}
            for r,g in zip(rows,dissolved,strict=True)]})
        write_json(OUTPUT/'candidates.geojson',{'type':'FeatureCollection','features':[
            {'type':'Feature','properties':{'id':r['id'],'selected_k':r['selected_k'],'eligible':r['eligible_positive_gap']},
             'geometry':mapping(LineString([end['coordinate'] for end in r['endpoints']]))} for r in links]})
        write_json(OUTPUT/'candidate-links.json',links)
        if inventory()!=before:
            raise ValueError('Original historical/source evidence changed.')
        report={'state_fips':'02','state':'Alaska','status':'diagnosis_complete','source':{
                'archive_sha256':EXPECTED_SHA,'block_count':len(records),'total_population':population_accounting['source_total_population'],
                'part_count':len(parts),'zero_population_block_count':sum(r['population']==0 for r in records)},
            'normalization':normalization,'graph':graph_metadata,'original_frame_graph':raw_metadata,
            'original_and_normalized_edges_identical':True,'synthetic_ownership_edges':False,
            'blocks_spanning_components':spanning,'components':rows,'links':links,'plans':plans,
            'population_accounting':population_accounting,
            'independent_full_polygon_validation':True,'actual_district_plan_generated':False,
            'preservation':{'original_files_byte_identical':True,'preserved_file_count':len(before)},
            'distance_model':'Nearest boundaries in a pair-local equirectangular plane; reported spherical endpoint distance, not certified shortest geodesic.',
            'limitations':['Candidate lines were checked against Alaska source interiors, not foreign land or a global land mask.',
                'An augmented source graph is not a solved connected balanced district plan.',
                'Normalized diagnostic coordinates can fall below -180; production export needs explicit wrap/split handling.',
                'Display outlines are simplified; all topology and endpoints use unsimplified source parts.'],
            'elapsed_seconds':time.perf_counter()-started,'peak_process_working_set_bytes':process_memory()[1],
            'code_sha256':{name:sha256(ROOT/name) for name in ('scripts/diagnose_alaska_topology.py','scripts/alaska_geometry.py','scripts/hawaii_population_links.py')},
            'artifact_sha256':{name:sha256(OUTPUT/name) for name in ('components.geojson','candidates.geojson','candidate-links.json','preserved-file-inventory.json')}}
        write_json(OUTPUT/'diagnosis.json',report)
        print(json.dumps({'status':report['status'],'components':len(rows),'plans':plans,'seconds':report['elapsed_seconds']}),flush=True)
        return report
    except Exception as error:
        write_json(OUTPUT/'failure.json',{'error':f'{type(error).__name__}: {error}',
            'preservation_unchanged':inventory()==before,'no_district_optimizer_ran':True})
        raise


if __name__=='__main__':
    run()
