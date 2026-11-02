"""Explicit picking targets and complete, atomic county detail in a viewport."""
from test_block_demo_integration_contract import run_node
from test_michigan_explorer_modes import HOOK_HOST


# Six narrow, non-overlapping synthetic counties straddle a district boundary.
# Every county intersects the centered 8x viewport, although half belong wholly
# to the other district. Set up before the real component's first render.
SIX_COUNTIES = HOOK_HOST.removesuffix("await flush();\n") + r"""
const rectangle=(w,s,e,n)=>[[w,s],[e,s],[e,n],[w,n],[w,s]];
overviewDocument.features=[districtFeature(0,rectangle(-86,42,-85.7,43)),districtFeature(1,rectangle(-85.7,42,-84,43))];
fineDocument.features=structuredClone(overviewDocument.features);censusDocument.features=structuredClone(overviewDocument.features);
const countyIds=['001','003','005','007','009','011'];
const countyNames=['Alpha','Beta','Gamma','Delta','Epsilon','Zeta'];
const summaries=countyIds.map((fips,i)=>{const west=-85.82+i*0.04,east=west+0.04,districtId=i<3?0:1;
 const features=[0,1].map(j=>({type:'Feature',properties:{geoid:`26${fips}000100100${j+1}`,population:50,district_id:districtId},geometry:{type:'Polygon',coordinates:[rectangle(west+j*0.02,42.2,west+(j+1)*0.02,42.4)]}}));
 countyDocuments[fips]=collection(features);documents.set(`/county-${fips}`,countyDocuments[fips]);
 return {fips,name:countyNames[i],population:100,blockCount:2,bbox:[west,42.2,east,42.4],districtShares:[{districtId,population:100,blockCount:2,percent:100}]};
});
countyGeometry.features=summaries.map(c=>({type:'Feature',properties:{geoid:`26${c.fips}`,name:c.name},geometry:{type:'Polygon',coordinates:[rectangle(...c.bbox)]}}));
summaryDocument.counties=summaries;summaryDocument.residentPopulation=600;summaryDocument.blockCount=12;
summaryDocument.districts=[0,1].map(id=>({districtId:id,population:300,blockCount:6,countyFips:countyIds.slice(id*3,id*3+3)}));
props.plan.residentPopulation=600;props.plan.blockCount=12;props.plan.districtPopulations=[300,300];props.plan.maxDeviationPeople=0;
indexDocument.counties=summaries.map(c=>({fips:c.fips,population:100,blockCount:2,asset:asset(`county-${c.fips}`)}));
const countyRequests=()=>requests.filter(r=>/^\/county-\d{3}$/.test(r.url));
const pendingCountyRequests=()=>countyRequests().filter(r=>!r.settled&&!r.signal.aborted);
const blockCanvas=()=>nodes().find(n=>Array.isArray(n.props.shapes)&&n.props.shapes.some(s=>s.feature?.properties?.geoid));
async function enterViewport(){await chooseDistrict(0);await centerOn([-85.7,42.3]);await enableBlocks();}
await flush();
"""


def test_inspection_limits_and_all_intersecting_counties_have_no_three_county_cap(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts');
for(const target of ['districts','counties']){assert.deepEqual(h.michiganZoomLimits(target),{min:1,max:256});assert.equal(h.michiganBlockDetailReady(target,256),false);}
assert.deepEqual(h.michiganZoomLimits('blocks'),{min:6,max:256});
assert.equal(h.michiganBlockDetailReady('blocks',6),true);assert.equal(h.michiganBlockDetailReady('blocks',5.999),false);
const view={x:-500,y:-310,k:2};
assert.deepEqual(h.viewportBounds(view),[[250,155],[750,465]]);
const counties=Array.from({length:8},(_,i)=>({fips:String(i+1).padStart(3,'0'),bounds:[[300+i*5,180],[350+i*5,230]]}));
counties.push({fips:'099',bounds:[[800,500],[900,600]]});
assert.deepEqual(h.visibleMichiganCountyFips([...counties].reverse(),view),counties.slice(0,8).map(c=>c.fips));
""")


COOPERATIVE_PREPARATION = r"""
const h=loadTs('lib/michigan-map-interaction.ts');
const scheduled=[];global.setTimeout=(callback,delay)=>{assert.equal(delay,0);scheduled.push(callback);return scheduled.length;};
const data=collection(Array.from({length:1200},(_,id)=>({type:'Feature',properties:{id},geometry:{type:'Polygon',coordinates:[[[id,0],[id+1,0],[id+1,1],[id,0]]]}})));
let boundsCalls=0,pathCalls=0;
const drawingPath=feature=>{pathCalls++;return `block-${feature.properties.id}`;};
drawingPath.bounds=feature=>{boundsCalls++;const id=feature.properties.id;return [[id,0],[id+1,1]];};
async function nextBatch(){assert.ok(scheduled.length>0);scheduled.shift()();await Promise.resolve();await Promise.resolve();}
"""


def test_cooperative_preparation_yields_and_matches_sync_picking_without_eager_paths(tmp_path):
    run_node(tmp_path, COOPERATIVE_PREPARATION + r"""
const pending=h.prepareMichiganCountyAsync(data,drawingPath,new AbortController().signal);
assert.equal(boundsCalls,512,'A large county yields before preparing the next batch');assert.equal(pathCalls,0);assert.equal(scheduled.length,1);
await nextBatch();assert.equal(boundsCalls,1024);assert.equal(scheduled.length,1);
await nextBatch();const result=await pending;
assert.equal(boundsCalls,1200);assert.equal(scheduled.length,0);assert.equal(result.shapes.length,1200);assert.equal(result.collection,data);
assert.equal(pathCalls,0,'Bounds/index preparation never builds unviewed paths');
assert.equal(result.shapes[17].d,'block-17');assert.equal(result.shapes[17].d,'block-17');assert.equal(pathCalls,1,'Each visible path is lazy and cached');
const synchronous=h.prepareMichiganCounty(data,drawingPath);
for(const point of [[0.5,0.5],[17.5,0.5],[511.5,0.5],[512.5,0.5],[1024.5,0.5],[1199.5,0.5],[-1,0.5],[1201,0.5]]){
 assert.deepEqual(result.hitCandidates(point),synchronous.hitCandidates(point));
}
""")


def test_cooperative_preparation_stops_after_abort_including_before_first_batch(tmp_path):
    run_node(tmp_path, COOPERATIVE_PREPARATION + r"""
const abort=new AbortController();const pending=h.prepareMichiganCountyAsync(data,drawingPath,abort.signal);
assert.equal(boundsCalls,512);abort.abort();
const rejected=assert.rejects(pending,error=>error.name==='AbortError');
await nextBatch();await rejected;
assert.equal(boundsCalls,512,'Canceled work never prepares the remaining county');assert.equal(pathCalls,0);assert.equal(scheduled.length,0);
const alreadyCanceled=new AbortController();alreadyCanceled.abort();
await assert.rejects(h.prepareMichiganCountyAsync(data,drawingPath,alreadyCanceled.signal),error=>error.name==='AbortError');
assert.equal(boundsCalls,512);assert.equal(scheduled.length,0);
""")


def test_viewport_batch_loads_all_counties_with_two_workers_and_publishes_atomically(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
countyIds.forEach(fips=>deferredUrls.add(`/county-${fips}`));
await enterViewport();
assert.equal(map().props['data-block-detail-active'],true);
assert.equal(pendingCountyRequests().length,2,'Only two network workers may start');
assert.equal(map().props['data-block-chunks'],0);assert.equal(map().props['data-block-batch-ready'],false);assert.equal(blockCanvas(),undefined);
let completed=0;
while(pendingCountyRequests().length){
 assert.ok(pendingCountyRequests().length<=2);
 const job=pendingCountyRequests()[0];job.resolveDocument(documents.get(job.url));completed++;await flush();
 if(completed<6){assert.equal(map().props['data-block-chunks'],0,'No incomplete viewport publication');assert.equal(blockCanvas(),undefined);}
}
assert.equal(completed,6);assert.deepEqual(countyRequests().map(r=>r.url).sort(),countyIds.map(f=>`/county-${f}`));
assert.equal(map().props['data-block-batch-ready'],true);assert.equal(map().props['data-block-chunks'],6);
assert.equal(blockCanvas().props.shapes.length,12,'Every visible county contributes all of its blocks');
assert.deepEqual([...new Set(blockCanvas().props.shapes.map(s=>s.feature.properties.district_id))].sort(),[0,1]);
""")


def test_county_batch_failure_keeps_the_whole_viewport_generalized(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
countyIds.forEach(fips=>deferredUrls.add(`/county-${fips}`));await enterViewport();
const first=pendingCountyRequests()[0];first.resolveDocument(documents.get(first.url));await flush();
assert.equal(map().props['data-block-chunks'],0);
pendingCountyRequests()[0].reject(new Error('Fixture county failed'));await flush();
for(const job of pendingCountyRequests())job.resolveDocument(documents.get(job.url));await flush();
assert.equal(map().props['data-block-batch-ready'],false);assert.equal(map().props['data-block-chunks'],0);assert.equal(blockCanvas(),undefined);
assert.ok(textContent(tree).includes('Fixture county failed'));
assert.equal(map().props['data-map-inspection'],'blocks','A failed layer does not discard inspection');
""")


def test_pan_reuses_unchanged_county_preparation_and_never_filters_to_selected_district(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
await enterViewport();assert.equal(map().props['data-block-chunks'],6);
const initial=new Map(blockBoundsPreparations),requestCount=countyRequests().length;
assert.equal(initial.size,12);assert.ok([...initial.values()].every(n=>n===1));
assert.equal(blockPreparations.size,0,'Preparation leaves expensive SVG paths lazy');
const stableShapes=new Map(blockCanvas().props.shapes.map(shape=>[shape.feature.properties.geoid,shape]));
const first=blockCanvas().props.shapes[0];assert.ok(first.d);assert.equal(first.d,first.d);assert.equal(blockPreparations.get(first.feature.properties.geoid),1,'A lazy block path is constructed once');
await centerOn([-85.84,42.3]);
assert.equal(map().props['data-block-batch-ready'],true);
assert.ok(blockCanvas().props.shapes.length<12);
for(const shape of blockCanvas().props.shapes){const geoid=shape.feature.properties.geoid;assert.equal(blockBoundsPreparations.get(geoid),initial.get(geoid),'Panning must reuse prepared geometry');assert.equal(shape,stableShapes.get(geoid),'Stable shape identity preserves cached canvas paths');}
assert.equal(countyRequests().length,requestCount,'Cached viewport counties do not refetch');
await centerOn([-85.7,42.3]);
assert.equal(blockCanvas().props.shapes.length,12);
assert.equal(selection()['data-selected-district'],0);
assert.ok(blockCanvas().props.shapes.some(s=>s.feature.properties.district_id===1),'Neighboring district blocks stay present');
""")


def test_inspection_target_is_explicit_and_county_clicks_can_switch_directly(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
assert.equal(map().props['data-inspection-target'],'districts');assert.notEqual(button('Blocks').props.disabled,true);
await chooseDistrict(0);assert.equal(map().props['data-inspection-target'],'districts');await click('Counties');
await mapClick([-85.81,42.3]);assert.equal(selection()['data-selected-county'],'001');
await mapClick([-85.77,42.3]);assert.equal(selection()['data-selected-county'],'003');
assert.equal(map().props['data-inspection-target'],'counties','Selecting a county must not silently start block picking');
assert.equal(selection()['data-selected-block'],'');assert.equal(countyRequests().length,0);
await mapClick([-85.69,42.3]);assert.equal(selection()['data-selected-county'],'007');
assert.equal(selection()['data-selected-district'],'','Unrelated county clears obsolete district context');
assert.equal(button('Back').props.disabled,true);
await click('Districts');await mapClick([-85.8,42.3]);
assert.equal(map().props['data-inspection-target'],'districts');assert.equal(selection()['data-selected-district'],0);assert.equal(selection()['data-selected-county'],'');
await mapClick([-85.6,42.3]);assert.equal(selection()['data-selected-district'],1);assert.equal(map().props['data-inspection-target'],'districts');
assert.equal(countyRequests().length,0);
""")


def test_blocks_always_selectable_keep_six_floor_and_release_on_inspection_change(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
await chooseDistrict(0);await centerOn([-85.7,42.3]);await zoomTo(8);
assert.equal(map().props['data-block-detail-active'],false);assert.equal(countyRequests().length,0,'Zoom alone does not load blocks');
await click('Blocks');assert.equal(map().props['data-block-chunks'],6);assert.equal(map().props['data-zoom-min'],6);
await zoomTo(6.5);assert.equal(map().props['data-block-batch-ready'],true);
for(let i=0;i<15;i++)if(!button('Zoom out').props.disabled)await click('Zoom out');
close(renderedView().k,6);assert.equal(map().props['data-inspection-target'],'blocks');assert.equal(map().props['data-block-detail-active'],true);
await click('Counties');assert.equal(map().props['data-block-chunks'],0);assert.equal(map().props['data-cached-chunks'],0);assert.equal(blockCanvas(),undefined);
assert.equal(map().props['data-zoom-min'],1);await zoomTo(1);assert.notEqual(button('Blocks').props.disabled,true);
await click('Blocks');close(renderedView().k,7);assert.equal(map().props['data-inspection-target'],'blocks');
""")


def test_neighbor_block_click_updates_its_actual_county_and_district(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
await chooseDistrict(0);await chooseCounty('Alpha');await centerOn([-85.7,42.3]);await enableBlocks();
assert.equal(selection()['data-selected-county'],'001');assert.equal(selection()['data-selected-district'],0);
assert.equal(map().props['data-block-chunks'],6);
await mapClick([-85.69,42.3]);
assert.equal(selection()['data-selected-county'],'007');assert.equal(selection()['data-selected-district'],1);
assert.equal(selection()['data-selected-block'],'260070001001001');
assert.equal(map().props['data-map-level'],'block');assert.equal(map().props['data-inspection-target'],'blocks');
assert.equal(one(n=>n.props.label==='County').props.value,'Delta');
assert.equal(one(n=>n.props.label==='Computed district').props.value,'2');
""")


def test_stale_pan_batch_cannot_replace_new_viewport_or_repopulate_after_exit(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
countyIds.forEach(fips=>deferredUrls.add(`/county-${fips}`));await enterViewport();
const old=pendingCountyRequests().slice();assert.equal(old.length,2);
await centerOn([-85.84,42.3]);
const wanted=map().props['data-visible-counties'].split(',');assert.ok(wanted.length>0&&wanted.length<6);
for(const job of old)assert.equal(job.signal.aborted,!wanted.includes(job.url.slice(-3)),'Only obsolete requests are aborted; overlapping requests survive');
let maxActive=0;
while(pendingCountyRequests().length){maxActive=Math.max(maxActive,pendingCountyRequests().length);const job=pendingCountyRequests()[0];job.resolveDocument(documents.get(job.url));await flush();}
assert.ok(maxActive<=2);assert.equal(map().props['data-block-chunks'],wanted.length);
const freshShapes=blockCanvas().props.shapes;
for(const job of old)job.resolveDocument({...structuredClone(documents.get(job.url)),marker:'obsolete viewport'});await flush();
assert.equal(blockCanvas().props.shapes,freshShapes);assert.equal(map().props['data-block-chunks'],wanted.length);
assert.equal(map().props['data-inspection-target'],'blocks');
await centerOn([-85.58,42.3]);const interrupted=pendingCountyRequests().slice();assert.ok(interrupted.length>0);
await click('Districts');assert.ok(interrupted.every(r=>r.signal.aborted));
for(const job of interrupted)job.resolveDocument(documents.get(job.url));await flush();
assert.equal(map().props['data-block-chunks'],0);assert.equal(map().props['data-cached-chunks'],0);assert.equal(map().props['data-retained-detail-assets'],0);
""")


def test_nested_cached_component_zoom_does_not_show_loading_or_fetch_or_prepare(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
await enterViewport();assert.equal(map().props['data-block-batch-ready'],true);
const requestCount=countyRequests().length,network=map().props['data-network-requests'],prepared=map().props['data-prepared-chunks'];
const bounds=new Map(blockBoundsPreparations),shapes=new Map(blockCanvas().props.shapes.map(shape=>[shape.feature.properties.geoid,shape]));
const frames=[],originalRender=render;
render=()=>{originalRender();frames.push({ready:map().props['data-block-batch-ready'],requests:map().props['data-network-requests'],prepared:map().props['data-prepared-chunks']});};
await zoomTo(16);
assert.equal(countyRequests().length,requestCount);assert.equal(map().props['data-network-requests'],network);assert.equal(map().props['data-prepared-chunks'],prepared);
for(const shape of blockCanvas().props.shapes)assert.equal(shape,shapes.get(shape.feature.properties.geoid));
assert.deepEqual(blockBoundsPreparations,bounds,'No bounds/index work is repeated for a cached subset');
await zoomTo(8);
assert.equal(countyRequests().length,requestCount);assert.equal(blockCanvas().props.shapes.length,12);
assert.ok(frames.length>0);assert.ok(frames.every(frame=>frame.ready&&frame.requests===network&&frame.prepared===prepared),'Every intermediate cached zoom frame is ready');
""")


def test_trusted_cached_blocks_remain_visible_and_pickable_while_new_area_loads(tmp_path):
    run_node(tmp_path, SIX_COUNTIES + r"""
await chooseDistrict(0);await centerOn([-85.84,42.3]);await enableBlocks();
assert.equal(map().props['data-block-batch-ready'],true);assert.ok(blockCanvas().props.shapes.length<12);
countyIds.forEach(fips=>deferredUrls.add(`/county-${fips}`));
await centerOn([-85.7,42.3]);assert.equal(map().props['data-block-batch-ready'],false);assert.ok(pendingCountyRequests().length>0);
assert.ok(blockCanvas().props.shapes.some(s=>s.feature.properties.geoid==='260010001001001'),'Trusted prior coverage stays available');
await mapClick([-85.81,42.3]);
assert.equal(selection()['data-selected-block'],'260010001001001');assert.equal(selection()['data-selected-county'],'001');
assert.equal(map().props['data-inspection-target'],'blocks');
""")
