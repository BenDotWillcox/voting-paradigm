#!/usr/bin/env node
/** Spatial-cache CPU evidence. Preserves the prior whole-county benchmark. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),Module=require('node:module'),os=require('node:os');
const {performance}=require('node:perf_hooks'),{gunzipSync}=require('node:zlib'),{spawnSync}=require('node:child_process');
const ROOT=path.resolve(__dirname,'..'),req=Module.createRequire(path.join(ROOT,'package.json')),ts=req('typescript'),{geoPath}=req('d3-geo');
const args=process.argv.slice(2),option=(name,fallback)=>{const i=args.indexOf(name);return i<0?fallback:args[i+1];};
const CACHE=path.resolve(option('--cache-root','C:/Users/benja/projects/voting_paradigm/.cache'));
const NAME=option('--scenario',null),SAMPLES=Number(option('--samples','3')),WARMUPS=1;
const OUTPUT=path.resolve(ROOT,option('--output','.cache/block-main-port/michigan-spatial-64mib-benchmark.json'));
const RETENTION_BYTES=64*1024*1024;
const relative=path.relative(path.join(ROOT,'.cache/block-main-port'),OUTPUT);assert.ok(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative));
assert.ok(Number.isInteger(SAMPLES)&&SAMPLES>=3&&SAMPLES<=10);
const pins=new Map(),sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function readPinned(filename,expected){const bytes=fs.readFileSync(filename),hash=sha(bytes);if(expected)assert.equal(hash,expected,filename);pins.set(filename,hash);return bytes;}
readPinned(__filename);
const baselinePath=path.join(ROOT,'.cache/block-main-port/michigan-viewport-benchmark.json'),baseline=JSON.parse(readPinned(baselinePath));
assert.equal(baseline.status,'complete');
const retentionBaselinePath=path.join(ROOT,'.cache/block-main-port/michigan-spatial-benchmark.json'),retentionBaseline=JSON.parse(readPinned(retentionBaselinePath));
assert.equal(retentionBaseline.methodology.cacheBudgetRawBytes,32*1024*1024);
const index=JSON.parse(readPinned(path.join(ROOT,'data/districting-block-plans/server-index.json')));
const manifest=JSON.parse(readPinned(path.join(ROOT,index.manifestPath),index.manifestSha256));readPinned(path.join(ROOT,index.catalogPath),index.catalogSha256);
const plan=manifest.plans['26-13'],explorer=manifest.michiganExplorer.plans[plan.id];
const fragmentPath=option('--fragment',null);
if(fragmentPath){const fragment=JSON.parse(readPinned(path.resolve(ROOT,fragmentPath)));assert.equal(fragment.status,'validated_plan_fragment');assert.equal(fragment.planId,plan.id);explorer.spatialIndex=fragment.spatialIndex;Object.assign(index.assets,fragment.assets);}
assert.ok(explorer.spatialIndex,'Publish spatial index before benchmarking, or supply --fragment');
function compressedAsset(asset){const key=asset.url.replace(/^\/api\/district-plans\//,''),entry=index.assets[key];assert.ok(entry);assert.ok(!path.isAbsolute(entry.path)&&!entry.path.includes('..')&&!entry.path.includes(':'));const filename=entry.path.startsWith('.cache/')?path.join(CACHE,entry.path.slice(7)):path.join(ROOT,entry.path);return readPinned(filename,entry.gzipSha256);}
function decodedAsset(asset){const raw=gunzipSync(compressedAsset(asset));assert.equal(sha(raw),asset.sha256);assert.equal(raw.length,asset.bytes);return JSON.parse(raw.toString('utf8'));}
const modules=new Map();function loadTs(relative){const filename=path.join(ROOT,relative);if(modules.has(filename))return modules.get(filename).exports;const m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));modules.set(filename,m);m.require=s=>s.startsWith('@/')?loadTs(s.slice(2)+'.ts'):req(s);m._compile(ts.transpileModule(readPinned(filename).toString('utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true},fileName:filename}).outputText,filename);return m.exports;}
const h=loadTs('lib/michigan-map-interaction.ts'),{MichiganSpatialBlockCache}=loadTs('lib/michigan-spatial-block-cache.ts'),{makeStateBlockProjection}=loadTs('lib/block-map-projection.ts');
const overview=decodedAsset(explorer.overview),summary=decodedAsset(explorer.summary),spatial=decodedAsset(explorer.spatialIndex),countyIndex=decodedAsset(plan.assets.detailIndex);
h.validateMichiganSummary(summary,plan);h.validateMichiganSpatialIndex(spatial,plan,summary);
const projection=makeStateBlockProjection(overview,'26'),drawingPath=geoPath(projection);
const projected=spatial.chunks.map(c=>({chunkId:c.chunkId,bounds:h.projectedMichiganCountyBounds(c.bbox,projection)}));
const chunkMap=new Map(spatial.chunks.map(c=>[c.chunkId,c]));
const select=view=>h.visibleMichiganSpatialChunks(projected,view);
const sum=(ids,key)=>ids.reduce((n,id)=>n+(key==='blocks'?chunkMap.get(id).blockCount:chunkMap.get(id).asset[key]),0);
function stats(values){const sorted=[...values].sort((a,b)=>a-b);return {samples:values,median:sorted[Math.floor(sorted.length/2)],min:sorted[0],max:sorted.at(-1)};}
function coords(value){if(!value)return 0;if(Array.isArray(value))return typeof value[0]==='number'?1:value.reduce((n,c)=>n+coords(c),0);if(value.type==='FeatureCollection')return value.features.reduce((n,f)=>n+coords(f.geometry),0);return coords(value.coordinates);}
const timed=fn=>{const start=performance.now(),value=fn();return {ms:performance.now()-start,value};};
async function run(name){
 const source=baseline.scenarios[name];assert.ok(source);const coldView=source.view,neighborView=source.neighbor.view;
 const nestedView=h.zoomAt(coldView,2,[500,310],{min:1,max:256});
 const views={cold:coldView,nested:nestedView,zoomBack:coldView,neighbor:neighborView,returnToOriginal:coldView};
 const selections=Object.fromEntries(Object.entries(views).map(([key,view])=>[key,select(view)]));
 assert.ok(selections.nested.every(id=>selections.cold.includes(id)),'Nested tiles must be a subset');
 const allIds=[...new Set(Object.values(selections).flat())],buffers=new Map(allIds.map(id=>[id,compressedAsset(chunkMap.get(id).asset)]));
 const measures=[],facts=new Map();let checksum=0;
 for(let round=-WARMUPS;round<SAMPLES;round++){
  if(global.gc)global.gc();let activeTimes=null,changed=0;
  const cache=new MichiganSpatialBlockCache({chunks:spatial.chunks,concurrency:2,onChange(){changed++;},
   async load(chunk,signal){assert.ok(activeTimes);const decode=timed(()=>JSON.parse(gunzipSync(buffers.get(chunk.chunkId)).toString('utf8')));
    const validate=timed(()=>h.validateMichiganSpatialBlocks(decode.value,plan,chunk));
    const prep=timed(()=>h.prepareMichiganCounty(validate.value,drawingPath));assert.equal(signal.aborted,false);
    activeTimes.decodeMs+=decode.ms;activeTimes.validateMs+=validate.ms;activeTimes.prepareMs+=prep.ms;
    if(!facts.has(chunk.chunkId))facts.set(chunk.chunkId,{coordinates:coords(decode.value)});
    return prep.value;
   }});
  const generated=new WeakSet(),row={};
  for(const [stage,view]of Object.entries(views)){
   const ids=selections[stage],before=cache.snapshot(ids),requestsBefore=before.networkRequests,preparedBefore=before.preparedChunks;
   activeTimes={decodeMs:0,validateMs:0,prepareMs:0};const start=performance.now();cache.setNeeded(ids);
   const readySynchronously=cache.snapshot(ids).ready;
   for(let turns=0;!cache.snapshot(ids).ready;turns++){assert.ok(turns<allIds.length*8+32);assert.equal(cache.snapshot(ids).error,null);await Promise.resolve();}
   const ready=cache.snapshot(ids),box=h.viewportBounds(view);
   const cull=timed(()=>ready.data.flatMap(c=>c.shapes).filter(s=>h.boundsIntersect(s.bounds,box)));
   const newPaths=cull.value.filter(shape=>!generated.has(shape)).length;
   const paths=timed(()=>cull.value.reduce((n,s)=>n+s.d.length,0));for(const shape of cull.value)generated.add(shape);checksum+=paths.value;
   row[stage]={...activeTimes,cullMs:cull.ms,visiblePathGenerationMs:paths.ms,totalCpuMs:performance.now()-start,
    readySynchronously,requests:ready.networkRequests-requestsBefore,preparedChunks:ready.preparedChunks-preparedBefore,
    neededChunks:ids.length,loadedBlocks:sum(ids,'blocks'),visibleBlocks:cull.value.length,newVisiblePaths:newPaths,
    rawBytes:sum(ids,'bytes'),gzipBytes:sum(ids,'gzipBytes'),cachedBytes:ready.cachedBytes,cacheSize:ready.cacheSize};
   if(stage==='nested') {assert.equal(readySynchronously,true);assert.equal(row[stage].requests,0);assert.equal(row[stage].preparedChunks,0);assert.equal(newPaths,0);}
   if(stage==='zoomBack'&&sum(selections.cold,'bytes')<=RETENTION_BYTES){assert.equal(readySynchronously,true);assert.equal(row[stage].requests,0);}
  }
  row.memory=process.memoryUsage();cache.dispose();assert.equal(cache.snapshot([]).cacheSize,0);
  if(round>=0)measures.push(row);
 }
 const peakPreparationRssKiB=process.resourceUsage().maxRSS;
 // Independent source parity: exact properties/coordinates and every original
 // viewport-visible block must appear in the spatial selection.
 const spatialFeatures=new Map();for(const id of allIds)for(const feature of decodedAsset(chunkMap.get(id).asset).features){const geoid=feature.properties.geoid;assert.ok(!spatialFeatures.has(geoid));spatialFeatures.set(geoid,feature);}
 const countyFips=new Set([...spatialFeatures.keys()].map(id=>id.slice(2,5)));
 for(const c of [...source.counties,...source.neighbor.counties])countyFips.add(c.fips);
 const expected=Object.fromEntries(Object.keys(views).map(stage=>[stage,new Set()]));let exactMatches=0;
 for(const fips of countyFips){const county=countyIndex.counties.find(c=>c.fips===fips);assert.ok(county);const original=decodedAsset(county.asset);h.validateCountyBlocks(original,plan,fips,county.population,county.blockCount);
  for(const feature of original.features){const geoid=feature.properties.geoid;if(spatialFeatures.has(geoid)){assert.deepEqual(spatialFeatures.get(geoid),feature);exactMatches++;}
   const bounds=drawingPath.bounds(feature);for(const [stage,view]of Object.entries(views))if(h.boundsIntersect(bounds,h.viewportBounds(view)))expected[stage].add(geoid);
  }
 }
 assert.equal(exactMatches,spatialFeatures.size);
 for(const [stage,ids]of Object.entries(selections)){const actual=new Set();for(const id of ids)for(const feature of decodedAsset(chunkMap.get(id).asset).features)if(h.boundsIntersect(drawingPath.bounds(feature),h.viewportBounds(views[stage])))actual.add(feature.properties.geoid);assert.deepEqual([...actual].sort(),[...expected[stage]].sort(),`Visible source parity: ${stage}`);}
 const stages=Object.fromEntries(Object.keys(views).map(stage=>[stage,Object.fromEntries(Object.keys(measures[0][stage]).map(key=>[key,key.endsWith('Ms')?stats(measures.map(row=>row[stage][key])):measures[0][stage][key]]))]));
 return {name,views,selections,stages,coordinateCounts:Object.fromEntries(Object.entries(selections).map(([stage,ids])=>[stage,ids.reduce((n,id)=>n+facts.get(id).coordinates,0)])),
  parity:{exactSourceFeatures:exactMatches,visibleSourceCounts:Object.fromEntries(Object.entries(expected).map(([stage,set])=>[stage,set.size])),duplicateGeoids:0},
  baseline:{cold:baseline.benchmarks[name].cold,neighborPan:baseline.benchmarks[name].neighborPan,gzipBytes:source.gzipBytes,rawBytes:source.rawBytes},
  retentionBaseline32MiB:{stages:retentionBaseline.benchmarks[name].stages},
  memorySamples:measures.map(row=>row.memory),peakPreparationRssKiB,peakIncludingAuditRssKiB:process.resourceUsage().maxRSS,checksum};
}
(async()=>{
 const report={schemaVersion:1,status:'complete',createdAtUtc:new Date().toISOString(),command:process.argv,planId:plan.id,
  methodology:{samples:SAMPLES,warmups:WARMUPS,cacheBudgetRawBytes:RETENTION_BYTES,cacheBudgetSource:'Production constructor default; no retainBytes override. Default64MiB independently covered by regression.',thresholds:'Same source-bbox-fit Kent/Wayne cameras and broad7x camera as preserved whole-county baseline.',
   timings:'Node CPU: gzip/JSON decode, production validation and synchronous equivalent bounds/picking preparation, cache scheduling, visible lazy SVG paths. Cooperative yields and browser/RAF wall time are excluded.',
   sourceParity:'Whole original features, including every property and geometry coordinate, are checked against preserved county assets. Visible GEOID sets match source in every camera.',
   limitations:['No browser FPS, input latency, Canvas/Path2D, network latency, or GPU measurement.','Byte budget measures raw JSON, not heap; all required chunks remain resident even over budget.','Each scenario is a fresh Node process. Compressed inputs are resident, explicit GC occurs between rounds, and concurrent desktop work may affect CPU timings.','Whole-county baseline is a separately saved run; comparison is indicative, not an isolated paired benchmark.']},
  environment:{node:process.version,v8:process.versions.v8,osRelease:os.release(),cpu:os.cpus()[0]?.model,logicalCpuCount:os.cpus().length,totalMemoryBytes:os.totalmem()},
  benchmarks:{}};
 if(NAME)report.benchmarks[NAME]=await run(NAME);
 else for(const name of ['kent','wayne','broad_7x']){const output=path.join(path.dirname(OUTPUT),`michigan-spatial-64mib-${name}-benchmark.json`);console.log(`Running spatial ${name}`);const child=spawnSync(process.execPath,['--preserve-symlinks','--preserve-symlinks-main','--expose-gc',__filename,'--scenario',name,'--cache-root',CACHE,'--samples',String(SAMPLES),'--output',output,...(fragmentPath?['--fragment',fragmentPath]:[])],{cwd:ROOT,encoding:'utf8',maxBuffer:1024*1024,timeout:240000});assert.equal(child.status,0,`${child.stderr}\n${child.stdout}`);const value=JSON.parse(fs.readFileSync(output,'utf8'));report.benchmarks[name]=value.benchmarks[name];for(const pin of value.preservedInputs){if(pins.has(pin.path))assert.equal(pins.get(pin.path),pin.sha256);pins.set(pin.path,pin.sha256);}}
 for(const [filename,expected]of pins)assert.equal(sha(fs.readFileSync(filename)),expected,`Input changed: ${filename}`);
 report.preservedInputs=[...pins].map(([filename,sha256])=>({path:filename,sha256}));report.inputFilesModified=0;
 fs.mkdirSync(path.dirname(OUTPUT),{recursive:true});fs.writeFileSync(OUTPUT,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({output:OUTPUT,status:report.status,results:Object.fromEntries(Object.entries(report.benchmarks).map(([name,b])=>[name,{blocks:b.stages.cold.loadedBlocks,gzipMiB:b.stages.cold.gzipBytes/1048576,coldCpuMs:b.stages.cold.totalCpuMs.median,nestedRequests:b.stages.nested.requests,nestedPrep:b.stages.nested.preparedChunks,panCpuMs:b.stages.neighbor.totalCpuMs.median}]))},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
