"""Behavioral contracts for spatial detail loading; no real map cache required."""
from test_block_demo_integration_contract import run_node


CACHE_HOST = r"""
const {MichiganSpatialBlockCache}=loadTs('lib/michigan-spatial-block-cache.ts');
const chunks=['a','b','c','d'].map((chunkId,i)=>({chunkId,bbox:[i,0,i+1,1],blockCount:1,population:10,asset:{url:`/${chunkId}`,bytes:128,gzipBytes:32,sha256:'fixture'}}));
const documents=new Map(chunks.map((chunk,i)=>{
 const feature={type:'Feature',properties:{geoid:`26001000100${String(1000+i)}`,population:10,district_id:i%2},geometry:{type:'Polygon',coordinates:[[[i,0],[i+1,0],[i+1,1],[i,0]]]}};
 return [chunk.chunkId,{collection:collection([feature]),shapes:[{feature,bounds:[[i,0],[i+1,1]],d:`path-${i}`}],hitCandidates:()=>[0]}];
}));
const jobs=[],notifications=[];
let needed=[];
const cache=new MichiganSpatialBlockCache({chunks,retainBytes:256,concurrency:2,
 load(chunk,signal){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});jobs.push({id:chunk.chunkId,signal,resolve,reject,settled:false});return promise;},
 onChange(){notifications.push(cache.snapshot(needed));}});
function setNeeded(ids){needed=ids;cache.setNeeded(ids);}
const snapshot=()=>cache.snapshot(needed);
const pending=()=>jobs.filter(job=>!job.settled&&!job.signal.aborted);
async function flush(){for(let i=0;i<12;i++)await Promise.resolve();}
async function resolve(job,value=documents.get(job.id)){job.settled=true;job.resolve(value);await flush();}
async function finish(){for(let guard=0;guard<12&&pending().length;guard++)await resolve(pending()[0]);}
"""


def test_overlapping_pending_chunks_reuse_requests_and_ignore_obsolete_results(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a','b']);await flush();
assert.deepEqual(pending().map(j=>j.id).sort(),['a','b']);
const oldA=jobs.find(j=>j.id==='a'),sharedB=jobs.find(j=>j.id==='b');
setNeeded(['b','c']);await flush();
assert.equal(oldA.signal.aborted,true);assert.equal(sharedB.signal.aborted,false,'Shared pending chunk must survive panning');
assert.equal(jobs.filter(j=>j.id==='b').length,1);assert.ok(snapshot().inFlight<=2);
await resolve(oldA);assert.equal(snapshot().ready,false,'Obsolete A cannot publish the current viewport');
await finish();
assert.equal(snapshot().ready,true);assert.equal(snapshot().data.length,2);
assert.equal(jobs.filter(j=>j.id==='b').length,1);assert.equal(jobs.filter(j=>j.id==='c').length,1);
assert.ok(snapshot().data.every(data=>data!==documents.get('a')));
cache.dispose();
""")


def test_late_completion_cannot_replace_a_new_request_for_the_same_chunk(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a']);await flush();const old=jobs[0];
setNeeded(['b']);await flush();setNeeded(['a']);await flush();
const newest=jobs.filter(job=>job.id==='a').at(-1);assert.notEqual(newest,old);assert.equal(old.signal.aborted,true);
await resolve(old);assert.equal(snapshot().ready,false,'Old controller cannot satisfy a newer request with the same ID');
await resolve(newest);assert.equal(snapshot().ready,true);assert.equal(snapshot().preparedChunks,1);
cache.dispose();
""")


def test_spatial_selection_includes_spanning_blocks_and_boundary_contacts(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts'),view={k:10,x:-4500,y:-2790};
const chunks=[
 {chunkId:'far-center-water',bounds:[[100,100],[551,300]]},
 {chunkId:'inside',bounds:[[475,300],[485,310]]},
 {chunkId:'boundary-touch',bounds:[[550,341],[700,500]]},
 {chunkId:'outside',bounds:[[0,0],[449,278]]},
];
assert.deepEqual(h.viewportBounds(view),[[450,279],[550,341]]);
assert.deepEqual(h.visibleMichiganSpatialChunks(chunks,view),['boundary-touch','far-center-water','inside']);
const narrow=h.zoomAt(view,2,[500,310]);
assert.ok(h.visibleMichiganSpatialChunks(chunks,narrow).every(id=>h.visibleMichiganSpatialChunks(chunks,view).includes(id)));
""")


def test_nested_cached_zoom_is_synchronous_without_loading_or_repreparation(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a','b','c']);await finish();assert.equal(snapshot().ready,true);
const calls=jobs.length,originals=new Set(snapshot().data),before=notifications.length;
setNeeded(['b']);
assert.equal(snapshot().ready,true,'A cached subset must never show a loading frame');
assert.equal(snapshot().pending,false);assert.equal(snapshot().inFlight,0);assert.equal(jobs.length,calls);
assert.equal(snapshot().data.length,1);assert.ok(originals.has(snapshot().data[0]),'Prepared objects keep stable identity');
for(const update of notifications.slice(before))assert.equal(update.ready,true,'No transient loading notification for cached subset');
// A nearby zoom back out stays within the bounded retained cache.
setNeeded(['b','c']);assert.equal(snapshot().ready,true);assert.equal(jobs.length,calls);
assert.ok(snapshot().data.every(data=>originals.has(data)));
cache.dispose();
""")


def test_lru_evicts_only_inactive_chunks_and_never_truncates_required_viewport(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
for(const id of ['a','b','c']){setNeeded([id]);await finish();assert.equal(snapshot().ready,true);}
assert.ok(snapshot().cacheSize<=2,'Inactive chunks respect the total byte budget');
assert.ok(snapshot().cachedBytes<=256);
const calls=jobs.length;setNeeded(['b']);assert.equal(snapshot().ready,true);assert.equal(jobs.length,calls,'Most recently used inactive B is retained');
setNeeded(['a']);await flush();assert.equal(snapshot().ready,false);assert.equal(jobs.length,calls+1,'Oldest inactive A was evicted');await finish();
setNeeded(['a','b','c','d']);await finish();
assert.equal(snapshot().ready,true);assert.equal(snapshot().data.length,4,'Required chunks are never capped to retained-cache budget');
assert.equal(snapshot().loaded,4);assert.equal(snapshot().total,4);assert.ok(snapshot().cachedBytes>=512);
cache.dispose();
""")


def test_production_default_retains_a_64_mib_view_through_nested_selection(tmp_path):
    run_node(tmp_path, CACHE_HOST.replace("retainBytes:256,", "") + r"""
for(const chunk of chunks)chunk.asset.bytes=32*1024*1024;
setNeeded(['a','b']);await finish();assert.equal(snapshot().cachedBytes,64*1024*1024);
const requests=jobs.length;setNeeded(['a']);assert.equal(snapshot().ready,true);
setNeeded(['a','b']);assert.equal(snapshot().ready,true);assert.equal(jobs.length,requests,'A64MiB cached viewport survives nested inspection');
setNeeded(['c']);await finish();assert.equal(snapshot().cachedBytes,64*1024*1024,'Inactive chunks beyond the default budget are evicted');
cache.dispose();
""")


def test_error_publication_is_atomic_and_retry_preserves_successful_chunks(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a','b']);await flush();const a=jobs.find(j=>j.id==='a'),b=jobs.find(j=>j.id==='b');
await resolve(b);assert.equal(snapshot().ready,false);assert.equal(snapshot().data.length,0,'Never publish only part of a viewport');
a.settled=true;a.reject(new Error('Fixture chunk failure'));await flush();
assert.equal(snapshot().ready,false);assert.equal(snapshot().data.length,0);assert.ok(String(snapshot().error).includes('Fixture chunk failure'));
const bCalls=jobs.filter(j=>j.id==='b').length;cache.retry();await finish();
assert.equal(snapshot().ready,true);assert.equal(jobs.filter(j=>j.id==='b').length,bCalls,'A good chunk is not reloaded during retry');
cache.dispose();
""")


def test_cached_overlap_stays_visible_until_complete_group_replaces_it(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a','b']);await finish();
const old=snapshot().renderData;assert.equal(old,snapshot().data);
// React asks for the new viewport before its setNeeded effect commits.
const beforeEffect=cache.snapshot(['b','c','d']);
assert.equal(beforeEffect.ready,false);assert.deepEqual(beforeEffect.renderData,[documents.get('b')]);
setNeeded(['b','c','d']);const overlap=snapshot().renderData;
assert.equal(overlap,beforeEffect.renderData);assert.equal(snapshot().data.length,0);
await resolve(pending().find(job=>job.id==='c'));
assert.equal(snapshot().renderData,overlap,'Individual arrivals must not restart drawing');
assert.equal(snapshot().data.length,0);assert.equal(snapshot().loaded,2);
await finish();assert.equal(snapshot().ready,true);
assert.equal(snapshot().data,snapshot().renderData);assert.equal(snapshot().renderData.length,3);
assert.notEqual(snapshot().renderData,overlap);
const published=snapshot().renderData;cache.retry();assert.equal(snapshot().renderData,published,'No-op retry preserves drawing identity');
assert.equal(jobs.filter(j=>j.id==='b').length,1);cache.dispose();
""")


def test_pending_error_and_rapid_pan_preserve_only_trusted_required_overlap(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a','b']);await finish();
setNeeded(['b','c']);const overlap=snapshot().renderData;
const c=pending().find(job=>job.id==='c');c.settled=true;c.reject(new Error('Offline'));await flush();
assert.equal(snapshot().ready,false);assert.equal(snapshot().renderData,overlap);assert.deepEqual(overlap,[documents.get('b')]);
cache.retry();assert.equal(snapshot().renderData,overlap);
const oldC=pending().find(job=>job.id==='c');setNeeded(['a','d']);
assert.deepEqual(snapshot().renderData,[documents.get('a')],'Previous geography is not exposed as current cached coverage');
await resolve(oldC);assert.equal(snapshot().renderData.length,1,'Obsolete late response cannot enter visible coverage');
await finish();assert.equal(snapshot().ready,true);assert.deepEqual(snapshot().renderData,[documents.get('a'),documents.get('d')]);
cache.dispose();assert.deepEqual(snapshot().renderData,[]);
""")


def test_duplicate_geoids_are_rejected_instead_of_silently_double_counted(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a','b']);await flush();await resolve(jobs.find(j=>j.id==='a'));
const duplicate=structuredClone(documents.get('b').collection.features[0]);duplicate.properties.geoid=documents.get('a').collection.features[0].properties.geoid;
await resolve(jobs.find(j=>j.id==='b'),{collection:collection([duplicate]),shapes:[{feature:duplicate,bounds:[[0,0],[1,1]],d:'duplicate'}],hitCandidates:()=>[0]});
assert.equal(snapshot().ready,false);assert.equal(snapshot().data.length,0);assert.match(String(snapshot().error),/duplicate|repeated/i);
assert.deepEqual(snapshot().renderData,[],'An invalid new group must never be displayed');
cache.dispose();
""")


def test_duplicate_new_chunk_does_not_erase_previous_trusted_coverage(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a']);await finish();setNeeded(['a','b']);const retained=snapshot().renderData;
const duplicate=structuredClone(documents.get('b').collection.features[0]);duplicate.properties.geoid=documents.get('a').collection.features[0].properties.geoid;
await resolve(pending()[0],{collection:collection([duplicate]),shapes:[],hitCandidates:()=>[]});
assert.equal(snapshot().ready,false);assert.match(snapshot().error,/Duplicate/);assert.equal(snapshot().renderData,retained);
assert.deepEqual(retained,[documents.get('a')]);cache.dispose();
""")


def test_exit_aborts_pending_releases_cache_and_ignores_late_completions(tmp_path):
    run_node(tmp_path, CACHE_HOST + r"""
setNeeded(['a','b']);await flush();await resolve(jobs.find(j=>j.id==='a'));const late=jobs.find(j=>j.id==='b');
const before=notifications.length;cache.dispose();assert.equal(late.signal.aborted,true);
const exited=cache.snapshot([]);assert.equal(exited.cacheSize,0);assert.equal(exited.cachedBytes,0);assert.equal(exited.inFlight,0);
await resolve(late);const after=cache.snapshot([]);assert.equal(after.cacheSize,0);assert.equal(after.inFlight,0);assert.equal(after.data.length,0);
assert.equal(notifications.length,before,'Disposed loader must not notify a detached component');
""")


def test_retained_raster_nested_transform_aligns_map_points_at_responsive_sizes(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts');
for(const [width,height]of [[1000,620],[500,310],[750,465]]){
 const previous={view:{x:-800,y:-600,k:4},appearanceKey:'land:solid:plan26-13',width,height};
 const view=h.zoomAt(previous.view,2,[200,150],{min:1,max:256});
 const result=h.retainedMichiganFrameTransform(previous,{view,appearanceKey:previous.appearanceKey,width,height,complete:true});
 assert.ok(result);assert.equal(result.scale,2);
 for(const point of [[225,175],[250,200],[300,240]]){
  const old=[(point[0]*previous.view.k+previous.view.x)*width/1000,(point[1]*previous.view.k+previous.view.y)*height/620];
  const expected=[(point[0]*view.k+view.x)*width/1000,(point[1]*view.k+view.y)*height/620];
  close(old[0]*result.scale+result.x,expected[0]);close(old[1]*result.scale+result.y,expected[1]);
 }
 const identical=h.retainedMichiganFrameTransform(previous,{...previous,complete:true});
 assert.deepEqual(identical,{scale:1,x:0,y:0});
}
""")


def test_retained_raster_clips_partial_pending_pans_and_rejects_incompatible_frames(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts');
const previous={view:{x:-800,y:-600,k:4},appearanceKey:'land:solid:26-13',width:1000,height:620};
const valid={...previous,view:h.zoomAt(previous.view,2,[500,310]),complete:true};
assert.ok(h.retainedMichiganFrameTransform(previous,valid));
assert.equal(h.retainedMichiganFrameTransform(null,valid),null);
// The old bitmap's own rectangle is its coverage clip. The parent map clips
// this transformed rectangle to the current viewport, leaving new area blank.
const pan={...previous,view:{...previous.view,x:previous.view.x-250},complete:false};
assert.deepEqual(h.retainedMichiganFrameTransform(previous,pan),{scale:1,x:-250,y:0});
const rapid={...pan,view:{...pan.view,x:previous.view.x-500}};
assert.deepEqual(h.retainedMichiganFrameTransform(previous,rapid),{scale:1,x:-500,y:0},'Rapid pans derive from published frame, not prior transform');
assert.ok(h.retainedMichiganFrameTransform(previous,{...valid,complete:false}));
const zoomOut={...valid,view:h.zoomAt(previous.view,0.5,[500,310]),complete:false};
assert.deepEqual(h.retainedMichiganFrameTransform(previous,zoomOut),{scale:0.5,x:250,y:155});
for(const current of [
 {...valid,view:{...previous.view,x:previous.view.x-1000}},
 {...valid,view:{...previous.view,y:previous.view.y-621}},
 {...valid,appearanceKey:'census:solid:26-13'},
 {...valid,appearanceKey:'land:density:26-13'},
 {...valid,appearanceKey:'land:solid:26-18'},
 {...valid,width:500,height:310},
 {...valid,width:1001},
])assert.equal(h.retainedMichiganFrameTransform(previous,current),null);
""")


CANVAS_HOST = r"""
const hooks=[],effects=[],raf=new Map(),allCallbacks=[],made=[];
let hookIndex=0,dirty=false,nextFrame=0,resizeCallback,tree,props;
const React={
 useRef(initial){const i=hookIndex++;return hooks[i]??=( {current:initial} );},
 useState(initial){const i=hookIndex++;hooks[i]??={value:initial};return [hooks[i].value,value=>{if(!Object.is(hooks[i].value,value)){hooks[i].value=value;dirty=true;}}];},
 useLayoutEffect(effect,deps){const i=hookIndex++,previous=hooks[i];if(!previous||deps.some((d,j)=>!Object.is(d,previous.deps[j]))){hooks[i]={deps,cleanup:previous?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=effect();});}},
};
const jsx=(type,props)=>({type,props});
function makeCanvas(){
 const ops=[],context={ops};
 for(const name of ['setTransform','clearRect','save','restore','translate','scale','beginPath','moveTo','lineTo','closePath','arc','fill','stroke','drawImage'])context[name]=(...args)=>ops.push([name,...args]);
 const canvas={width:1000,height:620,clientWidth:1000,clientHeight:620,style:{},getContext:()=>context,context};
 canvas.ownerDocument={createElement(){const target=makeCanvas();made.push(target);return target;}};return canvas;
}
const canvas=makeCanvas();
global.window={devicePixelRatio:1};
global.ResizeObserver=class{constructor(callback){resizeCallback=callback;}observe(){}disconnect(){}};
global.requestAnimationFrame=callback=>{const id=++nextFrame;raf.set(id,callback);allCallbacks.push(callback);return id;};
global.cancelAnimationFrame=id=>raf.delete(id);
let pathAllocations=0;
global.Path2D=class{constructor(d){this.d=d;pathAllocations++;}};
const filename=path.join(ROOT,'components/districting/michigan-map-canvas.tsx'),m=new Module(filename,module);
m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));
m.require=specifier=>specifier==='react'?React:specifier==='react/jsx-runtime'?{jsx,jsxs:jsx,Fragment:'fragment'}:specifier.startsWith('@/')?loadTs(specifier.slice(2)+'.ts'):rootRequire(specifier);
m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX},fileName:filename}).outputText,filename);
const Component=m.exports.MichiganBlockCanvas;
function visit(node){if(!node||typeof node!=='object')return;if(node.type==='canvas')node.props.ref.current=canvas;for(const child of [node.props?.children].flat())visit(child);}
function render(next=props){props=next;for(let i=0;i<20;i++){dirty=false;hookIndex=0;tree=Component(props);visit(tree);while(effects.length)effects.shift()();if(!dirty)return;}throw Error('Render loop');}
function settle(){for(let i=0;raf.size&&i<100;i++){const callbacks=[...raf.values()];raf.clear();for(const fn of callbacks)fn();if(dirty)render();}assert.equal(raf.size,0);}
function unmount(){for(const hook of hooks)hook?.cleanup?.();}
const identity=rootRequire('d3-geo').geoIdentity(),projection={stream:identity.stream.bind(identity),projectPoint:p=>p};
const shapes=[100,400,800,1100].map((x,i)=>({feature:{type:'Feature',properties:{district_id:i,geoid:String(i)},geometry:{type:'Polygon',coordinates:[]}},bounds:[[x,100],[x+50,150]],d:`block-${i}`}));
props={shapes:shapes.slice(0,3),view:{x:0,y:0,k:1},projection,clip:undefined,outlinesOnly:false,complete:true,appearanceKey:'26-13:land:solid'};
const publications=()=>canvas.context.ops.filter(op=>op[0]==='drawImage');
const fills=target=>target.context.ops.filter(op=>op[0]==='fill'&&op[1]instanceof Path2D).map(op=>op[1].d);
"""


def test_canvas_keeps_old_coverage_then_publishes_cached_new_area_while_pending(tmp_path):
    run_node(tmp_path, CANVAS_HOST + r"""
render();assert.equal(canvas.style.visibility,'hidden');settle();
assert.equal(publications().length,1);assert.deepEqual(fills(publications()[0][1]),['block-0','block-1','block-2']);
const cachedOverlap=[shapes[1],shapes[2],shapes[3]];
render({...props,shapes:cachedOverlap,view:{x:-250,y:0,k:1},complete:false});
assert.equal(canvas.style.visibility,'visible');assert.equal(canvas.style.transform,'translate(-250px, 0px) scale(1)');
assert.equal(publications().length,1,'Prior bitmap remains until new cached overlap is fully drawn');
settle();assert.equal(publications().length,2);
assert.deepEqual(fills(publications()[1][1]),['block-1','block-2','block-3'],'Cached new-area block appears even while an unrelated required chunk is missing');
assert.equal(canvas.style.visibility,'visible');assert.equal(canvas.style.transform,'none');
const count=publications().length,allocations=pathAllocations;
render({...props});settle();assert.equal(publications().length,count,'Loading/error status rerenders with stable shapes must not redraw');
assert.equal(pathAllocations,allocations,'Prepared paths retain identity');
render({...props,complete:true});assert.equal(canvas.style.visibility,'visible');settle();
assert.equal(publications().length,count+1,'Completed group is published in one frame');unmount();
""")


def test_canvas_rapid_pending_pans_cancel_old_draws_and_keep_geographic_alignment(tmp_path):
    run_node(tmp_path, CANVAS_HOST + r"""
render();settle();const initial=publications().length;
render({...props,view:{x:-250,y:0,k:1},complete:false});const obsolete=allCallbacks.at(-1);
render({...props,view:{x:-500,y:0,k:1},complete:false});
assert.equal(canvas.style.transform,'translate(-500px, 0px) scale(1)','Transform derives from last published view, not pending pan');
obsolete();assert.equal(publications().length,initial,'Canceled RAF cannot publish stale coverage');
settle();assert.equal(publications().length,initial+1);
// No cached overlap at all: preserve intersecting old pixels and expose base
// map outside their transformed rectangle, rather than clearing the canvas.
render({...props,shapes:[],view:{x:-700,y:0,k:1},complete:false});
assert.equal(canvas.style.visibility,'visible');assert.equal(canvas.style.transform,'translate(-200px, 0px) scale(1)');
assert.equal(raf.size,0);
render({...props,view:{x:-2000,y:0,k:1}});assert.equal(canvas.style.visibility,'hidden','Disjoint old coverage cannot be reused');
unmount();
""")


def test_canvas_style_resize_and_exit_never_publish_stale_or_unmasked_frames(tmp_path):
    run_node(tmp_path, CANVAS_HOST + r"""
render();settle();
const mask=collection([polygon([[0,0],[500,0],[500,620],[0,620],[0,0]],'26')]);
render({...props,clip:mask,complete:false,appearanceKey:'26-13:land:density',outlinesOnly:true});
assert.equal(canvas.style.visibility,'hidden','Old pixels have the wrong mask/style');
settle();const masked=publications().at(-1)[1];assert.ok(masked.context.ops.some(op=>op[0]==='fill'&&op[1]==='evenodd'),'Cached overlap receives the common land mask before publication');
assert.deepEqual(fills(masked),[],'Outline-only cached redraw must not retain old district fills');
canvas.clientWidth=500;canvas.clientHeight=310;resizeCallback();
assert.equal(canvas.style.visibility,'hidden','Old responsive backing dimensions are incompatible');
assert.equal(canvas.width,500);assert.equal(canvas.height,310);settle();assert.equal(canvas.style.visibility,'visible');
render({...props,view:{x:-100,y:0,k:1}});const late=allCallbacks.at(-1),count=publications().length;
unmount();late();assert.equal(publications().length,count,'Unmount cancels pending block publication');
""")
