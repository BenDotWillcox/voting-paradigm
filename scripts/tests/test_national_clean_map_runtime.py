"""Run the national map's real hooks/fetches/geometry with inert React SVG nodes."""
from test_block_demo_integration_contract import run_node
from test_michigan_explorer_modes import HOOK_HOST


# Reuse the established hook host, replacing only its explorer-specific fixture
# and entry point. The actual national component and its helpers run unchanged.
NATIONAL_HOST = HOOK_HOST.split("const asset=(name)=>", 1)[0] + r"""
// Only the national map's hookless memo children are evaluated here. Other
// explorer/canvas hosts remain unchanged. Match React.memo's shallow props
// comparison and retain each child's identity independently by component/key.
const memoChildren=new Map(),memoRenders=[];
React.memo=render=>({testMemoRender:render});
const descriptorJsx=jsxRuntime.jsx;
jsxRuntime.jsx=jsxRuntime.jsxs=(type,props,key)=>{
 if(!type?.testMemoRender)return descriptorJsx(type,props,key);
 const entries=memoChildren.get(type)??new Map();memoChildren.set(type,entries);
 const previous=entries.get(key),keys=Object.keys(props??{});
 if(previous&&keys.length===Object.keys(previous.props).length&&keys.every(k=>Object.is(props[k],previous.props[k])))return previous.node;
 const node=type.testMemoRender(props);entries.set(key,{props,node});memoRenders.push({name:type.testMemoRender.name,key});return node;
};
const asset=name=>({url:`/${name}`,bytes:1,gzipBytes:1,sha256:'fixture'});
const rectangle=(x0,y0,x1,y1)=>[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]];
const documents=new Map(), requests=[], deferredUrls=new Set(), selected=[];
const stateNames={'26':'Michigan','02':'Alaska','39':'Ohio'};
function feature(ring,state,population=1,id=0,planId='fixture') {
 return {type:'Feature',properties:{state_fips:state,state_name:stateNames[state],district_id:id,population,plan_id:planId},
  geometry:{type:'Polygon',coordinates:[ring]}};
}
const alaska=feature(rectangle(-190,52,-135,70),'02');
alaska.properties.coordinate_frame='alaska-continuous';
const ohio=feature(rectangle(-84.5,38.5,-80.5,41.5),'39');
const manifest={anchors:[],plans:{},stateOutlines:asset('state-boundaries'),landDisplays:{},stateExplorers:{'26':{plans:{}}}};
const fixtures=new Map();
for (const [houseSize,populations] of [[435,[60,40]],[574,[30,30,40]]]) {
 const count=populations.length, id=`26-${count}`, prefix=`anchor-${houseSize}`;
 const plan={id,stateFips:'26',districtCount:count,districtPopulations:populations,residentPopulation:100};
 const census=collection(populations.map((pop,i)=>feature(rectangle(-87.2+i*3.4/count,41.8,-87.2+(i+1)*3.4/count,45.2),'26',pop,i,id)));
 census.features.push(alaska,ohio);
 const overview=collection(populations.map((pop,i)=>feature(rectangle(-87+i*3/count,42,-87+(i+1)*3/count,45),'26',pop,i,id)));
 overview.metadata={planId:id,purpose:'display-only'};
 const coast=collection([{type:'Feature',properties:{plan_id:id,state_fips:'26',kind:'state-and-water-shoreline'},
  geometry:{type:'MultiLineString',coordinates:[rectangle(-87,42,-84,45),rectangle(-86.9,42.1,-86.8,42.2),
    rectangle(-86.88,42.12,-86.82,42.18)]}}]);
 coast.metadata={planId:id};
 const dividers=collection(populations.slice(1).map((_,i)=>({type:'Feature',properties:{plan_id:id,district_ids:[i,i+1],kind:'shared-district-divider'},
  geometry:{type:'LineString',coordinates:[[-87+(i+1)*3/count,42],[-87+(i+1)*3/count,45]]}})));
 dividers.metadata={planId:id};
 const linkPoints=[[-86.5,43],[-86.4,43.1],[-86.3,43.2]], blockPath=['260010001001001','260010001001002','260010001001003'];
 const connections=collection([{type:'Feature',properties:{id:'preserved-water-path',kind:'derived-water-adjacency',district_id:0,
  block_path:blockPath,water_block_count:1,endpoints:[{geoid:blockPath[0],coordinate:linkPoints[0]},{geoid:blockPath[2],coordinate:linkPoints[2]}]},
  geometry:{type:'LineString',coordinates:linkPoints}}]);
 connections.metadata={planId:id};
 manifest.plans[id]=plan;
 manifest.anchors.push({houseSize,planIds:[id],national:asset(`${prefix}-census`)});
 manifest.landDisplays[id]={planId:id,national:asset(`${prefix}-old-land`),stateOutline:asset(`${prefix}-old-border`),
  connections:asset(`${prefix}-connections`),summary:{derivedConnectionCount:1}};
 manifest.stateExplorers['26'].plans[id]={overview:asset(`${prefix}-overview`),coast:asset(`${prefix}-coast`),dividers:asset(`${prefix}-dividers`),
  detailDividers:asset(`${prefix}-detail-dividers`),spatialIndex:asset(`${prefix}-blocks-index`)};
 for (const [name,document] of Object.entries({census,overview,coast,dividers,connections}))documents.set(`/${prefix}-${name}`,document);
 fixtures.set(houseSize,{plan,census,overview,coast,dividers,connections});
}
const borders=collection([feature(rectangle(-87.2,41.8,-83.8,45.2),'26'),alaska,ohio]);
documents.set('/state-boundaries',borders);
const props={manifest,houseSize:435,onSelectState:state=>selected.push(state)};
global.fetch=(url,options={})=>{
 let resolve;const promise=new Promise(done=>{resolve=done;});
 const job={url,signal:options.signal,settled:false,resolveDocument(document){job.settled=true;resolve({ok:true,status:200,json:async()=>document});}};
 requests.push(job);assert.ok(documents.has(url),`Unexpected request ${url}`);
 if(!deferredUrls.has(url))job.resolveDocument(documents.get(url));return promise;
};
const {BlockNationalMap:Explorer}=loadUi('components/districting/block-national-map.tsx');
const layer=name=>nodes().filter(n=>n.props?.['data-layer']===name);
const districtPaths=state=>layer('district-fill').filter(n=>n.props['data-state']===state);
const boundaryPaths=state=>nodes(one(n=>n.props?.['data-layer']==='state-boundaries')).filter(n=>n.type==='g'&&n.props['data-state']===state).flatMap(n=>nodes(n).filter(v=>v.type==='path'));
async function extent(value){checkbox('Full census extent').props.onChange({target:{checked:value}});await flush();}
async function anchor(value){props.houseSize=value;dirty=true;await flush();}
const noDetailRequests=()=>assert.ok(requests.every(r=>r.url==='/state-boundaries'||/^\/anchor-(435|574)-(census|overview|coast|dividers|connections)$/.test(r.url)));
"""


def test_clean_meshes_replace_only_michigan_and_full_extent_reuses_census(tmp_path):
    run_node(tmp_path, NATIONAL_HOST + r"""
const before=JSON.stringify([...documents]);await flush();
assert.deepEqual(requests.map(r=>r.url).sort(),['/state-boundaries','/anchor-435-census','/anchor-435-overview','/anchor-435-coast','/anchor-435-dividers','/anchor-435-connections'].sort());
assert.equal(districtPaths('26').length,2);assert.ok(districtPaths('26').every(n=>n.props.stroke==='none'));
assert.equal(layer('michigan-district-dividers').length,1);
assert.equal(layer('michigan-interior-water').length,1);
assert.ok(layer('michigan-interior-water')[0].props.strokeOpacity<1);
assert.equal(layer('derived-water-connections')[0].props.strokeDasharray,'3 3');
assert.equal(nodes(layer('derived-water-connections')[0]).filter(n=>n.type==='path').length,1);
const savedAlaska=districtPaths('02')[0].props.d, savedOhio=districtPaths('39')[0].props.d;
const cleanMichigan=districtPaths('26')[0].props.d, cleanBorder=boundaryPaths('26')[1].props.d;
assert.equal(boundaryPaths('26')[1].props.stroke,'#454545');
assert.equal(boundaryPaths('26')[1].props.strokeWidth,1.3);
assert.equal(boundaryPaths('26')[0].props.strokeWidth,3);
// Only the outer shore gets the thick gold/casing stroke. The lake and the
// island inside it both stay in the subdued inland layer.
assert.equal((cleanBorder.match(/M/g)||[]).length,1);
assert.equal((boundaryPaths('26')[0].props.d.match(/M/g)||[]).length,1);
assert.equal((layer('michigan-interior-water')[0].props.d.match(/M/g)||[]).length,2);
assert.notEqual(cleanBorder,layer('michigan-interior-water')[0].props.d);
const count=requests.length;await extent(true);
assert.equal(requests.length,count);assert.ok(districtPaths('26').every(n=>n.props.stroke==='#454545'));
assert.notEqual(districtPaths('26')[0].props.d,cleanMichigan);
assert.notEqual(boundaryPaths('26')[1].props.d,cleanBorder);
assert.equal(layer('michigan-district-dividers').length,0);assert.equal(layer('michigan-interior-water').length,0);assert.equal(layer('derived-water-connections').length,0);
assert.equal(districtPaths('02')[0].props.d,savedAlaska);
// Ohio keeps its census geometry; its continental projection can legitimately
// refit slightly when Michigan's full census coverage changes the bounds.
assert.ok(savedOhio && districtPaths('39')[0].props.d);assert.equal(districtPaths('39')[0].props.stroke,'#454545');
await extent(false);assert.equal(requests.length,count);
assert.equal(districtPaths('26')[0].props.d,cleanMichigan);assert.equal(boundaryPaths('26')[1].props.d,cleanBorder);
assert.equal(districtPaths('39')[0].props.d,savedOhio);assert.equal(JSON.stringify([...documents]),before);
one(n=>n.type==='g'&&n.props['aria-label']==='Michigan, 2 districts. Open state map.').props.onClick();
assert.deepEqual(selected,['26']);noDetailRequests();
""")


def test_old_anchor_responses_cannot_restore_geometry_after_switching(tmp_path):
    run_node(tmp_path, NATIONAL_HOST + r"""
for (const name of ['census','overview','coast','dividers','connections'])deferredUrls.add(`/anchor-435-${name}`);
await flush();const old=requests.filter(r=>r.url.startsWith('/anchor-435-'));
assert.equal(old.length,5);assert.equal(districtPaths('26').length,0);
await anchor(574);assert.equal(districtPaths('26').length,3);
assert.ok(old.every(r=>r.signal.aborted));
const latest=JSON.stringify(nodes().filter(n=>n.type==='path').map(n=>n.props));
for (const request of old)request.resolveDocument(documents.get(request.url));
await flush();assert.equal(JSON.stringify(nodes().filter(n=>n.type==='path').map(n=>n.props)),latest);
assert.ok(textContent(tree).includes('Michigan land-focused pilot'));
assert.equal(layer('michigan-district-dividers').length,1);
const requestCount=requests.length;await extent(true);await extent(false);assert.equal(requests.length,requestCount);
for(const name of ['census','overview','coast','dividers','connections'])deferredUrls.delete(`/anchor-435-${name}`);
await anchor(435);assert.equal(districtPaths('26').length,2);
assert.equal(requests.filter(r=>r.url==='/anchor-435-overview').length,2,'Discarded stale assets do not enter the cache');
assert.equal(requests.filter(r=>r.url==='/state-boundaries').length,1);noDetailRequests();
""")


def test_wrong_plan_layer_fails_visibly_and_full_extent_remains_available(tmp_path):
    run_node(tmp_path, NATIONAL_HOST + r"""
documents.get('/anchor-435-coast').metadata.planId='26-3';
await flush();assert.equal(districtPaths('26').length,0);
assert.ok(nodes().some(n=>n.props?.role==='alert'&&textContent(n).includes('selected plan')));
assert.ok(button('Retry map'));await extent(true);
assert.equal(districtPaths('26').length,2);assert.equal(layer('michigan-district-dividers').length,0);
assert.equal(nodes().filter(n=>n.props?.role==='alert').length,0);
noDetailRequests();
""")
