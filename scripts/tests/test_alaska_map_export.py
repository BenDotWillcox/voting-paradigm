"""Independent polygon/link acceptance and longitude-export regressions."""
from copy import deepcopy
import gzip
import json

import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon, box, shape
from shapely.affinity import translate
from shapely.ops import unary_union

from scripts.alaska_map_export import (
    AlaskaMapValidationError, _distance, export_alaska_maps,
    validate_full_polygons, wrap_geometry,
)


def fixture_source(*, seam=False, multipart=False):
    parts=[box(-182,60,-181,61),box(-179,60,-178,61)] if seam else [box(-160,60,-159,61),box(-158,60,-157,61)]
    records=[{'geoid':'020010001001001','population':50,'land_area_m2':10,'water_area_m2':0,
        'source_part_count':2 if multipart else 1,'longitude_offset_degrees':-360 if seam else 0}]
    if not multipart:
        records.append({'geoid':'020010001001002','population':60,'land_area_m2':10,'water_area_m2':0,
            'source_part_count':1,'longitude_offset_degrees':0})
    owners=(0,0) if multipart else (0,1)
    indices=(0,1) if multipart else (0,0)
    coordinates=[[-181,60.5],[-179,60.5]] if seam else [[-159,60.5],[-158,60.5]]
    ends=[{'geoid':records[owners[n]]['geoid'],'part_node':n,'part_index':indices[n],
        'coordinate':coordinate,'source_coordinate':[coordinate[0]-records[owners[n]]['longitude_offset_degrees'],coordinate[1]]}
        for n,coordinate in enumerate(coordinates)]
    link={'id':'ak-water-001','candidate_id':'ak-candidate-00-01','state_fips':'02','kind':'recorded-water-connection',
        'component_ids':[0,1],'distance_m':_distance(*coordinates),'endpoints':ends}
    return parts,records,owners,indices,{r['geoid']:0 for r in records},[link]


def test_wrapped_polygon_with_hole_reconstructs_exactly():
    g=Polygon([(-182,60),(-178,60),(-178,64),(-182,64)],holes=[[(-181,61),(-181,63),(-179,63),(-179,61)]])
    wrapped,audit=wrap_geometry(g)
    assert wrapped.geom_type=='MultiPolygon'
    assert audit['wrapped_parts']==2
    assert audit['inverse_reconstruction_passed']
    restored=unary_union([translate(p,xoff=-offset) for p,offset in zip(wrapped.geoms,audit['part_offsets_from_working_degrees'])])
    assert restored.equals(g)
    assert restored.area==g.area
    assert audit['datum_transformed'] is False


def test_wrapping_separated_islands_does_not_invent_a_physical_edge():
    g=MultiPolygon([box(-182,60,-181,61),box(-179,60,-178,61)])
    wrapped,audit=wrap_geometry(g)
    assert len(wrapped.geoms)==2
    assert audit['input_parts']==audit['wrapped_parts']==2
    assert all(p.bounds[0]>=-180 and p.bounds[2]<=180 for p in wrapped.geoms)


def test_water_line_crossing_antimeridian_splits_without_world_segment():
    wrapped,audit=wrap_geometry(LineString([(-181,60),(-179,62)]))
    assert wrapped.geom_type=='MultiLineString'
    assert audit['part_offsets_from_working_degrees']==[360,0]
    assert [list(p.coords) for p in wrapped.geoms]==[[(179,60),(180,61)],[(-180,61),(-179,62)]]
    assert audit['no_world_spanning_segments']


@pytest.mark.parametrize('g',[box(179,60,180,61),box(-361,60,-359,61),Polygon(),LineString([(0,91),(-1,92)])])
def test_ambiguous_or_invalid_working_frame_is_rejected(g):
    with pytest.raises(AlaskaMapValidationError): wrap_geometry(g)


def test_one_district_is_physically_disconnected_but_valid_with_link():
    _,audit,links=validate_full_polygons(*fixture_source())
    assert audit['passed']
    assert audit['districts'][0]['physical_polygon_components']==2
    assert audit['districts'][0]['connected_components_after_links']==1
    assert audit['source_coverage_preserved_exactly']
    assert links['features'][0]['properties']['used_by_district']==0


def test_cross_district_link_is_retained_but_does_not_create_connectivity():
    parts,records,owners,indices,assignments,links=fixture_source()
    assignments[records[1]['geoid']]=1
    _,audit,features=validate_full_polygons(parts,records,owners,indices,assignments,links)
    assert audit['used_link_ids']==[]
    assert audit['unused_link_ids']==['ak-water-001']
    assert features['features'][0]['properties']['used_by_district'] is None
    assert all(row['physical_polygon_components']==1 for row in audit['districts'])


def test_missing_link_cannot_publish_disconnected_district():
    data=list(fixture_source());data[-1]=[]
    with pytest.raises(AlaskaMapValidationError,match='remain disconnected'):validate_full_polygons(*data)


def test_common_multipart_block_ownership_never_connects_polygons():
    data=list(fixture_source(multipart=True));data[-1]=[]
    with pytest.raises(AlaskaMapValidationError,match='remain disconnected'):validate_full_polygons(*data)


@pytest.mark.parametrize('change',[
    lambda e:e.update(part_node=1),lambda e:e.update(part_index=1),
    lambda e:e.update(geoid='020010001009999'),lambda e:e.update(coordinate=[-159.5,60.5]),
    lambda e:e.update(source_coordinate=[-159,60.7]),lambda e:e.update(coordinate=[float('nan'),60]),
])
def test_corrupt_source_endpoint_is_rejected(change):
    data=list(fixture_source());change(data[-1][0]['endpoints'][0])
    with pytest.raises(AlaskaMapValidationError):validate_full_polygons(*data)


@pytest.mark.parametrize('field,value',[
    ('component_ids',[1,0]),('component_ids',[0,0]),('component_ids',[True,1]),
    ('distance_m',1),('distance_m',True),('state_fips','12'),('kind','physical-shared-edge'),
])
def test_bad_recorded_connection_metadata_is_rejected(field,value):
    data=list(fixture_source());data[-1][0][field]=value
    with pytest.raises(AlaskaMapValidationError):validate_full_polygons(*data)


def test_duplicate_connection_is_rejected():
    data=list(fixture_source());data[-1].append(deepcopy(data[-1][0]))
    with pytest.raises(AlaskaMapValidationError):validate_full_polygons(*data)


def test_overlapping_source_parts_are_not_dissolved_away():
    data=list(fixture_source());data[0][1]=box(-159.5,60,-158.5,61)
    with pytest.raises(AlaskaMapValidationError,match='coverage is invalid'):validate_full_polygons(*data)


@pytest.mark.parametrize('bad',[{'020010001001001':0},{'020010001001001':0,'020010001001002':2},
    {'020010001001001':False,'020010001001002':0}])
def test_incomplete_or_ambiguous_assignments_fail(bad):
    data=list(fixture_source());data[-2]=bad
    with pytest.raises(AlaskaMapValidationError):validate_full_polygons(*data)


def test_complete_export_keeps_working_and_wrapped_frames_and_lazy_county_data(tmp_path):
    result=export_alaska_maps(*fixture_source(seam=True),tmp_path/'maps',projection={'kind':'unchanged benchmark projection'})
    assert result['status']=='validated_complete_map'
    assert result['total_population']==110 and result['block_count']==2
    assert result['district_populations']==[110]
    assert result['physical_validation']['district_component_counts']==[2]
    assert result['connectivity_validation']['passed']
    assert result['seam_validation']['passed']
    assert result['coordinate_frames']['strict_rfc7946_wgs84_conformance_claimed'] is False
    assert result['counties'][0]['block_count']==2
    assert result['map_payload_summary']['connections_gzip_bytes']>0
    assert result['artifact_sha256']['manifest.json']
    links=json.loads(gzip.decompress((tmp_path/'maps/connections.wrapped.geojson.gz').read_bytes()))
    assert links['features'][0]['geometry']['type']=='MultiLineString'
    assert links['features'][0]['properties']['used_by_district']==0
    for path in (tmp_path/'maps').rglob('*.gz'):
        data=json.loads(gzip.decompress(path.read_bytes()))
        assert data['type']=='FeatureCollection'
    assert not list((tmp_path/'maps').rglob('*.geojson'))


def test_multipart_block_population_is_counted_once(tmp_path):
    result=export_alaska_maps(*fixture_source(multipart=True),tmp_path/'maps')
    assert result['part_count']==2 and result['block_count']==1
    assert result['total_population']==50
    blocks=json.loads(gzip.decompress((tmp_path/'maps/counties/001.working.geojson.gz').read_bytes()))
    assert len(blocks['features'])==1
    assert blocks['features'][0]['geometry']['type']=='MultiPolygon'
    assert blocks['features'][0]['properties']['population']==50


def test_prior_map_directory_is_never_overwritten(tmp_path):
    target=tmp_path/'maps';target.mkdir();prior=target/'prior';prior.write_bytes(b'preserved')
    with pytest.raises(FileExistsError):export_alaska_maps(*fixture_source(),target)
    assert prior.read_bytes()==b'preserved'


def test_failed_polygon_validation_creates_no_accepted_map(tmp_path):
    data=list(fixture_source());data[-1]=[]
    with pytest.raises(AlaskaMapValidationError):export_alaska_maps(*data,tmp_path/'maps')
    assert not (tmp_path/'maps/manifest.json').exists()
