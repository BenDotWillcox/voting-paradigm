"""Source-pinned Alaska connections in a continuous longitude frame.

The source shape and whole-block populations stay unchanged. Geographic
attribution uses the preserved official regional maps; it is not a global
land-mask, foreign-territory, navigability or shortest-geodesic certificate.
"""
from __future__ import annotations

from collections.abc import Sequence
import copy
import hashlib
import json
import math
from numbers import Integral
from pathlib import Path
import time
from typing import Any

import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, Point

from districting.part_connectivity import PartGraph
from scripts import alaska_geometry
from scripts import diagnose_alaska_topology as diagnosis_helpers
from scripts import district_block_island_links as physical_helpers
from scripts.hawaii_population_links import _great_circle_m

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSTIC_DIR = ROOT / '.cache/state-block-benchmark/suite-through-1000/diagnostics/alaska'
SOURCE_ARCHIVE_PATH = ROOT / '.cache/state-block-benchmark/source/02/tl_2020_02_tabblock20.zip'
SOURCE_ARCHIVE_SHA256 = '6fe96f3a8bbaf78945ee3a3897264ed74f1b72bc0cb46ffd434039729dccf493'
POLICY = 'alaska-recorded-water-v1'
SUPPORTED_DISTRICT_COUNTS = (1, 2)
EXPECTED_BLOCKS, EXPECTED_PARTS, EXPECTED_POPULATION = 28_568, 28_706, 733_391
EXPECTED_COMPONENT_COUNT = 50
PINNED_EVIDENCE_SHA256 = {
    'diagnosis.json': 'a4b061ff4771cb739e5c7e8369b9d6da6f4c84f5de2014e9ad7d4e07c94b37a4',
    'candidate-links.json': '7b05a8bff15257f3c14911c569f3b7373dfed231410cc1c499bdd91254c5f03a',
    'geography-context.json': '40f19de7556c1ad4de292dc13f4dd27e95cc6507169884b487d3a5f06b3b6c78',
}
AUTHORIZED_CANDIDATE_IDS = (
    'ak-candidate-03-26', 'ak-candidate-06-42', 'ak-candidate-00-27', 'ak-candidate-00-24',
    'ak-candidate-10-37', 'ak-candidate-45-48', 'ak-candidate-19-34', 'ak-candidate-16-48',
    'ak-candidate-00-46', 'ak-candidate-00-21', 'ak-candidate-44-47', 'ak-candidate-00-08',
    'ak-candidate-18-20', 'ak-candidate-24-40', 'ak-candidate-00-15', 'ak-candidate-03-39',
    'ak-candidate-00-35', 'ak-candidate-00-38', 'ak-candidate-18-28', 'ak-candidate-09-48',
    'ak-candidate-00-29', 'ak-candidate-00-02', 'ak-candidate-10-45', 'ak-candidate-17-23',
    'ak-candidate-18-22', 'ak-candidate-03-49', 'ak-candidate-01-15', 'ak-candidate-00-13',
    'ak-candidate-03-20', 'ak-candidate-07-14', 'ak-candidate-03-25', 'ak-candidate-12-23',
    'ak-candidate-14-36', 'ak-candidate-00-04', 'ak-candidate-02-12', 'ak-candidate-00-47',
    'ak-candidate-02-43', 'ak-candidate-09-32', 'ak-candidate-00-31', 'ak-candidate-06-11',
    'ak-candidate-13-41', 'ak-candidate-17-25', 'ak-candidate-00-33', 'ak-candidate-18-32',
    'ak-candidate-30-37', 'ak-candidate-14-30', 'ak-candidate-05-31', 'ak-candidate-04-19',
    'ak-candidate-11-43',
)
_ENDPOINT_TOLERANCE_DEGREES = 1e-9
_INTERIOR_ROUNDOFF_TOLERANCE_DEGREES = 1e-10


def _sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _verified_source() -> tuple:
    """Independently reload source, instead of trusting caller-supplied arrays."""
    if _sha256(SOURCE_ARCHIVE_PATH) != SOURCE_ARCHIVE_SHA256:
        raise ValueError('Alaska source archive differs from the authorized source.')
    loaded = alaska_geometry.load_normalized_parts(SOURCE_ARCHIVE_PATH)
    if loaded[4]['source_archive_sha256'] != SOURCE_ARCHIVE_SHA256:
        raise ValueError('Alaska source archive changed during its independent load.')
    return loaded


def _finite_coordinate(value: Any) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x) for x in value))


def _validate_endpoint(candidate: dict, parts: Sequence, records: Sequence[dict], owners: tuple[int, ...],
                       part_indices: tuple[int, ...], membership: tuple[int, ...]) -> None:
    pair, endpoints = candidate.get('component_ids'), candidate.get('endpoints')
    if (not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]
            or any(isinstance(i, bool) or not isinstance(i, Integral) or not 0 <= i < EXPECTED_COMPONENT_COUNT for i in pair)
            or not isinstance(endpoints, list) or len(endpoints) != 2):
        raise ValueError('Candidate must identify two distinct physical components and endpoints.')
    for endpoint, component in zip(endpoints, pair, strict=True):
        if not isinstance(endpoint, dict):
            raise ValueError('Invalid candidate endpoint record.')
        node, part_index = endpoint.get('part_node'), endpoint.get('part_index')
        if isinstance(node, bool) or not isinstance(node, Integral) or not 0 <= node < len(parts):
            raise ValueError('Invalid candidate endpoint node.')
        record = records[owners[node]]
        if (endpoint.get('geoid') != record['geoid'] or isinstance(part_index, bool)
                or not isinstance(part_index, Integral) or part_index != part_indices[node]
                or membership[node] != component):
            raise ValueError('Candidate endpoint ownership/component differs from source.')
        working, original = endpoint.get('coordinate'), endpoint.get('source_coordinate')
        if not _finite_coordinate(working) or not _finite_coordinate(original):
            raise ValueError('Both original and working endpoint coordinates must be finite.')
        if not (-180 <= original[0] <= 180 and -90 <= original[1] <= 90):
            raise ValueError('Original endpoint coordinate is outside the geographic source frame.')
        offset = record['longitude_offset_degrees']
        if (abs(working[0] - (original[0] + offset)) > _ENDPOINT_TOLERANCE_DEGREES
                or abs(working[1] - original[1]) > _ENDPOINT_TOLERANCE_DEGREES):
            raise ValueError('Original and working endpoint coordinates do not use the same longitude translation.')
        if parts[node].boundary.distance(Point(working)) > _ENDPOINT_TOLERANCE_DEGREES:
            raise ValueError('Candidate endpoint is not on its unchanged source part boundary.')
        original_part = translate(parts[node], xoff=-offset) if offset else parts[node]
        if original_part.boundary.distance(Point(original)) > _ENDPOINT_TOLERANCE_DEGREES:
            raise ValueError('Candidate original endpoint is not on the original source boundary.')
    distance = candidate.get('distance_m')
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance <= 0:
        raise ValueError('Candidate requires a positive finite gap distance.')
    if not math.isclose(_great_circle_m(*(e['coordinate'] for e in endpoints)), distance, rel_tol=1e-12, abs_tol=1e-6):
        raise ValueError('Candidate distance differs from its recorded endpoints.')


def _validate_context(context: dict) -> None:
    if (not context.get('sources') or not context.get('label_basis') or not context.get('water_attribution')
            or 'no independent global land-mask' not in context['water_attribution']):
        raise ValueError('Geographic context must retain regional evidence and its untested global land-mask limitation.')
    if any(not isinstance(row, dict) or not row.get('title') or not str(row.get('url', '')).startswith('https://')
           for row in context['sources']):
        raise ValueError('Geographic attribution requires explicit primary source links.')


def build_alaska_connections(
    parts: Sequence, records: Sequence[dict], owners: Sequence[int], part_indices: Sequence[int],
    physical_graph: PartGraph, district_count: int, *, diagnosis_dir: Path = DEFAULT_DIAGNOSTIC_DIR,
) -> tuple[PartGraph, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Add only the preserved 49 connections after source and geometry checks.

The target-count root test is rerun. With zero or one eligible original root,
the existing population policy reduces to a single spanning tree. It does not
promise that a balanced two-district assignment will use the links correctly;
that is a separate per-district polygon-and-endpoint validation requirement.
"""
    started = time.perf_counter()
    if isinstance(district_count, bool) or not isinstance(district_count, Integral) or district_count not in SUPPORTED_DISTRICT_COUNTS:
        raise ValueError('Alaska recorded connections support integer district counts 1 and 2 only.')
    if (len(records) != EXPECTED_BLOCKS or len(parts) != EXPECTED_PARTS
            or len(parts) != len(owners) or len(parts) != len(part_indices)
            or len(records) != len(physical_graph.unit_to_parts)):
        raise ValueError('Alaska source block/part counts and ownership must match.')
    owners, part_indices = tuple(owners), tuple(part_indices)
    if (any(isinstance(i, bool) or not isinstance(i, Integral) for i in (*owners, *part_indices))
            or owners != physical_graph.part_to_unit):
        raise ValueError('Part ownership/order differs from the supplied physical graph.')
    geoids = [row.get('geoid') for row in records]
    if len(set(geoids)) != len(geoids) or any(not isinstance(g, str) or len(g) != 15 or not g.isascii()
            or not g.isdigit() or not g.startswith('02') for g in geoids):
        raise ValueError('Source GEOIDs must be unique 15-digit Alaska blocks.')
    populations = [row.get('population') for row in records]
    if any(isinstance(p, bool) or not isinstance(p, Integral) or p < 0 for p in populations) or sum(populations) != EXPECTED_POPULATION:
        raise ValueError('Alaska whole-block populations must retain the verified resident total.')
    diagnosis_dir = Path(diagnosis_dir)
    payloads = {name:(diagnosis_dir/name).read_bytes() for name in PINNED_EVIDENCE_SHA256}
    hashes = {name:hashlib.sha256(payload).hexdigest() for name,payload in payloads.items()}
    if hashes != PINNED_EVIDENCE_SHA256:
        raise ValueError('Preserved Alaska diagnostic evidence hash changed; links cannot be silently redefined.')
    diagnosis, candidates, context = [json.loads(payloads[name]) for name in ('diagnosis.json','candidate-links.json','geography-context.json')]
    _validate_context(context)
    if (diagnosis.get('state_fips') != '02' or diagnosis.get('status') != 'diagnosis_complete'
            or diagnosis.get('blocks_spanning_components') or diagnosis.get('actual_district_plan_generated') is not False
            or diagnosis.get('original_and_normalized_edges_identical') is not True
            or diagnosis['source']['archive_sha256'] != SOURCE_ARCHIVE_SHA256
            or diagnosis.get('normalization',{}).get('normalization') != alaska_geometry.NORMALIZATION):
        raise ValueError('Expected the preserved normalized Alaska source diagnosis and authorized archive.')
    if candidates != diagnosis.get('links'):
        raise ValueError('Preserved candidates disagree with Alaska diagnosis.')
    for name in ('scripts/alaska_geometry.py', 'scripts/diagnose_alaska_topology.py'):
        if diagnosis.get('code_sha256',{}).get(name) != _sha256(ROOT/name):
            raise ValueError('The diagnosed normalization or population selector changed; a new policy revision is required.')
    source_parts, source_records, source_owners, source_indices, source_metadata = _verified_source()
    if (owners != source_owners or part_indices != source_indices or list(records) != source_records
            or len(parts) != len(source_parts)
            or any(shapely.to_wkb(a) != shapely.to_wkb(b) for a,b in zip(parts,source_parts,strict=True))):
        raise ValueError('Supplied geometry, ownership or whole-block records differ from the independently verified source.')
    del source_parts, source_records
    physical_helpers._verify_physical_graph(list(parts), physical_graph)
    groups, membership = physical_helpers._components(physical_graph)
    if len(groups) != EXPECTED_COMPONENT_COUNT:
        raise ValueError('Physical source components differ from the preserved Alaska diagnosis.')
    component_units=[[] for _ in groups]
    for unit,nodes in enumerate(physical_graph.unit_to_parts):
        component_ids={membership[n] for n in nodes}
        if len(component_ids)!=1:
            raise ValueError('Whole-block ownership cannot connect disconnected physical components.')
        component_units[component_ids.pop()].append(unit)
    component_populations=[sum(populations[u] for u in units) for units in component_units]
    expected=diagnosis['components']
    if (component_populations != [r['population'] for r in expected]
            or [len(nodes) for nodes in groups] != [r['part_count'] for r in expected]
            or [len(units) for units in component_units] != [r['block_count'] for r in expected]
            or diagnosis['source']['total_population'] != sum(populations)
            or diagnosis['source']['part_count'] != len(parts) or diagnosis['source']['block_count'] != len(records)):
        raise ValueError('Alaska component populations and ownership differ from the preserved diagnosis.')
    by_id={c['id']:c for c in candidates}
    if len(by_id)!=len(candidates) or not set(AUTHORIZED_CANDIDATE_IDS).issubset(by_id):
        raise ValueError('Candidate IDs must be unique and include the authorized links.')
    tree=shapely.STRtree(parts)
    eligible=[]
    for candidate in candidates:
        _validate_endpoint(candidate,parts,records,owners,part_indices,membership)
        if candidate.get('eligible_positive_gap') is not True:
            continue
        if (candidate.get('source_boundaries_intersect') is not False
                or candidate.get('intervening_component_ids') or candidate.get('endpoint_component_interior_crossings')):
            raise ValueError('Candidate is not an eligible positive source-coverage gap.')
        line=LineString([e['coordinate'] for e in candidate['endpoints']])
        for node in tree.query(line):
            part=parts[int(node)]
            if line.intersection(part).difference(part.boundary).length > _INTERIOR_ROUNDOFF_TOLERANCE_DEGREES:
                raise ValueError('Candidate crosses an Alaska source part interior.')
        eligible.append(candidate)
    selection=diagnosis_helpers.single_group_forest(component_populations,eligible,int(district_count))
    saved_plans=[p for p in diagnosis['plans'] if p['district_count']==district_count]
    if (len(saved_plans)!=1 or selection['selected_link_ids']!=list(AUTHORIZED_CANDIDATE_IDS)
            or selection!=saved_plans[0].get('policy')
            or saved_plans[0].get('policy_population_bound')!=selection['population_bound']
            or saved_plans[0].get('selected_link_ids')!=list(AUTHORIZED_CANDIDATE_IDS)
            or saved_plans[0].get('actual_district_plan_generated') is not False
            or saved_plans[0].get('augmented_component_count')!=1):
        raise ValueError('Target-count population selection differs from the preserved authorized Alaska tree.')
    if _sha256(SOURCE_ARCHIVE_PATH)!=SOURCE_ARCHIVE_SHA256:
        raise ValueError('Alaska source archive changed during policy verification.')
    if {name:_sha256(diagnosis_dir/name) for name in PINNED_EVIDENCE_SHA256}!=hashes:
        raise ValueError('Alaska diagnostic evidence changed during policy verification.')
    provenance={'policy':POLICY,'builder_sha256':_sha256(Path(__file__)),
        'source_archive_sha256':SOURCE_ARCHIVE_SHA256,'diagnostic_evidence_sha256':hashes,
        'normalization':alaska_geometry.NORMALIZATION,'normalization_code_sha256':_sha256(Path(alaska_geometry.__file__)),
        'population_selector_sha256':_sha256(Path(diagnosis_helpers.__file__)),
        'physical_validation_helpers_sha256':_sha256(Path(physical_helpers.__file__)),
        'shapely_version':shapely.__version__,'geos_version':shapely.geos_version_string}
    regions={row['id']:row for row in context.get('long_connection_context',[])}
    connections=[]
    for index,candidate_id in enumerate(AUTHORIZED_CANDIDATE_IDS,1):
        candidate=by_id[candidate_id]
        region=regions.get(candidate_id,{})
        a,b=candidate['component_ids']
        summary=region.get('inferred_region',f'Recorded gap between Alaska census-coverage components {a} and {b}; regional ocean context, not a navigable route.')
        connections.append({**copy.deepcopy(candidate),'id':f'ak-water-{index:03d}','candidate_id':candidate_id,
            'kind':'recorded-water-connection','state_fips':'02','policy':POLICY,
            'geographic_context':{'evidence_basis':'Official regional geography and exact Alaska source-interior checks; not a global land-mask certificate.',
                'summary':summary,'sources':copy.deepcopy(context['sources']),
                'source_component_clearance_verified':True,'independent_global_land_mask_tested':False,
                'foreign_land_tested':False,'navigability_tested':False,'source_geometry_modified':False},
            'provenance':provenance,
            'distance_definition':'Spherical endpoint distance of a preserved pair-local planar nearest-boundary candidate; Census coverage includes water.',
            'coordinate_frame':'continuous Alaska longitude frame; original source coordinates are retained separately'})
    rows=[set(neighbors) for neighbors in physical_graph.adjacency]
    for connection in connections:
        a,b=[e['part_node'] for e in connection['endpoints']]
        rows[a].add(b); rows[b].add(a)
    augmented=PartGraph(tuple(tuple(sorted(row)) for row in rows),physical_graph.part_to_unit)
    augmented_groups,_=physical_helpers._components(augmented)
    physical_edges=sum(map(len,physical_graph.adjacency))//2
    augmented_edges=sum(map(len,augmented.adjacency))//2
    if (len(augmented_groups)!=1 or len(augmented_groups[0])!=len(parts)
            or augmented_edges-physical_edges!=len(AUTHORIZED_CANDIDATE_IDS)):
        raise ValueError('The authorized edges did not connect every Alaska part exactly once as a component tree.')
    audit={'schema_version':1,'policy':POLICY,'state_fips':'02','district_count':int(district_count),
        'source_geometry_modified':False,'longitude_representation_normalized':True,'source_files_modified':False,
        'synthetic_ownership_edges':False,'source_population':int(sum(populations)),'block_count':len(records),'part_count':len(parts),
        'physical_component_count':len(groups),'physical_edge_count':physical_edges,
        'synthetic_edge_count':len(connections),'augmented_edge_count':augmented_edges,
        'augmented_component_count':1,'augmented_graph_connected':True,'all_source_parts_reached':True,
        'target_selection_verified_against_diagnosis':True,'eligible_root_count':len(selection['eligible_root_component_ids']),
        'population_selection':selection,'groups':selection['groups'],'candidate_count':len(candidates),
        'eligible_candidate_count':len(eligible),'connection_kind_counts':{'recorded-water-connection':len(connections)},
        'components':[{'component_id':i,'population':component_populations[i],'part_count':len(nodes),
                       'block_count':len(component_units[i])} for i,nodes in enumerate(groups)],
        'normalized_source_reloaded_and_verified':True,
        'water_context_validation':{'official_regional_geography_reviewed':True,'source_component_clearance_verified':True,
             'independent_global_land_mask_tested':False,'foreign_land_tested':False,'navigability_tested':False},
        'source_normalization':source_metadata,'provenance':provenance,
        'endpoint_tolerance_degrees':_ENDPOINT_TOLERANCE_DEGREES,
        'interior_roundoff_tolerance_degrees':_INTERIOR_ROUNDOFF_TOLERANCE_DEGREES,
        'elapsed_seconds':time.perf_counter()-started}
    return augmented,tuple(connections),audit
