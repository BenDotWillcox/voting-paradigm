import type { BlockMapCollection } from "@/lib/block-map-projection";
import type { BlockLandDisplay, BlockNationalLandAssets, BlockPlan, BlockPlanAnchor } from "@/types/block-districting";
import type { Geometry, Position } from "geojson";
import { validateDerivedConnections } from "@/lib/block-land-display";

function invalidLayers(): never {
  throw new Error("National land layers do not match the selected plan or contain invalid geometry.");
}

function checkedLine(value: unknown, closed: boolean): Position[] {
  if (!Array.isArray(value) || value.length < (closed ? 4 : 2)
    || value.some((point) => !Array.isArray(point) || point.length !== 2
      || point.some((coordinate) => typeof coordinate !== "number" || !Number.isFinite(coordinate)))) {
    return invalidLayers();
  }
  const line = value as Position[];
  if (!line.some((point) => point[0] !== line[0][0] || point[1] !== line[0][1])) return invalidLayers();
  if (closed) {
    if (line[0][0] !== line[line.length - 1][0] || line[0][1] !== line[line.length - 1][1]) return invalidLayers();
    // Translate before summing to avoid cancellation for tiny geographic rings.
    const [x, y] = line[0];
    const area = line.slice(1).reduce((sum, point, index) => sum
      + (line[index][0] - x) * (point[1] - y) - (point[0] - x) * (line[index][1] - y), 0);
    if (area === 0) return invalidLayers();
  }
  return line;
}

function checkedLines(geometry: Geometry, closed: boolean): Position[][] {
  if (geometry?.type === "LineString") return [checkedLine(geometry.coordinates, closed)];
  if (geometry?.type !== "MultiLineString" || !Array.isArray(geometry.coordinates)
    || !geometry.coordinates.length) return invalidLayers();
  return geometry.coordinates.map((line) => checkedLine(line, closed));
}

interface ShoreRing {
  points: Position[];
  bbox: [number, number, number, number];
}

function shoreRing(points: Position[]): ShoreRing {
  const bbox: ShoreRing["bbox"] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of points) {
    bbox[0] = Math.min(bbox[0], x); bbox[1] = Math.min(bbox[1], y);
    bbox[2] = Math.max(bbox[2], x); bbox[3] = Math.max(bbox[3], y);
  }
  return { points, bbox };
}

/** -1 is on the boundary; 0 is outside; 1 is inside. Independent of winding. */
function pointLocation([x, y]: Position, ring: Position[]): -1 | 0 | 1 {
  let inside = false;
  for (let i = 1; i < ring.length; i++) {
    const [ax, ay] = ring[i - 1], [bx, by] = ring[i];
    const cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax);
    if (cross === 0 && x >= Math.min(ax, bx) && x <= Math.max(ax, bx)
      && y >= Math.min(ay, by) && y <= Math.max(ay, by)) return -1;
    if ((ay > y) !== (by > y) && x < ax + (y - ay) * (bx - ax) / (by - ay)) inside = !inside;
  }
  return inside ? 1 : 0;
}

function containsRing(outer: ShoreRing, inner: ShoreRing): boolean {
  if (outer.bbox[0] > inner.bbox[0] || outer.bbox[1] > inner.bbox[1]
    || outer.bbox[2] < inner.bbox[2] || outer.bbox[3] < inner.bbox[3]) return false;
  // Dissolved coast rings are disjoint or nested. A boundary point, unlike a
  // centroid, cannot land inside a smaller child lake and invert containment.
  for (let i = 0; i < inner.points.length - 1; i++) {
    const location = pointLocation(inner.points[i], outer.points);
    if (location !== -1) return location === 1;
    // Point-touching components are valid: try an edge midpoint if necessary.
    const next = inner.points[i + 1];
    const midpoint = pointLocation([(inner.points[i][0] + next[0]) / 2,
      (inner.points[i][1] + next[1]) / 2], outer.points);
    if (midpoint !== -1) return midpoint === 1;
  }
  return invalidLayers(); // Duplicate/coincident rings cannot be classified safely.
}

/** Validate matched clean layers, then style coast rings without changing geometry. */
export function validateStateNationalLayers(
  outlines: BlockMapCollection,
  coast: BlockMapCollection,
  dividers: BlockMapCollection,
  plan: BlockPlan,
): { exteriorCoast: BlockMapCollection; interiorWater: BlockMapCollection } {
  if (!/^\d{2}$/.test(plan.stateFips) || !Number.isInteger(plan.districtCount) || plan.districtCount < 1
    || plan.id !== `${plan.stateFips}-${plan.districtCount}` || plan.districtPopulations.length !== plan.districtCount) return invalidLayers();
  for (const layer of [outlines, coast, dividers]) {
    const metadata = (layer as BlockMapCollection & { metadata?: { planId?: unknown; stateFips?: unknown; coordinateFrame?: unknown } }).metadata;
    if (layer?.type !== "FeatureCollection" || !Array.isArray(layer.features)
      || metadata?.planId !== plan.id
      || (metadata.stateFips !== undefined && metadata.stateFips !== plan.stateFips)
      || (metadata.coordinateFrame !== undefined && metadata.coordinateFrame !== plan.coordinateFrame)
      || (plan.stateFips === "02" && metadata.coordinateFrame !== "alaska-continuous")) return invalidLayers();
  }
  if (outlines.features.length !== plan.districtCount || !coast.features.length) return invalidLayers();
  const seenDistricts = new Set<number>();
  let population = 0;
  for (const feature of outlines.features) {
    const properties = feature.properties;
    const id = properties?.district_id;
    if (typeof id !== "number" || !Number.isInteger(id) || id < 0 || id >= plan.districtCount || seenDistricts.has(id)
      || (properties.state_fips !== undefined && properties.state_fips !== plan.stateFips)
      || (properties.plan_id !== undefined && properties.plan_id !== plan.id)
      || !Number.isSafeInteger(properties.population) || Number(properties.population) < 0
      || properties.population !== plan.districtPopulations[id]) return invalidLayers();
    seenDistricts.add(id);
    population += Number(properties.population);
    const geometry = feature.geometry;
    const polygons = geometry?.type === "Polygon" ? [geometry.coordinates]
      : geometry?.type === "MultiPolygon" ? geometry.coordinates : null;
    if (!polygons?.length) return invalidLayers();
    for (const polygon of polygons) {
      if (!Array.isArray(polygon) || !polygon.length) return invalidLayers();
      for (const ring of polygon) checkedLine(ring, true);
    }
  }
  if (population !== plan.residentPopulation) return invalidLayers();
  const pairs = new Set<string>();
  for (const feature of dividers.features) {
    const properties = feature.properties, ids = properties?.district_ids;
    if (properties?.plan_id !== plan.id || properties.kind !== "shared-district-divider"
      || (properties.state_fips !== undefined && properties.state_fips !== plan.stateFips)
      || !Array.isArray(ids) || ids.length !== 2 || ids[0] === ids[1]
      || ids.some((id) => typeof id !== "number" || !Number.isInteger(id) || id < 0 || id >= plan.districtCount)) return invalidLayers();
    const key = [...ids].sort((a, b) => a - b).join("-");
    if (pairs.has(key)) return invalidLayers();
    pairs.add(key);
    checkedLines(feature.geometry, false);
  }
  const coastLines = coast.features.map((feature) => {
    if (feature.properties?.state_fips !== plan.stateFips || feature.properties.plan_id !== plan.id
      || feature.properties.kind !== "state-and-water-shoreline") return invalidLayers();
    return checkedLines(feature.geometry, true);
  });
  const classification = (coast as BlockMapCollection & { metadata?: { shorelineClassification?: unknown } }).metadata?.shorelineClassification;
  if (classification !== undefined) {
    if (classification !== "top-level-containment-v1"
      || coast.features.some((feature) => !["outer", "inland"].includes(String(feature.properties.shoreline_scope)))
      || !coast.features.some((feature) => feature.properties.shoreline_scope === "outer")) return invalidLayers();
    // New all-state exports classify rings once with a spatial index during
    // publication. Rechecking every pair in Alaska would block the browser.
    const selectScope = (scope: string): BlockMapCollection => ({ ...coast,
      features: coast.features.filter((feature) => feature.properties.shoreline_scope === scope) });
    return { exteriorCoast: selectScope("outer"), interiorWater: selectScope("inland") };
  }
  const featureRings = coastLines.map((lines) => lines.map(shoreRing));
  const allRings = featureRings.flat();
  // The prominent border denotes only the outer state silhouette. An island inside an inland
  // lake is land (even nesting depth), but its shore is still inland: styling
  // it as an exterior turns tiny islands into prominent dots nationally.
  // Keep every contained shoreline subdued, including islands within lakes.
  const interior = new Set(allRings.filter((ring) => allRings.reduce((depth, other) =>
    depth + (other !== ring && containsRing(other, ring) ? 1 : 0), 0) > 0));
  const select = (water: boolean): BlockMapCollection => ({ ...coast, features: coast.features.flatMap((feature, index) => {
    const coordinates = featureRings[index].filter((ring) => interior.has(ring) === water).map((ring) => ring.points);
    return coordinates.length ? [{ ...feature, geometry: { type: "MultiLineString" as const, coordinates } }] : [];
  }) });
  return { exteriorCoast: select(false), interiorWater: select(true) };
}

/** Compatibility validation for the preserved Michigan-only display bundle. */
export function validateMichiganNationalLayers(
  outlines: BlockMapCollection, coast: BlockMapCollection, dividers: BlockMapCollection, plan: BlockPlan,
) {
  if (plan.stateFips !== "26") return invalidLayers();
  return validateStateNationalLayers(outlines, coast, dividers, plan);
}

export interface NationalLandState {
  plan: BlockPlan;
  outlines: BlockMapCollection;
  exteriorCoast: BlockMapCollection;
  interiorWater: BlockMapCollection;
  dividers: BlockMapCollection;
  connections: BlockMapCollection;
  recordedConnections: BlockMapCollection;
}

export interface NationalLandCollections {
  outlines: BlockMapCollection;
  coast: BlockMapCollection;
  dividers: BlockMapCollection;
  connections: BlockMapCollection;
  recordedConnections?: BlockMapCollection;
}

/** Check the compact all-state aggregate against the unchanged accepted anchor. */
export function validateNationalLandLayers(
  layers: NationalLandCollections,
  descriptor: BlockNationalLandAssets,
  anchor: BlockPlanAnchor,
  plans: Record<string, BlockPlan>,
  displays: Record<string, BlockLandDisplay>,
): Map<string, NationalLandState> {
  const planIds = [...anchor.planIds].sort();
  const sameIds = (value: unknown) => Array.isArray(value) && value.length === planIds.length
    && [...value].sort().every((id, i) => id === planIds[i]);
  if (descriptor.houseSize !== anchor.houseSize || !sameIds(descriptor.planIds)
    || new Set(planIds).size !== planIds.length) return invalidLayers();
  const byState = new Map<string, BlockPlan>();
  for (const id of planIds) {
    const plan = plans[id];
    if (!plan || plan.id !== id || byState.has(plan.stateFips) || !displays[id] || displays[id].planId !== id) return invalidLayers();
    byState.set(plan.stateFips, plan);
  }
  const partition = (data: BlockMapCollection) => {
    const meta = (data as BlockMapCollection & { metadata?: Record<string, unknown> }).metadata;
    const frames = meta?.coordinateFrames as Record<string, unknown> | undefined;
    if (data.type !== "FeatureCollection" || !Array.isArray(data.features) || meta?.houseSize !== anchor.houseSize
      || !sameIds(meta.planIds) || !frames || Object.keys(frames).length !== byState.size
      || [...byState].some(([state, plan]) => frames[state] !== plan.coordinateFrame)) return invalidLayers();
    const result = new Map([...byState].map(([state, plan]) => [state, { type: "FeatureCollection" as const,
      metadata: { planId: plan.id, stateFips: state, coordinateFrame: plan.coordinateFrame,
        ...(meta.shorelineClassification !== undefined ? { shorelineClassification: meta.shorelineClassification } : {}) },
      features: [] as BlockMapCollection["features"] }]));
    for (const feature of data.features) {
      const state = String(feature.properties?.state_fips), plan = byState.get(state);
      if (!plan || feature.properties.plan_id !== plan.id || feature.properties.coordinate_frame !== plan.coordinateFrame) return invalidLayers();
      result.get(state)!.features.push(feature);
    }
    return result;
  };
  const outlines = partition(layers.outlines), coasts = partition(layers.coast), dividers = partition(layers.dividers);
  const connections = partition(layers.connections), recorded = layers.recordedConnections ? partition(layers.recordedConnections) : undefined;
  if ((layers.coast as BlockMapCollection & { metadata?: Record<string, unknown> }).metadata?.shorelineClassification !== "top-level-containment-v1") return invalidLayers();
  const result = new Map<string, NationalLandState>();
  for (const [state, plan] of byState) {
    const stateOutlines = outlines.get(state)!, stateCoast = coasts.get(state)!, stateDividers = dividers.get(state)!;
    const stateConnections = connections.get(state)!;
    const shoreline = validateStateNationalLayers(stateOutlines, stateCoast, stateDividers, plan);
    validateDerivedConnections(stateConnections, plan, displays[plan.id].summary.derivedConnectionCount);
    const stateRecorded = recorded?.get(state) ?? { type: "FeatureCollection" as const, features: [] };
    if (stateRecorded.features.length !== plan.recordedLinkCount) return invalidLayers();
    const ids = new Set<string>();
    for (const feature of stateRecorded.features) {
      const id = String(feature.properties.id ?? feature.id ?? "");
      if (!id || ids.has(id)) return invalidLayers();
      ids.add(id);
      checkedLines(feature.geometry, false);
    }
    result.set(state, { plan, outlines: stateOutlines, ...shoreline, dividers: stateDividers,
      connections: stateConnections, recordedConnections: stateRecorded });
  }
  return result;
}

/** All replacements retain the census feature's authoritative identity and metrics. */
export function nationalLandView(census: BlockMapCollection, states: ReadonlyMap<string, NationalLandState>): BlockMapCollection {
  const replacements = new Map<string, BlockMapCollection["features"][number]>();
  for (const [state, value] of states) for (const feature of value.outlines.features) {
    const key = `${state}:${feature.properties.district_id}`;
    if (replacements.has(key)) return invalidLayers();
    replacements.set(key, feature);
  }
  const seen = new Set<string>();
  const features = census.features.map((original) => {
    const state = String(original.properties.state_fips);
    if (!states.has(state)) return original;
    const key = `${state}:${original.properties.district_id}`, replacement = replacements.get(key);
    if (!replacement || seen.has(key) || replacement.properties.population !== original.properties.population
      || (original.properties.plan_id !== undefined && original.properties.plan_id !== states.get(state)!.plan.id)) return invalidLayers();
    seen.add(key);
    return { ...original, geometry: replacement.geometry };
  });
  if (seen.size !== replacements.size) return invalidLayers();
  return { ...census, features };
}

/** Replace only Michigan's display geometry, preserving district identity and totals. */
export function michiganNationalLandView(
  census: BlockMapCollection,
  land: BlockMapCollection,
): BlockMapCollection {
  const originals = census.features.filter((feature) => feature.properties.state_fips === "26");
  if (!originals.length || land.features.length !== originals.length) {
    throw new Error("Michigan land view does not match this House anchor.");
  }
  const byId = new Map(originals.map((feature) => [Number(feature.properties.district_id), feature]));
  const seen = new Set<number>();
  const replacements = land.features.map((feature) => {
    const id = Number(feature.properties.district_id);
    const original = byId.get(id);
    if (!original || seen.has(id) || !feature.geometry
      || !["Polygon", "MultiPolygon"].includes(feature.geometry.type)
      || (feature.properties.state_fips !== undefined && feature.properties.state_fips !== "26")
      || feature.properties.population !== original.properties.population) {
      throw new Error("Michigan land view changed a district identity or population.");
    }
    seen.add(id);
    // Original identity, population and plan metadata remain authoritative.
    return { ...original, geometry: feature.geometry };
  });
  return { ...census, features: [
    ...census.features.filter((feature) => feature.properties.state_fips !== "26"),
    ...replacements,
  ] };
}

export function michiganLandStateBorder(
  census: BlockMapCollection,
  land: BlockMapCollection,
): BlockMapCollection {
  if (land.features.length !== 1 || land.features[0].properties.state_fips !== "26"
    || !["Polygon", "MultiPolygon"].includes(land.features[0].geometry?.type)) {
    throw new Error("Michigan land border is invalid.");
  }
  return { ...census, features: census.features.map((feature) =>
    feature.properties.state_fips === "26" ? { ...feature, geometry: land.features[0].geometry } : feature) };
}
