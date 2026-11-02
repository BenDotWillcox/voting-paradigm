"""Alaska-only map export with full polygon/link and antimeridian audits.

Physical validation stays in the declared continuous longitude frame. Wrapped
copies preserve NAD83 source longitude/latitude: wrapping alone is not a datum
conversion or a claim of strict RFC 7946/WGS84 conformance. Seam cuts are display
operations, never new physical components or graph edges.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import gzip
import hashlib
import json
import math
from numbers import Integral
from pathlib import Path
import time
from typing import Any

import numpy as np
import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, box, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_TOLERANCE = 1e-9


class AlaskaMapValidationError(ValueError):
    """A saved map cannot establish the requested Alaska connectivity policy."""


def _parts(geometry: BaseGeometry, kind: str = 'polygon') -> list[BaseGeometry]:
    singular, plural = ('Polygon', 'MultiPolygon') if kind == 'polygon' else ('LineString', 'MultiLineString')
    if geometry.geom_type == singular:
        return [geometry]
    if geometry.geom_type == plural:
        return list(geometry.geoms)
    if geometry.geom_type == 'GeometryCollection':
        return [part for item in geometry.geoms for part in _parts(item, kind)
                if not part.is_empty]
    if geometry.is_empty or (kind == 'polygon' and geometry.geom_type in ('LineString','MultiLineString','Point','MultiPoint')):
        return []
    if kind == 'line' and geometry.geom_type in ('Point','MultiPoint'):
        return []
    raise AlaskaMapValidationError(f'Expected {kind} geometry, got {geometry.geom_type}.')


def wrap_geometry(geometry: BaseGeometry) -> tuple[BaseGeometry, dict[str, Any]]:
    """Cut at -180, translate western fragments +360, and verify reconstruction.

    Input is deliberately restricted to Alaska's continuous frame, excluding
    ambiguous multiple wraps. Returned offsets correspond to returned geometry
    parts and permit an independent reconstruction without interpreting a wide
    conventional longitude bounding box as geographic distance.
    """
    kind = 'polygon' if geometry.geom_type in ('Polygon','MultiPolygon') else 'line'
    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ('Polygon','MultiPolygon','LineString','MultiLineString'):
        raise AlaskaMapValidationError('Wrapping requires valid nonempty polygon or line geometry.')
    coords = shapely.get_coordinates(geometry)
    if not np.all(np.isfinite(coords)) or np.any(coords[:,0] < -360) or np.any(coords[:,0] > 0) or np.any(np.abs(coords[:,1]) > 90):
        raise AlaskaMapValidationError('Geometry is outside the single continuous Alaska longitude frame.')
    output, offsets = [], []
    for part in _parts(geometry,kind):
        if part.bounds[0] >= -180:
            pieces = [(part,0)]
        elif part.bounds[2] <= -180:
            pieces = [(part,360)]
        else:
            pieces = [(piece,offset) for extent,offset in ((box(-360,-90,-180,90),360),(box(-180,-90,0,90),0))
                      for piece in _parts(part.intersection(extent),kind)]
        for piece,offset in pieces:
            transformed = translate(piece,xoff=offset) if offset else piece
            output.append(transformed); offsets.append(offset)
    if not output:
        raise AlaskaMapValidationError('Wrapping discarded all geometry.')
    wrapped = output[0] if len(output)==1 else (MultiPolygon(output) if kind=='polygon' else MultiLineString(output))
    if not wrapped.is_valid:
        raise AlaskaMapValidationError('Wrapped geometry failed validity.')
    restored = unary_union([translate(part,xoff=-offset) if offset else part for part,offset in zip(output,offsets,strict=True)])
    difference = geometry.symmetric_difference(restored)
    # Full polygon coordinates in the Alaska source round-trip exactly. Generic
    # segment seam cuts can introduce sub-ULP interpolation noise; reject that
    # for polygons rather than silently changing coverage. For lines use both
    # Hausdorff and length checks, with the explicit numerical tolerance saved.
    tolerance = 1e-10 if kind=='line' else 0.0
    equivalent = difference.is_empty if kind=='polygon' else (
        geometry.hausdorff_distance(restored)<=tolerance and abs(geometry.length-restored.length)<=tolerance)
    if not equivalent:
        raise AlaskaMapValidationError('Wrapped geometry failed inverse seam reconstruction.')
    for part in output:
        sequences = [part.coords] if kind=='line' else [part.exterior.coords,*[r.coords for r in part.interiors]]
        for ring in sequences:
            points=np.asarray(ring)
            if np.any(np.abs(np.diff(points[:,0]))>180) or np.any(points[:,0]<-180) or np.any(points[:,0]>180):
                raise AlaskaMapValidationError('Wrapped geometry contains a world-spanning segment.')
    return wrapped, {'part_offsets_from_working_degrees':offsets,'input_parts':len(_parts(geometry,kind)),
        'wrapped_parts':len(output),'inverse_reconstruction_passed':True,
        'reconstruction_tolerance_degrees':tolerance,'source_datum':'NAD83',
        'datum_transformed':False,'longitude_domain':[-180,180],'no_world_spanning_segments':True}


def _distance(first: Sequence[float], second: Sequence[float]) -> float:
    x,y,u,v=map(math.radians,[*first,*second])
    value=math.sin((v-y)/2)**2+math.cos(y)*math.cos(v)*math.sin((u-x)/2)**2
    return 2*6371000*math.asin(math.sqrt(min(1,max(0,value))))


def _container(part: BaseGeometry, components: Sequence[BaseGeometry]) -> int:
    matches=[i for i,g in enumerate(components) if g.covers(part)]
    if len(matches)!=1:
        raise AlaskaMapValidationError('Source part does not belong to exactly one full dissolved component.')
    return matches[0]


def validate_full_polygons(parts: Sequence[BaseGeometry], records: Sequence[Mapping[str,Any]],
        owners: Sequence[int], part_indices: Sequence[int], assignments: Mapping[str,int],
        connections: Sequence[Mapping[str,Any]]) -> tuple[list[BaseGeometry],dict,dict]:
    """Independent unsimplified source/district polygon and endpoint audit."""
    if not records or len(parts)!=len(owners) or len(parts)!=len(part_indices):
        raise AlaskaMapValidationError('Source part/record arrays are incomplete.')
    geoids=[r.get('geoid') for r in records]
    if len(set(geoids))!=len(records) or set(geoids)!=set(assignments):
        raise AlaskaMapValidationError('Assignments must cover every source block exactly once.')
    if any(not isinstance(g,str) or len(g)!=15 or not g.startswith('02') or not g.isdigit() for g in geoids):
        raise AlaskaMapValidationError('Expected Alaska block GEOIDs.')
    if any(isinstance(x,bool) or not isinstance(x,Integral) or x<0 for x in assignments.values()):
        raise AlaskaMapValidationError('District IDs must be nonnegative integers.')
    k=max(assignments.values())+1
    if set(assignments.values())!=set(range(k)):
        raise AlaskaMapValidationError('District IDs must be contiguous and nonempty.')
    if any(isinstance(r.get('population'),bool) or not isinstance(r.get('population'),Integral) or r['population']<0 for r in records):
        raise AlaskaMapValidationError('Whole-block populations must be nonnegative integers.')
    expected=[]
    for owner,r in enumerate(records):
        count=r.get('source_part_count')
        if isinstance(count,bool) or not isinstance(count,Integral) or count<1:
            raise AlaskaMapValidationError('Source part ownership is missing.')
        expected.extend((owner,index) for index in range(count))
    if list(zip(owners,part_indices,strict=True))!=expected:
        raise AlaskaMapValidationError('Part ownership/index ordering differs from source records.')
    if any(p.is_empty or p.geom_type!='Polygon' or not p.is_valid for p in parts):
        raise AlaskaMapValidationError('Source polygon parts are invalid.')
    if not bool(shapely.coverage_is_valid(parts)):
        raise AlaskaMapValidationError('Normalized source coverage is invalid or overlapping.')
    source=unary_union(parts)
    source_components=_parts(source)
    source_matches=shapely.STRtree(source_components).query(np.asarray(parts,dtype=object),predicate='covered_by')
    source_members=[[] for _ in source_components]
    membership=[None]*len(parts)
    for node,component in zip(*source_matches,strict=True):
        if membership[int(node)] is not None:
            raise AlaskaMapValidationError('Source part belongs to multiple dissolved source components.')
        membership[int(node)]=int(component); source_members[int(component)].append(int(node))
    if any(component is None for component in membership) or any(not nodes for nodes in source_members):
        raise AlaskaMapValidationError('Source parts do not reconcile to full physical components.')
    component_order=sorted(range(len(source_members)),key=lambda c:(-len(source_members[c]),min(source_members[c])))
    source_component_ids={component:index for index,component in enumerate(component_order)}
    by_district=[[] for _ in range(k)]
    for part,owner in zip(parts,owners,strict=True):
        by_district[assignments[geoids[owner]]].append(part)
    full=[shapely.coverage_union_all(group) for group in by_district]
    if any(not g.is_valid or g.is_empty for g in full) or not bool(shapely.coverage_is_valid(full)):
        raise AlaskaMapValidationError('Dissolved district coverage is invalid or overlapping.')
    if not source.symmetric_difference(unary_union(full)).is_empty:
        raise AlaskaMapValidationError('Full districts changed source coverage.')
    components=[_parts(g) for g in full]
    parents=[list(range(len(group))) for group in components]
    def root(d,i):
        while parents[d][i]!=i:
            parents[d][i]=parents[d][parents[d][i]]; i=parents[d][i]
        return i
    features=[]; seen_ids=set(); seen_pairs=set(); used=[[] for _ in range(k)]
    for link in connections:
        identifier=link.get('id')
        if not isinstance(identifier,str) or not identifier or identifier in seen_ids:
            raise AlaskaMapValidationError('Connection identifiers must be unique.')
        seen_ids.add(identifier)
        if link.get('state_fips')!='02' or link.get('kind')!='recorded-water-connection':
            raise AlaskaMapValidationError('Expected an explicit Alaska recorded water connection.')
        ends=link.get('endpoints')
        if not isinstance(ends,(tuple,list)) or len(ends)!=2:
            raise AlaskaMapValidationError('Connections require two endpoints.')
        nodes=[]; endpoint_districts=[]; endpoint_components=[]; source_ids=[]; coordinates=[]
        for end in ends:
            n=end.get('part_node'); i=end.get('part_index'); geoid=end.get('geoid')
            if (isinstance(n,bool) or not isinstance(n,Integral) or not 0<=n<len(parts)
                    or isinstance(i,bool) or not isinstance(i,Integral) or i!=part_indices[n]
                    or geoid!=geoids[owners[n]]):
                raise AlaskaMapValidationError('Connection endpoint source-part ownership is corrupt.')
            coordinate=end.get('coordinate'); original=end.get('source_coordinate')
            if any(not isinstance(c,(list,tuple)) or len(c)!=2 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in c) for c in (coordinate,original)):
                raise AlaskaMapValidationError('Endpoint coordinates must be finite two-dimensional numbers.')
            point=Point(coordinate)
            if parts[n].boundary.distance(point)>BOUNDARY_TOLERANCE:
                raise AlaskaMapValidationError('Endpoint is not on its unchanged source part.')
            offset=records[owners[n]].get('longitude_offset_degrees',0)
            if abs(coordinate[0]-offset-original[0])>BOUNDARY_TOLERANCE or abs(coordinate[1]-original[1])>BOUNDARY_TOLERANCE:
                raise AlaskaMapValidationError('Original and working endpoint coordinates disagree.')
            d=assignments[geoid]
            nodes.append(int(n)); endpoint_districts.append(d); coordinates.append(list(coordinate))
            endpoint_components.append(_container(parts[n],components[d]))
            source_ids.append(source_component_ids[membership[n]])
        pair=tuple(sorted(nodes))
        if pair in seen_pairs or source_ids[0]==source_ids[1]:
            raise AlaskaMapValidationError('Duplicate link or a link inside one physical source component.')
        seen_pairs.add(pair)
        declared=link.get('component_ids')
        if (not isinstance(declared,(list,tuple)) or len(declared)!=2
                or any(isinstance(x,bool) or not isinstance(x,Integral) for x in declared)
                or list(declared)!=source_ids):
            raise AlaskaMapValidationError('Connection source component identifiers differ from independent polygon coverage.')
        distance=link.get('distance_m')
        if isinstance(distance,bool) or not isinstance(distance,(int,float)) or not math.isfinite(distance) or distance<=0 or abs(distance-_distance(*coordinates))>1e-3:
            raise AlaskaMapValidationError('Recorded connection length differs from source endpoints.')
        used_by=None
        if endpoint_districts[0]==endpoint_districts[1]:
            d=endpoint_districts[0]; a,b=[root(d,i) for i in endpoint_components]
            parents[d][a]=b; used[d].append(identifier); used_by=d
        features.append({'type':'Feature','id':identifier,'geometry':mapping(LineString(coordinates)),
            'properties':{**dict(link),'endpoint_districts':endpoint_districts,'used_by_district':used_by,
                          'physical_component_indices':source_ids}})
    rows=[{'district_id':d,'physical_polygon_components':len(group),
        'connected_components_after_links':len({root(d,i) for i in range(len(group))}),
        'used_link_ids':used[d]} for d,group in enumerate(components)]
    if any(row['connected_components_after_links']!=1 for row in rows):
        raise AlaskaMapValidationError('Full district polygons remain disconnected under same-district recorded links.')
    audit={'passed':True,'districts':rows,'source_polygon_components':len(source_components),
        'source_coverage_preserved_exactly':True,'independent_source_coverage_valid':True,
        'independent_district_coverage_valid':True,'validation_basis':'unsimplified normalized polygon union and source-part endpoint ownership; no graph traversal reused',
        'used_link_ids':[identifier for ids in used for identifier in ids],
        'unused_link_ids':[f['id'] for f in features if f['properties']['used_by_district'] is None],
        'endpoint_boundary_tolerance_degrees':BOUNDARY_TOLERANCE}
    return full,audit,{'type':'FeatureCollection','features':features}


def _json(value):
    return json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def _write_gzip(path:Path,value:Any)->dict:
    raw=_json(value); compressed=gzip.compress(raw,compresslevel=6,mtime=0)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(compressed)
    saved=path.read_bytes()
    if gzip.decompress(saved)!=raw:
        raise AlaskaMapValidationError('Compressed artifact verification failed.')
    return {'file':path.name,'raw_bytes':len(raw),'gzip_bytes':len(saved),
        'sha256':hashlib.sha256(saved).hexdigest(),'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'gzip_verified':True}


def _feature(geometry,properties):
    return {'type':'Feature','geometry':mapping(geometry),'properties':dict(properties)}


def export_alaska_maps(parts:Sequence[BaseGeometry],records:Sequence[Mapping[str,Any]],
        owners:Sequence[int],part_indices:Sequence[int],assignments:Mapping[str,int],
        connections:Sequence[Mapping[str,Any]],output_path:Path,*,projection:Mapping[str,Any]|None=None)->dict:
    """Export an accepted whole-block plan in working and wrapped frames."""
    started=time.perf_counter(); output=Path(output_path)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError('Alaska map output must be absent or empty.')
    full,audit,link_collection=validate_full_polygons(parts,records,owners,part_indices,assignments,connections)
    k=len(full); populations=[0]*k; counts=[0]*k
    for r in records:
        d=assignments[r['geoid']]; populations[d]+=int(r['population']); counts[d]+=1
    total=sum(populations); ideal=total/k
    if total<=0:
        raise AlaskaMapValidationError('Source population must be positive.')
    max_deviation=max(abs(p-ideal) for p in populations)
    district_properties=[{'district_id':d,'population':p,'block_count':counts[d],
        'deviation_people':p-ideal,'deviation_percent':100*(p-ideal)/ideal,
        **audit['districts'][d]} for d,p in enumerate(populations)]
    output.mkdir(parents=True,exist_ok=True)
    payloads={}; seams=[]
    def save(name,value):
        payloads[name]=_write_gzip(output/name,value)
        payloads[name]['file']=name
    def save_pair(stem,geometries,properties,exact):
        working={'type':'FeatureCollection','features':[_feature(g,p) for g,p in zip(geometries,properties,strict=True)]}
        save(f'{stem}.working.geojson.gz',working)
        wrapped=[]
        for g,p in zip(geometries,properties,strict=True):
            w,a=wrap_geometry(g)
            wrapped.append(_feature(w,{**p,'antimeridian':a}))
            if exact: seams.append({'artifact':stem,'id':p.get('district_id',p.get('id')),**a})
        save(f'{stem}.wrapped.geojson.gz',{'type':'FeatureCollection','features':wrapped})
    save_pair('districts-full',full,district_properties,True)
    for stem,tolerance in (('districts-state',.002),('districts-national',.015)):
        simplified=[g.simplify(tolerance,preserve_topology=True) for g in full]
        save_pair(stem,simplified,district_properties,False)
    link_geometries=[LineString(f['geometry']['coordinates']) for f in link_collection['features']]
    save_pair('connections',link_geometries,[f['properties'] for f in link_collection['features']],True)
    by_owner=[[] for _ in records]
    for part,owner in zip(parts,owners,strict=True): by_owner[owner].append(part)
    counties={}
    for i,r in enumerate(records): counties.setdefault(r['geoid'][2:5],[]).append(i)
    county_index=[]
    for county,units in sorted(counties.items()):
        geometries=[by_owner[i][0] if len(by_owner[i])==1 else MultiPolygon(by_owner[i]) for i in units]
        properties=[{'geoid':records[i]['geoid'],'population':int(records[i]['population']),
            'district_id':assignments[records[i]['geoid']],
            'land_area_m2':int(records[i].get('land_area_m2',0)),
            'water_area_m2':int(records[i].get('water_area_m2',0))} for i in units]
        save_pair(f'counties/{county}',geometries,properties,False)
        county_index.append({'county_fips':county,'block_count':len(units),
            'population':sum(p['population'] for p in properties),
            'working_file':f'counties/{county}.working.geojson.gz',
            'wrapped_file':f'counties/{county}.wrapped.geojson.gz'})
    manifest={'schema':1,'state_fips':'02','state':'Alaska','status':'validated_complete_map',
        'district_count':k,'total_population':total,'block_count':len(records),'part_count':len(parts),
        'ideal_population':ideal,'district_populations':populations,'districts':district_properties,
        'max_absolute_deviation_people':max_deviation,'max_absolute_deviation_percent':100*max_deviation/ideal,
        'connectivity_validation':audit,
        'physical_validation':{'all_districts_physically_connected':all(row['physical_polygon_components']==1 for row in audit['districts']),
            'district_component_counts':[row['physical_polygon_components'] for row in audit['districts']]},
        'seam_validation':{'passed':True,'full_and_link_reconstruction_audits':seams,
            'display_cuts_count_as_physical_components':False},
        'coordinate_frames':{'working':'continuous Alaska longitude frame; positive original longitudes translated by -360 degrees',
            'wrapped':'longitude in [-180,180] after seam cuts; NAD83 source datum retained',
            'datum_transformed':False,'strict_rfc7946_wgs84_conformance_claimed':False,
            'solver_projection':dict(projection or {}),'display_projection':'equirectangular at61 degrees north; approximate'},
        'simplification_degrees':{'national':.015,'state':.002,'full':0,'county_blocks':0},
        'simplification_note':'Display-only, independently per district; full source polygons alone determine connectivity and population acceptance.',
        'default_file':'districts-national.working.geojson.gz','state_file':'districts-state.working.geojson.gz',
        'full_file':'districts-full.working.geojson.gz','connections_file':'connections.working.geojson.gz',
        'counties':county_index,'payloads':payloads,
        'population_counted_once_per_source_block':True,'elapsed_seconds':time.perf_counter()-started}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (output/'index.html').write_bytes((ROOT/'scripts/assets/alaska-block-viewer.html').read_bytes())
    artifacts={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
    result={**manifest,'artifact_sha256':artifacts,'elapsed_seconds':time.perf_counter()-started,
        'map_payload_summary':{'national_gzip_bytes':payloads['districts-national.working.geojson.gz']['gzip_bytes'],
            'state_gzip_bytes':payloads['districts-state.working.geojson.gz']['gzip_bytes'],
            'full_gzip_bytes':payloads['districts-full.working.geojson.gz']['gzip_bytes'],
            'connections_gzip_bytes':payloads['connections.working.geojson.gz']['gzip_bytes'],
            'all_county_working_gzip_bytes':sum(v['gzip_bytes'] for n,v in payloads.items() if n.startswith('counties/') and '.working.' in n),
            'maximum_county_working_gzip_bytes':max(v['gzip_bytes'] for n,v in payloads.items() if n.startswith('counties/') and '.working.' in n)}}
    return result
