"""Real frontend runtime contracts for the all-state explorer rollout.

Synthetic Florida and Alaska fixtures exercise the published-data boundary and
the actual React handlers. The hook host deliberately permits responses after
abort; these are lifecycle tests, not browser performance measurements.
"""
import json

import pytest

from test_block_demo_integration_contract import run_node
from test_michigan_explorer_modes import HOOK_HOST
from test_michigan_spatial_inspection import CACHE_HOST, CANVAS_HOST


DATA_HOST = r"""
const h=loadTs('lib/state-map-interaction.ts');
const loader=loadTs('lib/state-spatial-blocks.ts');
function fixture(state='12') {
 const frame=state==='02'?'alaska-continuous':'source';
 const plan={id:`${state}-2`,stateFips:state,coordinateFrame:frame,districtCount:2,
  residentPopulation:100,blockCount:2,districtPopulations:[60,40]};
 const asset={url:'/geometry',bytes:200,gzipBytes:100,sha256:'a'.repeat(64)};
 const chunk={chunkId:'c001',blockCount:2,population:100,bbox:state==='02'?[-186,52,-184,54]:[-82,25,-80,27],
  asset,assignments:{url:'/assignments',bytes:100,gzipBytes:70,sha256:'b'.repeat(64)}};
 const [x,y]=chunk.bbox;
 const geometry={type:'FeatureCollection',metadata:{schemaVersion:2,stateFips:state,coordinateFrame:frame,chunkId:'c001',
  sharedAcrossPlans:true,wholeSavedBlocks:true,assignmentField:'district_id'},features:[60,40].map((population,i)=>({
   type:'Feature',properties:{geoid:`${state}001000100100${i}`,population,retained:{nested:['source',i]}},
   geometry:{type:'Polygon',coordinates:[[[x+i,y],[x+i+0.2,y],[x+i+0.2,y+0.2],[x+i,y+0.2],[x+i,y]]]}}))};
 const assignments={schemaVersion:1,planId:plan.id,stateFips:state,coordinateFrame:frame,chunkId:'c001',geometrySha256:asset.sha256,districtIds:[0,1]};
 const summary={planId:plan.id,stateFips:state,coordinateFrame:frame,residentPopulation:100,blockCount:2,
  counties:[{fips:'001',name:'Fixture',displayName:'Fixture County',population:100,blockCount:2,bbox:chunk.bbox,
   districtShares:[{districtId:0,population:60,blockCount:1,percent:60},{districtId:1,population:40,blockCount:1,percent:40}]}],
  districts:[{districtId:0,population:60,blockCount:1,countyFips:['001']},{districtId:1,population:40,blockCount:1,countyFips:['001']}]};
 const index={schemaVersion:2,planId:plan.id,stateFips:state,coordinateFrame:frame,totalBlockCount:2,totalPopulation:100,
  chunks:[chunk],counties:[{fips:'001',blockCount:2,population:100}]};
 return {plan,chunk,geometry,assignments,summary,index};
}
function deepFreeze(value){if(value&&typeof value==='object'){Object.freeze(value);for(const child of Object.values(value))deepFreeze(child);}return value;}
"""


@pytest.mark.parametrize("state", ["12", "02"])
def test_schema2_restores_exact_saved_ids_without_mutating_shared_geometry(tmp_path, state):
    run_node(tmp_path, DATA_HOST + f"const f=fixture({json.dumps(state)});\n" + r"""
const {plan,chunk,geometry,assignments,summary,index}=f;
assert.equal(h.validateStateSummary(summary,plan),summary);
assert.equal(h.validateStateSpatialIndex(index,plan,summary),index);
const before=JSON.stringify(geometry);deepFreeze(geometry);deepFreeze(assignments);
const result=loader.restoreStateSpatialAssignments(geometry,assignments,plan,chunk);
assert.notEqual(result,geometry);assert.notEqual(result.features,geometry.features);
assert.deepEqual(result.features.map(f=>f.properties.district_id),[0,1]);
assert.equal(JSON.stringify(geometry),before);
for(let i=0;i<2;i++){
 assert.notEqual(result.features[i],geometry.features[i]);assert.notEqual(result.features[i].properties,geometry.features[i].properties);
 assert.equal(result.features[i].geometry,geometry.features[i].geometry,'Large geometry stays shared');
 assert.equal(result.features[i].properties.retained,geometry.features[i].properties.retained);
 assert.equal(Object.hasOwn(geometry.features[i].properties,'district_id'),false);
}
assert.equal(h.validateCountyBlocks(result,plan,'001',100,2),result);
const other={...plan,id:plan.stateFips+'-3',districtCount:3};
const otherAssignments={...assignments,planId:other.id,districtIds:[2,0]};
const alternate=loader.restoreStateSpatialAssignments(geometry,otherAssignments,other,chunk);
assert.deepEqual(alternate.features.map(f=>f.properties.district_id),[2,0]);
assert.deepEqual(result.features.map(f=>f.properties.district_id),[0,1],'Loading another anchor cannot alter an existing plan');
""")


def test_schema2_fails_closed_on_mismatched_state_frame_digest_counts_and_saved_ids(tmp_path):
    run_node(tmp_path, DATA_HOST + r"""
const mutations=[
 f=>f.geometry.metadata.stateFips='26',f=>f.geometry.metadata.coordinateFrame='source',
 f=>delete f.geometry.metadata.coordinateFrame,f=>f.geometry.metadata.chunkId='other',
 f=>f.geometry.metadata.sharedAcrossPlans=false,f=>f.geometry.metadata.wholeSavedBlocks=false,
 f=>f.geometry.metadata.assignmentField='color',f=>f.geometry.features[0].properties.district_id=0,
 f=>f.assignments.planId='02-3',f=>f.assignments.stateFips='12',f=>f.assignments.coordinateFrame='source',
 f=>delete f.assignments.coordinateFrame,f=>f.assignments.chunkId='other',f=>f.assignments.geometrySha256='c'.repeat(64),
 f=>f.assignments.districtIds.pop(),f=>f.assignments.districtIds.push(0),f=>f.geometry.features.pop(),
 f=>f.chunk.blockCount=3,f=>f.chunk.population=99,
 ...[-1,2,0.5,'0',null,NaN,Infinity].map(id=>f=>f.assignments.districtIds[0]=id),
 f=>f.geometry.features[0].properties.geoid='120010001001000',
 f=>f.geometry.features[1].properties.geoid=f.geometry.features[0].properties.geoid,
 f=>f.geometry.features[0].properties.population=-1,
];
for(const mutate of mutations){const f=fixture('02');mutate(f);assert.throws(()=>loader.restoreStateSpatialAssignments(f.geometry,f.assignments,f.plan,f.chunk));}
for(const field of ['summary','index'])for(const mutate of [v=>v.stateFips='12',v=>v.coordinateFrame='source',v=>v.planId='02-3']){
 const f=fixture('02');mutate(f[field]);assert.throws(()=>field==='summary'?h.validateStateSummary(f.summary,f.plan):h.validateStateSpatialIndex(f.index,f.plan,f.summary));
}
for(const mutate of [f=>delete f.chunk.assignments,f=>f.chunk.assignments.bytes=0,f=>f.index.schemaVersion=1]){
 const f=fixture('12');mutate(f);assert.throws(()=>h.validateStateSpatialIndex(f.index,f.plan,f.summary));
}
""")


def test_schema2_parallel_fetch_uses_one_signal_and_rejects_late_aborted_completion(tmp_path):
    run_node(tmp_path, DATA_HOST + r"""
const f=fixture('02'),jobs=[];
global.fetch=(url,options)=>new Promise(resolve=>jobs.push({url,signal:options.signal,resolve}));
const controller=new AbortController(),pending=loader.loadStateSpatialBlocks(f.plan,f.chunk,controller.signal);
assert.deepEqual(jobs.map(j=>j.url),['/geometry','/assignments']);assert.ok(jobs.every(j=>j.signal===controller.signal));
controller.abort();
jobs[0].resolve({ok:true,json:async()=>f.geometry});jobs[1].resolve({ok:true,json:async()=>f.assignments});
await assert.rejects(pending,e=>e.name==='AbortError');
assert.ok(f.geometry.features.every(feature=>!Object.hasOwn(feature.properties,'district_id')));
global.fetch=async url=>({ok:true,json:async()=>url==='/geometry'?f.geometry:f.assignments});
const result=await loader.loadStateSpatialBlocks(f.plan,f.chunk,new AbortController().signal);
assert.deepEqual(result.features.map(feature=>feature.properties.district_id),[0,1]);
global.fetch=async url=>url==='/geometry'?{ok:true,json:async()=>f.geometry}:{ok:false,status:503};
await assert.rejects(loader.loadStateSpatialBlocks(f.plan,f.chunk,new AbortController().signal),/503/);
""")


def test_michigan_legacy_whole_block_chunks_and_compatibility_exports_still_work(tmp_path):
    run_node(tmp_path, DATA_HOST + r"""
const f=fixture('26'),legacy=loader.restoreStateSpatialAssignments(f.geometry,f.assignments,f.plan,f.chunk);
delete f.chunk.assignments;f.index.schemaVersion=1;delete f.index.coordinateFrame;delete f.summary.coordinateFrame;
const mi=loadTs('lib/michigan-map-interaction.ts');
assert.equal(mi.validateMichiganSummary,h.validateStateSummary);assert.equal(mi.prepareMichiganCountyAsync,h.prepareStateCountyAsync);
assert.equal(mi.validateMichiganSpatialIndex(f.index,f.plan,f.summary),f.index);
const jobs=[];global.fetch=async(url,options)=>{jobs.push({url,signal:options.signal});return {ok:true,json:async()=>legacy};};
const result=await loader.loadStateSpatialBlocks(f.plan,f.chunk,new AbortController().signal);
assert.equal(result,legacy);assert.equal(jobs.length,1);assert.equal(jobs[0].url,'/geometry');
assert.equal(loadTs('lib/michigan-spatial-block-cache.ts').MichiganSpatialBlockCache,
 loadTs('lib/state-spatial-block-cache.ts').StateSpatialBlockCache);
""")


def test_alaska_projection_keeps_wrapped_and_continuous_points_and_viewport_bounds_aligned(tmp_path):
    run_node(tmp_path, DATA_HOST + r"""
const p=loadTs('lib/block-map-projection.ts'),f=fixture('02');
const projection=p.makeStateBlockProjection(f.geometry,'02');
for(const latitude of [52,52.1,53]){
 const continuous=projection.projectPoint([-185,latitude]),wrapped=projection.projectPoint([175,latitude]);
 close(continuous[0],wrapped[0]);close(continuous[1],wrapped[1]);
 assert.ok(continuous.every(Number.isFinite));
}
const west=projection.projectPoint([-185.9,52.1]),east=projection.projectPoint([-184.9,52.1]);
assert.ok(west[0]<east[0],'Date-line points preserve geographic ordering without globe-spanning wrap');
const bounds=h.projectedStateCountyBounds(f.chunk.bbox,projection);
for(const longitude of [-186,-185,-184])for(const latitude of [52,53,54]){
 const point=projection.projectPoint([longitude,latitude]);
 assert.ok(point[0]>=bounds[0][0]&&point[0]<=bounds[1][0]&&point[1]>=bounds[0][1]&&point[1]<=bounds[1][1]);
}
const inside=projection.projectPoint([-185.9,52.1]);
assert.ok(h.pointInProjectedGeometry(f.geometry.features[0].geometry,inside,projection.projectPoint));
const screen=h.transformedProjection(projection,{x:-100,y:20,k:7}).projectPoint([174.1,52.1]);
close(screen[0],inside[0]*7-100);close(screen[1],inside[1]*7+20);
assert.notEqual(p.blockDistrictColor(1,'02'),p.blockDistrictColor(1,'26'));
assert.notEqual(p.blockDistrictColor(1,'12'),p.blockDistrictColor(1,'26'));
""")


def test_sidecar_cache_accounts_for_both_requests_and_bytes_and_retains_loaded_overlap(tmp_path):
    host = CACHE_HOST.replace("MichiganSpatialBlockCache", "StateSpatialBlockCache").replace(
        "lib/michigan-spatial-block-cache.ts", "lib/state-spatial-block-cache.ts")
    run_node(tmp_path, host + r"""
for(const chunk of chunks)chunk.assignments={url:`/${chunk.chunkId}-assignments`,bytes:64,gzipBytes:32,sha256:'fixture'};
setNeeded(['a','b']);await finish();
assert.equal(snapshot().networkRequests,4);assert.equal(snapshot().cachedBytes,384);assert.equal(snapshot().preparedChunks,2);
const b=documents.get('b');setNeeded(['b','c']);
assert.deepEqual(snapshot().renderData,[b]);assert.equal(snapshot().ready,false);assert.equal(snapshot().networkRequests,6);
await finish();assert.equal(snapshot().ready,true);assert.equal(snapshot().cachedBytes,384);
assert.equal(snapshot().cacheSize,2,'Pair bytes count toward inactive LRU eviction');
assert.equal(snapshot().renderData[0],b,'Shared cached geometry is not reloaded');
setNeeded(['b']);assert.equal(snapshot().ready,true);assert.equal(snapshot().networkRequests,6);
assert.equal(snapshot().cachedBytes,192);cache.dispose();
assert.equal(snapshot().cachedBytes,0);assert.deepEqual(snapshot().renderData,[]);
""")


def generic_hook_host(state):
    """Reuse the established hook runner while supplying schema-2 state fixtures."""
    host = HOOK_HOST.removesuffix("await flush();\n").replace(
        "makeStateBlockProjection(overviewDocument,'26')", "makeStateBlockProjection(overviewDocument,props.plan.stateFips)")
    # The parallel geometry/assignment loader has a longer promise chain than
    # the legacy single-file fixture. Give its completed effects time to settle.
    host = host.replace("for(let i=0;i<8;i++)", "for(let i=0;i<32;i++)")
    host = host.replace("{MichiganExplorer:Explorer}=loadUi('components/districting/michigan-explorer.tsx')",
                        "{StateBlockExplorer:Explorer}=loadUi('components/districting/state-block-explorer.tsx')")
    return host + "const fixtureState=" + json.dumps(state) + ";\n" + r"""
const coordinateFrame=fixtureState==='02'?'alaska-continuous':'source';
props.plan.id=`${fixtureState}-2`;props.plan.stateFips=fixtureState;
props.plan.stateName=fixtureState==='02'?'Alaska':'Florida';props.plan.coordinateFrame=coordinateFrame;
props.plan.recordedLinkCount=1;props.plan.assets.connections=asset('recorded');delete props.landDisplay;
props.explorer.detail=asset('fine');
props.cityMetadata={label:'Cities & places',description:'Synthetic 2020 place fixture.',sources:[],featureCount:1};
summaryDocument.planId=props.plan.id;summaryDocument.stateFips=fixtureState;summaryDocument.coordinateFrame=coordinateFrame;
for(const county of summaryDocument.counties)county.displayName=`${county.name} County`;
for(const document of [overviewDocument,fineDocument,censusDocument])for(const feature of document.features)feature.properties.state_fips=fixtureState;
for(const feature of countyGeometry.features)feature.properties.geoid=fixtureState+feature.properties.geoid.slice(2);
for(const [fips,document]of Object.entries(countyDocuments)){
 const districtIds=document.features.map(f=>f.properties.district_id);
 document.metadata={schemaVersion:2,stateFips:fixtureState,coordinateFrame,chunkId:fips,sharedAcrossPlans:true,wholeSavedBlocks:true,assignmentField:'district_id'};
 for(const feature of document.features){feature.properties.geoid=fixtureState+feature.properties.geoid.slice(2);delete feature.properties.district_id;}
 documents.set(`/assignments-${fips}`,{schemaVersion:1,planId:props.plan.id,stateFips:fixtureState,coordinateFrame,chunkId:fips,geometrySha256:'fixture',districtIds});
}
spatialIndexDocument.schemaVersion=2;spatialIndexDocument.planId=props.plan.id;spatialIndexDocument.stateFips=fixtureState;spatialIndexDocument.coordinateFrame=coordinateFrame;
Object.defineProperty(spatialIndexDocument,'chunks',{get(){return summaryDocument.counties.map(c=>({chunkId:c.fips,bbox:c.bbox,blockCount:c.blockCount,population:c.population,asset:asset(`county-${c.fips}`),assignments:asset(`assignments-${c.fips}`)}));}});
documents.set('/recorded',collection([{type:'Feature',properties:{kind:'recorded_water',link_id:'fixture-water',distance_m:1234,district_id:0},geometry:{type:'LineString',coordinates:[[-85.9,42.1],[-85.1,42.1]]}}]));
documents.set('/cities',collection([{type:'Feature',properties:{geoid:`${fixtureState}99999`,name:'Fixture Place',population:10000,year:2020,rank:1},geometry:{type:'Point',coordinates:[-85.9,42.1]}}]));
if(fixtureState==='02'){
 const shifted=new Set();
 const shift=coordinates=>{if(typeof coordinates[0]==='number'){coordinates[0]-=100;return;}for(const child of coordinates)shift(child);};
 for(const document of [...documents.values(),countyGeometry])for(const feature of document.features??[]){if(shifted.has(feature.geometry))continue;shifted.add(feature.geometry);shift(feature.geometry.coordinates);}
 for(const county of summaryDocument.counties){county.bbox[0]-=100;county.bbox[2]-=100;}
}
await flush();
"""


@pytest.mark.parametrize("state", ["12", "02"])
def test_generic_explorer_defaults_city_and_recorded_layers_and_switches_counties_in_blocks(tmp_path, state):
    run_node(tmp_path, generic_hook_host(state) + r"""
assert.equal(map().props['data-map-inspection'],'districts');
assert.equal(checkbox('Cities & places').props.checked,true);assert.equal(checkbox('Recorded connections (1)').props.checked,true);
assert.ok(requests.some(r=>r.url==='/cities'));assert.ok(requests.some(r=>r.url==='/recorded'));
assert.ok(nodes().some(n=>n.props?.['data-map-layer']==='recorded-connection'));
assert.equal(nodes().filter(n=>n.type==='label'&&textContent(n)==='Full census extent').length,0);
assert.ok(!requests.some(r=>r.url==='/census-overview'),'Wrapped national geometry is never used in state inspection');
await chooseDistrict(0);await click('Counties');await chooseCounty('Kent');await chooseCounty('Wayne');
assert.equal(selection()['data-selected-county'],'163');assert.equal(map().props['data-inspection-target'],'counties');
assert.equal(map().props['data-cached-chunks'],0);
await click('Blocks');await chooseCounty('Kent');
assert.equal(map().props['data-inspection-target'],'blocks');assert.equal(map().props['data-block-batch-ready'],true);
const canvas=one(n=>n.props?.shapes&&n.props?.appearanceKey);
assert.equal(canvas.props.stateFips,fixtureState);assert.ok(canvas.props.shapes.length>0);
assert.ok(canvas.props.shapes.every(s=>s.feature.properties.geoid.startsWith(fixtureState)));
const geoid=fixtureState+'0810001001001';
control('Find a census block by GEOID').props.onChange({target:{value:geoid}});await flush();await click(`Block ${geoid} · 60 residents`);
assert.equal(selection()['data-selected-block'],geoid);
await chooseCounty('Wayne');assert.equal(selection()['data-selected-county'],'163');assert.equal(selection()['data-selected-block'],'');
assert.equal(map().props['data-inspection-target'],'blocks');assert.equal(map().props['data-block-batch-ready'],true);
assert.ok(requests.some(r=>r.url==='/assignments-163'));
const camera=renderedView();await click('Counties');assert.deepEqual(renderedView(),camera);
assert.equal(map().props['data-retained-detail-assets'],0);assert.equal(map().props['data-cached-chunks'],0);
assert.equal(map().props['data-block-chunks'],0);assert.equal(retained(fineDocument),false);
assert.equal(nodes().filter(n=>n.props?.shapes?.some?.(s=>s.feature?.properties?.geoid)).length,0);
if(fixtureState==='02')assert.match(textContent(tree),/continuous longitude frame/);
""")


@pytest.mark.parametrize("state", ["12", "02"])
def test_generic_explorer_aborts_both_chunk_files_and_ignores_old_session_after_exit(tmp_path, state):
    run_node(tmp_path, generic_hook_host(state) + r"""
deferredUrls.add('/county-081');deferredUrls.add('/assignments-081');
await chooseCounty('Kent');await click('Blocks');
const stale=requests.filter(r=>r.url==='/county-081'||r.url==='/assignments-081');assert.equal(stale.length,2);
assert.ok(stale.every(r=>!r.signal.aborted));assert.equal(stale[0].signal,stale[1].signal);
await click('Counties');assert.ok(stale.every(r=>r.signal.aborted));
await click('Blocks');const latest=requests.filter(r=>r.url==='/county-081'||r.url==='/assignments-081').slice(-2);
assert.ok(latest.every(r=>!r.signal.aborted));
for(const job of stale)job.resolveDocument(documents.get(job.url));await flush();
assert.equal(map().props['data-cached-chunks'],0,'Late schema-2 pair cannot enter the new inspection session');
for(const job of latest)job.resolveDocument(documents.get(job.url));await flush();
assert.equal(map().props['data-block-batch-ready'],true);assert.ok(map().props['data-cached-chunks']>0);
await click('Districts');assert.equal(map().props['data-cached-chunks'],0);assert.equal(map().props['data-retained-detail-assets'],0);
assert.ok(Object.values(countyDocuments).every(d=>d.features.every(f=>!Object.hasOwn(f.properties,'district_id'))));
""")


def test_block_canvas_uses_selected_state_palette_and_legacy_michigan_default(tmp_path):
    host = CANVAS_HOST.replace("const ops=[],context={ops};", "const ops=[],context={ops};Object.defineProperty(context,'fillStyle',{set(value){ops.push(['fillStyle',value]);}});")
    run_node(tmp_path, host + r"""
const color=loadTs('lib/block-map-projection.ts').blockDistrictColor;
render({...props,stateFips:'12'});settle();
assert.deepEqual(publications().at(-1)[1].context.ops.filter(op=>op[0]==='fillStyle').map(op=>op[1]),[0,1,2].map(d=>color(d,'12')));
render({...props,stateFips:'02',appearanceKey:'02-2:source:solid'});settle();
assert.deepEqual(publications().at(-1)[1].context.ops.filter(op=>op[0]==='fillStyle').map(op=>op[1]),[0,1,2].map(d=>color(d,'02')));
const legacy={...props,appearanceKey:'26-2:land:solid'};delete legacy.stateFips;render(legacy);settle();
assert.deepEqual(publications().at(-1)[1].context.ops.filter(op=>op[0]==='fillStyle').map(op=>op[1]),[0,1,2].map(d=>color(d,'26')));unmount();
""")


def test_anchor_change_remounts_explorer_when_alaska_reuses_the_same_saved_plan(tmp_path):
    run_node(tmp_path, r"""
let params=new URLSearchParams('cap=435&state=02');
const Explorer=function StateBlockExplorer(){};
const inert=new Proxy({}, {get:(_target,name)=>String(name)});
const filename=path.join(ROOT,'components/districting/block-district-explorer.tsx');
const parent=new Module(filename,module);parent.filename=filename;
parent.require=specifier=>{
 if(specifier==='react')return {useTransition:()=>[false,callback=>callback()],useCallback:callback=>callback};
 if(specifier==='react/jsx-runtime')return {jsx:(type,props,key)=>({type,props,key}),jsxs:(type,props,key)=>({type,props,key}),Fragment:'Fragment'};
 if(specifier==='next/navigation')return {useRouter:()=>({push(){}}),useSearchParams:()=>params};
 if(specifier==='./state-block-explorer')return {StateBlockExplorer:Explorer};
 if(specifier==='@/lib/block-plan-selection')return loadTs('lib/block-plan-selection.ts');
 if(specifier==='@/lib/us-states')return loadTs('lib/us-states.ts');
 return inert;
};
parent._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{
 compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX},fileName:filename,
}).outputText,filename);
const plans={};
for(const [id,stateFips,districtCount,houseSizes]of [
 ['02-1','02',1,[435,574]],['02-2','02',2,[692,1000]],['26-13','26',13,[435,574]],
])plans[id]={id,stateFips,stateName:stateFips==='02'?'Alaska':'Michigan',districtCount,houseSizes,blockCount:100};
const asset={url:'/fixture',bytes:1,gzipBytes:1,sha256:'fixture'};
const manifest={plans,anchors:[435,574,692,1000].map(houseSize=>({houseSize,planIds:Object.values(plans).filter(p=>p.houseSizes.includes(houseSize)).map(p=>p.id)})),
 stateExplorers:{'02':{cities:asset,plans:{'02-1':{summary:asset},'02-2':{summary:asset}}}},
 michiganExplorer:{cities:asset,plans:{'26-13':{summary:asset}}}};
const saved=JSON.stringify(manifest);
function explorerAt(cap,state='02'){
 params=new URLSearchParams(`cap=${cap}&state=${state}`);
 const tree=parent.exports.BlockDistrictExplorer({manifest}),found=[];
 function visit(node){if(Array.isArray(node)){node.forEach(visit);return;}if(!node||typeof node!=='object')return;if(node.type===Explorer)found.push(node);visit(node.props?.children);}
 visit(tree);assert.equal(found.length,1);return found[0];
}
for(const [firstCap,secondCap,state]of [[435,574,'02'],[692,1000,'02'],[435,574,'26']]){
 const first=explorerAt(firstCap,state),second=explorerAt(secondCap,state);
 assert.equal(first.props.plan,second.props.plan,'The original saved plan is reused without copying or recomputation');
 assert.notEqual(first.key,second.key,'Changing anchors must remount selection, controls and the fine-geometry cache even when plan IDs match');
 assert.equal(second.key,explorerAt(secondCap,state).key,'Rendering the same anchor should preserve the active explorer');
}
assert.equal(JSON.stringify(manifest),saved);
""")
