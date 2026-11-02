#!/usr/bin/env node
/** Controlled request-completion replay; does not change maps or prior evidence. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const Module = require('node:module');
const { performance } = require('node:perf_hooks');
const { gunzipSync } = require('node:zlib');
const ROOT = path.resolve(__dirname, '..');
const requireRoot = Module.createRequire(path.join(ROOT, 'package.json'));
const ts = requireRoot('typescript');
const { geoPath } = requireRoot('d3-geo');
const args = process.argv.slice(2);
function option(name, fallback) { const i = args.indexOf(name); return i < 0 ? fallback : args[i + 1]; }
const CACHE = path.resolve(option('--cache-root', 'C:/Users/benja/projects/voting_paradigm/.cache'));
const OUTPUT = path.resolve(ROOT, option('--output', '.cache/block-main-port/michigan-inspection-progressive-replay.json'));
const OLD_CACHE = path.join(ROOT, '.cache/block-main-port/michigan-inspection-before/runtime-snapshot/lib/michigan-spatial-block-cache.ts');
const relativeOutput = path.relative(path.join(ROOT, '.cache/block-main-port'), OUTPUT);
assert.ok(relativeOutput && !relativeOutput.startsWith('..') && !path.isAbsolute(relativeOutput));
assert.equal(fs.existsSync(OUTPUT), false, 'Never overwrite earlier evidence; select a fresh output path.');
const pins = new Map();
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function readPinned(filename, expected) {
  const bytes = fs.readFileSync(filename), hash = sha(bytes);
  if (expected) assert.equal(hash, expected, filename);
  pins.set(filename, hash); return bytes;
}
readPinned(__filename);
const modules = new Map();
function loadTs(relative) {
  const filename = path.isAbsolute(relative) ? relative : path.join(ROOT, relative);
  if (modules.has(filename)) return modules.get(filename).exports;
  const m = new Module(filename, module); m.filename = filename;
  m.paths = Module._nodeModulePaths(path.dirname(filename)); modules.set(filename, m);
  m.require = specifier => specifier.startsWith('@/') ? loadTs(specifier.slice(2) + '.ts') : requireRoot(specifier);
  m._compile(ts.transpileModule(readPinned(filename).toString('utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true }, fileName: filename,
  }).outputText, filename);
  return m.exports;
}
const h = loadTs('lib/michigan-map-interaction.ts');
const { makeStateBlockProjection } = loadTs('lib/block-map-projection.ts');
const BeforeCache = loadTs(OLD_CACHE).MichiganSpatialBlockCache;
const AfterCache = loadTs('lib/michigan-spatial-block-cache.ts').MichiganSpatialBlockCache;
const index = JSON.parse(readPinned(path.join(ROOT, 'data/districting-block-plans/server-index.json')));
const manifest = JSON.parse(readPinned(path.join(ROOT, index.manifestPath), index.manifestSha256));
readPinned(path.join(ROOT, index.catalogPath), index.catalogSha256);
const plan = manifest.plans['26-13'], explorer = manifest.michiganExplorer.plans[plan.id];
function readAsset(asset) {
  const entry = index.assets[asset.url.replace(/^\/api\/district-plans\//, '')]; assert.ok(entry);
  assert.ok(!path.isAbsolute(entry.path) && !entry.path.includes('..') && !entry.path.includes(':'));
  const filename = entry.path.startsWith('.cache/') ? path.join(CACHE, entry.path.slice(7)) : path.join(ROOT, entry.path);
  const compressed = readPinned(filename, entry.gzipSha256), raw = gunzipSync(compressed);
  assert.equal(raw.length, asset.bytes); assert.equal(sha(raw), asset.sha256);
  return { compressed, document: JSON.parse(raw.toString('utf8')) };
}
const overview = readAsset(explorer.overview).document;
const summary = readAsset(explorer.summary).document;
const spatial = readAsset(explorer.spatialIndex).document;
h.validateMichiganSummary(summary, plan); h.validateMichiganSpatialIndex(spatial, plan, summary);
const baselinePath = path.join(ROOT, '.cache/block-main-port/michigan-viewport-benchmark.json');
const baseline = JSON.parse(readPinned(baselinePath));
const views = { cold: baseline.scenarios.kent.view, neighbor: baseline.scenarios.kent.neighbor.view };
views.nested = h.zoomAt(views.cold, 2, [500, 310], { min: 1, max: 256 });
const projection = makeStateBlockProjection(overview, '26'), drawingPath = geoPath(projection);
const projected = spatial.chunks.map(chunk => ({ chunkId: chunk.chunkId, bounds: h.projectedMichiganCountyBounds(chunk.bbox, projection) }));
const selected = Object.fromEntries(Object.entries(views).map(([name, view]) => [name, h.visibleMichiganSpatialChunks(projected, view)]));
assert.ok(selected.nested.every(id => selected.cold.includes(id)));
assert.ok(selected.neighbor.some(id => !selected.cold.includes(id)), 'Pan must enter an uncached area.');
assert.ok(selected.neighbor.some(id => selected.cold.includes(id)), 'Pan must retain a shared area.');
const ids = [...new Set([...selected.cold, ...selected.neighbor])];
const chunkById = new Map(spatial.chunks.map(chunk => [chunk.chunkId, chunk]));
const compressed = new Map(ids.map(id => [id, readAsset(chunkById.get(id).asset).compressed]));
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

async function replay(CacheClass, label) {
  let needed = [], currentView = views.cold, peakInFlight = 0;
  const jobs = [], events = [], decodeTimings = [], preparationTimings = [];
  const cache = new CacheClass({ chunks: spatial.chunks, concurrency: 2, onChange() {},
    load(chunk, signal) {
      let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; });
      jobs.push({ id: chunk.chunkId, signal, resolve, reject, settled: false }); return promise;
    },
  });
  const pending = () => jobs.filter(job => !job.settled && !job.signal.aborted);
  function record(stage) {
    const state = cache.snapshot(needed), bounds = h.viewportBounds(currentView);
    peakInFlight = Math.max(peakInFlight, state.inFlight);
    const renderData = state.renderData ?? state.data;
    const features = renderData.flatMap(chunk => chunk.shapes);
    const visible = features.filter(shape => h.boundsIntersect(shape.bounds, bounds));
    const geoids = features.map(shape => String(shape.feature.properties.geoid));
    assert.equal(new Set(geoids).size, geoids.length, 'No duplicated features in a partial or complete snapshot.');
    const result = { stage, ready: state.ready, pending: state.pending, error: state.error,
      loadedChunks: state.loaded, totalChunks: state.total, publishedChunks: state.data.length,
      renderedChunks: renderData.length,
      publishedBlocks: features.length, viewportVisibleBlocks: visible.length,
      requests: state.networkRequests, preparations: state.preparedChunks, inFlight: state.inFlight };
    events.push(result); return result;
  }
  function select(stage, idsToUse, view) {
    needed = idsToUse; currentView = view; const start = performance.now(); cache.setNeeded(needed);
    const result = record(stage); result.selectionCpuMs = performance.now() - start; return result;
  }
  async function complete(job) {
    assert.ok(job && !job.settled && !job.signal.aborted);
    const chunk = chunkById.get(job.id), start = performance.now();
    const decoded = JSON.parse(gunzipSync(compressed.get(job.id)).toString('utf8'));
    const valid = h.validateMichiganSpatialBlocks(decoded, plan, chunk);
    decodeTimings.push(performance.now() - start);
    const before = performance.now(), prepared = h.prepareMichiganCounty(valid, drawingPath);
    preparationTimings.push(performance.now() - before);
    job.settled = true; job.resolve(prepared); await flush();
  }
  async function finish(stage) {
    for (let guard = 0; !cache.snapshot(needed).ready; guard++) {
      assert.ok(guard < ids.length * 2); assert.equal(cache.snapshot(needed).error, null);
      await complete(pending()[0]); record(stage);
    }
  }
  select('cold-pending', selected.cold, views.cold);
  await complete(pending()[0]); record('cold-first-completion'); await finish('cold-progress');
  record('cold-ready');
  const nested = select('nested-cached', selected.nested, views.nested);
  const back = select('zoom-back-cached', selected.cold, views.cold);
  assert.equal(nested.ready, true); assert.equal(back.ready, true);
  const coldReady = events.find(event => event.stage === 'cold-ready');
  for (const event of [nested, back]) {
    assert.equal(event.requests, coldReady.requests); assert.equal(event.preparations, coldReady.preparations);
  }
  const neighborPending = select('neighbor-pending', selected.neighbor, views.neighbor);
  const retainedRenderData = cache.snapshot(needed).renderData;
  await complete(pending()[0]); record('neighbor-first-completion');
  if (label === 'after') assert.equal(cache.snapshot(needed).renderData, retainedRenderData, 'Individual new-area completion must not replace retained geometry.');
  await finish('neighbor-progress');
  const neighborReady = record('neighbor-ready');
  const returned = select('return-cached', selected.cold, views.cold);
  assert.equal(returned.ready, true); assert.equal(returned.requests, neighborReady.requests);
  assert.equal(returned.preparations, neighborReady.preparations); assert.ok(peakInFlight <= 2);
  if (label === 'before') {
    assert.equal(neighborPending.renderedChunks, 0, 'Captured baseline cache must hide incomplete viewports.');
  } else {
    assert.ok(neighborPending.renderedChunks > 0 && neighborPending.renderedChunks < neighborPending.totalChunks);
    assert.equal(neighborPending.publishedChunks, 0, 'The requested viewport remains incomplete.');
    const first = events.find(event => event.stage === 'neighbor-first-completion');
    assert.equal(first.renderedChunks, neighborPending.renderedChunks);
    assert.equal(first.viewportVisibleBlocks, neighborPending.viewportVisibleBlocks);
    assert.equal(first.ready, false, 'Retained visibility must not claim a complete viewport.');
    assert.equal(neighborReady.renderedChunks, neighborReady.totalChunks);
  }
  cache.dispose(); assert.equal(cache.snapshot([]).cacheSize, 0);
  return { label, events, peakInFlight, totalNetworkRequests: jobs.length,
    decodeAndValidationCpuMs: decodeTimings.reduce((a, b) => a + b, 0),
    synchronousPreparationCpuMs: preparationTimings.reduce((a, b) => a + b, 0),
    emptyAfterDispose: true };
}

(async () => {
  const before = await replay(BeforeCache, 'before'), after = await replay(AfterCache, 'after');
  assert.equal(before.totalNetworkRequests, after.totalNetworkRequests);
  for (const [filename, expected] of pins) assert.equal(sha(fs.readFileSync(filename)), expected, `Input changed: ${filename}`);
  const report = { schemaVersion: 1, status: 'complete', createdAtUtc: new Date().toISOString(), planId: plan.id,
    methodology: { purpose: 'Compare old hidden-incomplete rendering and new retained-cached rendering under the same controlled request completions. New-area geometry still publishes as a complete validated group.',
      cameraSource: baselinePath, views, selectedChunkCounts: Object.fromEntries(Object.entries(selected).map(([name, value]) => [name, value.length])),
      scheduling: 'Requests are held in explicit deferred promises, then completed one at a time with production validation and synchronous bounds preparation. The same saved source chunks feed both implementations.',
      limitations: ['This is a deterministic behavior replay, not a simulated network-speed claim.', 'CPU sums exclude browser paint, Canvas/Path2D generation, network transfer, and cooperative preparation yielding.', 'Single before/after run; CPU sums are informational and must not be presented as a speedup.'] },
    before, after, sourcePayloadsModified: 0, preservedInputs: [...pins].map(([filename, sha256]) => ({ path: filename, sha256 })) };
  fs.mkdirSync(path.dirname(OUTPUT), { recursive: true }); fs.writeFileSync(OUTPUT, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ output: OUTPUT, status: report.status,
    before: before.events.find(event => event.stage === 'neighbor-pending'),
    after: after.events.find(event => event.stage === 'neighbor-pending'),
    totalRequestsEach: after.totalNetworkRequests }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
