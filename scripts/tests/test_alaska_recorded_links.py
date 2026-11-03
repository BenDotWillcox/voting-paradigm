"""Source, frame, population and geometric guards for recorded Alaska links."""
from copy import deepcopy
import json

import pytest
import shapely
from shapely.affinity import translate
from shapely.geometry import box

from districting.part_connectivity import PartGraph
from scripts import alaska_recorded_links as policy
from scripts.diagnose_alaska_topology import single_group_forest
from scripts.hawaii_population_links import _great_circle_m


def _repin(diagnostic, monkeypatch):
    monkeypatch.setattr(policy,'PINNED_EVIDENCE_SHA256',{
        name:policy._sha256(diagnostic/name) for name in policy.PINNED_EVIDENCE_SHA256})


def _fixture(tmp_path, monkeypatch):
    # Three mainland blocks plus two western islands, originally positive lon.
    xs=[-179.,-178.9,-178.8,-178.7]
    parts=[box(xs[i],60,xs[i+1],60.1) for i in range(3)]
    parts += [box(-181,60,-180.9,60.1),box(-183,60,-182.9,60.1)]
    pops=[100,100,100,3,2]
    records=[{'geoid':f'02013000100{i:04d}','population':pops[i],
              'land_area_m2':100,'water_area_m2':100,'longitude_offset_degrees':-360. if i>=3 else 0.,
              'source_part_count':1,'internal_point':[parts[i].centroid.x+(360 if i>=3 else 0),60.05],
              'working_internal_point':[parts[i].centroid.x,60.05]} for i in range(5)]
    owners=tuple(range(5)); indices=(0,)*5
    graph=PartGraph(((1,),(0,2),(1,),(),()),owners)
    archive=tmp_path/'source.zip'; archive.write_bytes(b'synthetic source fixture')
    monkeypatch.setattr(policy,'SOURCE_ARCHIVE_PATH',archive)
    monkeypatch.setattr(policy,'SOURCE_ARCHIVE_SHA256',policy._sha256(archive))
    monkeypatch.setattr(policy,'EXPECTED_BLOCKS',5)
    monkeypatch.setattr(policy,'EXPECTED_PARTS',5)
    monkeypatch.setattr(policy,'EXPECTED_POPULATION',305)
    monkeypatch.setattr(policy,'EXPECTED_COMPONENT_COUNT',3)
    metadata={'source_archive_sha256':policy._sha256(archive),'normalization':policy.alaska_geometry.NORMALIZATION}
    original_parts=list(parts); original_records=deepcopy(records)
    monkeypatch.setattr(policy,'_verified_source',lambda:(original_parts,deepcopy(original_records),owners,indices,metadata))
    def endpoint(node, coordinate):
        return {'geoid':records[node]['geoid'],'part_node':node,'part_index':0,'coordinate':coordinate,
                'source_coordinate':[coordinate[0]-records[node]['longitude_offset_degrees'],coordinate[1]],
                'source_boundary_error_degrees':0.}
    def candidate(a,b,left,right,eligible=True):
        ends=[endpoint(*left),endpoint(*right)]
        return {'id':f'ak-candidate-{a:02d}-{b:02d}','component_ids':[a,b],
                'endpoints':ends,'distance_m':_great_circle_m(*(e['coordinate'] for e in ends)),
                'eligible_positive_gap':eligible,'source_boundaries_intersect':False,
                'intervening_component_ids':[] if eligible else [1],
                'endpoint_component_interior_crossings':[],'selected_k':[1,2] if eligible else [],
                'classification':'geometric candidate; geographic water attribution not certified'}
    candidates=[candidate(0,1,(0,[-179,60.05]),(3,[-180.9,60.05])),
                candidate(1,2,(3,[-181,60.05]),(4,[-182.9,60.05])),
                candidate(0,2,(0,[-179,60.05]),(4,[-182.9,60.05]),False)]
    selected=single_group_forest([300,3,2],candidates[:2],1)['selected_link_ids']
    monkeypatch.setattr(policy,'AUTHORIZED_CANDIDATE_IDS',tuple(selected))
    plans=[]
    for k in [1,2]:
        result=single_group_forest([300,3,2],candidates[:2],k)
        plans.append({'district_count':k,'policy':result,'selected_link_ids':selected,
                      'policy_population_bound':result['population_bound'],
                      'augmented_component_count':1,'actual_district_plan_generated':False})
    diagnostic=tmp_path/'diagnosis'; diagnostic.mkdir()
    diagnosis={'state_fips':'02','status':'diagnosis_complete','blocks_spanning_components':[],
        'actual_district_plan_generated':False,'original_and_normalized_edges_identical':True,
        'source':{'archive_sha256':policy.SOURCE_ARCHIVE_SHA256,'block_count':5,'part_count':5,'total_population':305},
        'normalization':{'normalization':policy.alaska_geometry.NORMALIZATION},
        'code_sha256':{name:policy._sha256(policy.ROOT/name) for name in ('scripts/alaska_geometry.py','scripts/diagnose_alaska_topology.py')},
        'links':candidates,'plans':plans,
        'components':[{'population':300,'part_count':3,'block_count':3},
                      {'population':3,'part_count':1,'block_count':1},
                      {'population':2,'part_count':1,'block_count':1}]}
    context={'sources':[{'title':'Synthetic regional evidence','url':'https://example.invalid/map'}],
        'label_basis':'Synthetic region labels','water_attribution':'Regional evidence; no independent global land-mask certificate.',
        'long_connection_context':[]}
    (diagnostic/'diagnosis.json').write_text(json.dumps(diagnosis))
    (diagnostic/'candidate-links.json').write_text(json.dumps(candidates))
    (diagnostic/'geography-context.json').write_text(json.dumps(context))
    _repin(diagnostic,monkeypatch)
    return parts,records,owners,indices,graph,diagnostic


def _build(args,k=1):
    return policy.build_alaska_connections(*args[:5],k,diagnosis_dir=args[5])


def _change_diagnosis(args, monkeypatch, change):
    path=args[5]/'diagnosis.json'; data=json.loads(path.read_text())
    change(data); path.write_text(json.dumps(data)); _repin(args[5],monkeypatch)


def _change_candidate(args,monkeypatch,change,index=0):
    path=args[5]/'candidate-links.json'; rows=json.loads(path.read_text())
    change(rows[index]); path.write_text(json.dumps(rows))
    _change_diagnosis(args,monkeypatch,lambda data:data.update(links=rows))


def test_both_counts_use_same_links_and_preserve_source(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    shapes=[p.wkb for p in args[0]]; records=deepcopy(args[1])
    first=None
    for k in [1,2]:
        augmented,links,audit=_build(args,k)
        assert augmented.part_to_unit==args[4].part_to_unit
        assert args[4].adjacency==((1,),(0,2),(1,),(),())
        assert augmented.adjacency==((1,3),(0,2),(1,),(0,4),(3,))
        assert [l['id'] for l in links]==['ak-water-001','ak-water-002']
        assert links==(first or links); first=links
        assert audit['physical_component_count']==3
        assert audit['augmented_component_count']==1
        assert audit['source_population']==305
        assert audit['synthetic_edge_count']==2
        assert audit['physical_edge_count']==2
        assert audit['augmented_edge_count']==4
        assert audit['eligible_root_count']==(0 if k==1 else 1)
        assert audit['population_selection']['groups'][0]['district_count']==k
        assert audit['target_selection_verified_against_diagnosis']
        assert not links[0]['geographic_context']['independent_global_land_mask_tested']
        assert not links[0]['geographic_context']['foreign_land_tested']
        assert links[0]['endpoints'][1]['coordinate'][0] < -180
        assert links[0]['endpoints'][1]['source_coordinate'][0] > 0
    assert shapes==[p.wkb for p in args[0]] and args[1]==records
    assert before=={p:p.read_bytes() for p in before}


@pytest.mark.parametrize('k',[True,1.,0,3,65,11037])
def test_only_authorized_integer_counts(tmp_path,monkeypatch,k):
    with pytest.raises(ValueError,match='counts 1 and 2 only'):
        _build(_fixture(tmp_path,monkeypatch),k)


def test_changed_evidence_cannot_redefine_policy(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    with (args[5]/'geography-context.json').open('a') as out: out.write('\n')
    with pytest.raises(ValueError,match='evidence hash changed'): _build(args)


def test_archive_changed_during_verification_rejected(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    policy.SOURCE_ARCHIVE_PATH.write_bytes(b'changed')
    with pytest.raises(ValueError,match='archive changed'): _build(args)


@pytest.mark.parametrize('kind',['coordinates','population','population_redistribution','part_order','record_land','record_offset'])
def test_caller_arrays_must_equal_independently_reloaded_source(tmp_path,monkeypatch,kind):
    args=list(_fixture(tmp_path,monkeypatch))
    if kind=='coordinates': args[0]=[translate(args[0][0],yoff=.001),*args[0][1:]]
    elif kind=='population': args[1][0]['population']-=1
    elif kind=='population_redistribution': args[1][0]['population']-=1; args[1][1]['population']+=1
    elif kind=='part_order': args[3]=(0,0,0,1,0)
    elif kind=='record_land': args[1][0]['land_area_m2']+=1
    elif kind=='record_offset': args[1][3]['longitude_offset_degrees']=0
    with pytest.raises(ValueError,match='verified resident total|independently verified source'): _build(args)


def test_omitted_physical_edge_rejected(tmp_path,monkeypatch):
    args=list(_fixture(tmp_path,monkeypatch))
    args[4]=PartGraph(((),(2,),(1,),(),()),args[2])
    with pytest.raises(ValueError,match='exactly match source shared-edge'): _build(args)


def test_invented_physical_water_edge_rejected(tmp_path,monkeypatch):
    args=list(_fixture(tmp_path,monkeypatch))
    args[4]=PartGraph(((1,3),(0,2),(1,),(0,),()),args[2])
    with pytest.raises(ValueError,match='exactly match source shared-edge'): _build(args)


@pytest.mark.parametrize(('field','value','message'),[
    ('geoid','020130001009999','ownership/component'),('part_node',True,'endpoint node'),
    ('part_index',True,'ownership/component'),('part_index',1,'ownership/component'),
    ('coordinate',[-179,61],'longitude translation'),('source_coordinate',[-179,61],'longitude translation'),
    ('source_coordinate',[181,60.05],'geographic source frame'),('coordinate',[float('nan'),60],'finite'),
])
def test_endpoint_source_identity_and_frames_checked(tmp_path,monkeypatch,field,value,message):
    args=_fixture(tmp_path,monkeypatch)
    _change_candidate(args,monkeypatch,lambda c:c['endpoints'][0].update({field:value}))
    with pytest.raises(ValueError,match=message): _build(args)


def test_consistent_endpoint_off_boundary_is_rejected(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    def change(c):
        c['endpoints'][0]['coordinate']=[-178.95,60.05]
        c['endpoints'][0]['source_coordinate']=[-178.95,60.05]
    _change_candidate(args,monkeypatch,change)
    with pytest.raises(ValueError,match='source part boundary'): _build(args)


@pytest.mark.parametrize('distance',[0,-1,True,float('inf'),float('nan')])
def test_nonpositive_or_nonfinite_gap_rejected(tmp_path,monkeypatch,distance):
    args=_fixture(tmp_path,monkeypatch)
    _change_candidate(args,monkeypatch,lambda c:c.update(distance_m=distance))
    with pytest.raises(ValueError,match='positive finite gap'): _build(args)


def test_wrong_spherical_distance_rejected(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    _change_candidate(args,monkeypatch,lambda c:c.update(distance_m=c['distance_m']+1))
    with pytest.raises(ValueError,match='distance differs'): _build(args)


def test_a_crossing_cannot_become_eligible_by_repinning_flag(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    _change_candidate(args,monkeypatch,lambda c:c.update(eligible_positive_gap=True,intervening_component_ids=[]),index=2)
    with pytest.raises(ValueError,match='crosses an Alaska source part interior'): _build(args)


def test_changed_saved_target_selection_rejected(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    _change_diagnosis(args,monkeypatch,lambda d:d['plans'][0].update(selected_link_ids=[]))
    with pytest.raises(ValueError,match='population selection differs'): _build(args)


def test_saved_population_redistribution_rejected(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    _change_diagnosis(args,monkeypatch,lambda d:d['components'][0].update(population=299))
    with pytest.raises(ValueError,match='component populations'): _build(args)


def test_changed_normalization_code_rejected(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    _change_diagnosis(args,monkeypatch,lambda d:d['code_sha256'].update({'scripts/alaska_geometry.py':'0'*64}))
    with pytest.raises(ValueError,match='normalization or population selector changed'): _build(args)


def test_spanning_whole_block_ownership_cannot_be_silently_accepted(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    _change_diagnosis(args,monkeypatch,lambda d:d.update(blocks_spanning_components=[{'geoid':'some-block'}]))
    with pytest.raises(ValueError,match='preserved normalized Alaska'): _build(args)


def test_water_context_cannot_lose_qualification(tmp_path,monkeypatch):
    args=_fixture(tmp_path,monkeypatch)
    path=args[5]/'geography-context.json'; context=json.loads(path.read_text())
    context['water_attribution']='Certified by a global land mask.'
    path.write_text(json.dumps(context)); _repin(args[5],monkeypatch)
    with pytest.raises(ValueError,match='untested global land-mask'): _build(args)


def test_source_loader_checks_archive_before_reading(monkeypatch,tmp_path):
    path=tmp_path/'source.zip'; path.write_bytes(b'changed')
    monkeypatch.setattr(policy,'SOURCE_ARCHIVE_PATH',path)
    monkeypatch.setattr(policy,'SOURCE_ARCHIVE_SHA256','0'*64)
    monkeypatch.setattr(policy.alaska_geometry,'load_normalized_parts',lambda _:pytest.fail('Read only verified archives'))
    with pytest.raises(ValueError,match='differs from the authorized'): policy._verified_source()
