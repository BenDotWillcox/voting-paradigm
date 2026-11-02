"""Bound active block-detail work by changing the camera, never dropping blocks."""
from test_block_demo_integration_contract import run_node
from test_state_explorer_runtime import generic_hook_host


def test_cheap_views_are_unchanged_and_dense_views_include_every_visible_chunk(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/state-map-interaction.ts');
const view={x:-3000,y:-1860,k:7};
const chunks=Array.from({length:30},(_,i)=>({chunkId:String(i),bounds:[[430+i*4,290],[434+i*4,330]],rawBytes:2*1024*1024,blockCount:1000}));
const cheap=h.fitStateBlockBudget(view,[chunks[0]]);assert.equal(cheap.view,view);assert.equal(cheap.adjusted,false);assert.equal(cheap.blocked,false);
const dense=h.fitStateBlockBudget(view,chunks);assert.equal(dense.adjusted,true);assert.equal(dense.blocked,false);assert.ok(dense.view.k>view.k&&dense.view.k<=256);
assert.ok(dense.rawBytes<=h.STATE_BLOCK_MAX_RAW_BYTES);assert.ok(dense.blockCount<=h.STATE_BLOCK_MAX_VISIBLE_BLOCKS);
assert.deepEqual(dense.chunkIds,h.visibleStateSpatialChunks(chunks,dense.view));
assert.equal(h.fitStateBlockBudget(dense.view,chunks).view,dense.view,'A safe camera is stable on the next render');
const originalPoint=h.mapPoint([500,310],{left:0,top:0,width:1000,height:620},view);
const newPoint=h.mapPoint([500,310],{left:0,top:0,width:1000,height:620},dense.view);
close(originalPoint[0],newPoint[0]);close(originalPoint[1],newPoint[1]);
const countBound=h.fitStateBlockBudget(view,chunks.map(c=>({...c,rawBytes:1,blockCount:2000})));
assert.ok(countBound.blockCount<=20000);assert.ok(countBound.adjusted);assert.deepEqual(countBound.chunkIds,h.visibleStateSpatialChunks(chunks,countBound.view));
""")


def test_budget_handles_edge_anchors_outliers_invalid_costs_and_max_zoom_without_omission(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/state-map-interaction.ts'),view={x:0,y:0,k:7};
const outlier={chunkId:'whole',bounds:[[-1000,-1000],[1000,1000]],rawBytes:h.STATE_BLOCK_MAX_RAW_BYTES+1,blockCount:1};
const blocked=h.fitStateBlockBudget(view,[outlier]);assert.equal(blocked.blocked,true);assert.equal(blocked.view,view);assert.deepEqual(blocked.chunkIds,['whole']);
assert.equal(h.fitStateBlockBudget({...view,k:256},[outlier]).blocked,true);
for(const patch of [{rawBytes:NaN},{rawBytes:-1},{blockCount:0},{blockCount:1.5},{bounds:undefined},{bounds:null},{bounds:[[0,0],[NaN,1]]}]){
 assert.equal(h.fitStateBlockBudget(view,[{...outlier,...patch}]).blocked,true);
}
assert.equal(h.fitStateBlockBudget({...view,k:NaN},[]).blocked,true);
const chunks=[{chunkId:'near',bounds:[[0,0],[1,1]],rawBytes:1,blockCount:1},{chunkId:'far',bounds:[[10,10],[100,100]],rawBytes:h.STATE_BLOCK_MAX_RAW_BYTES,blockCount:1}];
const result=h.fitStateBlockBudget(view,chunks,[0,0]);assert.equal(result.blocked,false);assert.ok(result.adjusted);
assert.deepEqual(result.chunkIds,h.visibleStateSpatialChunks(chunks,result.view));
assert.equal(result.view.x,0);assert.equal(result.view.y,0);
""")


DENSE_CHUNKS = r"""
const denseDescriptors=[];
for(const [fips,document]of Object.entries(countyDocuments))for(let i=0;i<document.features.length;i++){
 const feature=document.features[i],chunkId=`${fips}-${i}`,coordinates=feature.geometry.coordinates.flat();
 const bbox=[Math.min(...coordinates.map(p=>p[0])),Math.min(...coordinates.map(p=>p[1])),Math.max(...coordinates.map(p=>p[0])),Math.max(...coordinates.map(p=>p[1]))];
 const shared={type:'FeatureCollection',metadata:{...document.metadata,chunkId},features:[feature]};
 const saved={...documents.get(`/assignments-${fips}`),chunkId,districtIds:[i]};
 documents.set(`/chunk-${chunkId}`,shared);documents.set(`/ids-${chunkId}`,saved);
 denseDescriptors.push({chunkId,bbox,population:feature.properties.population,blockCount:1,asset:{...asset(`chunk-${chunkId}`),bytes:24*1024*1024},assignments:asset(`ids-${chunkId}`)});
}
Object.defineProperty(spatialIndexDocument,'chunks',{get(){return denseDescriptors;}});
const chunkRequests=()=>requests.filter(r=>r.url.startsWith('/chunk-'));
"""


def test_delayed_index_never_launches_the_oversized_initial_camera_and_switches_counties(tmp_path):
    run_node(tmp_path, generic_hook_host("12") + DENSE_CHUNKS + r"""
deferredUrls.add('/spatial-index');await chooseCounty('Kent');await centerOn([-85.69,42.1]);await click('Blocks');
const initialView=renderedView();assert.equal(chunkRequests().length,0);
requests.filter(r=>r.url==='/spatial-index').at(-1).resolveDocument(spatialIndexDocument);await flush();
assert.ok(renderedView().k>initialView.k);assert.equal(map().props['data-block-budget-ready'],true);
assert.equal(map().props['data-block-batch-ready'],true);assert.equal(chunkRequests().length,1,'Unsafe two-chunk camera must never request both chunks');
assert.ok(map().props['data-block-view-raw-bytes']<=32*1024*1024);
assert.ok(map().props['data-block-view-count']<=20000);
const before=renderedView();
listeners.get('wheel')({deltaY:120,clientX:500,clientY:310,ctrlKey:false,metaKey:false,preventDefault(){}});await flush();
assert.ok(renderedView().k<=before.k+1e-9,'Trying to zoom out never zooms in');
assert.equal(map().props['data-block-budget-ready'],true);assert.equal(chunkRequests().length,1);
await chooseCounty('Wayne');await centerOn([-84.69,42.1]);assert.equal(selection()['data-selected-county'],'163');assert.equal(map().props['data-inspection-target'],'blocks');
assert.equal(map().props['data-block-budget-ready'],true);assert.equal(map().props['data-block-batch-ready'],true);
assert.ok(map().props['data-block-view-raw-bytes']<=32*1024*1024);
await click('Counties');assert.equal(map().props['data-cached-chunks'],0);assert.equal(map().props['data-retained-detail-assets'],0);
await click('Reset view');assert.deepEqual(renderedView(),{x:0,y:0,k:1});
""")


def test_indivisible_oversized_chunk_has_clear_status_and_starts_no_block_requests(tmp_path):
    run_node(tmp_path, generic_hook_host("02") + r"""
const originalChunks=spatialIndexDocument.chunks;
Object.defineProperty(spatialIndexDocument,'chunks',{get(){return originalChunks.map(c=>({...c,asset:{...c.asset,bytes:40*1024*1024}}));}});
await chooseCounty('Kent');await click('Blocks');
assert.equal(map().props['data-block-budget-blocked'],true);assert.equal(map().props['data-block-batch-ready'],false);
assert.ok(!requests.some(r=>r.url.startsWith('/county-')||r.url.startsWith('/assignments-')));
assert.match(textContent(tree),/Block detail is unavailable for this area/);
assert.ok(!textContent(tree).includes('No Alaska blocks intersect this view'));
await click('inspect counties');assert.equal(map().props['data-inspection-target'],'counties');assert.equal(map().props['data-cached-chunks'],0);
""")
