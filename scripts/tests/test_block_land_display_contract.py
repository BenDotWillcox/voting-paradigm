"""Execute the actual TypeScript display contract without modifying saved plans."""
from test_block_demo_integration_contract import run_node


FIXTURE = r"""
const h=loadTs('lib/block-land-display.ts');
const asset=name=>({url:'/'+name,bytes:100,gzipBytes:50,sha256:name});
const plan={id:'26-13',stateFips:'26',districtCount:13,
 assets:{state:asset('census'),full:asset('exact')}};
const display={planId:plan.id,state:asset('land'),national:asset('land-national'),
 stateOutline:asset('land-state'),connections:asset('derived'),
 summary:{derivedConnectionCount:1,zeroLandPopulation:265,zeroLandBlockCount:10332,method:'water-only removal'}};
const ids=['260010001001001','260010001001002','260010001001003'];
const feature={type:'Feature',properties:{id:'mi-derived-1',kind:'derived-water-adjacency',
 district_id:0,block_path:ids,water_block_count:1,
 endpoints:[{geoid:ids[0],coordinate:[-85,45]},{geoid:ids[2],coordinate:[-84,45]}]},
 geometry:{type:'LineString',coordinates:[[-85,45],[-84.5,45],[-84,45]]}};
const document={type:'FeatureCollection',metadata:{planId:plan.id},features:[feature]};
"""


def test_exterior_strokes_omit_only_holes_and_preserve_every_island_without_mutation(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/block-land-display.ts');
const ring=(x,y,size)=>[[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]];
const mainland=ring(0,0,10),lake=ring(2,2,5),island=ring(3,3,1),islandLake=ring(3.2,3.2,0.2),offshore=ring(12,0,1);
const geometry={type:'MultiPolygon',coordinates:[[mainland,lake],[island,islandLake],[offshore]]};
const before=JSON.stringify(geometry);
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value)}}
freeze(geometry);
const strokes=h.polygonExteriorStrokeGeometry(geometry);
assert.deepEqual(strokes,{type:'MultiLineString',coordinates:[mainland,island,offshore]});
assert.equal(JSON.stringify(geometry),before);
assert.equal(geometry.coordinates[0].length,2,'The lake remains in the full fill/clip/hit geometry');
assert.equal(geometry.coordinates[1].length,2,'Island lake remains in the source');
strokes.coordinates[0][0][0]=999;
assert.equal(geometry.coordinates[0][0][0][0],0,'Stroke coordinates do not alias the original geometry');
assert.deepEqual(h.polygonExteriorStrokeGeometry({type:'Polygon',coordinates:[mainland,lake]}),{type:'MultiLineString',coordinates:[mainland]});
assert.equal(h.polygonExteriorStrokeGeometry(null),null);
assert.equal(h.polygonExteriorStrokeGeometry({type:'LineString',coordinates:[[0,0],[1,1]]}),null);
""")


def test_masked_canvas_publishes_once_after_mask_and_rejects_cancelled_or_resized_frames(tmp_path):
    run_node(tmp_path, r"""
const {createBlockCanvasFrame}=loadTs('lib/block-canvas-frame.ts');
const projection=rootRequire('d3-geo').geoIdentity();
const made=[];
function makeCanvas(){
 const events=[],saved=[];
 const ctx={events,globalAlpha:0.5,globalCompositeOperation:'source-over',fillStyle:'red',
  setTransform(...args){events.push(['transform',...args])},clearRect(...args){events.push(['clear',...args])},
  save(){saved.push([this.globalAlpha,this.globalCompositeOperation,this.fillStyle])},
  restore(){[this.globalAlpha,this.globalCompositeOperation,this.fillStyle]=saved.pop()},
  beginPath(){events.push(['begin'])},moveTo(...p){events.push(['move',...p])},lineTo(...p){events.push(['line',...p])},
  closePath(){events.push(['close'])},arc(...args){events.push(['arc',...args])},
  fill(rule){events.push(['fill',rule,this.globalCompositeOperation,this.globalAlpha,this.fillStyle])},
  clip(){throw Error('Per-feature clipping must not be used')},
  drawImage(target){events.push(['image',target])}};
 const canvas={width:200,height:124,getContext:()=>ctx,ownerDocument:{createElement(tag){assert.equal(tag,'canvas');const result=makeCanvas();made.push(result);return result}}};
 return canvas;
}
const canvas=makeCanvas(),mask=collection([{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[
 [[0,0],[10,0],[10,10],[0,10],[0,0]],[[2,2],[2,3],[3,3],[3,2],[2,2]]
]}}]);
const frame=createBlockCanvasFrame(canvas,projection,mask),target=made[0];
assert.notEqual(frame.context,canvas.getContext());
assert.equal(target.width,200);assert.equal(target.height,124);
for(let i=0;i<20;i++)frame.context.fill('evenodd');
assert.equal(canvas.getContext().events.length,0,'No unmasked intermediate pixels are presented');
assert.equal(frame.context.events.filter(e=>e[0]==='fill'&&e[2]==='destination-in').length,0);
assert.equal(frame.publish(),true);
const masks=frame.context.events.filter(e=>e[0]==='fill'&&e[2]==='destination-in');
assert.deepEqual(masks,[['fill','evenodd','destination-in',1,'#fff']]);
assert.equal(frame.context.events.filter(e=>e[0]==='close').length,2,'Outer boundary and hole both contribute to the mask');
assert.equal(canvas.getContext().events.filter(e=>e[0]==='image').length,1);
assert.equal(canvas.getContext().events.find(e=>e[0]==='image')[1],target);
assert.equal(frame.publish(),false,'Repeated publication must not reapply the expensive mask');
const cancelled=createBlockCanvasFrame(canvas,projection,mask);cancelled.cancel();assert.equal(cancelled.publish(),false);
assert.equal(cancelled.context.events.filter(e=>e[0]==='fill').length,0);
const resized=createBlockCanvasFrame(canvas,projection,mask);canvas.width+=1;assert.equal(resized.publish(),false);
assert.equal(resized.context.events.filter(e=>e[0]==='fill').length,0);
const allocationCount=made.length,direct=createBlockCanvasFrame(canvas,projection);
assert.equal(direct.context,canvas.getContext(),'Other states and full extent continue drawing directly');
assert.equal(made.length,allocationCount);assert.equal(direct.publish(),true);
const beforeAtomicImages=canvas.getContext().events.filter(e=>e[0]==='image').length;
const atomic=createBlockCanvasFrame(canvas,projection,undefined,true);
assert.notEqual(atomic.context,canvas.getContext(),'Uniform Michigan detail uses an offscreen frame even without a land mask');
for(let i=0;i<20;i++)atomic.context.fill('evenodd');
assert.equal(canvas.getContext().events.filter(e=>e[0]==='image').length,beforeAtomicImages,'Incomplete block batches never reach the screen');
assert.equal(atomic.publish(),true);
assert.equal(canvas.getContext().events.filter(e=>e[0]==='image').length,beforeAtomicImages+1);
assert.equal(atomic.context.events.filter(e=>e[0]==='fill'&&e[2]==='destination-in').length,0,'Full census extent does not gain an unintended land mask');
assert.equal(atomic.publish(),false);
const cancelledAtomic=createBlockCanvasFrame(canvas,projection,undefined,true);cancelledAtomic.cancel();
assert.equal(cancelledAtomic.publish(),false);
const resizedAtomic=createBlockCanvasFrame(canvas,projection,undefined,true);canvas.height++;
assert.equal(resizedAtomic.publish(),false);
""")


def test_default_land_display_full_extent_exact_and_mismatched_plan(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
const before=JSON.stringify(plan);
assert.equal(h.selectBlockDisplayAsset(plan,display,false,false).asset,display.national);
assert.equal(h.selectBlockDisplayAsset(plan,display,false,true).asset,display.national);
assert.equal(h.selectBlockDisplayAsset(plan,display,false,false,true).asset,display.state);
assert.equal(h.selectBlockDisplayAsset(plan,display,false,true,true).asset,display.state);
assert.equal(h.selectBlockDisplayAsset(plan,display,false,true).landFocused,true);
assert.equal(h.selectBlockDisplayAsset(plan,display,true,false).asset,plan.assets.state);
assert.equal(h.selectBlockDisplayAsset(plan,display,true,true).asset,plan.assets.full);
assert.equal(h.selectBlockDisplayAsset(plan,display,true,false,true).asset,plan.assets.state);
assert.equal(h.selectBlockDisplayAsset(plan,display,true,true,true).asset,plan.assets.full);
assert.equal(h.selectBlockDisplayAsset(plan,display,true,false).landFocused,false);
assert.equal(h.selectBlockDisplayAsset(plan,{...display,planId:'26-17'},false,false).asset,plan.assets.state);
assert.equal(h.selectBlockDisplayAsset(plan,{...display,planId:'26-17'},false,false,true).asset,plan.assets.state);
const alaska={...plan,id:'02-1',stateFips:'02'};
assert.equal(h.selectBlockDisplayAsset(alaska,undefined,false,false).asset,alaska.assets.state);
assert.equal(h.selectBlockDisplayAsset(alaska,undefined,false,true).asset,alaska.assets.full);
assert.equal(h.selectBlockDisplayAsset(alaska,undefined,false,false,true).asset,alaska.assets.state);
assert.equal(h.selectBlockDisplayAsset(alaska,undefined,false,true,true).asset,alaska.assets.full);
assert.equal(h.selectBlockDisplayAsset(alaska,display,false,false).landFocused,false);
assert.equal(JSON.stringify(plan),before);
""")


def test_county_and_connection_inspection_require_fine_geometry_but_overview_does_not(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
assert.equal(h.needsFineBlockDisplay(false,'state',false),false);
assert.equal(h.needsFineBlockDisplay(true,'state',false),true,'Manual detail works at whole-state scale');
assert.equal(h.needsFineBlockDisplay(false,'state',true),true,'Loaded county blocks keep fine coverage even after zooming out');
for (const focus of ['county','connection','derived']) {
 for (const hasCounty of [false,true]) {
  const fine=h.needsFineBlockDisplay(false,focus,hasCounty);
  assert.equal(fine,true,`${focus} requires finer geometry`);
  assert.equal(h.selectBlockDisplayAsset(plan,display,false,false,fine).asset,display.state);
 }
}
const returned=h.needsFineBlockDisplay(false,'state',false);
assert.equal(h.selectBlockDisplayAsset(plan,display,false,false,returned).asset,display.national,'Returning to state with blocks cleared restores the smooth overview');
""")


def test_derived_connection_requires_same_plan_path_and_distinct_kind(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
assert.equal(h.validateDerivedConnections(document,plan,1)[0],feature);
assert.throws(()=>h.validateDerivedConnections(document,plan,2),/selected plan/);
for (const mutate of [
 doc=>{doc.metadata.planId='26-17'},
 doc=>{doc.features[0].properties.kind='recorded-water-connection'},
 doc=>{doc.features[0].properties.district_id=13},
 doc=>{doc.features[0].properties.district_id=-1},
 doc=>{doc.features[0].properties.district_id=1.5},
 doc=>{doc.features[0].properties.block_path[1]='020010001001002'},
 doc=>{doc.features[0].properties.block_path.pop()},
 doc=>{doc.features[0].properties.water_block_count=4},
 doc=>{doc.features[0].properties.endpoints[0].geoid=ids[1]},
 doc=>{doc.features[0].geometry.type='MultiLineString'},
 doc=>{doc.features[0].geometry.coordinates[0]=[Infinity,45]},
 doc=>{doc.features[0].properties.endpoints[0].coordinate=['bad',45]},
 doc=>{doc.features[0].properties.endpoints[0]=null},
 doc=>{doc.features[0].geometry.coordinates[0]=[-84,45]},
]) {
 const changed=structuredClone(document);mutate(changed);
 assert.throws(()=>h.validateDerivedConnections(changed,plan,1));
}
assert.throws(()=>h.validateDerivedConnections({...document,features:[feature,feature]},plan,2),/invalid path/);
// Two different parts of one land-bearing block may be the endpoints.
const multipart=structuredClone(document);
multipart.features[0].properties.block_path[2]=ids[0];
multipart.features[0].properties.endpoints[1].geoid=ids[0];
assert.equal(h.validateDerivedConnections(multipart,plan,1).length,1);
""")


def test_aborted_or_stale_plan_fetch_cannot_return_derived_lines(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
let calls=0, resolveDocument;
global.fetch=async()=>{calls++;return {ok:true,json:()=>new Promise(resolve=>{resolveDocument=resolve})}};
const stopped=new AbortController();stopped.abort();
await assert.rejects(h.loadDerivedConnections(plan,display,stopped.signal),{name:'AbortError'});
assert.equal(calls,0);
await assert.rejects(h.loadDerivedConnections(plan,{...display,planId:'26-17'},new AbortController().signal),/selected plan/);
assert.equal(calls,0);
const request=new AbortController();
const loading=h.loadDerivedConnections(plan,display,request.signal);
while(!resolveDocument) await new Promise(resolve=>setImmediate(resolve));
request.abort();resolveDocument(document);
await assert.rejects(loading,{name:'AbortError'});
global.fetch=async()=>({ok:true,json:async()=>({...document,metadata:{planId:'26-17'}})});
await assert.rejects(h.loadDerivedConnections(plan,display,new AbortController().signal),/selected plan/);
global.fetch=async()=>({ok:true,json:async()=>document});
assert.equal((await h.loadDerivedConnections(plan,display,new AbortController().signal))[0],feature);
""")
