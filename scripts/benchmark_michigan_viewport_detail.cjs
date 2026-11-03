#!/usr/bin/env node
/** Read-only real-data viewport workload and CPU benchmark; never a browser FPS test. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const Module = require('node:module');
const { performance } = require('node:perf_hooks');
const { gunzipSync } = require('node:zlib');
const { spawnSync } = require('node:child_process');
const ROOT = path.resolve(__dirname, '..');
const rootRequire = Module.createRequire(path.join(ROOT, 'package.json'));
const ts = rootRequire('typescript');
const { geoPath } = rootRequire('d3-geo');
const argv = process.argv.slice(2);
function option(name, fallback) {
  const at = argv.indexOf(name);
  if (at < 0) return fallback;
  assert.ok(argv[at + 1] && !argv[at + 1].startsWith('--'), `Missing value for ${name}`);
  return argv[at + 1];
}
const CACHE = path.resolve(option('--cache-root', process.env.BLOCK_PLAN_CACHE_ROOT || 'C:/Users/benja/projects/voting_paradigm/.cache'));
const INVENTORY_ONLY = argv.includes('--inventory-only');
const CHILD_SCENARIO = option('--scenario', null);
const SAMPLES = Number(option('--samples', '3'));
const WARMUPS = Number(option('--warmups', '1'));
assert.ok(Number.isInteger(SAMPLES) && SAMPLES >= 3 && SAMPLES <= 20);
assert.ok(Number.isInteger(WARMUPS) && WARMUPS >= 1 && WARMUPS <= 5);
const OUTPUT = path.resolve(ROOT, option('--output', `.cache/block-main-port/michigan-viewport-${INVENTORY_ONLY ? 'inventory' : 'benchmark'}.json`));
const outputRelative = path.relative(path.join(ROOT, '.cache', 'block-main-port'), OUTPUT);
assert.ok(outputRelative && !outputRelative.startsWith('..') && !path.isAbsolute(outputRelative), 'Output must be in task evidence directory');
const preserved = new Map();
const sha = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
function readPinned(filename, expected) {
  const bytes = fs.readFileSync(filename), hash = sha(bytes);
  if (expected) assert.equal(hash, expected, `Input hash mismatch: ${filename}`);
  preserved.set(filename, hash); return bytes;
}
readPinned(__filename);
const index = JSON.parse(readPinned(path.join(ROOT, 'data/districting-block-plans/server-index.json')));
const manifest = JSON.parse(readPinned(path.join(ROOT, index.manifestPath), index.manifestSha256));
readPinned(path.join(ROOT, index.catalogPath), index.catalogSha256);
assert.equal(manifest.catalogSha256, index.catalogSha256);
const plan = manifest.plans['26-13'], explorer = manifest.michiganExplorer.plans['26-13'];
function locateAsset(asset) {
  const key = asset.url.replace(/^\/api\/district-plans\//, '');
  assert.notEqual(key, asset.url);
  const entry = index.assets[key]; assert.ok(entry);
  assert.ok(!path.isAbsolute(entry.path) && !entry.path.includes('..') && !entry.path.includes(':'));
  const filename = entry.path.startsWith('.cache/') ? path.join(CACHE, entry.path.slice(7)) : path.join(ROOT, entry.path);
  return { entry, filename };
}
function readAsset(asset) {
  const { entry, filename } = locateAsset(asset);
  const compressed = readPinned(filename, entry.gzipSha256), raw = gunzipSync(compressed);
  assert.equal(sha(raw), asset.sha256); assert.equal(sha(raw), entry.rawSha256); assert.equal(raw.length, asset.bytes);
  return { data: JSON.parse(raw.toString('utf8')), compressed, rawBytes: raw.length };
}
const loadedModules = new Map();
function loadTs(relative) {
  const filename = path.isAbsolute(relative) ? relative : path.join(ROOT, relative);
  if (loadedModules.has(filename)) return loadedModules.get(filename).exports;
  const m = new Module(filename, module); m.filename = filename; m.paths = Module._nodeModulePaths(path.dirname(filename));
  loadedModules.set(filename, m);
  m.require = (specifier) => specifier.startsWith('@/') ? loadTs(specifier.slice(2) + '.ts') : rootRequire(specifier);
  m._compile(ts.transpileModule(readPinned(filename).toString('utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true }, fileName: filename,
  }).outputText, filename);
  return m.exports;
}
const { makeStateBlockProjection } = loadTs('lib/block-map-projection.ts');
const interaction = loadTs('lib/michigan-map-interaction.ts');
const overview = readAsset(explorer.overview).data;
const summary = readAsset(explorer.summary).data;
const detailIndex = readAsset(plan.assets.detailIndex).data;
interaction.validateMichiganSummary(summary, plan);
const projection = makeStateBlockProjection(overview, '26'), svgPath = geoPath(projection);
function bboxFeature([w, s, e, n]) {
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[w,s],[e,s],[e,n],[w,n],[w,s]]] } };
}
const countyBounds = summary.counties.map((county) => {
  const info = detailIndex.counties.find((entry) => entry.fips === county.fips); assert.ok(info);
  assert.equal(info.population, county.population); assert.equal(info.blockCount, county.blockCount);
  return { fips: county.fips, name: county.name, bounds: interaction.projectedMichiganCountyBounds
    ? interaction.projectedMichiganCountyBounds(county.bbox, projection) : svgPath.bounds(bboxFeature(county.bbox)), ...info };
});
const boxAt = (view) => [[-view.x / view.k, -view.y / view.k], [(1000 - view.x) / view.k, (620 - view.y) / view.k]];
function selected(view) {
  const direct = countyBounds.filter((county) => interaction.boundsIntersect(county.bounds, boxAt(view))).sort((a,b) => a.fips.localeCompare(b.fips));
  if (interaction.visibleMichiganCountyFips) assert.deepEqual(interaction.visibleMichiganCountyFips(countyBounds, view), direct.map((c) => c.fips));
  return direct;
}
function viewAt(x, y, k = 7) { return { x: 500 - x * k, y: 310 - y * k, k }; }
function fittedCounty(fips) {
  const county = countyBounds.find((entry) => entry.fips === fips); assert.ok(county);
  const fit = interaction.fitMapBounds(county.bounds);
  return viewAt((county.bounds[0][0] + county.bounds[1][0]) / 2, (county.bounds[0][1] + county.bounds[1][1]) / 2, Math.max(7, fit.k));
}
function workload(view) {
  const counties = selected(view);
  return { view, viewportBounds: boxAt(view), countyCount: counties.length,
    counties: counties.map((c) => ({ fips: c.fips, name: c.name, blocks: c.blockCount, population: c.population, rawBytes: c.asset.bytes, gzipBytes: c.asset.gzipBytes })),
    blocks: counties.reduce((n,c) => n + c.blockCount, 0),
    rawBytes: counties.reduce((n,c) => n + c.asset.bytes, 0), gzipBytes: counties.reduce((n,c) => n + c.asset.gzipBytes, 0) };
}
const scan = countyBounds.map((county) => ({ source: `county-center-${county.fips}`, view: viewAt((county.bounds[0][0] + county.bounds[1][0]) / 2, (county.bounds[0][1] + county.bounds[1][1]) / 2) }));
for (let x = 28; x <= 972; x += 24) for (let y = 28; y <= 592; y += 24) scan.push({ source: `grid-${x}-${y}`, view: viewAt(x,y) });
const heaviest = scan.map((entry) => ({ ...entry, ...workload(entry.view) })).sort((a,b) => b.rawBytes - a.rawBytes || a.source.localeCompare(b.source))[0];
const scenarios = { kent: workload(fittedCounty('081')), wayne: workload(fittedCounty('163')), broad_7x: heaviest };
for (const scenario of Object.values(scenarios)) {
  // Move the camera east by one quarter of its width, with unchanged scale.
  scenario.neighbor = workload({ ...scenario.view, x: scenario.view.x - 250 });
  const current = new Set(scenario.counties.map((c) => c.fips)), next = new Set(scenario.neighbor.counties.map((c) => c.fips));
  scenario.panCache = { retainedFips: [...current].filter((fips) => next.has(fips)), evictedFips: [...current].filter((fips) => !next.has(fips)),
    addedFips: [...next].filter((fips) => !current.has(fips)),
    addedRawBytes: scenario.neighbor.counties.filter((c) => !current.has(c.fips)).reduce((n,c) => n+c.rawBytes,0),
    addedGzipBytes: scenario.neighbor.counties.filter((c) => !current.has(c.fips)).reduce((n,c) => n+c.gzipBytes,0) };
}
const report = { schemaVersion: 1, status: 'inventory-complete', createdAtUtc: new Date().toISOString(), command: process.argv, planId: plan.id,
  methodology: { countySelection: 'Conservative intersection of projected source county bounding boxes; independent of selection; no county-count cap. Uses production sampled-edge/padded projection helper when available.',
    kentWayneViews: 'Fit source county bounding box, then increase to at least 7x about the same center.',
    broadView: 'Highest whole-county raw payload among county centers and a 24-unit grid over the 1000x620 map plane at exactly 7x; not a proof of a global maximum.',
    scannedViewCount: scan.length, pan: 'East by one quarter of viewport width at unchanged zoom.',
    limits: ['County payloads include blocks outside the visible area, including water.', 'Metadata counts are exact for selected county files, not counts of visible blocks.', 'This is local geometry workload evidence; no browser FPS or network latency claims.'] },
  scenarios, inputFilesModified: 0 };
function coordinateCount(value) {
  if (!value) return 0;
  if (Array.isArray(value)) return typeof value[0] === 'number' ? 1 : value.reduce((n, child) => n + coordinateCount(child), 0);
  if (value.type === 'FeatureCollection') return value.features.reduce((n, f) => n + coordinateCount(f.geometry), 0);
  if (value.type === 'GeometryCollection') return value.geometries.reduce((n, g) => n + coordinateCount(g), 0);
  return coordinateCount(value.coordinates);
}
function stats(values) {
  const sorted = [...values].sort((a,b) => a-b), m = Math.floor(sorted.length/2);
  return { samples: values, median: sorted.length % 2 ? sorted[m] : (sorted[m-1]+sorted[m])/2, min: sorted[0], max: sorted.at(-1) };
}
function timed(operation) { const start = performance.now(), value = operation(); return { ms: performance.now()-start, value }; }
function runScenario(name) {
  assert.ok(interaction.prepareMichiganCounty && interaction.visibleMichiganCountyFips && interaction.viewportBounds, 'Production viewport helpers must be available');
  const scenario = scenarios[name]; assert.ok(scenario, 'Unknown scenario');
  const primary = scenario.counties.map((c) => c.fips), neighbor = scenario.neighbor.counties.map((c) => c.fips);
  const needed = [...new Set([...primary,...neighbor])], buffers = new Map();
  const countyFacts = new Map();
  for (const fips of needed) {
    const county = countyBounds.find((c) => c.fips === fips), {entry,filename} = locateAsset(county.asset);
    const bytes = readPinned(filename, entry.gzipSha256);
    assert.equal(bytes.length, county.asset.gzipBytes); buffers.set(fips, bytes);
  }
  const rows = [], counters = { preparedCounties: 0, reusedCounties: 0, evictedCounties: 0 };
  let checksum = 0;
  function prepareCounty(fips) {
    const county = countyBounds.find((c) => c.fips === fips);
    let raw, collection;
    const decode = timed(() => { raw = gunzipSync(buffers.get(fips)); collection = JSON.parse(raw.toString('utf8')); });
    const verify = timed(() => {
      assert.equal(sha(raw), county.asset.sha256); assert.equal(raw.length, county.asset.bytes);
      interaction.validateCountyBlocks(collection, plan, fips, county.population, county.blockCount);
    });
    const prepare = timed(() => interaction.prepareMichiganCounty(collection, svgPath));
    if (!countyFacts.has(fips)) countyFacts.set(fips, { fips, name: county.name, blocks: collection.features.length,
      coordinates: coordinateCount(collection), gzipBytes: buffers.get(fips).length, rawBytes: raw.length });
    counters.preparedCounties++;
    return { value: prepare.value, decodeMs: decode.ms, validateMs: verify.ms, prepareMs: prepare.ms };
  }
  function cachedStage(cache, fipsList, view, generatedPaths) {
    const times = { decodeMs: 0, validateMs: 0, prepareMs: 0, preparedCounties: 0, reusedCounties: 0, evictedCounties: 0 };
    const wanted = new Set(fipsList);
    const stageStart = performance.now();
    for (const fips of [...cache.keys()]) if (!wanted.has(fips)) { cache.delete(fips); times.evictedCounties++; counters.evictedCounties++; }
    for (const fips of fipsList) {
      if (cache.has(fips)) { times.reusedCounties++; counters.reusedCounties++; continue; }
      const prepared = prepareCounty(fips); cache.set(fips,prepared.value);
      times.decodeMs += prepared.decodeMs; times.validateMs += prepared.validateMs; times.prepareMs += prepared.prepareMs; times.preparedCounties++;
    }
    const box = interaction.viewportBounds(view);
    const cull = timed(() => [...cache.values()].flatMap((county) => county.shapes).filter((shape) => interaction.boundsIntersect(shape.bounds, box)));
    times.cullMs = cull.ms; times.activeBlocks = [...cache.values()].reduce((n,c) => n+c.shapes.length,0); times.visibleBlocks = cull.value.length;
    times.newVisiblePaths = cull.value.filter((shape) => !generatedPaths.has(shape)).length;
    const paths = timed(() => cull.value.reduce((n,shape) => n+shape.d.length,0));
    for (const shape of cull.value) generatedPaths.add(shape);
    times.visiblePathGenerationMs = paths.ms; times.visiblePathCharacters = paths.value; checksum += times.visiblePathCharacters;
    times.totalCpuMs = performance.now()-stageStart;
    return times;
  }
  const start = performance.now(), before = process.memoryUsage();
  if (argv.includes('--memory-probe')) {
    assert.ok(global.gc, 'Memory probe requires --expose-gc');
    global.gc();
    const baselineAfterGc = process.memoryUsage(), cache = new Map(), generatedPaths = new WeakSet();
    const cold = cachedStage(cache, primary, scenario.view, generatedPaths);
    const afterColdBeforeGc = process.memoryUsage();
    global.gc(); const activeAfterGc = process.memoryUsage();
    const activeCountyCount = cache.size; cache.clear();
    global.gc(); const releasedAfterGc = process.memoryUsage();
    return {status:'complete',name,scenario,cold,activeCountyCount,primaryCoordinates:primary.reduce((n,fips)=>n+countyFacts.get(fips).coordinates,0),
      memory:{baselineAfterGc,afterColdBeforeGc,activeAfterGc,releasedAfterGc,
        activeHeapIncreaseBytes:activeAfterGc.heapUsed-baselineAfterGc.heapUsed,
        releasedHeapDecreaseBytes:activeAfterGc.heapUsed-releasedAfterGc.heapUsed,
        peakRssKiB:process.resourceUsage().maxRSS},
      elapsedMs:performance.now()-start,
      methodology:'One cold active viewport; forced GC before loading, with active cache held, and after clearing it. GC is outside cold timing. Compressed current/neighbor buffers remain resident. No browser or Path2D memory is measured.'};
  }
  for (let round = -WARMUPS; round < SAMPLES; round++) {
    if (global.gc) global.gc();
    const cache = new Map(), generatedPaths = new WeakSet();
    const cold = cachedStage(cache, primary, scenario.view, generatedPaths);
    const afterCold = process.memoryUsage();
    const reusedIdentities = new Map([...cache].filter(([fips]) => neighbor.includes(fips)));
    const pan = cachedStage(cache, neighbor, scenario.neighbor.view, generatedPaths);
    for (const [fips,value] of reusedIdentities) assert.equal(cache.get(fips),value,'Pan rebuilt retained county');
    assert.deepEqual([...cache.keys()].sort(),[...neighbor].sort());
    const afterPan = process.memoryUsage();
    if (round >= 0) rows.push({cold,pan,afterCold,afterPan});
    // Avoid the benchmark retaining the previous active viewport through its
    // identity-check map when the next round starts. This is not app code.
    reusedIdentities.clear(); cache.clear();
  }
  const aggregate = (label) => Object.fromEntries(Object.keys(rows[0][label]).map((key) => [key,key.endsWith('Ms') ? stats(rows.map((r) => r[label][key])) : rows[0][label][key]]));
  return { status: 'complete', name, scenario, rounds: {warmups:WARMUPS,measured:SAMPLES,forceGcBetweenRounds:typeof global.gc==='function'},
    cold: aggregate('cold'), neighborPan: aggregate('pan'), countyFacts:[...countyFacts.values()],
    primaryCoordinates: primary.reduce((n,fips) => n+countyFacts.get(fips).coordinates,0), neighborCoordinates: neighbor.reduce((n,fips) => n+countyFacts.get(fips).coordinates,0),
    memory: {before, samples: rows.map(({afterCold,afterPan})=>({afterCold,afterPan})), after:process.memoryUsage(), peakRssKiB:process.resourceUsage().maxRSS},
    elapsedMs:performance.now()-start, counters, checksum,
    environment:{node:process.version,v8:process.versions.v8,platform:process.platform,arch:process.arch,cpuModel:os.cpus()[0]?.model,logicalCpuCount:os.cpus().length,totalMemoryBytes:os.totalmem(),osRelease:os.release()},
    limitations: ['Fresh process per scenario; warm-up and measured rounds within one process with explicit GC between rounds.',
      'Compressed inputs for the current and neighboring viewport are resident; cold means an empty prepared-county cache, not cold OS disk cache or network.',
      'JSON decode, assignment validation, d3 bounds/picking preparation and visible-only lazy SVG path generation are measured; production helper code is pinned.',
      'Rendered-block counts conservatively use projected bounding-box intersection; no Canvas rasterization, Path2D parsing, React, browser frame rate, or GPU time is measured.',
      'Node memory is process-level and includes benchmark fixtures, assertions, and transient allocations; not browser-memory evidence. Other desktop workloads may run concurrently.'] };
}
if (!INVENTORY_ONLY && CHILD_SCENARIO) {
  report.benchmark = runScenario(CHILD_SCENARIO); report.status='complete';
} else if (!INVENTORY_ONLY) {
  report.benchmarks = {};
  for (const name of Object.keys(scenarios)) {
    const childOutput = path.join(path.dirname(OUTPUT),`michigan-viewport-${name}-benchmark.json`);
    console.log(`Running ${name}: ${scenarios[name].countyCount} counties / ${scenarios[name].blocks} blocks`);
    const result = spawnSync(process.execPath,['--preserve-symlinks','--preserve-symlinks-main','--expose-gc',__filename,'--cache-root',CACHE,'--scenario',name,'--samples',String(SAMPLES),'--warmups',String(WARMUPS),'--output',childOutput],{cwd:ROOT,encoding:'utf8',maxBuffer:1024*1024,timeout:240000});
    assert.equal(result.status,0,`Scenario failed: ${name}\n${result.error || ''}\n${result.stderr}\n${result.stdout}`);
    const child = JSON.parse(fs.readFileSync(childOutput,'utf8')); assert.equal(child.status,'complete');
    report.benchmarks[name]=child.benchmark;
    for(const input of child.preservedInputs) { const existing=preserved.get(input.path); if(existing) assert.equal(existing,input.sha256); preserved.set(input.path,input.sha256); }
  }
  report.status='complete';
}
for (const [filename, expected] of preserved) assert.equal(sha(fs.readFileSync(filename)), expected, `Input changed: ${filename}`);
report.preservedInputs = [...preserved].map(([filename, sha256]) => ({ path: filename, sha256 }));
fs.mkdirSync(path.dirname(OUTPUT), { recursive: true }); fs.writeFileSync(OUTPUT, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ output: OUTPUT, status: report.status, scenarios: Object.fromEntries(Object.entries(scenarios).map(([key,value]) => [key, { k: value.view.k, counties: value.countyCount, blocks: value.blocks, rawMiB: value.rawBytes/1048576, gzipMiB: value.gzipBytes/1048576, addedGzipMiB: value.panCache.addedGzipBytes/1048576 }])) }, null, 2));
