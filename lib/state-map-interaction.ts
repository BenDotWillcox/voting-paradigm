import { geoTransform } from "d3-geo";
import type { GeoPath, GeoPermissibleObjects } from "d3-geo";
import type { Feature, Geometry, Position } from "geojson";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { BlockMapProperties } from "@/lib/block-map-projection";
import type { BlockPlan, StateExplorerSummary, StateSpatialBlockChunk, StateSpatialBlockIndex } from "@/types/block-districting";

export interface MapViewport { x: number; y: number; k: number }
export type MapBounds = [[number, number], [number, number]];
export const INITIAL_VIEW: MapViewport = { x: 0, y: 0, k: 1 };
export const MAX_MAP_ZOOM = 256;
export interface MapZoomLimits { min: number; max: number }
export type StateInspectionTarget = "districts" | "counties" | "blocks";

/** Blocks keep their detail floor independently of the current selection. */
export function stateBlockDetailReady(inspection: StateInspectionTarget, zoom: number) {
  return inspection === "blocks" && Number.isFinite(zoom) && zoom >= 6;
}

export function viewportBounds(view: MapViewport): MapBounds {
  return [[-view.x / view.k, -view.y / view.k], [(1000 - view.x) / view.k, (620 - view.y) / view.k]];
}

export interface StateCanvasFrame { view: MapViewport; appearanceKey: string; width: number; height: number }

/** Reuse only the old raster's geographic footprint, including while loading.
 * The transformed canvas rectangle clips that footprint; newly exposed map
 * area remains transparent. Always transform from the published camera, never
 * from a previous CSS transform, so rapid pans cannot accumulate drift. */
export function retainedStateFrameTransform(previous: StateCanvasFrame | null, current: StateCanvasFrame & { complete: boolean }) {
  if (!previous || previous.appearanceKey !== current.appearanceKey || previous.width !== current.width || previous.height !== current.height) return null;
  const oldBox = viewportBounds(previous.view), nextBox = viewportBounds(current.view);
  if (nextBox[0][0] >= oldBox[1][0] || nextBox[1][0] <= oldBox[0][0] || nextBox[0][1] >= oldBox[1][1] || nextBox[1][1] <= oldBox[0][1]) return null;
  const scale = current.view.k / previous.view.k;
  return { scale, x: (current.view.x - previous.view.x * scale) * current.width / 1000,
    y: (current.view.y - previous.view.y * scale) * current.height / 620 };
}

/** Source extents include water, unlike the display-only county outlines. */
export function projectedStateCountyBounds(box: readonly number[], projection: BlockMapProjection): MapBounds {
  const [west, south, east, north] = box;
  const points: [number, number][] = [];
  // Densify curved conic-projection edges and conservatively pad the result.
  // Alaska's continuous projection is linear, including longitudes below -180.
  for (let i = 0; i <= 32; i++) {
    const t = i / 32;
    points.push(projection.projectPoint([west + (east - west) * t, south]), projection.projectPoint([west + (east - west) * t, north]),
      projection.projectPoint([west, south + (north - south) * t]), projection.projectPoint([east, south + (north - south) * t]));
  }
  return [[Math.min(...points.map((p) => p[0])) - 0.5, Math.min(...points.map((p) => p[1])) - 0.5],
    [Math.max(...points.map((p) => p[0])) + 0.5, Math.max(...points.map((p) => p[1])) + 0.5]];
}

export function visibleStateCountyFips(counties: readonly { fips: string; bounds: MapBounds }[], view: MapViewport): string[] {
  const box = viewportBounds(view);
  return counties.filter((county) => boundsIntersect(county.bounds, box)).map((county) => county.fips).sort();
}

export function visibleStateSpatialChunks(chunks: readonly { chunkId: string; bounds: MapBounds }[], view: MapViewport): string[] {
  const box = viewportBounds(view);
  return chunks.filter((chunk) => boundsIntersect(chunk.bounds, box)).map((chunk) => chunk.chunkId).sort();
}

// Raw JSON is a conservative request-cost signal, not a browser heap limit.
// Whole chunks remain intact, and every chunk intersecting the chosen view is
// included. Dense views change the camera rather than omit blocks/counties.
export const STATE_BLOCK_MAX_RAW_BYTES = 32 * 1024 * 1024;
export const STATE_BLOCK_MAX_VISIBLE_BLOCKS = 20_000;
export interface StateBlockBudgetChunk { chunkId: string; bounds: MapBounds; rawBytes: number; blockCount: number }
export interface StateBlockBudgetResult { view: MapViewport; chunkIds: string[]; rawBytes: number; blockCount: number; adjusted: boolean; blocked: boolean }

export function fitStateBlockBudget(view: MapViewport, chunks: readonly StateBlockBudgetChunk[], anchor: readonly number[] = [500, 310]): StateBlockBudgetResult {
  const valid = [view.x, view.y, view.k, ...anchor].every(Number.isFinite) && view.k > 0 && view.k <= MAX_MAP_ZOOM
    && anchor.length === 2 && anchor[0] >= 0 && anchor[0] <= 1000 && anchor[1] >= 0 && anchor[1] <= 620
    && chunks.every((chunk) => Number.isSafeInteger(chunk.rawBytes) && chunk.rawBytes > 0 && Number.isSafeInteger(chunk.blockCount) && chunk.blockCount > 0
      && Array.isArray(chunk.bounds) && chunk.bounds.length === 2 && chunk.bounds.every((point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite))
      && chunk.bounds[0][0] <= chunk.bounds[1][0] && chunk.bounds[0][1] <= chunk.bounds[1][1]);
  if (!valid) return { view, chunkIds: [], rawBytes: 0, blockCount: 0, adjusted: false, blocked: true };
  const measure = (candidate: MapViewport) => {
    const box = viewportBounds(candidate), chunkIds: string[] = [];
    let rawBytes = 0, blockCount = 0;
    for (const chunk of chunks) if (boundsIntersect(chunk.bounds, box)) {
      chunkIds.push(chunk.chunkId); rawBytes += chunk.rawBytes; blockCount += chunk.blockCount;
    }
    return { view: candidate, chunkIds: chunkIds.sort(), rawBytes, blockCount };
  };
  const affordable = (value: ReturnType<typeof measure>) => value.rawBytes <= STATE_BLOCK_MAX_RAW_BYTES && value.blockCount <= STATE_BLOCK_MAX_VISIBLE_BLOCKS;
  const initial = measure(view);
  if (affordable(initial)) return { ...initial, adjusted: false, blocked: false };
  let low = view.k, high = view.k, accepted = initial;
  // Nested viewports around one on-screen anchor make cost non-increasing.
  // At most eight doubling steps from the Blocks floor (6x) to the 256x cap.
  for (let step = 0; step < 16 && high < MAX_MAP_ZOOM; step++) {
    high = Math.min(MAX_MAP_ZOOM, high * 2);
    accepted = measure(zoomAt(view, high / view.k, anchor));
    if (affordable(accepted)) break;
    low = high;
  }
  // One indivisible/coast-spanning block can exceed the budget at every zoom.
  // Keep the requested camera and explicitly withhold detail in that case.
  if (!affordable(accepted)) return { ...initial, adjusted: false, blocked: true };
  for (let step = 0; step < 12; step++) {
    const middle = (low + high) / 2, candidate = measure(zoomAt(view, middle / view.k, anchor));
    if (affordable(candidate)) { high = middle; accepted = candidate; } else low = middle;
  }
  return { ...accepted, adjusted: true, blocked: false };
}

export interface StatePreparedBlockShape { feature: Feature<Geometry, BlockMapProperties>; bounds: MapBounds; readonly d: string }
export interface StatePreparedCounty {
  collection: BlockMapCollection;
  shapes: StatePreparedBlockShape[];
  hitCandidates: (point: readonly number[]) => number[];
}

function prepareStateBlock(feature: Feature<Geometry, BlockMapProperties>, path: GeoPath<unknown, GeoPermissibleObjects>): StatePreparedBlockShape {
  let d: string | undefined;
  return { feature, bounds: path.bounds(feature) as MapBounds, get d() { return d ??= path(feature) ?? ""; } };
}

/** Bounds/picking are prepared once per loaded county; paths only when drawn. */
export function prepareStateCounty(collection: BlockMapCollection, path: GeoPath<unknown, GeoPermissibleObjects>): StatePreparedCounty {
  const shapes = collection.features.map((feature) => prepareStateBlock(feature, path));
  return { collection, shapes, hitCandidates: makeBoundsIndex(shapes.map((shape) => shape.bounds)) };
}

/** Keep large viewport loads interruptible while building identical geometry. */
export async function prepareStateCountyAsync(collection: BlockMapCollection, path: GeoPath<unknown, GeoPermissibleObjects>, signal: AbortSignal): Promise<StatePreparedCounty> {
  const shapes: StatePreparedBlockShape[] = [], index = createBoundsIndex();
  for (let offset = 0; offset < collection.features.length; offset += 512) {
    if (signal.aborted) throw new DOMException("County preparation was canceled.", "AbortError");
    const end = Math.min(offset + 512, collection.features.length);
    for (let i = offset; i < end; i++) {
      const shape = prepareStateBlock(collection.features[i], path);
      shapes.push(shape); index.add(shape.bounds, i);
    }
    if (end < collection.features.length) await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  if (signal.aborted) throw new DOMException("County preparation was canceled.", "AbortError");
  return { collection, shapes, hitCandidates: index.query };
}

export function stateZoomLimits(inspection: StateInspectionTarget): MapZoomLimits {
  return { min: inspection === "blocks" ? 6 : 1, max: MAX_MAP_ZOOM };
}

/** Enforces inspection zoom limits without moving the point beneath the anchor. */
export function constrainViewport(view: MapViewport, limits: MapZoomLimits, anchor: readonly number[] = [500, 310]): MapViewport {
  const k = Math.max(limits.min, Math.min(limits.max, view.k));
  if (k === view.k) return view;
  const ratio = k / view.k;
  return { k, x: anchor[0] - (anchor[0] - view.x) * ratio, y: anchor[1] - (anchor[1] - view.y) * ratio };
}

export function zoomAt(view: MapViewport, factor: number, point: readonly number[], limits: MapZoomLimits = { min: 1, max: MAX_MAP_ZOOM }): MapViewport {
  if (!Number.isFinite(factor) || factor <= 0) return view;
  const k = Math.max(limits.min, Math.min(limits.max, view.k * factor));
  const ratio = k / view.k;
  return { k, x: point[0] - (point[0] - view.x) * ratio, y: point[1] - (point[1] - view.y) * ratio };
}

export function fitMapBounds(bounds: MapBounds, width = 1000, height = 620, padding = 52): MapViewport {
  const [[x0, y0], [x1, y1]] = bounds;
  if (![x0, y0, x1, y1].every(Number.isFinite) || x1 < x0 || y1 < y0) return { ...INITIAL_VIEW };
  const k = Math.max(1, Math.min(MAX_MAP_ZOOM, (width - 2 * padding) / Math.max(x1 - x0, 1), (height - 2 * padding) / Math.max(y1 - y0, 1)));
  return { k, x: width / 2 - k * (x0 + x1) / 2, y: height / 2 - k * (y0 + y1) / 2 };
}

/** A deep fit of a scattered island group should not crop around open ocean.
 * This changes only the camera; all parts and whole-county statistics remain. */
export function fitStateInspectionFeature(feature: Feature<Geometry, BlockMapProperties>, path: GeoPath<unknown, GeoPermissibleObjects>, minZoom = 1): MapViewport {
  const whole = fitMapBounds(path.bounds(feature) as MapBounds);
  if (whole.k >= minZoom || feature.geometry.type !== "MultiPolygon" || feature.geometry.coordinates.length < 2) return whole;
  let largest: Feature<Geometry, BlockMapProperties> | null = null, largestArea = -1;
  for (const coordinates of feature.geometry.coordinates) {
    const part: Feature<Geometry, BlockMapProperties> = { type: "Feature", properties: feature.properties, geometry: { type: "Polygon", coordinates } };
    const area = path.area(part);
    if (Number.isFinite(area) && area > largestArea) { largest = part; largestArea = area; }
  }
  return largest ? fitMapBounds(path.bounds(largest) as MapBounds) : whole;
}

/** Converts responsive SVG coordinates into the shared, unzoomed map plane. */
export function mapPoint(client: readonly number[], rect: { left: number; top: number; width: number; height: number }, view: MapViewport): [number, number] {
  return [(1000 * (client[0] - rect.left) / rect.width - view.x) / view.k,
    (620 * (client[1] - rect.top) / rect.height - view.y) / view.k];
}

export function transformedProjection(base: BlockMapProjection, view: MapViewport): BlockMapProjection {
  const projectPoint = (p: readonly number[]): [number, number] => {
    const point = base.projectPoint(p);
    return [point[0] * view.k + view.x, point[1] * view.k + view.y];
  };
  const transform = geoTransform({ point(x, y) { const p = projectPoint([x, y]); this.stream.point(p[0], p[1]); } });
  return { stream: transform.stream.bind(transform), projectPoint };
}

export function boundsIntersect(a: MapBounds, b: MapBounds) {
  return a[0][0] <= b[1][0] && a[1][0] >= b[0][0] && a[0][1] <= b[1][1] && a[1][1] >= b[0][1];
}

function inRing(ring: Position[], point: readonly number[], project: (p: readonly number[]) => [number, number]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = project(ring[i]), b = project(ring[j]);
    const cross = (point[0] - a[0]) * (b[1] - a[1]) - (point[1] - a[1]) * (b[0] - a[0]);
    if (Math.abs(cross) < 1e-9 && point[0] >= Math.min(a[0], b[0]) && point[0] <= Math.max(a[0], b[0]) && point[1] >= Math.min(a[1], b[1]) && point[1] <= Math.max(a[1], b[1])) return true;
    if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}

/** Planar picking respects holes and multipart islands; no spherical winding assumptions. */
export function pointInProjectedGeometry(geometry: Geometry | null, point: readonly number[], project: (p: readonly number[]) => [number, number]): boolean {
  const polygons = geometry?.type === "Polygon" ? [geometry.coordinates] : geometry?.type === "MultiPolygon" ? geometry.coordinates : [];
  return polygons.some((rings) => rings.length > 0 && inRing(rings[0], point, project) && !rings.slice(1).some((ring) => inRing(ring, point, project)));
}

function createBoundsIndex(size = 8) {
  const bounds: MapBounds[] = [];
  const cells = new Map<string, number[]>(), overflow: number[] = [];
  const add = (box: MapBounds, index: number) => {
    bounds[index] = box;
    if (!box.flat().every(Number.isFinite)) return;
    const x0 = Math.floor(box[0][0] / size), x1 = Math.floor(box[1][0] / size), y0 = Math.floor(box[0][1] / size), y1 = Math.floor(box[1][1] / size);
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > 2048) { overflow.push(index); return; }
    for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
      const key = `${x}:${y}`, row = cells.get(key) ?? []; row.push(index); cells.set(key, row);
    }
  };
  const query = (point: readonly number[]) => [...(cells.get(`${Math.floor(point[0] / size)}:${Math.floor(point[1] / size)}`) ?? []), ...overflow]
    .filter((i) => point[0] >= bounds[i][0][0] && point[0] <= bounds[i][1][0] && point[1] >= bounds[i][0][1] && point[1] <= bounds[i][1][1]);
  return { add, query };
}

/** Small fixed grid narrows block picking; exceptionally large water blocks use overflow. */
export function makeBoundsIndex(bounds: MapBounds[], size = 8) {
  const index = createBoundsIndex(size);
  bounds.forEach((box, i) => index.add(box, i));
  return index.query;
}

export function validateStateSummary(value: StateExplorerSummary, plan: BlockPlan) {
  if (value.planId !== plan.id || value.stateFips !== plan.stateFips || (value.coordinateFrame !== undefined && value.coordinateFrame !== plan.coordinateFrame) || value.residentPopulation !== plan.residentPopulation || value.blockCount !== plan.blockCount || !Array.isArray(value.counties) || !Array.isArray(value.districts)) throw new Error("State detail summary does not match the saved plan.");
  const countyIds = new Set<string>();
  let people = 0, blocks = 0;
  const populations = Array<number>(plan.districtCount).fill(0), counts = Array<number>(plan.districtCount).fill(0);
  for (const county of value.counties) {
    if (!/^\d{3}$/.test(county.fips) || countyIds.has(county.fips) || !county.name || !Number.isSafeInteger(county.population) || county.population < 0 || !Number.isSafeInteger(county.blockCount) || county.blockCount < 1 || !Array.isArray(county.districtShares)
      || !Array.isArray(county.bbox) || county.bbox.length !== 4 || !county.bbox.every(Number.isFinite) || county.bbox[0] > county.bbox[2] || county.bbox[1] > county.bbox[3]) throw new Error("Invalid county detail summary.");
    countyIds.add(county.fips);
    const ids = new Set<number>(); let p = 0, b = 0;
    for (const share of county.districtShares) {
      if (!Number.isInteger(share.districtId) || share.districtId < 0 || share.districtId >= plan.districtCount || ids.has(share.districtId) || !Number.isSafeInteger(share.population) || share.population < 0 || !Number.isSafeInteger(share.blockCount) || share.blockCount < 1 || !Number.isFinite(share.percent) || Math.abs(share.percent - (county.population ? share.population / county.population * 100 : 0)) > 1e-6) throw new Error("Invalid county population shares.");
      ids.add(share.districtId); p += share.population; b += share.blockCount;
      populations[share.districtId] += share.population; counts[share.districtId] += share.blockCount;
    }
    if (p !== county.population || b !== county.blockCount) throw new Error("County population shares do not reconcile.");
    people += p; blocks += b;
  }
  if (people !== plan.residentPopulation || blocks !== plan.blockCount || value.districts.length !== plan.districtCount) throw new Error("State county totals do not reconcile.");
  const seen = new Set<number>();
  for (const district of value.districts) {
    if (!Number.isInteger(district.districtId) || district.districtId < 0 || district.districtId >= plan.districtCount || seen.has(district.districtId) || district.population !== populations[district.districtId] || district.population !== plan.districtPopulations[district.districtId] || district.blockCount !== counts[district.districtId] || !Array.isArray(district.countyFips)) throw new Error("State district totals do not reconcile.");
    seen.add(district.districtId);
    const expected = value.counties.filter((c) => c.districtShares.some((s) => s.districtId === district.districtId)).map((c) => c.fips).sort();
    if (JSON.stringify([...district.countyFips].sort()) !== JSON.stringify(expected)) throw new Error("State county membership does not match the plan.");
  }
  return value;
}

export function validateCountyBlocks(data: BlockMapCollection, plan: BlockPlan, fips: string, population: number, count: number) {
  const seen = new Set<string>(); let total = 0;
  if (data.features.length !== count) throw new Error("County block count differs from the saved summary.");
  for (const feature of data.features) {
    const { geoid, district_id: district, population: p } = feature.properties;
    if (typeof geoid !== "string" || !/^\d{15}$/.test(geoid) || !geoid.startsWith(`${plan.stateFips}${fips}`) || seen.has(geoid) || !Number.isInteger(district) || Number(district) < 0 || Number(district) >= plan.districtCount || typeof p !== "number" || !Number.isSafeInteger(p) || p < 0 || !feature.geometry || !["Polygon", "MultiPolygon"].includes(feature.geometry.type)) throw new Error("County block data does not match the selected plan.");
    seen.add(geoid); total += p;
  }
  if (total !== population) throw new Error("County block populations do not reconcile.");
  return data;
}

export function validateStateSpatialIndex(index: StateSpatialBlockIndex, plan: BlockPlan, summary: StateExplorerSummary) {
  if (![1, 2].includes(index.schemaVersion) || index.planId !== plan.id || index.stateFips !== plan.stateFips || (index.coordinateFrame !== undefined && index.coordinateFrame !== plan.coordinateFrame) || index.totalBlockCount !== plan.blockCount || index.totalPopulation !== plan.residentPopulation || !Array.isArray(index.chunks) || !index.chunks.length || !Array.isArray(index.counties)) throw new Error("Spatial block index does not match this plan.");
  const ids = new Set<string>(); let count = 0, population = 0;
  for (const chunk of index.chunks) {
    if (!chunk.chunkId || ids.has(chunk.chunkId) || !Number.isSafeInteger(chunk.blockCount) || chunk.blockCount < 1 || !Number.isSafeInteger(chunk.population) || chunk.population < 0
      || !Array.isArray(chunk.bbox) || chunk.bbox.length !== 4 || !chunk.bbox.every(Number.isFinite) || chunk.bbox[0] > chunk.bbox[2] || chunk.bbox[1] > chunk.bbox[3]
      || !chunk.asset?.url || !Number.isSafeInteger(chunk.asset.bytes) || chunk.asset.bytes < 1) throw new Error("Invalid spatial block index entry.");
    ids.add(chunk.chunkId); count += chunk.blockCount; population += chunk.population;
    if (index.schemaVersion === 2 && (!chunk.assignments?.url || !Number.isSafeInteger(chunk.assignments.bytes) || chunk.assignments.bytes < 1)) throw new Error("Shared block geometry lacks its saved assignments.");
    if (index.schemaVersion === 1 && chunk.assignments) throw new Error("Unexpected assignment sidecar for whole-block chunk.");
  }
  const counties = new Set<string>();
  for (const county of index.counties) {
    const expected = summary.counties.find((value) => value.fips === county.fips);
    if (counties.has(county.fips) || !expected || expected.blockCount !== county.blockCount || expected.population !== county.population) throw new Error("Spatial county totals do not match the saved plan.");
    counties.add(county.fips);
  }
  if (count !== plan.blockCount || population !== plan.residentPopulation || counties.size !== summary.counties.length) throw new Error("Spatial block totals do not reconcile.");
  return index;
}

export function validateStateSpatialBlocks(data: BlockMapCollection, plan: BlockPlan, chunk: StateSpatialBlockChunk) {
  const seen = new Set<string>(); let population = 0;
  if (data.features.length !== chunk.blockCount) throw new Error("Spatial chunk block count differs from its index.");
  for (const feature of data.features) {
    const { geoid, district_id: district, population: p } = feature.properties;
    if (typeof geoid !== "string" || (!/^\d{15}$/.test(geoid) || !geoid.startsWith(plan.stateFips)) || seen.has(geoid) || !Number.isInteger(district) || Number(district) < 0 || Number(district) >= plan.districtCount || typeof p !== "number" || !Number.isSafeInteger(p) || p < 0 || !feature.geometry || !["Polygon", "MultiPolygon"].includes(feature.geometry.type)) throw new Error("Spatial block data does not match the selected plan.");
    seen.add(geoid); population += p;
  }
  if (population !== chunk.population) throw new Error("Spatial chunk populations do not reconcile.");
  return data;
}
