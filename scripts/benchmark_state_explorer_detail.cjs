#!/usr/bin/env node
/** Read-only, paired Node CPU/payload evidence for shared state block geometry. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const crypto = require('node:crypto'), Module = require('node:module'), os = require('node:os');
const {performance} = require('node:perf_hooks'), {gunzipSync} = require('node:zlib'), {spawnSync} = require('node:child_process');
const ROOT = path.resolve(__dirname, '..'), req = Module.createRequire(path.join(ROOT, 'package.json'));
const ts = req('typescript'), {geoPath} = req('d3-geo');
const args = process.argv.slice(2), option = (name, fallback) => { const i = args.indexOf(name); return i < 0 ? fallback : args[i + 1]; };
const CACHE = path.resolve(option('--cache-root', 'C:/Users/benja/projects/voting_paradigm/.cache'));
const SCENARIO = option('--scenario', null), SAMPLES = Number(option('--samples', '3')), WARMUPS = 1;
const MODE = option('--mode', 'paired');
assert.ok(['paired', 'baseline-only', 'viewport-only'].includes(MODE));
const OUTPUT = path.resolve(ROOT, option('--output', '.cache/block-main-port/state-explorer-detail-benchmark.json'));
const outputRelative = path.relative(path.join(ROOT, '.cache/block-main-port'), OUTPUT);
assert.ok(outputRelative && !outputRelative.startsWith('..') && !path.isAbsolute(outputRelative));
assert.ok(Number.isInteger(SAMPLES) && SAMPLES >= 3 && SAMPLES <= 10);
let progressSequence = 0;
function checkpoint(stage, details = {}) {
  const value = {schemaVersion: 1, scenario: SCENARIO, mode: MODE, sequence: ++progressSequence, stage, details,
    recordedAtUtc: new Date().toISOString(), elapsedMs: performance.now(), memory: process.memoryUsage()};
  fs.mkdirSync(path.dirname(OUTPUT), {recursive: true});
  const target = OUTPUT.replace(/\.json$/, '') + '.progress.json', temporary = target + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(value, null, 2) + '\n'); fs.renameSync(temporary, target);
}
const SCENARIOS = {
  alaska_aleutians_west: {planId: '02-2', countyFips: '016', countyName: 'Aleutians West'},
  rhode_island_providence: {planId: '44-2', countyFips: '007', countyName: 'Providence'},
  california_los_angeles: {planId: '06-52', countyFips: '037', countyName: 'Los Angeles'},
  new_york_new_york: {planId: '36-26', countyFips: '061', countyName: 'New York'},
  texas_harris: {planId: '48-38', countyFips: '201', countyName: 'Harris'},
};
const pins = new Map(), sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function readPinned(filename, expected) {
  const bytes = fs.readFileSync(filename), value = sha(bytes);
  if (expected) assert.equal(value, expected, filename);
  if (pins.has(filename)) assert.equal(value, pins.get(filename), `Input changed: ${filename}`);
  pins.set(filename, value); return bytes;
}
readPinned(__filename);
readPinned(path.join(ROOT, 'scripts/state_explorer_benchmark_memory.cjs'));
const {releaseAssetLookups, scopeAssetLookups} = require('./state_explorer_benchmark_memory.cjs');
checkpoint('read-server-index');
const index = JSON.parse(readPinned(path.join(ROOT, 'data/districting-block-plans/server-index.json')));
checkpoint('read-manifest');
const manifest = JSON.parse(readPinned(path.join(ROOT, index.manifestPath), index.manifestSha256));
readPinned(path.join(ROOT, index.catalogPath), index.catalogSha256);
function fragmentPaths(name) {
  const {planId} = SCENARIOS[name];
  return {blocks: path.join(ROOT, 'data/districting-block-plans/state-explorer-blocks-v1', `${planId.slice(0, 2)}.json`),
    geometry: path.join(ROOT, 'data/districting-block-plans/state-explorer-geometry-fragments', `${planId}.json`)};
}
function availability(name) {
  const files = fragmentPaths(name);
  if (!fs.existsSync(files.blocks)) return {status: 'pending', reason: 'Complete state block fragment not yet available.'};
  if (!fs.existsSync(files.geometry)) return {status: 'pending', reason: 'Complete plan geometry fragment not yet available.'};
  const blocks = JSON.parse(fs.readFileSync(files.blocks, 'utf8')), geometry = JSON.parse(fs.readFileSync(files.geometry, 'utf8'));
  assert.equal(blocks.status, 'complete'); assert.equal(blocks.catalogSha256, index.catalogSha256);
  assert.equal(geometry.status, 'complete'); assert.equal(geometry.identity.catalogSha256, index.catalogSha256);
  assert.ok(blocks.plans[SCENARIOS[name].planId]);
  return {status: 'available'};
}
function compressedAsset(asset) {
  assert.ok(asset.url.startsWith('/api/district-plans/'));
  const entry = index.assets[asset.url.slice('/api/district-plans/'.length)]; assert.ok(entry, asset.url);
  assert.ok(!path.isAbsolute(entry.path) && !entry.path.includes('..') && !entry.path.includes(':'));
  assert.equal(entry.rawSha256, asset.sha256); assert.equal(entry.rawBytes, asset.bytes); assert.equal(entry.gzipBytes, asset.gzipBytes);
  const filename = entry.path.startsWith('.cache/') ? path.join(CACHE, entry.path.slice(7)) : path.join(ROOT, entry.path);
  const bytes = readPinned(filename, entry.gzipSha256); assert.equal(bytes.length, asset.gzipBytes); return bytes;
}
function decode(buffer, asset) {
  const raw = gunzipSync(buffer); assert.equal(raw.length, asset.bytes); assert.equal(sha(raw), asset.sha256);
  return JSON.parse(raw.toString('utf8'));
}
function decodedAsset(asset) { return decode(compressedAsset(asset), asset); }
const modules = new Map();
function loadTs(relative) {
  const filename = path.join(ROOT, relative); if (modules.has(filename)) return modules.get(filename).exports;
  const m = new Module(filename, module); m.filename = filename; m.paths = Module._nodeModulePaths(path.dirname(filename)); modules.set(filename, m);
  m.require = spec => spec.startsWith('@/') ? loadTs(spec.slice(2) + '.ts') : req(spec);
  m._compile(ts.transpileModule(readPinned(filename).toString('utf8'), {compilerOptions: {target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS, esModuleInterop: true}, fileName: filename}).outputText, filename); return m.exports;
}
const h = loadTs('lib/state-map-interaction.ts');
const {StateSpatialBlockCache} = loadTs('lib/state-spatial-block-cache.ts');
const {restoreStateSpatialAssignments} = loadTs('lib/state-spatial-blocks.ts');
const {makeStateBlockProjection} = loadTs('lib/block-map-projection.ts');
const timed = fn => { const start = performance.now(), value = fn(); return {ms: performance.now() - start, value}; };
function stats(values) { const sorted = [...values].sort((a, b) => a - b); return {samples: values, median: sorted[Math.floor(sorted.length / 2)], min: sorted[0], max: sorted.at(-1)}; }
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
function summaryRows(rows) {
  return Object.fromEntries(Object.keys(rows[0]).map(key => [key, key.endsWith('Ms') ? stats(rows.map(r => r[key])) : rows[0][key]]));
}

async function run(name) {
  checkpoint('load-plan-metadata', {name});
  assert.equal(availability(name).status, 'available', `Scenario not yet available: ${name}`);
  const spec = SCENARIOS[name], files = fragmentPaths(name), plan = manifest.plans[spec.planId]; assert.ok(plan);
  const blocks = JSON.parse(readPinned(files.blocks)), geometry = JSON.parse(readPinned(files.geometry));
  Object.assign(index.assets, blocks.assets, geometry.assets);
  const explorer = {...geometry.record, ...blocks.plans[plan.id]};
  const overview = decodedAsset(explorer.overview), summary = decodedAsset(explorer.summary), spatial = decodedAsset(explorer.spatialIndex);
  const originalIndex = decodedAsset(plan.assets.detailIndex), referenceCounties = decodedAsset(manifest.comparisonLayers[plan.stateFips].counties.asset);
  h.validateStateSummary(summary, plan); h.validateStateSpatialIndex(spatial, plan, summary); assert.equal(spatial.schemaVersion, 2);
  const selectedCounty = summary.counties.find(c => c.fips === spec.countyFips); assert.ok(selectedCounty);
  assert.ok(selectedCounty.name.includes(spec.countyName));
  const projection = makeStateBlockProjection(overview, plan.stateFips), drawingPath = geoPath(projection);
  const reference = referenceCounties.features.find(f => f.properties.geoid === plan.stateFips + spec.countyFips); assert.ok(reference);
  const projectedChunks = spatial.chunks.map(c => ({chunkId: c.chunkId, bounds: h.projectedStateCountyBounds(c.bbox, projection),
    rawBytes: c.asset.bytes + (c.assignments?.bytes ?? 0), blockCount: c.blockCount}));
  const projectedCounties = summary.counties.map(c => ({fips: c.fips, bounds: h.projectedStateCountyBounds(c.bbox, projection)}));
  const countyFit = h.constrainViewport(h.fitMapBounds(drawingPath.bounds(reference)), {min: 7, max: 256});
  const requestedCold = h.constrainViewport(h.fitStateInspectionFeature(reference, drawingPath, 7), {min: 7, max: 256});
  const coldBudget = h.fitStateBlockBudget(requestedCold, projectedChunks); assert.equal(coldBudget.blocked, false, 'Production budget must permit this scenario');
  const cold = coldBudget.view;
  const focus = {method: 'production-county-inspection-fit', originalFit: countyFit, originalFitChunks: h.visibleStateSpatialChunks(projectedChunks, countyFit).length,
    inspectionFit: requestedCold, inspectionFitChunks: h.visibleStateSpatialChunks(projectedChunks, requestedCold).length,
    budgetedFit: cold, budgetedFitChunks: coldBudget.chunkIds.length};
  if (reference.geometry.type === 'MultiPolygon') {
    const parts = reference.geometry.coordinates.map((coordinates, i) => {
      const feature = {...reference, geometry: {type: 'Polygon', coordinates}};
      return {feature, partIndex: i, projectedArea: drawingPath.area(feature)};
    }).sort((a, b) => b.projectedArea - a.projectedArea || a.partIndex - b.partIndex);
    const largest = parts[0], candidateView = h.constrainViewport(h.fitMapBounds(drawingPath.bounds(largest.feature)), {min: 7, max: 256});
    focus.largestReferencePolygonCandidate = {partIndex: largest.partIndex, projectedArea: largest.projectedArea, view: candidateView,
      visibleChunks: h.visibleStateSpatialChunks(projectedChunks, candidateView).length};
  }
  const nestedBudget = h.fitStateBlockBudget(h.zoomAt(cold, 2, [500, 310], {min: 6, max: 256}), projectedChunks);
  const neighborBudget = h.fitStateBlockBudget({...cold, x: cold.x - 320}, projectedChunks);
  assert.equal(nestedBudget.blocked, false); assert.equal(neighborBudget.blocked, false);
  const nested = nestedBudget.view, neighbor = neighborBudget.view;
  const views = {cold, nested, zoomBack: cold, neighbor, returnToOriginal: cold};
  const selections = Object.fromEntries(Object.entries(views).map(([stage, view]) => [stage, h.visibleStateSpatialChunks(projectedChunks, view)]));
  const cameraBudgets = {cold: coldBudget, nested: nestedBudget, neighbor: neighborBudget};
  for (const [stage, budget] of Object.entries(cameraBudgets)) {
    assert.deepEqual(selections[stage], budget.chunkIds, 'Budget fitting must retain every visible chunk');
    assert.ok(budget.rawBytes <= h.STATE_BLOCK_MAX_RAW_BYTES); assert.ok(budget.blockCount <= h.STATE_BLOCK_MAX_VISIBLE_BLOCKS);
  }
  assert.ok(selections.cold.length); assert.ok(selections.nested.every(id => selections.cold.includes(id)));
  const chunkMap = new Map(spatial.chunks.map(c => [c.chunkId, c])), allIds = [...new Set(Object.values(selections).flat())];
  let scopedAssets = scopeAssetLookups(index.assets, [
    ...originalIndex.counties.map(county => county.asset),
    ...(MODE === 'baseline-only' ? [] : allIds.flatMap(id => {const chunk = chunkMap.get(id); return [chunk.asset, chunk.assignments];})),
  ]);
  checkpoint('release-national-lookups-before-block-decode', {selectedChunks: allIds.length, scopedEntries: Object.keys(scopedAssets).length});
  const earlyMetadataLookupMemory = releaseAssetLookups([
    {name: 'serverIndex', owner: index}, {name: 'stateBlockFragment', owner: blocks}, {name: 'planGeometryFragment', owner: geometry},
  ]);
  index.assets = scopedAssets;
  scopedAssets = null;
  const buffers = new Map();
  checkpoint('load-selected-chunk-buffers', {selectedChunks: MODE === 'baseline-only' ? 0 : allIds.length});
  if (MODE !== 'baseline-only') for (const id of allIds) { const chunk = chunkMap.get(id); assert.ok(chunk.assignments); buffers.set(id, {geometry: compressedAsset(chunk.asset), assignments: compressedAsset(chunk.assignments)}); }
  const sourceCountyIds = new Set(Object.values(views).flatMap(view => h.visibleStateCountyFips(projectedCounties, view)));
  // Include every county touched by fetched chunks, even broad spanning chunks.
  checkpoint('discover-source-county-membership');
  if (MODE !== 'baseline-only') for (const id of allIds) {
    const features = decode(buffers.get(id).geometry, chunkMap.get(id).asset).features;
    for (const feature of features) sourceCountyIds.add(feature.properties.geoid.slice(2, 5));
  }
  const sourceCounties = [...sourceCountyIds].sort().map(fips => { const c = originalIndex.counties.find(c => c.fips === fips); assert.ok(c); return c; });
  checkpoint('load-original-county-buffers', {counties: sourceCounties.map(c => ({fips: c.fips, bytes: c.asset.bytes, blocks: c.blockCount}))});
  const countyBuffers = new Map(sourceCounties.map(c => [c.fips, compressedAsset(c.asset)]));
  assert.equal(buffers.size, MODE === 'baseline-only' ? 0 : allIds.length); assert.equal(countyBuffers.size, sourceCounties.length);
  const metadataLookupMemory = releaseAssetLookups([
    {name: 'serverIndex', owner: index}, {name: 'stateBlockFragment', owner: blocks}, {name: 'planGeometryFragment', owner: geometry},
  ]);
  assert.ok(metadataLookupMemory.released.every(owner => owner.retainedAssetEntries === 0));
  assert.ok(pins.has(path.join(ROOT, 'data/districting-block-plans/server-index.json')));
  // All subsequent preparation/audit uses these already hash-checked resident
  // buffers. Full-index and fragment hashes remain pinned through completion.
  const bytes = ids => ids.reduce((sum, id) => { const c = chunkMap.get(id); return sum + c.asset.gzipBytes + c.assignments.gzipBytes; }, 0);
  const rawBytes = ids => ids.reduce((sum, id) => { const c = chunkMap.get(id); return sum + c.asset.bytes + c.assignments.bytes; }, 0);
  const measured = [], baseline = [];
  const baselineIds = new Set(h.visibleStateCountyFips(projectedCounties, cold));
  const wholeCountyReference = sourceCounties.filter(c => baselineIds.has(c.fips)).reduce((result, county) => ({
    gzipBytes: result.gzipBytes + county.asset.gzipBytes, rawBytes: result.rawBytes + county.asset.bytes, loadedBlocks: result.loadedBlocks + county.blockCount,
  }), {gzipBytes: 0, rawBytes: 0, loadedBlocks: 0});
  for (let round = -WARMUPS; round < SAMPLES; round++) {
    if (global.gc) global.gc();
    const baselineRow = {decodeMs: 0, validateMs: 0, prepareMs: 0, visiblePathMs: 0, loadedBlocks: 0, visibleBlocks: 0, gzipBytes: 0, rawBytes: 0};
    // A cold whole-county alternative uses the same source-bbox visibility rule.
    if (MODE !== 'viewport-only') for (const county of sourceCounties.filter(c => baselineIds.has(c.fips))) {
      checkpoint('baseline-decode-county', {round, county: county.fips, bytes: county.asset.bytes, blocks: county.blockCount});
      const decoded = timed(() => decode(countyBuffers.get(county.fips), county.asset));
      const valid = timed(() => h.validateCountyBlocks(decoded.value, plan, county.fips, county.population, county.blockCount));
      checkpoint('baseline-prepare-county', {round, county: county.fips});
      const prepared = timed(() => h.prepareStateCounty(valid.value, drawingPath));
      checkpoint('baseline-visible-paths', {round, county: county.fips});
      const paths = timed(() => prepared.value.shapes.filter(s => h.boundsIntersect(s.bounds, h.viewportBounds(cold))).reduce((sum, s) => sum + s.d.length, 0));
      baselineRow.decodeMs += decoded.ms; baselineRow.validateMs += valid.ms; baselineRow.prepareMs += prepared.ms; baselineRow.visiblePathMs += paths.ms;
      baselineRow.loadedBlocks += county.blockCount; baselineRow.visibleBlocks += prepared.value.shapes.filter(s => h.boundsIntersect(s.bounds, h.viewportBounds(cold))).length;
      baselineRow.gzipBytes += county.asset.gzipBytes; baselineRow.rawBytes += county.asset.bytes;
    }
    baselineRow.totalCpuMs = baselineRow.decodeMs + baselineRow.validateMs + baselineRow.prepareMs + baselineRow.visiblePathMs;
    if (round >= 0 && MODE !== 'viewport-only') baseline.push(baselineRow);
    if (MODE === 'baseline-only') continue;
    if (global.gc) global.gc();
    let activeTimes;
    const cache = new StateSpatialBlockCache({chunks: spatial.chunks, concurrency: 2, onChange() {}, async load(chunk, signal) {
      const input = buffers.get(chunk.chunkId);
      const decoded = timed(() => ({geometry: decode(input.geometry, chunk.asset), assignments: decode(input.assignments, chunk.assignments)}));
      const restored = timed(() => restoreStateSpatialAssignments(decoded.value.geometry, decoded.value.assignments, plan, chunk));
      const prepared = timed(() => h.prepareStateCounty(restored.value, drawingPath)); assert.equal(signal.aborted, false);
      activeTimes.decodeMs += decoded.ms; activeTimes.restoreAndValidateMs += restored.ms; activeTimes.prepareMs += prepared.ms; return prepared.value;
    }});
    const generated = new WeakSet(), row = {};
    for (const [stage, view] of Object.entries(views)) {
      checkpoint('viewport-prepare', {round, stage, chunks: selections[stage].length, rawBytes: rawBytes(selections[stage])});
      const ids = selections[stage], before = cache.snapshot(ids);
      activeTimes = {decodeMs: 0, restoreAndValidateMs: 0, prepareMs: 0};
      const start = performance.now(); cache.setNeeded(ids); const readySynchronously = cache.snapshot(ids).ready;
      for (let tick = 0; ids.length && !cache.snapshot(ids).ready; tick++) { assert.ok(tick < allIds.length * 8 + 32); assert.equal(cache.snapshot(ids).error, null); await Promise.resolve(); }
      const ready = cache.snapshot(ids), visible = timed(() => ready.data.flatMap(c => c.shapes).filter(s => h.boundsIntersect(s.bounds, h.viewportBounds(view))));
      const newPaths = visible.value.filter(s => !generated.has(s)).length;
      const paths = timed(() => visible.value.reduce((sum, s) => sum + s.d.length, 0)); for (const shape of visible.value) generated.add(shape);
      row[stage] = {...activeTimes, cullMs: visible.ms, visiblePathMs: paths.ms, totalCpuMs: performance.now() - start,
        readySynchronously, requests: ready.networkRequests - before.networkRequests, preparedChunks: ready.preparedChunks - before.preparedChunks,
        neededChunks: ids.length, loadedBlocks: ids.reduce((sum, id) => sum + chunkMap.get(id).blockCount, 0), visibleBlocks: visible.value.length,
        newVisiblePaths: newPaths, gzipBytes: bytes(ids), rawBytes: rawBytes(ids), cachedBytes: ready.cachedBytes};
      if (stage === 'nested') { if (ids.length) assert.equal(readySynchronously, true); assert.equal(row[stage].requests, 0); assert.equal(row[stage].preparedChunks, 0); assert.equal(newPaths, 0); }
      if (stage === 'zoomBack' && rawBytes(selections.cold) <= 64 * 1024 * 1024) { assert.equal(readySynchronously, true); assert.equal(row[stage].requests, 0); assert.equal(row[stage].preparedChunks, 0); }
    }
    row.memory = process.memoryUsage(); cache.dispose(); assert.equal(cache.snapshot([]).cacheSize, 0);
    if (round >= 0) measured.push(row);
  }
  const peakPreparationRssKiB = process.resourceUsage().maxRSS;
  const common = {name, mode: MODE, planId: plan.id, state: plan.stateName, county: selectedCounty.displayName ?? selectedCounty.name, countyFips: spec.countyFips,
    coordinateFrame: plan.coordinateFrame, focus, views, cameraBudgets, wholeCountyReference, baselineWholeCounties: baseline.length ? summaryRows(baseline) : null,
    earlyMetadataLookupMemory, metadataLookupMemory, peakPreparationRssKiB};
  if (MODE === 'baseline-only') return {...common, stages: null, parity: {status: 'not-run', reason: 'Baseline-only mode validates original county block totals; chunk restoration belongs to viewport-only/paired mode.'}, memorySamples: [], peakIncludingAuditRssKiB: process.resourceUsage().maxRSS};
  if (global.gc) global.gc();
  checkpoint('audit-restored-chunk-features', {chunks: allIds.length});
  const fingerprints = new Map(), actualVisible = Object.fromEntries(Object.keys(views).map(stage => [stage, new Set()]));
  for (const id of allIds) {
    const chunk = chunkMap.get(id), input = buffers.get(id);
    const document = restoreStateSpatialAssignments(decode(input.geometry, chunk.asset), decode(input.assignments, chunk.assignments), plan, chunk);
    for (const feature of document.features) {
      const geoid = feature.properties.geoid; assert.ok(!fingerprints.has(geoid), `Duplicate source GEOID ${geoid}`);
      fingerprints.set(geoid, sha(canonical(feature)));
      const bounds = drawingPath.bounds(feature);
      for (const [stage, view] of Object.entries(views)) if (selections[stage].includes(id) && h.boundsIntersect(bounds, h.viewportBounds(view))) actualVisible[stage].add(geoid);
    }
  }
  const expectedVisible = Object.fromEntries(Object.keys(views).map(stage => [stage, new Set()])); let exactMatches = 0;
  for (const county of sourceCounties) {
    checkpoint('audit-original-county', {county: county.fips, bytes: county.asset.bytes, blocks: county.blockCount});
    const document = decode(countyBuffers.get(county.fips), county.asset); h.validateCountyBlocks(document, plan, county.fips, county.population, county.blockCount);
    for (const feature of document.features) {
      const geoid = feature.properties.geoid;
      if (fingerprints.has(geoid)) { assert.equal(sha(canonical(feature)), fingerprints.get(geoid), `Source feature changed: ${geoid}`); exactMatches++; }
      const bounds = drawingPath.bounds(feature);
      for (const [stage, view] of Object.entries(views)) if (h.boundsIntersect(bounds, h.viewportBounds(view))) expectedVisible[stage].add(geoid);
    }
  }
  assert.equal(exactMatches, fingerprints.size);
  for (const stage of Object.keys(views)) assert.deepEqual([...actualVisible[stage]].sort(), [...expectedVisible[stage]].sort(), `Visible GEOID coverage: ${stage}`);
  if (baseline.length) assert.equal(measured[0].cold.visibleBlocks, baseline[0].visibleBlocks);
  return {...common,
    stages: Object.fromEntries(Object.keys(views).map(stage => [stage, summaryRows(measured.map(row => row[stage]))])),
    parity: {exactRestoredSourceFeatures: exactMatches, duplicateGeoids: 0, visibleSourceCounts: Object.fromEntries(Object.entries(expectedVisible).map(([stage, ids]) => [stage, ids.size]))},
    memorySamples: measured.map(row => row.memory), peakIncludingAuditRssKiB: process.resourceUsage().maxRSS};
}

(async () => {
  const selected = SCENARIO ? [SCENARIO] : option('--scenarios', Object.keys(SCENARIOS).join(',')).split(',');
  for (const name of selected) assert.ok(SCENARIOS[name], `Unknown scenario ${name}`);
  const available = Object.fromEntries(selected.map(name => [name, availability(name)]));
  if (SCENARIO || args.includes('--require-all')) assert.ok(Object.values(available).every(value => value.status === 'available'), 'Required complete fragments are still pending.');
  const report = {schemaVersion: 1, status: 'complete', createdAtUtc: new Date().toISOString(), availability: available,
    methodology: {mode: MODE, samples: SAMPLES, warmups: WARMUPS, cacheBudgetRawBytes: 64 * 1024 * 1024,
      activeViewportBudget: {rawBytes: h.STATE_BLOCK_MAX_RAW_BYTES, blocks: h.STATE_BLOCK_MAX_VISIBLE_BLOCKS},
      camera: 'Production county inspection fit and Blocks minimum 7x, then production fitStateBlockBudget. Apply the same budget preflight after nested 2x zoom and 320 map-unit east pan. Every visible chunk remains included. Prior broad county-fit cameras remain recorded; these tighter views are a workload change, not a same-view speedup.',
      timings: 'Node CPU with resident gzip buffers: hash-checked decode, production restore/validation, production synchronous bounds/picking preparation, production cache scheduling and lazy visible SVG paths. Cooperative yields and browser/RAF wall time are excluded.',
      baseline: 'Paired whole-county preparation in the same fresh scenario process, one county at a time to bound memory. Both strategies use the same viewport and validate source population totals.',
      metadataOwnership: 'After plan metadata establishes viewport refs, retain only exact verified entries for selected chunks and state county assets; release national/fragment dictionaries before block decoding. Release the scoped lookup once required buffers are hash-checked. Driver releases its unused dictionary before children. All source hashes remain pinned.',
      limitations: ['No browser FPS, input latency, actual Canvas/Path2D, network latency, or GPU measurements.', '64 MiB is a raw JSON retention budget, not a heap bound; active visible coverage can exceed it.', 'Each scenario runs serially in a fresh Node process capped at 2 GiB JS heap; desktop contention may affect timing.', 'Resource maxRSS fields cover process startup and metadata parsing through their observation point, not only client preparation. Per-round heap samples follow metadata release.', 'Display land clipping is not applied to the bounds-visibility benchmark; all source geography including water is audited.']},
    environment: {node: process.version, v8: process.versions.v8, osRelease: os.release(), cpu: os.cpus()[0]?.model, logicalCpuCount: os.cpus().length, totalMemoryBytes: os.totalmem()}, benchmarks: {}};
  const priorFailure = path.join(ROOT, '.cache/block-main-port/state-explorer-detail-final-failure.json');
  if (fs.existsSync(priorFailure)) report.preservedPriorFailure = {path: priorFailure, sha256: sha(readPinned(priorFailure)),
    note: 'Original California child exhausted its unchanged 2 GiB heap while the harness retained the full server lookup map; no browser failure is established by that attempt.'};
  if (SCENARIO) report.benchmarks[SCENARIO] = await run(SCENARIO);
  else {
    report.driverMetadataLookupMemory = releaseAssetLookups([{name: 'serverIndex', owner: index}]);
    assert.equal(Object.keys(index.assets).length, 0);
    for (const name of selected.filter(name => available[name].status === 'available')) {
    const output = path.join(path.dirname(OUTPUT), path.basename(OUTPUT, '.json') + '-' + name + '.json');
    console.log(`Benchmarking ${name}`);
    const child = spawnSync(process.execPath, ['--preserve-symlinks', '--preserve-symlinks-main', '--expose-gc', '--max-old-space-size=2048', __filename,
      '--scenario', name, '--mode', MODE, '--cache-root', CACHE, '--samples', String(SAMPLES), '--output', output], {cwd: ROOT, encoding: 'utf8', maxBuffer: 1024 * 1024, timeout: 900000});
    assert.equal(child.status, 0, `${child.error ?? ''}\n${child.stderr}\n${child.stdout}`);
    const value = JSON.parse(fs.readFileSync(output, 'utf8')); report.benchmarks[name] = value.benchmarks[name];
    for (const pin of value.preservedInputs) { if (pins.has(pin.path)) assert.equal(pins.get(pin.path), pin.sha256); pins.set(pin.path, pin.sha256); }
    }
  }
  if (Object.values(available).some(value => value.status === 'pending')) report.status = Object.keys(report.benchmarks).length ? 'partial' : 'pending';
  for (const [filename, expected] of pins) assert.equal(sha(fs.readFileSync(filename)), expected, `Input changed: ${filename}`);
  report.preservedInputs = [...pins].map(([filename, sha256]) => ({path: filename, sha256})); report.inputFilesModified = 0;
  checkpoint('complete', {scenarios: Object.keys(report.benchmarks)});
  fs.mkdirSync(path.dirname(OUTPUT), {recursive: true}); const temporary = OUTPUT + '.tmp'; fs.writeFileSync(temporary, JSON.stringify(report, null, 2) + '\n'); fs.renameSync(temporary, OUTPUT);
  console.log(JSON.stringify({output: OUTPUT, status: report.status, availability: report.availability,
    results: Object.fromEntries(Object.entries(report.benchmarks).map(([name, b]) => [name, {wholeCountyGzipBytes: b.wholeCountyReference.gzipBytes,
      viewportGzipBytes: b.stages?.cold.gzipBytes ?? null, coldCpuMs: b.stages?.cold.totalCpuMs.median ?? null, nestedRequests: b.stages?.nested.requests ?? null,
      nestedPreparedChunks: b.stages?.nested.preparedChunks ?? null, exactRestoredFeatures: b.parity.exactRestoredSourceFeatures ?? null}]))}, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
