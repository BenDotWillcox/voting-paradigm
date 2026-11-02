"""Prepared national SVG reuse, isolated interaction, and bounded retention."""
from test_block_demo_integration_contract import run_node
from test_national_all_state_land_runtime import AGGREGATE_HOST


INSTRUMENT = r"""
const renderHelper=loadUi('lib/block-national-render.ts');
let preparationCount=0;
const originalPrepare=renderHelper.prepareNationalMap;
renderHelper.prepareNationalMap=(...args)=>{preparationCount++;return originalPrepare(...args)};
const stateButton=name=>one(n=>n.type==='g'&&n.props.role==='button'&&n.props['aria-label'].startsWith(name+','));
const diagnostic=()=>one(n=>n.props?.['data-national-prepared-cache']!==undefined).props;
async function remount(cap=props.houseSize){
 for(const slot of hooks)slot.cleanup?.();hooks.length=0;pendingEffects.clear();memoChildren.clear();
 props.houseSize=cap;dirty=true;tree=undefined;await flush();
}
"""


def test_hover_reuses_every_district_and_static_layer_and_preserves_focus(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + INSTRUMENT + r"""
await flush();assert.equal(preparationCount,1);
const initialPaths=nodes().filter(n=>n.type==='path'),initialFills=districtPaths('26');
const staticWater=layer('michigan-interior-water')[0],staticConnections=layer('derived-water-connections')[0];
memoRenders.length=0;stateButton('Michigan').props.onMouseEnter();await flush();
assert.deepEqual(memoRenders,[{name:'NationalStateButton',key:'26'},{name:'NationalStateBorder',key:'26'}]);
assert.equal(preparationCount,1);assert.equal(districtPaths('26')[0],initialFills[0]);
assert.equal(layer('michigan-interior-water')[0],staticWater);assert.equal(layer('derived-water-connections')[0],staticConnections);
assert.equal(layer('state-district-fills').find(n=>n.props['data-state']==='26').props.fillOpacity,1);
assert.equal(districtPaths('26')[0].props.fillOpacity,undefined,'Opacity is inherited per path, not composited on the whole state');
memoRenders.length=0;stateButton('Ohio').props.onMouseEnter();await flush();
assert.deepEqual(memoRenders.filter(r=>r.name==='NationalStateButton').map(r=>r.key).sort(),['26','39']);
assert.ok(memoRenders.every(r=>['NationalStateButton','NationalStateBorder'].includes(r.name)));
assert.equal(preparationCount,1);
stateButton('Ohio').props.onMouseLeave();stateButton('Alaska').props.onFocus();await flush();
stateButton('Alaska').props.onMouseLeave();await flush();
assert.equal(stateButton('Alaska').props['data-state-highlighted'],true,'Keyboard focus survives pointer departure');
stateButton('Michigan').props.onMouseEnter();await flush();
assert.equal(stateButton('Alaska').props['data-state-highlighted'],true);assert.equal(stateButton('Michigan').props['data-state-highlighted'],true);
stateButton('Michigan').props.onMouseLeave();stateButton('Alaska').props.onBlur();await flush();
assert.equal(stateButton('Alaska').props['data-state-highlighted'],false);
let prevented=0;stateButton('Alaska').props.onKeyDown({key:' ',preventDefault(){prevented++}});
stateButton('Alaska').props.onKeyDown({key:'Enter',preventDefault(){prevented++}});
stateButton('Alaska').props.onKeyDown({key:'x',preventDefault(){prevented++}});
stateButton('Alaska').props.onClick();assert.equal(prevented,2);assert.deepEqual(selected,['02','02','02']);
assert.equal(nodes(stateButton('Alaska')).filter(n=>n.props?.['data-layer']==='state-inset').length,1);
assert.equal(nodes().filter(n=>n.props?.role==='button').length,3,'One target per fixture state');
assert.equal(preparationCount,1);assert.equal(initialPaths.length,nodes().filter(n=>n.type==='path').length);
const updatedSelection=[];props.onSelectState=state=>updatedSelection.push(state);dirty=true;await flush();
stateButton('Alaska').props.onClick();assert.deepEqual(updatedSelection,['02'],'Memoized state actions use the current parent callback');
assert.equal(preparationCount,1);
""")


def test_prepared_views_survive_remount_and_census_toggle_but_invalidate_new_content(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + INSTRUMENT + r"""
await flush();const originalFill=districtPaths('26')[0].props.d;assert.equal(preparationCount,1);
assert.equal(diagnostic()['data-national-prepared-cache'],'miss');const requestsBefore=requests.length;
await remount();assert.equal(preparationCount,1);assert.equal(requests.length,requestsBefore);
assert.equal(diagnostic()['data-national-prepared-cache'],'hit');
await extent(true);assert.equal(preparationCount,2);assert.notEqual(districtPaths('26')[0].props.d,originalFill);
await extent(false);assert.equal(preparationCount,2);assert.equal(districtPaths('26')[0].props.d,originalFill);
assert.equal(diagnostic()['data-national-prepared-cache'],'hit');
await extent(true);await remount();assert.equal(checkbox('Full census extent').props.checked,false,'Anchor remount keeps the land-default reset');
assert.equal(preparationCount,2);assert.equal(districtPaths('26')[0].props.d,originalFill);
const newDescriptor=structuredClone(manifest.landAnchors['435']);
for(const kind of ['outlines','coast','dividers','connections','recordedConnections']){
 const old=newDescriptor[kind];newDescriptor[kind]={...old,url:old.url+'-national',sha256:'new-'+kind};
 documents.set(newDescriptor[kind].url,structuredClone(documents.get(old.url)));
}
manifest.nationalLandAnchors={'435':newDescriptor};dirty=true;await flush();
assert.equal(preparationCount,3);assert.equal(diagnostic()['data-national-prepared-cache'],'miss');
assert.ok(requests.some(r=>r.url==='/all-435-outlines-national'),'National-only assets take precedence');
assert.equal(districtPaths('26')[0].props.d,originalFill,'An unchanged geometry still has exactly the same paths');
await remount(574);assert.equal(preparationCount,4);await remount(435);assert.equal(preparationCount,4);
""")


def test_failed_border_preparation_is_not_cached_as_a_complete_map(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + INSTRUMENT + r"""
const originalFetch=global.fetch;
global.fetch=async(url,options)=>url==='/state-boundaries'?{ok:false,status:503}:originalFetch(url,options);
await flush();assert.equal(preparationCount,1);assert.equal(districtPaths('26').length,2);
assert.equal(boundaryPaths('26').length,0);assert.equal(diagnostic()['data-national-prepared-cache'],'miss');
global.fetch=originalFetch;await click('Retry borders');
assert.equal(preparationCount,2);assert.equal(boundaryPaths('26').length,2);
await remount();assert.equal(preparationCount,2);assert.equal(diagnostic()['data-national-prepared-cache'],'hit');
""")


def test_late_anchor_response_never_populates_prepared_cache(tmp_path):
    run_node(tmp_path, AGGREGATE_HOST + INSTRUMENT + r"""
for(const kind of ['outlines','coast','dividers','connections','recordedConnections'])deferredUrls.add(`/all-435-${kind}`);
await flush();assert.equal(preparationCount,0);const old=requests.filter(r=>r.url.startsWith('/all-435-'));
await anchor(574);assert.equal(preparationCount,1);assert.equal(diagnostic()['data-national-prepared-cache'],'miss');
for(const request of old)request.resolveDocument(documents.get(request.url));await flush();
assert.equal(preparationCount,1);assert.equal(districtPaths('26').length,3);
deferredUrls.clear();await remount(435);assert.equal(preparationCount,2);assert.equal(diagnostic()['data-national-prepared-cache'],'miss');
assert.equal(districtPaths('26').length,2);await remount(574);assert.equal(preparationCount,2);assert.equal(diagnostic()['data-national-prepared-cache'],'hit');
""")


def test_cache_evicts_lru_views_and_honors_byte_budget_and_failed_factories(tmp_path):
    run_node(tmp_path, r"""
const {NationalPreparedCache,nationalPreparedKey}=loadTs('lib/block-national-render.ts');
const cache=new NationalPreparedCache(2,1000),made=[];
const create=(id,bytes=400)=>()=>{made.push(id);return {states:[],borders:[],meshes:[],derived:[],recorded:[],estimatedBytes:bytes,pathCount:0,id};};
const first=cache.getOrPrepare('a',create('a'));assert.equal(first.cacheHit,false);
cache.getOrPrepare('b',create('b'));assert.equal(cache.getOrPrepare('a',create('unexpected')).map,first.map);
assert.deepEqual(cache.snapshot(),{entries:2,estimatedBytes:800,keys:['b','a']});
cache.getOrPrepare('c',create('c'));assert.deepEqual(cache.snapshot().keys,['a','c']);
cache.getOrPrepare('large',create('large',1001));assert.deepEqual(cache.snapshot().keys,['a','c'],'Oversize result is usable without evicting useful entries');
assert.throws(()=>cache.getOrPrepare('failed',()=>{throw Error('broken geometry')}),/broken/);
assert.deepEqual(cache.snapshot().keys,['a','c']);
cache.getOrPrepare('d',create('d',700));assert.deepEqual(cache.snapshot(),{entries:1,estimatedBytes:700,keys:['d']});
assert.equal(cache.getOrPrepare('a',create('a-again')).cacheHit,false);assert.deepEqual(cache.snapshot().keys,['a']);
const plans=[{id:'02-1',stateFips:'02',coordinateFrame:'alaska-continuous'}],assets=[{url:'/outlines',sha256:'one'}];
const key=nationalPreparedKey(435,'land',assets,plans);
assert.equal(key,nationalPreparedKey(435,'land',structuredClone(assets),structuredClone(plans)));
assert.notEqual(key,nationalPreparedKey(574,'land',assets,plans));
assert.notEqual(key,nationalPreparedKey(435,'census',assets,plans));
assert.notEqual(key,nationalPreparedKey(435,'land',[{url:'/outlines',sha256:'two'}],plans));
assert.notEqual(key,nationalPreparedKey(435,'land',[{url:'/other',sha256:'one'}],plans));
assert.notEqual(key,nationalPreparedKey(435,'land',assets,[{...plans[0],coordinateFrame:'source'}]));
assert.notEqual(key,nationalPreparedKey(435,'land',assets,[{...plans[0],id:'02-2'}]));
""")
