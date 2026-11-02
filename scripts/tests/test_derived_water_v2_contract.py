"""Part-level display paths retain the distinction from recorded policy links."""
from test_block_demo_integration_contract import run_node
from test_block_land_display_contract import FIXTURE


V2_FIXTURE = FIXTURE + r"""
plan.recordedLinkCount=1;
const v2=structuredClone(document),p=v2.features[0].properties;
p.derivation_schema_version=2;p.schematic=true;
p.source_part_path=ids.map((geoid,i)=>({geoid,source_polygon_part:i,water_only:i===1}));
p.land_component_ids=[4,8];
p.endpoints=p.endpoints.map((e,i)=>({...e,kind:'land-component',source_polygon_part:i*2,land_component_id:i===0?4:8}));
"""


def test_v2_physical_parts_preserve_land_paths_and_zero_land_policy_access(tmp_path):
    run_node(tmp_path, V2_FIXTURE + r"""
const snapshot=JSON.stringify(v2);
assert.equal(h.validateDerivedConnections(v2,plan,1)[0],v2.features[0]);
assert.equal(JSON.stringify(v2),snapshot);
assert.equal(h.validateDerivedConnections(document,plan,1)[0],feature,'Legacy Michigan evidence remains valid');
const access=structuredClone(v2),a=access.features[0].properties;
a.source_part_path[2].water_only=true;a.water_block_count=2;a.land_component_ids[1]=null;
a.endpoints[1]={...a.endpoints[1],kind:'recorded-connection-endpoint',recorded_link_id:'ri-water-001',recorded_endpoint_index:0};
delete a.endpoints[1].land_component_id;
assert.equal(h.validateDerivedConnections(access,plan,1).length,1,'A physical path may end at an unchanged recorded endpoint inside removed water');
const samePart=structuredClone(access),s=samePart.features[0].properties;
s.block_path=[ids[1]];s.source_part_path=[{geoid:ids[1],source_polygon_part:7,water_only:true}];
s.water_block_count=1;s.land_component_ids=[null,null];
s.endpoints=s.endpoints.map((e,i)=>({geoid:ids[1],coordinate:e.coordinate,kind:'recorded-connection-endpoint',
 source_polygon_part:7,recorded_link_id:'ri-water-001',recorded_endpoint_index:i}));
assert.equal(h.validateDerivedConnections(samePart,plan,1).length,1,'Two original endpoints may occupy one physical water part');
const sameGeoid=structuredClone(v2),g=sameGeoid.features[0].properties;
g.block_path[2]=ids[0];g.source_part_path[2].geoid=ids[0];g.endpoints[1].geoid=ids[0];
assert.equal(h.validateDerivedConnections(sameGeoid,plan,1).length,1,'Different parts of one block retain distinct source-part identity');
for(const badPlan of [{...plan,recordedLinkCount:0},{...plan,recordedLinkCount:undefined}]){
 assert.throws(()=>h.validateDerivedConnections(access,badPlan,1),/recorded-endpoint/);
 assert.equal(h.validateDerivedConnections(v2,badPlan,1).length,1,'Physical land paths need no recorded link');
}
""")


def test_v2_rejects_inconsistent_source_parts_and_endpoint_roles(tmp_path):
    run_node(tmp_path, V2_FIXTURE + r"""
for(const mutate of [
 p=>{p.derivation_schema_version=3},p=>{p.schematic=false},p=>{delete p.source_part_path},
 p=>{p.source_part_path.pop()},p=>{p.source_part_path[1]=null},
 p=>{p.source_part_path[1].geoid=ids[0]},p=>{p.source_part_path[1].source_polygon_part=-1},
 p=>{p.source_part_path[1].source_polygon_part=1.5},p=>{p.source_part_path[1].water_only='true'},
 p=>{p.water_block_count=0},p=>{p.water_block_count=0;p.source_part_path.forEach(part=>{part.water_only=false})},
 p=>{p.land_component_ids[0]=null},p=>{p.land_component_ids.push(2)},
 p=>{p.land_component_ids[0]=-1},p=>{p.land_component_ids[0]=999},
 p=>{p.endpoints[0].source_polygon_part=1},p=>{p.endpoints[0].source_polygon_part='0'},
 p=>{p.endpoints[0].kind='recorded-water-connection'},p=>{p.endpoints[0].recorded_link_id='ri-water-001'},
 p=>{p.endpoints[0].recorded_endpoint_index=0},p=>{p.endpoints[0].land_component_id=-1},
 p=>{p.source_part_path[0].water_only=true;p.water_block_count=2},
 ]){const changed=structuredClone(v2);mutate(changed.features[0].properties);assert.throws(()=>h.validateDerivedConnections(changed,plan,1));}
const access=structuredClone(v2),a=access.features[0].properties;
a.source_part_path[2].water_only=true;a.water_block_count=2;a.land_component_ids[1]=null;
a.endpoints[1]={geoid:ids[2],coordinate:[-84,45],kind:'recorded-connection-endpoint',source_polygon_part:2,recorded_link_id:'ri-water-001',recorded_endpoint_index:1};
for(const mutate of [
 p=>{p.endpoints[1].recorded_link_id=''},p=>{delete p.endpoints[1].recorded_link_id},
 p=>{p.endpoints[1].recorded_endpoint_index=2},p=>{p.endpoints[1].recorded_endpoint_index='1'},
 p=>{p.endpoints[1].land_component_id=8},p=>{p.land_component_ids[1]=8},
 p=>{p.source_part_path[2].water_only=false;p.water_block_count=1},
 p=>{p.endpoints[1].coordinate=[-84.01,45]},
 ]){const changed=structuredClone(access);mutate(changed.features[0].properties);assert.throws(()=>h.validateDerivedConnections(changed,plan,1));}
""")
