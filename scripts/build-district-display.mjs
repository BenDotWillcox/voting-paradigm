#!/usr/bin/env node
/**
 * Build browser display artifacts for cached district plans.
 *
 * Source: full-resolution tract topology per plan, written by
 * `scripts/build_district_topojson.py` to `data/districting/tract-topo/`.
 * That source is one arc per ring (no shared boundaries) and is far too
 * large to ship — California alone is ~23 MB.
 *
 * Output, per plan, under `public/data/district-plans/{fips}/{plan}/`:
 *
 * - `plan.json`           metrics, centers, and provenance; no geometry.
 *                         Small enough for the server to embed in a page.
 * - `districts.topo.json` tracts dissolved into one outline per district.
 * - `tracts.topo.json`    tract polygons, fetched lazily for hover detail.
 *
 * Both geometry layers are built from ONE shared-arc topology that is
 * simplified once (Visvalingam, weighted, keep-shapes) to a display
 * resolution, then dissolved. District edges therefore coincide exactly
 * with tract edges, and neighboring polygons never open gaps.
 *
 * The build is deterministic: same source bytes + same parameters produce
 * the same outputs. `plan.json` records the source hash and parameters.
 *
 * Usage:
 *   node scripts/build-district-display.mjs            # every plan
 *   node scripts/build-district-display.mjs --state 26 # one state
 */

import { createHash } from "node:crypto";
import { mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

import { geoArea } from "d3-geo";
import mapshaper from "mapshaper";
import { feature } from "topojson-client";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE_ROOT = join(ROOT, "data", "districting", "tract-topo");
const OUTPUT_ROOT = join(ROOT, "public", "data", "district-plans");
const STATES_SOURCE = join(ROOT, "public", "data", "us-states.json");
const STATES_OUTPUT = join(ROOT, "public", "data", "us-states.display.json");

/** Display parameters. Maps render into an 800x600 viewBox (2x for HiDPI). */
const PARAMS = {
  simplify: "resolution=1600x1200 weighted keep-shapes",
  quantization: 20_000,
};
/** National map renders at 975x610; state outlines also frame state maps. */
const STATE_PARAMS = {
  simplify: "resolution=2400x1500 weighted keep-shapes",
  precision: 0.001,
};
const ARTIFACT_VERSION = 1;

async function main() {
  const stateFilter = parseStateArg(process.argv.slice(2));
  const sources = await findSources(stateFilter);
  if (sources.length === 0) {
    throw new Error(`No source plans found under ${relative(ROOT, SOURCE_ROOT)}`);
  }

  for (const source of sources) {
    await buildPlan(source);
  }
  if (!stateFilter) {
    await buildStates();
  }
}

function parseStateArg(args) {
  const index = args.indexOf("--state");
  if (index === -1) return null;
  const value = args[index + 1];
  if (!value || !/^\d{1,2}$/.test(value)) {
    throw new Error("--state expects a state FIPS code, e.g. --state 26");
  }
  return value.padStart(2, "0");
}

async function findSources(stateFilter) {
  const states = stateFilter ? [stateFilter] : (await readdir(SOURCE_ROOT)).sort();
  const sources = [];
  for (const fips of states) {
    const dir = join(SOURCE_ROOT, fips);
    const files = (await readdir(dir)).filter((name) => name.endsWith(".topo.json")).sort();
    for (const name of files) {
      sources.push({ fips, path: join(dir, name), planId: name.replace(/\.topo\.json$/, "") });
    }
  }
  return sources;
}

async function buildPlan({ fips, path, planId }) {
  const started = Date.now();
  const bytes = await readFile(path);
  const plan = JSON.parse(bytes.toString("utf8"));
  const topology = plan.display_topology;
  const tracts = feature(topology, topology.objects.districts);

  const outputs = await mapshaper.applyCommands(
    [
      "-i tracts.json name=tracts",
      "-filter-fields geoid,district_id,population",
      `-simplify ${PARAMS.simplify}`,
      "-dissolve district_id sum-fields=population + name=districts",
      `-o target=tracts tracts.topo.json format=topojson quantization=${PARAMS.quantization}`,
      `-o target=districts districts.topo.json format=topojson quantization=${PARAMS.quantization}`,
    ].join(" "),
    { "tracts.json": tracts }
  );

  const tractsTopo = JSON.parse(text(outputs["tracts.topo.json"]));
  const districtsTopo = JSON.parse(text(outputs["districts.topo.json"]));
  assertCount("tracts", tractsTopo.objects.tracts, tracts.features.length);
  assertCount("districts", districtsTopo.objects.districts, plan.seats);
  assertWinding("tracts", feature(tractsTopo, tractsTopo.objects.tracts).features);
  assertWinding("districts", feature(districtsTopo, districtsTopo.objects.districts).features);

  const { display_topology: _geometry, display_unit: _unit, notes, ...metadata } = plan;
  const planJson = {
    ...metadata,
    notes: (notes ?? []).filter((note) => !note.startsWith("Display geometry")),
    display: {
      artifact_version: ARTIFACT_VERSION,
      source_sha256: createHash("sha256").update(bytes).digest("hex"),
      simplify: PARAMS.simplify,
      quantization: PARAMS.quantization,
      tract_count: tracts.features.length,
      district_count: plan.seats,
    },
  };

  const outDir = join(OUTPUT_ROOT, fips, planId);
  await rm(outDir, { recursive: true, force: true });
  await mkdir(outDir, { recursive: true });
  const files = {
    "plan.json": JSON.stringify(planJson),
    "districts.topo.json": JSON.stringify(districtsTopo),
    "tracts.topo.json": JSON.stringify(tractsTopo),
  };
  for (const [name, body] of Object.entries(files)) {
    await writeFile(join(outDir, name), body);
  }

  console.log(
    `${fips}/${planId}: ${kb(bytes.length)} source -> ` +
      Object.entries(files)
        .map(([name, body]) => `${name} ${kb(body.length)} (${kb(gzipSync(body).length)} gz)`)
        .join(", ") +
      ` [${Date.now() - started} ms]`
  );
}

async function buildStates() {
  const source = JSON.parse(await readFile(STATES_SOURCE, "utf8"));
  const outputs = await mapshaper.applyCommands(
    [
      "-i states.json",
      `-simplify ${STATE_PARAMS.simplify}`,
      `-o states.out.json format=geojson id-field=id precision=${STATE_PARAMS.precision}`,
    ].join(" "),
    { "states.json": source }
  );
  const simplified = JSON.parse(text(outputs["states.out.json"]));
  if (simplified.features.length !== source.features.length) {
    throw new Error("State simplification dropped features");
  }
  // mapshaper writes RFC 7946 (counter-clockwise) GeoJSON; d3-geo reads a
  // CCW exterior as "the globe minus the state". Restore d3's convention.
  for (const state of simplified.features) rewindForD3(state.geometry);
  assertWinding("states", simplified.features);
  const body = JSON.stringify(simplified);
  await writeFile(STATES_OUTPUT, body);
  console.log(`us-states.display.json: ${kb(body.length)} (${kb(gzipSync(body).length)} gz)`);
}

function assertCount(label, object, expected) {
  const actual = object.geometries.filter((geometry) => geometry.type).length;
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected} geometries, got ${actual}`);
  }
}

/**
 * d3-geo treats rings spherically: a feature with a reversed exterior ring
 * covers the rest of the globe, which silently breaks projection fitting.
 */
function assertWinding(label, features) {
  const inverted = features.filter((f) => f.geometry && geoArea(f) > 2 * Math.PI);
  if (inverted.length > 0) {
    throw new Error(`${label}: ${inverted.length} feature(s) have inverted ring winding`);
  }
}

/** Exterior rings clockwise, holes counter-clockwise (planar lon/lat). */
function rewindForD3(geometry) {
  const polygons =
    geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  for (const polygon of polygons) {
    polygon.forEach((ring, index) => {
      const clockwise = signedArea(ring) < 0;
      if ((index === 0) !== clockwise) ring.reverse();
    });
  }
}

function signedArea(ring) {
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    sum += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  }
  return sum / 2;
}

function text(output) {
  return typeof output === "string" ? output : Buffer.from(output).toString("utf8");
}

function kb(n) {
  return `${(n / 1024).toFixed(0)} KB`;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
