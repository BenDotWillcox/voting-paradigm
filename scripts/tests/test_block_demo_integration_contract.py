"""Run real TypeScript helpers in Node with synthetic map/API fixtures.

No browser dependency, dev server, original benchmark mutation or app build is
needed. Browser interactions and request timing still need separate UI QA.
"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is required for TypeScript integration contracts")


def run_node(tmp_path: Path, source: str):
    """Transpile only imported app modules; erase server-only's build-time marker."""
    runner = tmp_path / "contract.cjs"
    preamble = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const rootRequire = Module.createRequire(path.join(ROOT, 'package.json'));
const ts = rootRequire('typescript');
const loaded = new Map();
function loadTs(relative) {
  const filename = path.isAbsolute(relative) ? relative : path.join(ROOT, relative);
  if (loaded.has(filename)) return loaded.get(filename).exports;
  const m = new Module(filename, module);
  m.filename = filename;
  m.paths = Module._nodeModulePaths(path.dirname(filename));
  loaded.set(filename, m);
  m.require = specifier => {
    if (specifier === 'server-only') return {};
    if (specifier.startsWith('@/')) return loadTs(specifier.slice(2) + '.ts');
    if (specifier.startsWith('.')) {
      const resolved = path.resolve(path.dirname(filename), specifier);
      if (fs.existsSync(resolved + '.ts')) return loadTs(resolved + '.ts');
    }
    return rootRequire(specifier);
  };
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
      esModuleInterop: true, jsx: ts.JsxEmit.ReactJSX}, fileName: filename,
  });
  m._compile(output.outputText, filename);
  return m.exports;
}
function collection(features) { return {type:'FeatureCollection', features}; }
function polygon(ring, fips='54') {
  return {type:'Feature',properties:{state_fips:fips},geometry:{type:'Polygon',coordinates:[ring]}};
}
function close(a,b,tolerance=1e-7) {
  assert.ok(Math.abs(a-b) <= tolerance, `${a} != ${b}`);
}
"""
    runner.write_text("const ROOT = " + json.dumps(str(ROOT)) + ";\n" + preamble +
                      "\n(async () => {\n" + source + "\n})().catch(error => { console.error(error); process.exitCode=1; });\n",
                      encoding="utf-8")
    result = subprocess.run([NODE, "--preserve-symlinks", "--preserve-symlinks-main", str(runner)],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_only_four_exact_block_anchors_are_accepted_without_interpolation(tmp_path):
    run_node(tmp_path, r"""
const s=loadTs('lib/block-plan-selection.ts');
assert.deepEqual([...s.BLOCK_HOUSE_SIZES],[435,574,692,1000]);
for (const cap of [435,574,692,1000]) {
  assert.equal(s.isBlockHouseSize(cap),true);
  assert.equal(s.blockHouseSize(cap),cap);
  assert.equal(s.blockHouseSize(String(cap)),cap);
}
for (const cap of [436,573,575,691,693,999,1001,11037,0,-1,Infinity,NaN]) {
  assert.equal(s.isBlockHouseSize(cap),false);
  assert.equal(s.blockHouseSize(cap),435);
}
for (const cap of [null,undefined,'','garbage','574.5']) assert.equal(s.blockHouseSize(cap),435);
""")


def test_same_district_count_reuses_one_selected_plan_without_changing_requested_anchor(tmp_path):
    run_node(tmp_path, r"""
const s=loadTs('lib/block-plan-selection.ts');
const shared={id:'02-1',stateFips:'02',districtCount:1,houseSizes:[435,574]};
const larger={id:'02-2',stateFips:'02',districtCount:2,houseSizes:[692,1000]};
const manifest={plans:{'02-1':shared,'02-2':larger}, anchors:[
 {houseSize:435,planIds:['02-1']},{houseSize:574,planIds:['02-1']},
 {houseSize:692,planIds:['02-2']},{houseSize:1000,planIds:['02-2']}]};
assert.equal(s.blockPlanAt(manifest,435,'02'),shared);
assert.equal(s.blockPlanAt(manifest,574,'02'),shared);
assert.equal(s.blockPlanAt(manifest,692,'02'),larger);
assert.equal(s.blockPlanAt(manifest,1000,'02'),larger);
assert.equal(new URL(s.blockPlanUrl(574,'02'),'http://local').searchParams.get('cap'),'574');
""")


def test_plan_lookup_does_not_fall_back_to_other_state_or_unselected_plan(tmp_path):
    run_node(tmp_path, r"""
const s=loadTs('lib/block-plan-selection.ts');
const manifest={plans:{'01-7':{stateFips:'01'},'02-1':{stateFips:'02'}},anchors:[{houseSize:435,planIds:['01-7','missing']}]};
for (const state of [null,'02','99','1']) assert.equal(s.blockPlanAt(manifest,435,state),null);
assert.equal(s.blockPlanAt(manifest,574,'01'),null);
assert.equal(s.blockPlanAt(manifest,435,'01'),manifest.plans['01-7']);
""")


def test_navigation_keeps_selected_state_and_anchor_and_clear_state_returns_national(tmp_path):
    run_node(tmp_path, r"""
const s=loadTs('lib/block-plan-selection.ts');
for (const cap of s.BLOCK_HOUSE_SIZES) {
 const url=new URL(s.blockPlanUrl(cap,'02'),'http://local');
 assert.equal(url.pathname,'/districts');
 assert.equal(url.searchParams.has('tab'),false);
 assert.equal(url.searchParams.get('cap'),String(cap));
 assert.equal(url.searchParams.get('state'),'02');
 const national=new URL(s.blockPlanUrl(cap,null),'http://local');
 assert.equal(national.searchParams.get('cap'),String(cap));
 assert.equal(national.searchParams.has('state'),false);
}
""")


def test_state_projection_is_winding_agnostic_and_fits_planar_polygon(tmp_path):
    run_node(tmp_path, r"""
const p=loadTs('lib/block-map-projection.ts'), {geoPath}=rootRequire('d3-geo');
const ring=[[-82,38],[-81,38],[-81,39],[-82,39],[-82,38]];
const ccw=collection([polygon(ring)]), cw=collection([polygon([...ring].reverse())]);
const a=geoPath(p.makeStateBlockProjection(ccw,'54',800,500,20));
const b=geoPath(p.makeStateBlockProjection(cw,'54',800,500,20));
const ab=a.bounds(ccw),bb=b.bounds(cw);
for (let i=0;i<2;i++) for(let j=0;j<2;j++) close(ab[i][j],bb[i][j]);
assert.ok(ab[0][0]>=19.999 && ab[1][0]<=780.001);
assert.ok(ab[0][1]>=19.999 && ab[1][1]<=480.001);
assert.ok(a.area(ccw)>1000);
close(a.area(ccw),b.area(cw),1e-5);
assert.ok(!a(ccw).includes('NaN'));
""")


def test_alaska_dateline_coordinates_share_continuous_working_frame(tmp_path):
    run_node(tmp_path, r"""
const p=loadTs('lib/block-map-projection.ts');
const geo=collection([polygon([[179,51],[-179,51],[-179,53],[179,53],[179,51]],'02')]);
assert.deepEqual([...p.blockCoordinateBounds(geo,true)],[-181,51,-179,53]);
const projection=p.makeStateBlockProjection(geo,'02',800,500,20);
const a=projection.projectPoint([179,52]),b=projection.projectPoint([-181,52]);
close(a[0],b[0]);close(a[1],b[1]);
const c=projection.projectPoint([-179,52]);
assert.ok(c[0]>a[0] && c[0]-a[0]<760);
for (const point of [a,b,c]) assert.ok(point.every(Number.isFinite));
""")


def test_national_projection_places_alaska_and_hawaii_inside_separate_labeled_insets(tmp_path):
    run_node(tmp_path, r"""
const p=loadTs('lib/block-map-projection.ts');
const geo=collection([
 polygon([[-125,25],[-67,25],[-67,49],[-125,49],[-125,25]],'01'),
 polygon([[-181,51],[-130,51],[-130,72],[-181,72],[-181,51]],'02'),
 polygon([[-161,18],[-154,18],[-154,23],[-161,23],[-161,18]],'15')]);
const national=p.makeNationalBlockProjection(geo);
for (const [fips,name,point] of [['02','alaska',[179,60]],['15','hawaii',[-157,20]]]) {
 const inset=p.BLOCK_MAP_INSETS[name], xy=national.projectionForState(fips).projectPoint(point);
 assert.ok(xy[0]>=inset.x && xy[0]<=inset.x+inset.width);
 assert.ok(xy[1]>=inset.y && xy[1]<=inset.y+inset.height);
}
assert.notEqual(national.projectionForState('02'),national.projectionForState('15'));
assert.equal(national.projectionForState('01'),national.projectionForState('54'));
""")


def test_map_fetch_preserves_abort_signal_and_rejects_failed_or_wrong_shape_payloads(tmp_path):
    run_node(tmp_path, r"""
const p=loadTs('lib/block-map-projection.ts'), signal=new AbortController().signal;
global.fetch=async (url,options)=>{assert.equal(url,'/asset');assert.equal(options.signal,signal);return new Response(JSON.stringify(collection([])),{status:200});};
assert.deepEqual(await p.fetchBlockCollection('/asset',signal),collection([]));
global.fetch=async ()=>new Response('bad',{status:404});
await assert.rejects(p.fetchBlockCollection('/asset',signal),/404/);
global.fetch=async ()=>new Response(JSON.stringify({type:'Feature'}),{status:200});
await assert.rejects(p.fetchBlockCollection('/asset',signal),/not a feature collection/);
""")


ASSET_FIXTURE = r"""
const {createHash}=require('node:crypto'), {gzipSync,gunzipSync}=require('node:zlib');
const fixtureRoot=path.join(path.dirname(__filename),'bundle');
const digest=b=>createHash('sha256').update(b).digest('hex');
const save=(relative,bytes)=>{const file=path.join(fixtureRoot,relative);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,bytes);return file;};
const catalogBytes=Buffer.from(JSON.stringify({status:'complete'}));
const manifestBytes=Buffer.from(JSON.stringify({schemaVersion:1,catalogSha256:digest(catalogBytes)}));
const reportBytes=Buffer.from(JSON.stringify({status:'complete'}));
const mapManifestBytes=Buffer.from(JSON.stringify({quality:{valid:true}}));
const raw=Buffer.from(JSON.stringify(collection([polygon([[-82,38],[-81,38],[-81,39],[-82,38]])])));
const compressed=gzipSync(raw), rawHash=digest(raw), gzipHash=digest(compressed);
const segments=[rawHash,'national.geojson'];
const reportFile=save('.cache/saved/benchmark.json',reportBytes);
const mapManifestFile=save('.cache/saved/maps/map-manifest.json',mapManifestBytes);
const assetFile=save('.cache/saved/maps/national.geojson.gz',compressed);
save('prompts/catalog.json',catalogBytes);
save('data/districting-block-plans/manifest.json',manifestBytes);
const index={schemaVersion:1,catalogPath:'prompts/catalog.json',catalogSha256:digest(catalogBytes),
 manifestPath:'data/districting-block-plans/manifest.json',manifestSha256:digest(manifestBytes),
 proofs:{'54-3':{reportPath:'.cache/saved/benchmark.json',reportSha256:digest(reportBytes),
 manifestPath:'.cache/saved/maps/map-manifest.json',manifestSha256:digest(mapManifestBytes)}},
 assets:{[segments.join('/')]:{path:'.cache/saved/maps/national.geojson.gz',rawSha256:rawHash,
 gzipSha256:gzipHash,rawBytes:raw.length,gzipBytes:compressed.length,
 contentType:'application/geo+json; charset=utf-8',proof:'54-3'}}};
const indexFile=save('data/districting-block-plans/server-index.json',JSON.stringify(index));
const service=loadTs('lib/load-block-plans.ts');
const request=(headers={},method='GET')=>new Request('http://local/api/district-plans/'+segments.join('/'),{headers,method});
const serve=(req=request(),asset=segments)=>service.serveBlockPlanAsset(req,asset,{root:fixtureRoot});
"""


def test_route_serves_gzip_or_decoded_json_with_truthful_lengths_etags_and_media_type(tmp_path):
    run_node(tmp_path, ASSET_FIXTURE + r"""
const gzip=await serve(request({'accept-encoding':'gzip'}));
assert.equal(gzip.status,200);
assert.equal(gzip.headers.get('content-encoding'),'gzip');
assert.equal(Number(gzip.headers.get('content-length')),compressed.length);
assert.equal(gzip.headers.get('content-type'),'application/geo+json; charset=utf-8');
assert.equal(gzip.headers.get('vary'),'Accept-Encoding');
assert.match(gzip.headers.get('cache-control'),/immutable/);
assert.deepEqual(gunzipSync(Buffer.from(await gzip.arrayBuffer())),raw);
const identity=await serve();
assert.equal(identity.status,200);
assert.equal(identity.headers.get('content-encoding'),null);
assert.equal(Number(identity.headers.get('content-length')),raw.length);
assert.notEqual(identity.headers.get('etag'),gzip.headers.get('etag'));
assert.deepEqual(Buffer.from(await identity.arrayBuffer()),raw);
assert.deepEqual(await service.loadBlockPlanManifest(fixtureRoot),JSON.parse(manifestBytes));
""")


def test_external_cache_mount_preserves_local_metadata_and_pinned_evidence(tmp_path):
    run_node(tmp_path, ASSET_FIXTURE + r"""
const cacheRoot=path.join(path.dirname(__filename),'preserved-cache');
fs.renameSync(path.join(fixtureRoot,'.cache'),cacheRoot);
assert.equal((await serve()).status,503,'no silent fallback to other repositories');
const response=await service.serveBlockPlanAsset(request(),segments,{root:fixtureRoot,cacheRoot});
assert.equal(response.status,200);
assert.deepEqual(Buffer.from(await response.arrayBuffer()),raw);
assert.deepEqual(await service.loadBlockPlanManifest(fixtureRoot),JSON.parse(manifestBytes));
fs.appendFileSync(path.join(cacheRoot,'saved/benchmark.json'),' ');
const changed=await service.serveBlockPlanAsset(request(),segments,{root:fixtureRoot,cacheRoot});
assert.equal(changed.status,503,'external evidence is still pinned');
""")


def test_environment_cache_mount_only_affects_production_default_root(tmp_path):
    run_node(tmp_path, ASSET_FIXTURE + r"""
const cacheRoot=path.join(path.dirname(__filename),'preserved-cache');
fs.renameSync(path.join(fixtureRoot,'.cache'),cacheRoot);
process.env.BLOCK_PLAN_CACHE_ROOT=cacheRoot;
process.chdir(fixtureRoot);
const response=await service.serveBlockPlanAsset(request(),segments);
assert.equal(response.status,200);
assert.deepEqual(Buffer.from(await response.arrayBuffer()),raw);
assert.equal((await serve()).status,503,'injected test roots are self-contained');
""")


def test_external_cache_mount_rejects_allowlist_path_escape(tmp_path):
    run_node(tmp_path, ASSET_FIXTURE + r"""
const cacheRoot=path.join(path.dirname(__filename),'preserved-cache');
fs.renameSync(path.join(fixtureRoot,'.cache'),cacheRoot);
index.assets[segments.join('/')].path='.cache/../outside.geojson.gz';
fs.writeFileSync(indexFile,JSON.stringify(index));
const response=await service.serveBlockPlanAsset(request(),segments,{root:fixtureRoot,cacheRoot});
assert.equal(response.status,503);
""")


def test_route_head_and_conditional_requests_preserve_representation_identity(tmp_path):
    run_node(tmp_path, ASSET_FIXTURE + r"""
const head=await serve(request({'accept-encoding':'gzip'},'HEAD'));
assert.equal(head.status,200);
assert.equal((await head.arrayBuffer()).byteLength,0);
assert.equal(Number(head.headers.get('content-length')),compressed.length);
const tag=head.headers.get('etag');
const unchanged=await serve(request({'accept-encoding':'gzip','if-none-match':`W/${tag}`}));
assert.equal(unchanged.status,304);
assert.equal(unchanged.headers.get('content-length'),null);
assert.equal((await unchanged.arrayBuffer()).byteLength,0);
const other=await serve(request({'accept-encoding':'identity','if-none-match':tag}));
assert.equal(other.status,200);
assert.deepEqual(Buffer.from(await other.arrayBuffer()),raw);
""")


def test_route_respects_explicitly_rejected_encodings_and_quality_preferences(tmp_path):
    run_node(tmp_path, ASSET_FIXTURE + r"""
for(const [encoding,status,wantGzip] of [
 ['gzip;q=0',200,false],['br',200,false],['gzip, identity;q=0.5',200,true],
 ['GZIP;q=0.5, identity;q=0',200,true],['*;q=0',406,false],
 ['identity;q=0,gzip;q=0',406,false],['gzip;q=invalid',200,false]]) {
 const response=await serve(request({'accept-encoding':encoding}));
 assert.equal(response.status,status,encoding);
 assert.equal(response.headers.get('content-encoding')==='gzip',wantGzip,encoding);
 await response.arrayBuffer();
}
""")


def test_route_rejects_traversal_unknown_assets_and_wrong_methods(tmp_path):
    run_node(tmp_path, ASSET_FIXTURE + r"""
for (const asset of [[],segments.slice(0,1),[...segments,'extra'],['..','national.geojson'],
 [rawHash,'../national.geojson'],[rawHash,'%2e%2e.json'],[rawHash,'other.json'],
 ['0'.repeat(64),'national.geojson'],[rawHash,'C:\\secret.json']]) {
 const response=await serve(request(),asset);
 assert.equal(response.status,404,asset.join('/'));
 assert.doesNotMatch(await response.text(),/benchmark\.json|fixtureRoot/);
}
const response=await serve(request({},'POST'));
assert.equal(response.status,405);assert.equal(response.headers.get('allow'),'GET, HEAD');
""")


@pytest.mark.parametrize("artifact", ["report", "map_manifest", "compressed_asset"])
def test_route_fails_closed_when_saved_evidence_or_map_bytes_change(tmp_path, artifact):
    run_node(tmp_path, ASSET_FIXTURE + "\nconst artifact=" + json.dumps(artifact) + r""";
// Populate the metadata cache first: request-time proof and asset checks must remain live.
const before=await serve();assert.equal(before.status,200);await before.arrayBuffer();
if(artifact==='report')fs.appendFileSync(reportFile,' ');
if(artifact==='map_manifest')fs.appendFileSync(mapManifestFile,' ');
if(artifact==='compressed_asset'){const altered=Buffer.from(compressed);altered[altered.length-1]^=1;fs.writeFileSync(assetFile,altered);}
const response=await serve();
assert.equal(response.status,503);
assert.equal(response.headers.get('cache-control'),'no-store');
assert.equal(await response.text(),'Validated district-plan data unavailable');
""")


@pytest.mark.parametrize("change", [
    {"path": ".cache/../../outside.gz"},
    {"path": "package.json"},
    {"contentType": "text/html"},
    {"rawSha256": "0" * 64},
    {"proof": "unknown-plan"},
])
def test_route_rejects_invalid_generated_allowlist_entries(tmp_path, change):
    run_node(tmp_path, ASSET_FIXTURE + "\nObject.assign(index.assets[segments.join('/')]," + json.dumps(change) + r""");
fs.writeFileSync(indexFile,JSON.stringify(index));
const response=await serve();assert.equal(response.status,503);await response.arrayBuffer();
""")


def test_next_get_and_head_wrappers_forward_resolved_segments_without_changing_method(tmp_path):
    run_node(tmp_path, r"""
const service=loadTs('lib/load-block-plans.ts'), calls=[];
service.serveBlockPlanAsset=async (request,asset)=>{calls.push([request.method,asset]);return new Response(null);};
const route=loadTs('app/api/district-plans/[...asset]/route.ts');
assert.equal(route.runtime,'nodejs');
for(const method of ['GET','HEAD']) {
 const req=new Request('http://local',{method});
 await route[method](req,{params:Promise.resolve({asset:['hash','name.geojson']})});
}
assert.deepEqual(calls,[['GET',['hash','name.geojson']],['HEAD',['hash','name.geojson']]]);
""")


# More than one 64-KiB read is necessary to distinguish cancel/abort cleanup
# from a tiny response that reaches EOF in the stream's first automatic pull.
LIFECYCLE_FIXTURE = ASSET_FIXTURE.replace(
    "const raw=Buffer.from(JSON.stringify(collection([polygon([[-82,38],[-81,38],[-81,39],[-82,38]])])));",
    "const raw=Buffer.from(JSON.stringify({type:'FeatureCollection',features:[],padding:require('node:crypto').randomBytes(512*1024).toString('base64')}));",
) + r"""
assert.ok(compressed.length>256*1024);
const fsp=require('node:fs/promises'), originalOpen=fsp.open;
const handles=[];
let openHook=null, readHook=null;
fsp.open=async (...args)=>{
 const file=await originalOpen(...args);
 const realClose=file.close.bind(file), realRead=file.read.bind(file);
 let resolveClosed;
 const record={file,closeCalls:0,readCalls:0,closed:new Promise(resolve=>{resolveClosed=resolve;})};
 handles.push(record);
 file.close=async ()=>{
  record.closeCalls++;
  try{return await realClose();}finally{resolveClosed();}
 };
 file.read=async (...readArgs)=>{
  record.readCalls++;
  const read=()=>realRead(...readArgs);
  return readHook ? readHook(record,readArgs,read) : read();
 };
 if(openHook)await openHook(record);
 return file;
};
const lifecycleRequest=(controller,encoding='gzip',method='GET',extra={})=>new Request('http://local/asset',{
 method,signal:controller?.signal,headers:{'accept-encoding':encoding,...extra},
});
async function requireClosedOnce(expected=1){
 assert.equal(handles.length,expected,'asset open count');
 for(const record of handles){
  let timeout;
  try{await Promise.race([record.closed,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('handle not explicitly closed')),2000);})]);}
  finally{clearTimeout(timeout);}
 }
 // Permit queued cancellation propagation to finish before checking idempotence.
 await new Promise(resolve=>setImmediate(resolve));
 for(const record of handles){assert.equal(record.closeCalls,1,'descriptor must close exactly once');assert.equal(record.file.fd,-1);}
}
"""


@pytest.mark.parametrize("mode", ["gzip_get", "identity_get", "head", "not_modified"])
def test_asset_descriptor_closes_exactly_once_after_normal_response(tmp_path, mode):
    run_node(tmp_path, LIFECYCLE_FIXTURE + "\nconst mode=" + json.dumps(mode) + r""";
const encoding=mode==='identity_get'?'identity':'gzip';
const method=mode==='head'?'HEAD':'GET';
const extra=mode==='not_modified'?{'if-none-match':`"${gzipHash}-gzip"`}:{};
const response=await serve(lifecycleRequest(null,encoding,method,extra));
assert.equal(response.status,mode==='not_modified'?304:200);
const body=Buffer.from(await response.arrayBuffer());
if(mode==='head'||mode==='not_modified')assert.equal(body.length,0);
else assert.deepEqual(encoding==='gzip'?gunzipSync(body):body,raw);
await requireClosedOnce();
""")


def test_already_aborted_request_never_opens_asset_descriptor(tmp_path):
    run_node(tmp_path, LIFECYCLE_FIXTURE + r"""
const abort=new AbortController();abort.abort();
const response=await serve(lifecycleRequest(abort));
assert.equal(response.status,503);await response.arrayBuffer();
await requireClosedOnce(0);
""")


@pytest.mark.parametrize("phase", ["after_open", "during_hash", "after_headers"])
def test_request_abort_closes_descriptor_during_verification_or_delivery(tmp_path, phase):
    run_node(tmp_path, LIFECYCLE_FIXTURE + "\nconst phase=" + json.dumps(phase) + r""";
const abort=new AbortController();
if(phase==='after_open')openHook=()=>abort.abort();
if(phase==='during_hash')readHook=async(record,args,read)=>{const result=await read();if(record.readCalls===1)abort.abort();return result;};
const response=await serve(lifecycleRequest(abort));
if(phase==='after_headers'){
 assert.equal(response.status,200);abort.abort();
 await assert.rejects(response.arrayBuffer());
}else{assert.equal(response.status,503);await response.arrayBuffer();}
await requireClosedOnce();
""")


@pytest.mark.parametrize("encoding", ["gzip", "identity"])
def test_consumer_body_cancel_closes_descriptor_without_garbage_collection(tmp_path, encoding):
    run_node(tmp_path, LIFECYCLE_FIXTURE + "\nconst encoding=" + json.dumps(encoding) + r""";
const response=await serve(lifecycleRequest(null,encoding));
assert.equal(response.status,200);
const reader=response.body.getReader();
const first=await reader.read();assert.equal(first.done,false);assert.ok(first.value.length>0);
await reader.cancel('navigation changed');
await requireClosedOnce();
""")


@pytest.mark.parametrize("phase", ["hash", "delivery"])
def test_asset_read_error_closes_descriptor_and_cannot_report_successful_body(tmp_path, phase):
    run_node(tmp_path, LIFECYCLE_FIXTURE + "\nconst phase=" + json.dumps(phase) + r""";
const verificationReads=Math.ceil(compressed.length/(64*1024));
readHook=async(record,args,read)=>{
 if(record.readCalls===(phase==='hash'?1:verificationReads+1))throw Error('synthetic positioned-read failure');
 return read();
};
const response=await serve(lifecycleRequest(null));
if(phase==='hash'){assert.equal(response.status,503);await response.arrayBuffer();}
else{assert.equal(response.status,200);await assert.rejects(response.arrayBuffer(),/synthetic positioned-read failure/);}
await requireClosedOnce();
""")


def test_identity_decompression_error_propagates_cancellation_and_closes_descriptor(tmp_path):
    run_node(tmp_path, LIFECYCLE_FIXTURE + r"""
// The outer saved-byte hash passes; an invalid gzip stream must still clean up.
const broken=Buffer.from(compressed);broken[0]=0;
fs.writeFileSync(assetFile,broken);
index.assets[segments.join('/')].gzipSha256=digest(broken);
fs.writeFileSync(indexFile,JSON.stringify(index));
const response=await serve(lifecycleRequest(null,'identity'));
assert.equal(response.status,200);await assert.rejects(response.arrayBuffer());
await requireClosedOnce();
""")
