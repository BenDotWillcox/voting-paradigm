"""Aggregate national land layers use the real validators, hooks and SVG render."""
from test_block_demo_integration_contract import run_node
from test_national_clean_map_runtime import NATIONAL_HOST


AGGREGATE_HOST = NATIONAL_HOST + r"""
manifest.landAnchors={};
for(const [houseSize,f] of fixtures){
 const extraPlans=[['02',alaska],['39',ohio]].map(([state,feature])=>({id:`${state}-1`,stateFips:state,districtCount:1,
  districtPopulations:[1],residentPopulation:1,coordinateFrame:state==='02'?'alaska-continuous':'source',recordedLinkCount:state==='02'?1:0}));
 f.plan.coordinateFrame='source';f.plan.recordedLinkCount=0;
 const allPlans=[f.plan,...extraPlans], planIds=allPlans.map(p=>p.id);
 const frames=Object.fromEntries(allPlans.map(p=>[p.stateFips,p.coordinateFrame]));
 const anchor=manifest.anchors.find(a=>a.houseSize===houseSize);anchor.planIds=planIds;
 for(const plan of extraPlans){manifest.plans[plan.id]=plan;manifest.landDisplays[plan.id]={planId:plan.id,
  connections:asset(`not-fetched-${plan.id}`),summary:{derivedConnectionCount:0}};}
 const tag=(feature,plan)=>({...feature,properties:{...feature.properties,state_fips:plan.stateFips,plan_id:plan.id,coordinate_frame:plan.coordinateFrame}});
 const forPlan=(features,plan)=>features.map(feature=>tag(feature,plan));
 for(const feature of f.census.features){const plan=allPlans.find(p=>p.stateFips===feature.properties.state_fips);feature.properties.plan_id=plan.id;}
 const outlines=collection([...forPlan(f.overview.features,f.plan),...extraPlans.map(p=>tag(p.stateFips==='02'?alaska:ohio,p))]);
 const coast=collection([
  ...f.coast.features.flatMap(feature=>feature.geometry.coordinates.map((ring,i)=>tag({...feature,
   properties:{...feature.properties,shoreline_scope:i===0?'outer':'inland'},geometry:{type:'LineString',coordinates:ring}},f.plan))),
  ...extraPlans.map(plan=>({type:'Feature',properties:{state_fips:plan.stateFips,plan_id:plan.id,coordinate_frame:plan.coordinateFrame,
   kind:'state-and-water-shoreline',shoreline_scope:'outer'},geometry:{type:'LineString',coordinates:(plan.stateFips==='02'?alaska:ohio).geometry.coordinates[0]}}))]);
 const dividers=collection(forPlan(f.dividers.features,f.plan));
 const connections=collection(forPlan(f.connections.features,f.plan));
 const recordedConnections=collection([{type:'Feature',properties:{id:'ak-water-001',kind:'water',state_fips:'02',plan_id:'02-1',coordinate_frame:'alaska-continuous'},
  geometry:{type:'LineString',coordinates:[[-186,53],[-184,54]]}}]);
 const descriptor={houseSize,planIds};
 for(const [name,data] of Object.entries({outlines,coast,dividers,connections,recordedConnections})){
  data.metadata={houseSize,planIds,coordinateFrames:frames,...(name==='coast'?{shorelineClassification:'top-level-containment-v1'}:{})};
  const key=`all-${houseSize}-${name}`;descriptor[name]=asset(key);documents.set('/'+key,data);
 }
 manifest.landAnchors[String(houseSize)]=descriptor;
}
const aggregateLayers=cap=>Object.fromEntries(['outlines','coast','dividers','connections','recordedConnections'].map(k=>[k,documents.get(`/all-${cap}-${k}`)]));
"""


def test_aggregate_uses_five_shared_assets_preserves_alaska_and_distinguishes_recorded_paths(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + r"""
const before=JSON.stringify([...documents]);await flush();
assert.deepEqual(requests.map(r=>r.url).sort(),['/state-boundaries','/anchor-435-census',
 '/all-435-outlines','/all-435-coast','/all-435-dividers','/all-435-connections','/all-435-recordedConnections'].sort());
for(const state of ['26','02','39'])assert.ok(districtPaths(state).every(p=>p.props.stroke==='none'));
assert.equal(layer('land-district-dividers').length,2);assert.equal(layer('michigan-district-dividers').length,1);
assert.equal((boundaryPaths('26')[1].props.d.match(/M/g)||[]).length,1,'Inland islands never gain the prominent border');
for(const state of ['26','02','39']){assert.equal(boundaryPaths(state)[1].props.stroke,'#454545');assert.equal(boundaryPaths(state)[1].props.strokeWidth,1.3);}
const recorded=nodes(layer('recorded-connections')[0]).filter(n=>n.type==='path');
assert.equal(recorded.length,1);assert.equal(recorded[0].props['data-state'],'02');assert.equal(recorded[0].props.stroke,'#a445a2');
assert.equal(nodes(layer('derived-water-connections')[0]).filter(n=>n.type==='path').length,1);
const alaskanPath=districtPaths('02')[0].props.d;assert.ok(alaskanPath&&!alaskanPath.includes('NaN'));
const count=requests.length;await extent(true);assert.equal(requests.length,count);
assert.ok(districtPaths('02')[0].props.d);assert.equal(layer('recorded-connections').length,0);
await extent(false);assert.equal(requests.length,count);assert.equal(districtPaths('02')[0].props.d,alaskanPath);
assert.equal(JSON.stringify([...documents]),before);assert.ok(textContent(tree).includes('Land-focused boundaries'));
""")


def test_aggregate_rejects_wrong_anchor_frame_unknown_states_missing_links_and_unclassified_coast(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + r"""
const h=loadTs('lib/block-national-land-display.ts');
const a=manifest.anchors[0],d=manifest.landAnchors['435'];
const check=layers=>h.validateNationalLandLayers(layers,d,a,manifest.plans,manifest.landDisplays);
const original=aggregateLayers(435);const valid=check(original);assert.equal(valid.size,3);
const mixed=h.nationalLandView(fixtures.get(435).census,valid);
assert.deepEqual(mixed.features.map(f=>f.properties),fixtures.get(435).census.features.map(f=>f.properties));
for(const mutate of [
 l=>l.outlines.metadata.houseSize=574,l=>l.dividers.metadata.planIds=['26-2'],
 l=>l.coast.metadata.coordinateFrames['02']='source',l=>delete l.coast.metadata.shorelineClassification,
 l=>l.outlines.features[2].properties.coordinate_frame='source',l=>l.outlines.features[2].properties.state_fips='12',
 l=>l.connections.features[0].properties.plan_id='26-3',l=>l.recordedConnections.features=[],
 l=>l.coast.features[0].properties.shoreline_scope='lake',l=>l.outlines.features[0].properties.population++,
 l=>l.coast.features.forEach(f=>{f.properties.shoreline_scope='inland'}),
 l=>l.recordedConnections.features[0].geometry.coordinates[0][0]=Infinity,
]){const layers=structuredClone(original);mutate(layers);assert.throws(()=>check(layers));}
""")


def test_aggregate_late_responses_never_replace_another_anchor(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + r"""
for(const name of ['outlines','coast','dividers','connections','recordedConnections'])deferredUrls.add(`/all-435-${name}`);
await flush();const old=requests.filter(r=>r.url.startsWith('/all-435-'));
assert.equal(old.length,5);assert.equal(districtPaths('26').length,0);
await anchor(574);assert.equal(districtPaths('26').length,3);assert.ok(old.every(r=>r.signal.aborted));
const latest=JSON.stringify(nodes().filter(n=>n.type==='path').map(n=>n.props));
for(const request of old)request.resolveDocument(documents.get(request.url));
await flush();assert.equal(JSON.stringify(nodes().filter(n=>n.type==='path').map(n=>n.props)),latest);
assert.ok(!requests.some(r=>/block|detail|old-land|old-border/.test(r.url)));
""")


def test_noninteractive_derived_paths_share_one_svg_node_per_state(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + r"""
const data=documents.get('/all-435-connections');
data.features=Array.from({length:250},(_,i)=>{const feature=structuredClone(data.features[0]);feature.properties.id=`derived-${i}`;return feature});
manifest.landDisplays['26-2'].summary.derivedConnectionCount=250;
await flush();const paths=nodes(layer('derived-water-connections')[0]).filter(n=>n.type==='path');
assert.equal(paths.length,1,'National DOM size depends on states, not explanatory connection count');
assert.equal(paths[0].props['data-connection-count'],250);
assert.equal((paths[0].props.d.match(/M/g)||[]).length,250,'All physical paths remain present as independent SVG subpaths');
""")
