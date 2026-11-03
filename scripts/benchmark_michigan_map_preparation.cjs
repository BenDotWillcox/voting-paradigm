#!/usr/bin/env node
/**
 * Read-only CPU benchmark of Michigan map geometry preparation.
 *
 * Uses the application's actual projection/picking helpers and d3 path code.
 * This measures Node preprocessing, not browser frame rate, raster paint, GPU
 * composition, React scheduling, user input latency, or download performance.
 *
 * node --preserve-symlinks --preserve-symlinks-main \
 *   scripts/benchmark_michigan_map_preparation.cjs \
 *   --cache-root C:/Users/benja/projects/voting_paradigm/.cache
 */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const Module = require('node:module');
const { performance } = require('node:perf_hooks');
const { gunzipSync } = require('node:zlib');

const ROOT = path.resolve(__dirname, '..');
const rootRequire = Module.createRequire(path.join(ROOT, 'package.json'));
const ts = rootRequire('typescript');
const { geoPath } = rootRequire('d3-geo');
const argv = process.argv.slice(2);
function option(name, fallback) {
  const i = argv.indexOf(name);
  if (i < 0) return fallback;
  if (i + 1 >= argv.length || argv[i + 1].startsWith('--')) throw Error(`Missing value for ${name}`);
  return argv[i + 1];
}
const envText = fs.existsSync(path.join(ROOT, '.env.local')) ? fs.readFileSync(path.join(ROOT, '.env.local'), 'utf8') : '';
const envCache = envText.match(/^BLOCK_PLAN_CACHE_ROOT=(.+)$/m)?.[1].trim().replace(/^['"]|['"]$/g, '');
const CACHE = path.resolve(option('--cache-root', process.env.BLOCK_PLAN_CACHE_ROOT || envCache || path.join(ROOT, '.cache')));
const PLAN_ID = option('--plan', '26-13');
const SAMPLES = Number(option('--samples', '7'));
const WARMUPS = Number(option('--warmups', '2'));
assert.ok(Number.isInteger(SAMPLES) && SAMPLES >= 3 && SAMPLES <= 50, 'Use 3–50 measured samples');
assert.ok(Number.isInteger(WARMUPS) && WARMUPS >= 1 && WARMUPS <= 10, 'Use 1–10 warm-up samples');
const OUTPUT = path.resolve(ROOT, option('--output', '.cache/block-main-port/michigan-map-preparation-benchmark.json'));
assert.ok(path.relative(path.join(ROOT, '.cache', 'block-main-port'), OUTPUT) && !path.relative(path.join(ROOT, '.cache', 'block-main-port'), OUTPUT).startsWith('..'), 'Output must stay in the task evidence directory');
const NOTE = option('--note', 'Local desktop benchmark; other desktop/browser/agent work may be active. No CPU affinity or process isolation.');

const pinnedInputs = new Map();
function sha(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function pinnedRead(filename, expected) {
  const bytes = fs.readFileSync(filename);
  const actual = sha(bytes);
  if (expected) assert.equal(actual, expected, `Hash mismatch: ${filename}`);
  pinnedInputs.set(filename, actual);
  return bytes;
}
function within(root, relative) {
  assert.ok(!path.isAbsolute(relative) && !relative.includes('..') && !relative.includes(':'), 'Unsafe indexed path');
  const resolved = path.resolve(root, relative);
  assert.ok(!path.relative(root, resolved).startsWith('..'), 'Resource escaped its root');
  return resolved;
}
const indexBytes = pinnedRead(path.join(ROOT, 'data/districting-block-plans/server-index.json'));
const index = JSON.parse(indexBytes);
const manifestBytes = pinnedRead(path.join(ROOT, index.manifestPath), index.manifestSha256);
const manifest = JSON.parse(manifestBytes);
pinnedRead(path.join(ROOT, index.catalogPath), index.catalogSha256);
assert.equal(manifest.catalogSha256, index.catalogSha256);
const plan = manifest.plans[PLAN_ID];
assert.ok(plan && plan.stateFips === '26', 'Benchmark requires a Michigan plan');
const explorer = manifest.michiganExplorer.plans[PLAN_ID];
assert.ok(explorer, 'Michigan explorer assets are required');
const compressed = new Map(), decoded = new Map(), loadEvents = [];
function assetEntry(asset) {
  const key = asset.url.replace(/^\/api\/district-plans\//, '');
  assert.notEqual(key, asset.url, 'Unexpected asset URL');
  const entry = index.assets[key];
  assert.ok(entry, 'Asset is not in the pinned server index');
  const filename = entry.path.startsWith('.cache/') ? within(CACHE, entry.path.slice(7)) : within(ROOT, entry.path);
  return { entry, filename };
}
function loadAsset(label, asset) {
  const { entry, filename } = assetEntry(asset);
  const readStart = performance.now();
  const bytes = fs.readFileSync(filename);
  const fileReadMs = performance.now() - readStart;
  assert.equal(sha(bytes), entry.gzipSha256);
  pinnedInputs.set(filename, entry.gzipSha256);
  const decodeStart = performance.now();
  const raw = gunzipSync(bytes);
  const inflateMs = performance.now() - decodeStart;
  assert.equal(sha(raw), asset.sha256);
  assert.equal(sha(raw), entry.rawSha256);
  assert.equal(raw.length, asset.bytes);
  const parseStart = performance.now();
  const data = JSON.parse(raw.toString('utf8'));
  const jsonDecodeMs = performance.now() - parseStart;
  compressed.set(label, bytes); decoded.set(label, data);
  loadEvents.push({ label, fileReadMs, inflateMs, jsonDecodeMs, gzipBytes: bytes.length, rawBytes: raw.length, sha256: asset.sha256 });
  return data;
}
const overview = loadAsset('overview', explorer.overview);
const fine = loadAsset('fine', manifest.landDisplays[PLAN_ID].state);
const overviewDividers = loadAsset('overview_dividers', explorer.dividers);
const fineDividers = loadAsset('fine_dividers', explorer.detailDividers);
const coast = loadAsset('overview_coast', explorer.coast);
const detailIndex = loadAsset('county_index', plan.assets.detailIndex);
const summary = loadAsset('summary', explorer.summary);
const kentInfo = detailIndex.counties.find((county) => county.fips === '081');
const kentSummary = summary.counties.find((county) => county.fips === '081');
assert.ok(kentInfo && kentSummary?.name === 'Kent');
const kent = loadAsset('kent_blocks', kentInfo.asset);
assert.equal(kent.features.length, kentInfo.blockCount);
assert.equal(kent.features.reduce((total, feature) => total + feature.properties.population, 0), kentInfo.population);
assert.equal(new Set(kent.features.map((feature) => feature.properties.geoid)).size, kent.features.length);
assert.ok(kent.features.every((feature) => feature.properties.geoid.startsWith('26081')));
for (const collection of [overview, fine]) {
  assert.equal(collection.features.length, plan.districtCount);
  for (const feature of collection.features) assert.equal(feature.properties.population, plan.districtPopulations[feature.properties.district_id]);
}

// Same transpilation/import path used by the repository's TS contract tests.
const loaded = new Map();
function loadTs(relative) {
  const filename = path.isAbsolute(relative) ? relative : path.join(ROOT, relative);
  if (loaded.has(filename)) return loaded.get(filename).exports;
  const m = new Module(filename, module);
  m.filename = filename; m.paths = Module._nodeModulePaths(path.dirname(filename)); loaded.set(filename, m);
  m.require = (specifier) => {
    if (specifier.startsWith('@/')) return loadTs(specifier.slice(2) + '.ts');
    return rootRequire(specifier);
  };
  const source = pinnedRead(filename).toString('utf8');
  const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true }, fileName: filename });
  m._compile(output.outputText, filename);
  return m.exports;
}
const { makeStateBlockProjection } = loadTs('lib/block-map-projection.ts');
const { makeBoundsIndex, boundsIntersect } = loadTs('lib/michigan-map-interaction.ts');
const { validateCountyBlocks, validateMichiganSummary } = loadTs('lib/michigan-map-interaction.ts');
validateMichiganSummary(summary, plan);
validateCountyBlocks(kent, plan, '081', kentInfo.population, kentInfo.blockCount);

function countCoordinates(value) {
  if (!value) return 0;
  if (Array.isArray(value)) {
    if (typeof value[0] === 'number') return 1;
    return value.reduce((n, child) => n + countCoordinates(child), 0);
  }
  if (value.type === 'FeatureCollection') return value.features.reduce((n, feature) => n + countCoordinates(feature.geometry), 0);
  if (value.type === 'GeometryCollection') return value.geometries.reduce((n, geometry) => n + countCoordinates(geometry), 0);
  return countCoordinates(value.coordinates);
}
function statistics(values) {
  const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
  return { samples: values, median: sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2,
    minimum: sorted[0], maximum: sorted.at(-1), p95NearestRank: sorted[Math.ceil(sorted.length * 0.95) - 1] };
}
let sink = 0;
function timed(fn) { const start = performance.now(); const result = fn(); return { ms: performance.now() - start, result }; }
function consumeShapes(shapes) { for (const value of shapes) sink += value.d.length; }
const projection = makeStateBlockProjection(overview, '26');
const svgPath = geoPath(projection);
function prepareShapes(collection) {
  return collection.features.map((feature) => ({ feature, bounds: svgPath.bounds(feature), d: svgPath(feature) || '' }));
}
function prepareLines(collection, repeat = 1) {
  let count = 0;
  for (const feature of collection.features) for (let i = 0; i < repeat; i++) count += (svgPath(feature) || '').length;
  sink += count; return count;
}
function streamMask(collection) {
  const counts = { moveTo: 0, lineTo: 0, closePath: 0, arc: 0 };
  const context = { moveTo() { counts.moveTo++; }, lineTo() { counts.lineTo++; }, closePath() { counts.closePath++; }, arc() { counts.arc++; } };
  geoPath(projection, context)(collection);
  sink += counts.lineTo; return counts;
}
function workload(kind) {
  const data = kind === 'selected_county_zoomed_out_fine' ? fine : overview;
  const events = {};
  const start = performance.now();
  let part = timed(() => prepareShapes(data)); events.outlinePathsAndBoundsMs = part.ms; consumeShapes(part.result);
  const outlines = part.result;
  part = timed(() => prepareLines(kind === 'selected_county_zoomed_out_fine' ? fineDividers : overviewDividers)); events.dividerPathsOnceMs = part.ms;
  if (kind === 'selected_county_zoomed_out_fine') {
    part = timed(() => prepareShapes(kent)); events.blockPathsAndBoundsMs = part.ms; consumeShapes(part.result);
    const blocks = part.result;
    part = timed(() => makeBoundsIndex(blocks.map((shape) => shape.bounds))); events.blockPickingIndexMs = part.ms;
    sink += part.result([500, 310]).length;
    events.preparedBlockCount = blocks.length;
    events.visibleBlockCountAtStateScale = blocks.filter((block) => boundsIntersect(block.bounds, [[0, 0], [1000, 620]])).length;
  } else {
    part = timed(() => prepareLines(coast)); events.coastPathsOnceMs = part.ms;
    events.blockPathsAndBoundsMs = 0; events.blockPickingIndexMs = 0;
    events.preparedBlockCount = 0; events.visibleBlockCountAtStateScale = 0;
  }
  events.totalPreparationMs = performance.now() - start;
  events.outlinePathCharacters = outlines.reduce((total, shape) => total + shape.d.length, 0);
  return events;
}
const scenarios = ['selected_county_zoomed_out_fine', 'overview_with_block_detail_omitted'];
const measurements = Object.fromEntries(scenarios.map((name) => [name, []]));
const projectionSamples = [], fineMaskSamples = [], overviewMaskSamples = [], oldUncachedDividerSamples = [], decodeSamples = {};
for (const label of ['overview', 'fine', 'kent_blocks']) decodeSamples[label] = [];
const memoryBefore = process.memoryUsage();
const benchmarkStart = performance.now();
for (let round = -WARMUPS; round < SAMPLES; round++) {
  const order = Math.abs(round) % 2 ? [...scenarios].reverse() : scenarios;
  for (const scenario of order) {
    const value = workload(scenario);
    if (round >= 0) measurements[scenario].push(value);
  }
  const preparedProjection = timed(() => makeStateBlockProjection(overview, '26'));
  sink += preparedProjection.result.projectPoint([-85.7, 43])[0];
  const fineMask = timed(() => streamMask(fine));
  const overviewMask = timed(() => streamMask(overview));
  const oldUncachedDividers = timed(() => prepareLines(fineDividers, 2));
  if (round >= 0) {
    projectionSamples.push(preparedProjection.ms); fineMaskSamples.push(fineMask.ms); overviewMaskSamples.push(overviewMask.ms);
    oldUncachedDividerSamples.push(oldUncachedDividers.ms);
  }
  // Gzip inflate + JSON parse are separate from geometry preparation. Buffers
  // are already resident; these are not cold-disk or network measurements.
  for (const label of ['overview', 'fine', 'kent_blocks']) {
    const result = timed(() => JSON.parse(gunzipSync(compressed.get(label)).toString('utf8')));
    sink += result.result.features.length;
    if (round >= 0) decodeSamples[label].push(result.ms);
  }
}
const elapsedMs = performance.now() - benchmarkStart;
const memoryAfter = process.memoryUsage();
const summaries = {};
for (const name of scenarios) {
  const sample = measurements[name][0];
  summaries[name] = {};
  for (const key of Object.keys(sample)) summaries[name][key] = key.endsWith('Ms') ? statistics(measurements[name].map((row) => row[key])) : sample[key];
}
const firstMedian = summaries[scenarios[0]].totalPreparationMs.median;
const secondMedian = summaries[scenarios[1]].totalPreparationMs.median;
for (const [filename, expected] of pinnedInputs) assert.equal(sha(fs.readFileSync(filename)), expected, `Input changed during benchmark: ${filename}`);
const report = {
  schemaVersion: 1, status: 'complete', createdAtUtc: new Date().toISOString(),
  command: process.argv, planId: PLAN_ID, county: { fips: '081', name: 'Kent', population: kentInfo.population, blockCount: kentInfo.blockCount },
  methodology: {
    scope: 'Node CPU geometry preprocessing microbenchmark using actual app projection/path/picking helpers and pinned saved assets; not browser FPS.',
    scenarios: {
      selected_county_zoomed_out_fine: 'Counterfactual legacy workload: whole-state fine district coverage with Kent still selected, preparing all county block paths and picking index. This is initial/rebuild preparation, not a claim that those memoized paths regenerate each pan.',
      overview_with_block_detail_omitted: 'Clean overview coverage and divider/coast paths; no county block shape or picking-index preparation at overview scale.',
    },
    measuredRounds: SAMPLES, warmupRounds: WARMUPS, order: 'Alternate scenario order each round; no forced garbage collection.',
    linePaths: 'Each divider path generated once in main scenarios. Separate diagnostic measures the old JSX pattern of twice per divider each render.',
    projection: 'Same overview-derived state projection in both scenarios, matching the app. Projection setup measured separately.',
    maskDiagnostic: 'd3 projection and path streaming into a counting context; no Canvas raster calls or Path2D parsing. Overview block-detail omission avoids this block-canvas mask entirely; overview mask timing is included only as reference.',
    decode: 'Repeated gzip inflate and JSON parse from resident compressed buffers; filesystem load events are single observations, not cold-cache benchmarks.',
    limitations: ['No DOM, React render/commit, Canvas rasterization, Path2D parsing, GPU, input dispatch or network costs are measured.', 'No FPS, frame-time percentile, interaction-latency or browser-memory claim follows from these results.', 'Measured in one non-isolated desktop Node process; JIT, garbage collection, thermal state and concurrent work affect timings.'],
  },
  environment: { note: NOTE, node: process.version, v8: process.versions.v8, platform: process.platform, arch: process.arch,
    osRelease: os.release(), cpuModel: os.cpus()[0]?.model, logicalCpuCount: os.cpus().length, totalMemoryBytes: os.totalmem(),
    processMemoryBefore: memoryBefore, processMemoryAfter: memoryAfter, peakProcessRssKiB: process.resourceUsage().maxRSS },
  geometryWorkload: Object.fromEntries([...decoded].filter(([, data]) => data.type === 'FeatureCollection').map(([label, data]) => [label, { featureCount: data.features.length, coordinateCount: countCoordinates(data) }])),
  singleFileLoadObservations: loadEvents,
  decodeFromResidentGzipMs: Object.fromEntries(Object.entries(decodeSamples).map(([label, values]) => [label, statistics(values)])),
  sharedProjectionSetupMs: statistics(projectionSamples), scenarios: summaries,
  diagnostics: { fineLandMaskProjectionStreamMs: statistics(fineMaskSamples), fineLandMaskCommands: streamMask(fine),
    overviewLandMaskProjectionStreamMs: statistics(overviewMaskSamples), overviewLandMaskCommands: streamMask(overview),
    legacyUncachedFineDividerPathsTwicePerRenderMs: statistics(oldUncachedDividerSamples) },
  comparison: { initialGeometryPreparationMedianRatio: firstMedian / secondMedian,
    initialGeometryPreparationMedianReductionPercent: (1 - secondMedian / firstMedian) * 100,
    interpretation: 'Work avoided by returning to overview mode; not an end-to-end browser speedup.' },
  preservedInputs: [...pinnedInputs].map(([filename, sha256]) => ({ path: filename, sha256 })),
  inputFilesModified: 0, benchmarkElapsedMs: elapsedMs, checksum: sink,
};
fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
fs.writeFileSync(OUTPUT, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ output: OUTPUT, status: report.status, oldPreparationMedianMs: firstMedian,
  overviewPreparationMedianMs: secondMedian, ratio: firstMedian / secondMedian,
  fineMaskStreamMedianMs: statistics(fineMaskSamples).median, elapsedMs }, null, 2));
