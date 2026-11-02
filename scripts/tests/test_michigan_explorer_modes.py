"""Exercise the real explorer's handlers and effects without a browser or map cache.

The small hook host runs only MichiganExplorer. Child drawing components remain
JSX descriptors; their geometry/viewport props and the parent resource lifecycle
are observable. Deferred network responses deliberately ignore AbortSignal so
the tests cover stale completion guards as well as transport cancellation.
"""
from test_block_demo_integration_contract import run_node


HOOK_HOST = r"""
const hooks = [];
let position = 0, dirty = true, tree;
const pendingEffects = new Set();
const same = (a,b) => a && b && a.length===b.length && a.every((v,i)=>Object.is(v,b[i]));
function hookSlot(kind, create) {
 const index=position++;
 if(!hooks[index]) hooks[index]={kind,...create()};
 assert.equal(hooks[index].kind,kind,'Stable hook order');
 return hooks[index];
}
const React = {
 useState(initial) {const slot=hookSlot('state',()=>({value:typeof initial==='function'?initial():initial}));return [slot.value, value=>{const next=typeof value==='function'?value(slot.value):value;if(!Object.is(next,slot.value)){slot.value=next;dirty=true;}}];},
 useRef(initial) {return hookSlot('ref',()=>({value:{current:initial}})).value;},
 useMemo(factory,deps) {const slot=hookSlot('memo',()=>({deps:undefined}));if(!same(slot.deps,deps)){slot.value=factory();slot.deps=deps;}return slot.value;},
 useCallback(callback,deps) {return this.useMemo(()=>callback,deps);},
 useEffect(effect,deps) {const index=position,slot=hookSlot('effect',()=>({deps:undefined,cleanup:undefined}));if(!same(slot.deps,deps)){slot.deps=deps;slot.effect=effect;pendingEffects.add(index);}},
};
// Keep descriptors inert, including canvas children. Real component handlers,
// projections, validators, asset fetchers and effect bodies run unmodified.
const jsx = (type,props,key) => ({type,key,props:props??{}});
const jsxRuntime={jsx,jsxs:jsx,Fragment:Symbol('fragment')};
const uiModules=new Map();
const blockPreparations=new Map();
const blockBoundsPreparations=new Map();
const d3Geo=rootRequire('d3-geo');
const observedD3={...d3Geo,geoPath(...args){const result=d3Geo.geoPath(...args);return new Proxy(result,{
 apply(target,thisArg,callArgs){const geoid=callArgs[0]?.properties?.geoid;if(/^\d{15}$/.test(geoid??''))blockPreparations.set(geoid,(blockPreparations.get(geoid)??0)+1);return Reflect.apply(target,thisArg,callArgs);},
 get(target,key){if(key==='bounds')return feature=>{const geoid=feature?.properties?.geoid;if(/^\d{15}$/.test(geoid??''))blockBoundsPreparations.set(geoid,(blockBoundsPreparations.get(geoid)??0)+1);return target.bounds(feature);};return Reflect.get(target,key);},
 });}};
const comparisonState={data:null,error:null,retry(){}};
const comparisonModule={
 useComparisonLayer:(state,kind,asset,enabled)=>({...comparisonState,data:enabled&&kind==='counties'?countyGeometry:null}),
 ComparisonBoundaries(){},ComparisonLayerControl(){},DensityCanvas(){},DensityLegend(){},
};
function loadUi(relative) {
 const filename=path.isAbsolute(relative)?relative:path.join(ROOT,relative);
 if(uiModules.has(filename))return uiModules.get(filename).exports;
 const m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));uiModules.set(filename,m);
 m.require=specifier=>{
  if(specifier==='react')return React;
  if(specifier==='react/jsx-runtime')return jsxRuntime;
  if(specifier==='d3-geo')return observedD3;
  if(specifier==='./block-comparison-layers')return comparisonModule;
  if(specifier==='./michigan-map-canvas')return {MichiganBlockCanvas(){}};
  if(specifier.startsWith('@/')||specifier.startsWith('.')){
   const base=specifier.startsWith('@/')?path.join(ROOT,specifier.slice(2)):path.resolve(path.dirname(filename),specifier);
   for(const suffix of ['.ts','.tsx'])if(fs.existsSync(base+suffix))return loadUi(base+suffix);
  }
  return rootRequire(specifier);
 };
 const output=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX},fileName:filename});
 m._compile(output.outputText,filename);return m.exports;
}
let nextTimer=0;
const timers=new Map();
global.setTimeout=callback=>{const id=++nextTimer;timers.set(id,callback);return id;};
global.clearTimeout=id=>timers.delete(id);
global.requestAnimationFrame=global.setTimeout;
global.cancelAnimationFrame=global.clearTimeout;
const capturedPointers=new Set(),listeners=new Map();
const svgElement={getBoundingClientRect:()=>({left:0,top:0,width:1000,height:620}),focus(){},
 setPointerCapture:id=>capturedPointers.add(id),hasPointerCapture:id=>capturedPointers.has(id),releasePointerCapture:id=>capturedPointers.delete(id),
 addEventListener:(kind,callback)=>listeners.set(kind,callback),removeEventListener:(kind,callback)=>{if(listeners.get(kind)===callback)listeners.delete(kind);}};
function render(){position=0;dirty=false;tree=Explorer(props);assert.equal(position,hooks.length);for(const node of nodes())if(node.type==='svg'&&node.props.ref)node.props.ref.current=svgElement;const effects=[...pendingEffects];pendingEffects.clear();for(const index of effects){const slot=hooks[index];slot.cleanup?.();slot.cleanup=slot.effect();}}
async function flush(){for(let turns=0;turns<80;turns++){if(dirty)render();await Promise.resolve();await Promise.resolve();if(dirty)continue;if(timers.size){const queued=[...timers];timers.clear();for(const [,callback]of queued)callback();continue;}let changed=false;for(let i=0;i<8;i++){await Promise.resolve();if(dirty||timers.size){changed=true;break;}}if(!changed)return;}throw Error('Hook host did not settle');}
function nodes(node){if(arguments.length===0)node=tree;if(node===null||node===undefined||typeof node==='boolean')return [];if(Array.isArray(node))return node.flatMap(n=>nodes(n));if(typeof node!=='object')return [];return [node,...nodes(node.props?.children)];}
function textContent(node){if(node===null||node===undefined||typeof node==='boolean')return '';if(Array.isArray(node))return node.map(textContent).join('');if(typeof node!=='object')return String(node);return textContent(node.props?.children);}
function one(predicate){const found=nodes().filter(predicate);assert.equal(found.length,1,`Expected one node, got ${found.length}`);return found[0];}
function control(label){return one(n=>n.props?.['aria-label']===label);}
function button(label){return one(n=>n.type==='button'&&(n.props['aria-label']===label||textContent(n)===label));}
function checkbox(label){return nodes(one(n=>n.type==='label'&&textContent(n)===label)).find(n=>n.type==='input'&&n.props.type==='checkbox');}
async function click(label){const found=button(label);assert.notEqual(found.props.disabled,true,`${label} is enabled`);found.props.onClick();await flush();}
async function chooseDistrict(id){control('Explore computed district').props.onChange({target:{value:String(id)}});await flush();}
async function chooseCounty(name){control('Find a county by name').props.onChange({target:{value:name}});await flush();await click(`${name} County`);}
async function enableBlocks(){await zoomTo(8);if(button('Blocks').props['aria-pressed']!==true)await click('Blocks');}
async function zoomTo(target,anchor=[500,310]){for(let tries=0;tries<80;tries++){const current=renderedView().k;if(Math.abs(current-target)<1e-7)return;const deltaY=Math.max(-120,Math.min(120,-Math.log(target/current)/0.0025));assert.ok(listeners.has('wheel'));listeners.get('wheel')({deltaY,clientX:anchor[0],clientY:anchor[1],ctrlKey:false,metaKey:false,preventDefault(){}});await flush();}throw Error(`Could not reach zoom ${target}`);}
async function centerOn(coordinates){const projection=loadUi('lib/block-map-projection.ts').makeStateBlockProjection(overviewDocument,'26'),point=projection.projectPoint(coordinates),view=renderedView();const event={button:0,pointerId:3,clientX:500,clientY:310,currentTarget:svgElement,preventDefault(){}};interactive().props.onPointerDown(event);interactive().props.onPointerMove({...event,clientX:1000-(point[0]*view.k+view.x),clientY:620-(point[1]*view.k+view.y)});interactive().props.onPointerUp({...event,clientX:1000-(point[0]*view.k+view.x),clientY:620-(point[1]*view.k+view.y)});await flush();}
async function mapClick(coordinates){const projection=loadUi('lib/block-map-projection.ts').makeStateBlockProjection(overviewDocument,'26'),point=projection.projectPoint(coordinates),view=renderedView();const event={button:0,pointerId:4,clientX:point[0]*view.k+view.x,clientY:point[1]*view.k+view.y,currentTarget:svgElement,preventDefault(){}};interactive().props.onPointerDown(event);interactive().props.onPointerUp(event);await flush();}
const map=()=>one(n=>n.props?.['data-map-inspection']!==undefined);
const selection=()=>one(n=>n.props?.['data-selected-district']!==undefined).props;
const interactive=()=>one(n=>n.type==='svg'&&n.props.role==='application');
function renderedView(){const g=one(n=>n.type==='svg'&&n.props['aria-hidden']==='true').props.children;const match=/translate\(([-\d.e]+) ([-\d.e]+)\) scale\(([-\d.e]+)\)/.exec(g.props.transform);assert.ok(match);return {x:Number(match[1]),y:Number(match[2]),k:Number(match[3])};}
const asset=(name)=>({url:`/${name}`,bytes:1,gzipBytes:1,sha256:'fixture'});
const ring=(west,south,size=0.4)=>[[west,south],[west+size,south],[west+size,south+size],[west,south+size],[west,south]];
const districtFeature=(id,coordinates)=>({type:'Feature',properties:{district_id:id,state_fips:'26'},geometry:{type:'Polygon',coordinates:[coordinates]}});
const overviewDocument=collection([districtFeature(0,ring(-86,42,0.6)),districtFeature(1,ring(-85,42,1))]);
const fineDocument={...structuredClone(overviewDocument),marker:'fine geometry'};
const censusDocument={...structuredClone(overviewDocument),marker:'generalized census geometry'};
const countyGeometry=collection([{type:'Feature',properties:{geoid:'26081',name:'Kent'},geometry:{type:'Polygon',coordinates:[ring(-86,42,0.6)]}},
 {type:'Feature',properties:{geoid:'26163',name:'Wayne'},geometry:{type:'Polygon',coordinates:[ring(-85,42,1)]}}]);
const blocks=(fips,base)=>collection([
 {type:'Feature',properties:{geoid:`26${fips}0001001001`,population:60,district_id:0},geometry:{type:'Polygon',coordinates:[ring(base,42,0.2)]}},
 {type:'Feature',properties:{geoid:`26${fips}0001001002`,population:40,district_id:1},geometry:{type:'Polygon',coordinates:[ring(base+0.3,42,0.2)]}},
]);
const countyDocuments={'081':blocks('081',-86),'163':blocks('163',-85)};
const summaryDocument={planId:'26-2',stateFips:'26',residentPopulation:200,blockCount:4,
 counties:[['081','Kent',-86],['163','Wayne',-85]].map(([fips,name,west])=>({fips,name,population:100,blockCount:2,bbox:[west,42,west+1,43],districtShares:[{districtId:0,population:60,blockCount:1,percent:60},{districtId:1,population:40,blockCount:1,percent:40}]})),
 districts:[{districtId:0,population:120,blockCount:2,countyFips:['081','163']},{districtId:1,population:80,blockCount:2,countyFips:['081','163']}]};
const indexDocument={planId:'26-2',counties:summaryDocument.counties.map(c=>({fips:c.fips,population:c.population,blockCount:c.blockCount,asset:asset(`county-${c.fips}`)}))};
const props={plan:{id:'26-2',stateFips:'26',houseSizes:[435],districtCount:2,residentPopulation:200,blockCount:4,districtPopulations:[120,80],maxDeviationPeople:20,recordedLinkCount:0,assets:{national:asset('census-overview'),state:asset('census'),full:asset('exact'),detailIndex:asset('index')}},
 comparisonLayers:{counties:{asset:asset('county-reference')}},landDisplay:{state:asset('fine'),national:asset('old-overview')},
 explorer:{overview:asset('overview'),coast:asset('coast'),dividers:asset('dividers'),detailDividers:asset('detail-dividers'),summary:asset('summary'),spatialIndex:asset('spatial-index')},cities:asset('cities')};
const documents=new Map([['/overview',overviewDocument],['/coast',collection([])],['/dividers',collection([])],['/detail-dividers',collection([])],['/fine',fineDocument],['/census-overview',censusDocument],['/census',censusDocument],['/exact',fineDocument],['/summary',summaryDocument],['/index',indexDocument],['/county-081',countyDocuments['081']],['/county-163',countyDocuments['163']]]);
documents.set('/cities',collection([]));
// One synthetic spatial chunk per fixture county keeps navigation fixtures
// readable. Dedicated spatial tests cover multiple chunks, overlap and LRU.
const spatialIndexDocument={schemaVersion:1,planId:'26-2',stateFips:'26',
 get totalBlockCount(){return props.plan.blockCount;},get totalPopulation(){return props.plan.residentPopulation;},
 get counties(){return summaryDocument.counties.map(({fips,blockCount,population})=>({fips,blockCount,population}));},
 get chunks(){return summaryDocument.counties.map(c=>({chunkId:c.fips,bbox:c.bbox,blockCount:c.blockCount,population:c.population,asset:asset(`county-${c.fips}`)}));}};
documents.set('/spatial-index',spatialIndexDocument);
const requests=[],deferredUrls=new Set();
global.fetch=(url,options={})=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});const job={url,signal:options.signal,settled:false,resolveDocument(document){job.settled=true;resolve({ok:true,status:200,json:async()=>document});},reject(reason){job.settled=true;reject(reason);}};requests.push(job);assert.ok(documents.has(url),`Unexpected request ${url}`);if(!deferredUrls.has(url))job.resolveDocument(documents.get(url));return promise;};
const {MichiganExplorer:Explorer}=loadUi('components/districting/michigan-explorer.tsx');
const stateValues=()=>hooks.filter(h=>h.kind==='state'||h.kind==='ref').map(h=>h.value);
function containsIdentity(root,target,seen=new Set()){if(root===target)return true;if(!root||typeof root!=='object'||seen.has(root))return false;seen.add(root);if(root instanceof Map)return [...root.values()].some(v=>containsIdentity(v,target,seen));return Object.values(root).some(v=>containsIdentity(v,target,seen));}
function retained(target){return stateValues().some(v=>containsIdentity(v,target));}
const countyCaches=()=>hooks.filter(h=>h.kind==='ref').map(h=>h.value.current instanceof Map?h.value.current:h.value.current?.cache).filter(value=>value instanceof Map);
await flush();
"""


def test_inspection_zoom_limits_preserve_pointer_anchor(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts');
const simple={min:1,max:256},blocks={min:6,max:256};
const anchor=[243,178],rect={left:0,top:0,width:1000,height:620},start={x:-300,y:-170,k:8};
const point=h.mapPoint(anchor,rect,start);
for(const limits of [simple,blocks])for(const factor of [0.001,0.5,1.5,1000]){
 const next=h.zoomAt(start,factor,anchor,limits);assert.ok(next.k>=limits.min&&next.k<=256);
 const actual=h.mapPoint(anchor,rect,next);close(actual[0],point[0]);close(actual[1],point[1]);
}
for(const factor of [NaN,Infinity,0,-1])assert.equal(h.zoomAt(start,factor,anchor,blocks),start);
""")


def test_districts_and_counties_stay_simplified_at_every_zoom_and_selection(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
assert.equal(map().props['data-map-inspection'],'districts');assert.equal(map().props['data-zoom-min'],1);assert.equal(map().props['data-zoom-max'],256);
assert.notEqual(button('Blocks').props.disabled,true);
await chooseDistrict(0);assert.equal(map().props['data-inspection-target'],'districts');assert.equal(map().props['data-zoom-min'],1);
await click('Counties');await chooseCounty('Kent');assert.equal(map().props['data-inspection-target'],'counties');
await zoomTo(256);assert.equal(map().props['data-boundary-detail'],'simplified');
await zoomTo(1);assert.equal(map().props['data-map-level'],'county');
assert.equal(map().props['data-retained-detail-assets'],0);assert.equal(map().props['data-cached-chunks'],0);
assert.ok(!requests.some(r=>r.url==='/fine'||r.url==='/spatial-index'||r.url==='/detail-dividers'||r.url.startsWith('/county-')));
checkbox('Full census extent').props.onChange({target:{checked:true}});await flush();
assert.equal(checkbox('Exact district outlines Blocks + full census extent').props.disabled,true);
assert.ok(requests.some(r=>r.url==='/census-overview'));assert.ok(!requests.some(r=>['/fine','/census','/exact','/detail-dividers'].includes(r.url)));
assert.equal(nodes().filter(n=>n.type==='button'&&textContent(n)==='Exit detail view').length,0);
""")


def test_blocks_enter_at_seven_then_selection_and_back_preserve_inspection_and_six_floor(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
await click('Blocks');close(renderedView().k,7);assert.equal(map().props['data-zoom-min'],6);assert.equal(map().props['data-zoom-max'],256);
await chooseDistrict(0);await chooseCounty('Kent');assert.equal(map().props['data-inspection-target'],'blocks');assert.equal(map().props['data-zoom-min'],6);
control('Find a census block by GEOID').props.onChange({target:{value:'260810001001001'}});await flush();await click('Block 260810001001001 · 60 residents');
assert.equal(selection()['data-selected-block'],'260810001001001');assert.equal(map().props['data-zoom-min'],6);
await zoomTo(6);assert.equal(map().props['data-map-level'],'block');
await click('Back');assert.equal(map().props['data-map-level'],'county');await click('Back');assert.equal(map().props['data-map-level'],'district');
assert.equal(map().props['data-inspection-target'],'blocks');assert.equal(map().props['data-zoom-min'],6);
await click('Michigan');assert.equal(map().props['data-map-level'],'state');assert.equal(map().props['data-inspection-target'],'blocks');close(renderedView().k,6);
await click('Reset view');assert.equal(map().props['data-inspection-target'],'districts');assert.deepEqual(renderedView(),{x:0,y:0,k:1});
""")


def test_leaving_blocks_releases_detail_and_pending_motion_without_resetting_camera(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
await chooseCounty('Kent');await enableBlocks();
assert.equal(retained(fineDocument),true);assert.equal(retained(countyDocuments['081']),true);
control('Find a census block by GEOID').props.onChange({target:{value:'260810001001001'}});await flush();await click('Block 260810001001001 · 60 residents');
const before=renderedView();
const event={button:0,pointerId:7,clientX:400,clientY:250,currentTarget:svgElement,preventDefault(){}};
interactive().props.onPointerDown(event);interactive().props.onPointerMove({...event,clientX:470,clientY:280});
assert.ok(capturedPointers.has(7));button('Counties').props.onClick();assert.equal(capturedPointers.size,0);await flush();
assert.deepEqual(renderedView(),{...before,x:before.x+70,y:before.y+30});
assert.equal(map().props['data-inspection-target'],'counties');assert.equal(selection()['data-selected-block'],'');assert.equal(selection()['data-selected-county'],'081');
assert.equal(map().props['data-retained-detail-assets'],0);assert.equal(map().props['data-cached-chunks'],0);assert.equal(map().props['data-block-chunks'],0);
assert.equal(retained(fineDocument),false);assert.equal(retained(countyDocuments['081']),false);assert.ok(countyCaches().every(c=>c.size===0));
assert.equal(nodes().filter(n=>n.props?.shapes?.some?.(s=>s.feature?.properties?.geoid)).length,0);
""")


def test_late_fine_response_cannot_replace_reentered_block_session_and_base_stays_visible(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
deferredUrls.add('/fine');await click('Blocks');
const old=requests.filter(r=>r.url==='/fine').at(-1);assert.ok(old&&!old.signal.aborted);
assert.equal(map().props['data-boundary-detail'],'simplified');
assert.ok(nodes(one(n=>n.type==='svg'&&n.props['aria-hidden']==='true')).some(n=>n.type==='path'),'Simplified fill stays visible during upgrade');
await click('Counties');assert.equal(old.signal.aborted,true);await click('Blocks');
const fresh=requests.filter(r=>r.url==='/fine').at(-1);assert.notEqual(fresh,old);
const newest={...structuredClone(fineDocument),marker:'new block session'};
fresh.resolveDocument(newest);await flush();old.resolveDocument(fineDocument);await flush();
assert.equal(retained(fineDocument),false);assert.equal(retained(newest),true);
await click('Districts');assert.equal(retained(newest),false);assert.equal(map().props['data-retained-detail-assets'],0);
""")


def test_chunks_loaded_before_fine_mask_cannot_be_picked_or_searched_until_visible(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
deferredUrls.add('/fine');await chooseCounty('Kent');await click('Blocks');
assert.equal(map().props['data-block-batch-ready'],true);assert.ok(map().props['data-block-chunks']>0);
assert.equal(map().props['data-boundary-detail'],'simplified');
assert.equal(control('Find a census block by GEOID').props.disabled,true);
control('Find a census block by GEOID').props.onChange({target:{value:'260810001001001'}});await flush();
assert.equal(nodes().filter(n=>n.type==='button'&&textContent(n).startsWith('Block 260810001001001')).length,0);
await mapClick([-85.9,42.1]);assert.equal(selection()['data-selected-block'],'','Invisible blocks cannot be selected through the simplified mask');
requests.filter(r=>r.url==='/fine').at(-1).resolveDocument(fineDocument);await flush();
assert.equal(control('Find a census block by GEOID').props.disabled,false);
assert.equal(nodes().filter(n=>n.type==='button'&&textContent(n).startsWith('Block 260810001001001')).length,1);
await mapClick([-85.9,42.1]);assert.equal(selection()['data-selected-block'],'260810001001001');
""")


def test_late_spatial_response_cannot_repopulate_after_leaving_blocks_and_reentry(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
deferredUrls.add('/county-081');await chooseCounty('Kent');await enableBlocks();
const old=requests.filter(r=>r.url==='/county-081').at(-1);assert.ok(old&&!old.signal.aborted);
await click('Counties');assert.equal(old.signal.aborted,true);old.resolveDocument(countyDocuments['081']);await flush();
assert.equal(retained(countyDocuments['081']),false);assert.equal(map().props['data-cached-chunks'],0);
await click('Blocks');const fresh=requests.filter(r=>r.url==='/county-081').at(-1);assert.notEqual(fresh,old);
const newest={...structuredClone(countyDocuments['081']),marker:'new chunk session'};fresh.resolveDocument(newest);await flush();assert.equal(retained(newest),true);
await click('Districts');assert.equal(retained(newest),false);assert.equal(map().props['data-cached-chunks'],0);
""")


def test_extent_changes_do_not_change_camera_or_selection_zoom_floor(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
await chooseCounty('Kent');await enableBlocks();
control('Find a census block by GEOID').props.onChange({target:{value:'260810001001001'}});await flush();await click('Block 260810001001001 · 60 residents');
const selectedView=renderedView();checkbox('Full census extent').props.onChange({target:{checked:true}});await flush();
assert.equal(map().props['data-zoom-min'],6);assert.deepEqual(renderedView(),selectedView);assert.equal(selection()['data-selected-block'],'260810001001001');
const exact=checkbox('Exact district outlines Blocks + full census extent');assert.equal(exact.props.disabled,false);exact.props.onChange({target:{checked:true}});await flush();assert.ok(requests.some(r=>r.url==='/exact'));
await click('Counties');assert.equal(map().props['data-zoom-min'],1);assert.equal(map().props['data-retained-detail-assets'],0);assert.equal(map().props['data-cached-chunks'],0);
assert.equal(checkbox('Exact district outlines Blocks + full census extent').props.checked,false);assert.equal(checkbox('Exact district outlines Blocks + full census extent').props.disabled,true);
assert.equal(selection()['data-selected-block'],'');assert.equal(selection()['data-selected-county'],'081');await zoomTo(1);
""")


def test_searching_unrelated_county_clears_district_context_without_switching_inspection(tmp_path):
    run_node(tmp_path, HOOK_HOST + r"""
summaryDocument.counties[1].districtShares=[{districtId:1,population:100,blockCount:2,percent:100}];
summaryDocument.districts=[{districtId:0,population:60,blockCount:1,countyFips:['081']},{districtId:1,population:140,blockCount:3,countyFips:['081','163']}];
props.plan.districtPopulations=[60,140];props.plan.maxDeviationPeople=40;for(const feature of countyDocuments['163'].features)feature.properties.district_id=1;
loadUi('lib/michigan-map-interaction.ts').validateMichiganSummary(summaryDocument,props.plan);
await chooseDistrict(0);await chooseCounty('Wayne');
assert.equal(selection()['data-selected-district'],'');assert.equal(selection()['data-selected-county'],'163');assert.equal(map().props['data-inspection-target'],'districts');
assert.equal(button('Back').props.disabled,true);assert.equal(one(n=>n.props.label==='Selected district context').props.value,'All districts');
assert.equal(map().props['data-cached-chunks'],0);assert.equal(map().props['data-retained-detail-assets'],0);
""")
