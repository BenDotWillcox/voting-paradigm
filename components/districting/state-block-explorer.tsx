"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import type { Feature, Geometry } from "geojson";
import { Minus, Plus, RotateCcw, Scan, Undo2 } from "lucide-react";
import type { BlockAsset, BlockLandDisplay, BlockPlan, BlockStateComparisonLayers, StateExplorerPlanAssets, StateExplorerSummary, StateSpatialBlockIndex, StateCityMetadata } from "@/types/block-districting";
import { blockDistrictColor, fetchBlockCollection, makeStateBlockProjection } from "@/lib/block-map-projection";
import type { BlockMapCollection, BlockMapProperties } from "@/lib/block-map-projection";
import { loadDerivedConnections } from "@/lib/block-land-display";
import { MAP_COLORS } from "@/lib/districts-palette";
import { boundsIntersect, constrainViewport, fitMapBounds, fitStateInspectionFeature, fitStateBlockBudget, INITIAL_VIEW, MAX_MAP_ZOOM, mapPoint, stateZoomLimits, pointInProjectedGeometry, prepareStateCountyAsync, projectedStateCountyBounds, transformedProjection, validateStateSpatialIndex, validateStateSummary, viewportBounds, visibleStateCountyFips, zoomAt } from "@/lib/state-map-interaction";
import type { MapBounds, MapViewport, StateInspectionTarget, StateBlockBudgetChunk } from "@/lib/state-map-interaction";
import { StateSpatialBlockCache } from "@/lib/state-spatial-block-cache";
import { loadStateSpatialBlocks } from "@/lib/state-spatial-blocks";
import { ComparisonBoundaries, ComparisonLayerControl, DensityCanvas, DensityLegend, useComparisonLayer } from "./block-comparison-layers";
import { StateBlockCanvas } from "./state-map-canvas";

type MapFeature = Feature<Geometry, BlockMapProperties>;
const EMPTY_CHUNK_IDS: readonly string[] = Object.freeze([]);

function useCollection(asset: BlockAsset | undefined, enabled = true, retainWhenDisabled = true, scope = 0) {
  const [value, setValue] = React.useState<{ key: string; data: BlockMapCollection } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [retry, setRetry] = React.useState(0);
  const url = asset?.url;
  const key = `${scope}:${url ?? ""}`;
  React.useEffect(() => {
    if (!enabled || !url) {
      if (!retainWhenDisabled) { if (value) setValue(null); setError(null); }
      return;
    }
    if (value?.key === key) return;
    const abort = new AbortController(); setError(null);
    fetchBlockCollection(url, abort.signal).then((data) => { if (!abort.signal.aborted) setValue({ key, data }); })
      .catch((cause: unknown) => { if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load map layer."); });
    return () => abort.abort();
  }, [enabled, url, key, retainWhenDisabled, retry, value]);
  return { data: enabled && value && value.key === key ? value.data : null, retained: value !== null, error: enabled ? error : null, retry: () => setRetry((n) => n + 1) };
}

function featureCollection(features: MapFeature[]): BlockMapCollection { return { type: "FeatureCollection", features }; }
function bboxFeature(box: readonly number[]): MapFeature {
  const [w, s, e, n] = box;
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } };
}
function signed(value: number, digits = 3) { return `${value > 0 ? "+" : ""}${value.toLocaleString(undefined, { maximumFractionDigits: digits })}`; }
function connectionId(feature: MapFeature) { return String(feature.properties.id ?? feature.id ?? ""); }
function connectionKind(feature: MapFeature) { return String(feature.properties.kind ?? "water").includes("exclave") ? "Exclave" : "Water"; }

export function StateBlockExplorer({ plan, comparisonLayers, landDisplay, explorer, cities, cityMetadata, navigation, heading, onExit }: {
  navigation?: React.ReactNode; heading?: React.ReactNode; onExit?: () => void;
  plan: BlockPlan; comparisonLayers?: BlockStateComparisonLayers; landDisplay?: BlockLandDisplay;
  explorer: StateExplorerPlanAssets; cities: BlockAsset; cityMetadata?: StateCityMetadata;
}) {
  const stateName = plan.stateName || (plan.stateFips === "26" ? "Michigan" : "State");
  const cityLabel = cityMetadata?.label ?? "City points";
  const countyLabel = (value: StateExplorerSummary["counties"][number]) => value.displayName ?? (plan.stateFips === "26" ? `${value.name} County` : value.name);
  const [summary, setSummary] = React.useState<StateExplorerSummary | null>(null);
  const [spatialIndex, setSpatialIndex] = React.useState<StateSpatialBlockIndex | null>(null);
  const [summaryError, setSummaryError] = React.useState<string | null>(null);
  const [summaryRetry, setSummaryRetry] = React.useState(0);
  const [district, setDistrict] = React.useState<number | null>(null);
  const [countyFips, setCountyFips] = React.useState<string | null>(null);
  const [block, setBlock] = React.useState<MapFeature | null>(null);
  const [view, setView] = React.useState<MapViewport>({ ...INITIAL_VIEW });
  const [inspection, setInspection] = React.useState<StateInspectionTarget>("districts");
  const inspectionRef = React.useRef(inspection); inspectionRef.current = inspection;
  const detailEpoch = React.useRef(0);
  const [detailSession, setDetailSession] = React.useState(0);
  const zoomLimits = stateZoomLimits(inspection);
  const zoomLimitsRef = React.useRef(zoomLimits); zoomLimitsRef.current = zoomLimits;
  const budgetChunksRef = React.useRef<readonly StateBlockBudgetChunk[] | null>(null);
  const retainedTargetRef = React.useRef<readonly string[]>(EMPTY_CHUNK_IDS);
  const [fullExtent, setFullExtent] = React.useState(false);
  const [exact, setExact] = React.useState(false);
  const [showCounties, setShowCounties] = React.useState(true);
  const [showDensity, setShowDensity] = React.useState(false);
  const [showCongress, setShowCongress] = React.useState(false);
  const [showCities, setShowCities] = React.useState(true);
  const [showDerived, setShowDerived] = React.useState(false);
  const [showRecorded, setShowRecorded] = React.useState(plan.recordedLinkCount > 0);
  const [selectedConnection, setSelectedConnection] = React.useState("");
  const [countyOpacity, setCountyOpacity] = React.useState(0.45);
  const [densityOpacity, setDensityOpacity] = React.useState(0.9);
  const [congressOpacity, setCongressOpacity] = React.useState(0.8);
  const [cityOpacity, setCityOpacity] = React.useState(0.9);
  const [derived, setDerived] = React.useState<BlockMapCollection | null>(null);
  const [derivedError, setDerivedError] = React.useState<string | null>(null);
  const [derivedRetry, setDerivedRetry] = React.useState(0);
  const [countyQuery, setCountyQuery] = React.useState("");
  const [blockQuery, setBlockQuery] = React.useState("");
  const overview = useCollection(explorer.overview);
  const coast = useCollection(explorer.coast);
  const dividers = useCollection(explorer.dividers);
  const fine = inspection === "blocks";
  const fullOverview = useCollection(explorer.censusOverview
    ?? (plan.coordinateFrame === "alaska-continuous" ? plan.assets.state : plan.assets.national), !!landDisplay && fullExtent, false);
  const detail = useCollection(exact ? plan.assets.full : fullExtent ? plan.assets.state : landDisplay?.state ?? explorer.detail ?? plan.assets.state, fine, false, detailSession);
  const detailDividers = useCollection(explorer.detailDividers, fine && !fullExtent && !exact, false, detailSession);
  const cityLayer = useCollection(cities, showCities);
  const recorded = useCollection(plan.assets.connections, showRecorded);
  // County shapes also supply hit testing, even when their visual layer is off.
  const counties = useComparisonLayer(plan.stateFips, "counties", comparisonLayers?.counties, true);
  const density = useComparisonLayer(plan.stateFips, "density", comparisonLayers?.density, showDensity);
  const congressional = useComparisonLayer(plan.stateFips, "congressional", comparisonLayers?.congressional, showCongress);
  const coarseData = landDisplay && fullExtent ? fullOverview.data : overview.data;
  const data = fine ? detail.data ?? coarseData : coarseData;
  const renderingFine = fine && detail.data !== null;
  const projection = React.useMemo(() => overview.data ? makeStateBlockProjection(overview.data, plan.stateFips) : null, [overview.data, plan.stateFips]);
  const screenProjection = React.useMemo(() => projection ? transformedProjection(projection, view) : null, [projection, view]);
  const path = React.useMemo(() => projection ? geoPath(projection) : null, [projection]);
  const county = summary?.counties.find((c) => c.fips === countyFips) ?? null;
  const districtSummary = summary?.districts.find((d) => d.districtId === district) ?? null;
  const level = block ? "block" : county ? "county" : district !== null ? "district" : "state";
  const svgRef = React.useRef<SVGSVGElement>(null);
  const viewRef = React.useRef(view); viewRef.current = view;
  const viewFrame = React.useRef(0);
  const pendingView = React.useRef(view);
  const drag = React.useRef<{ pointer: number; startX: number; startY: number; x: number; y: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const scheduleView = React.useCallback((next: MapViewport, anchor: readonly number[] = [500, 310]) => {
    let bounded = constrainViewport(next, zoomLimitsRef.current, anchor);
    if (inspectionRef.current === "blocks" && budgetChunksRef.current) {
      const result = fitStateBlockBudget(bounded, budgetChunksRef.current, anchor);
      const previous = viewRef.current, ratio = bounded.k / previous.k;
      const onlyZoomingOut = bounded.k < previous.k
        && Math.abs(bounded.x - (anchor[0] - (anchor[0] - previous.x) * ratio)) < 1e-6
        && Math.abs(bounded.y - (anchor[1] - (anchor[1] - previous.y) * ratio)) < 1e-6;
      // A discrete chunk boundary must not turn a zoom-out gesture into zoom-in.
      bounded = onlyZoomingOut && !result.blocked && result.view.k >= previous.k ? previous : result.view;
    }
    pendingView.current = bounded; viewRef.current = bounded;
    if (!viewFrame.current) viewFrame.current = requestAnimationFrame(() => { viewFrame.current = 0; setView(pendingView.current); });
  }, []);
  React.useEffect(() => () => cancelAnimationFrame(viewFrame.current), []);

  React.useEffect(() => {
    const abort = new AbortController(); setSummaryError(null);
    fetch(explorer.summary.url, { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Unable to load State summaries.");
        const value = await response.json() as StateExplorerSummary;
        validateStateSummary(value, plan);
        if (!abort.signal.aborted) setSummary(value);
      }).catch((cause: unknown) => { if (!abort.signal.aborted) setSummaryError(cause instanceof Error ? cause.message : "Unable to load State summaries."); });
    return () => abort.abort();
  }, [explorer.summary.url, plan, summaryRetry]);

  const [spatialIndexError, setSpatialIndexError] = React.useState<string | null>(null);
  const spatialIndexUrl = explorer.spatialIndex?.url;
  React.useEffect(() => {
    if (!fine) { setSpatialIndex(null); setSpatialIndexError(null); return; }
    if (!summary) return;
    const abort = new AbortController(); setSpatialIndexError(null);
    if (!spatialIndexUrl) { setSpatialIndexError("Spatial block detail is unavailable for this plan."); return; }
    fetch(spatialIndexUrl, { signal: abort.signal }).then(async (response) => {
      if (!response.ok) throw new Error("Unable to load the spatial block index.");
      const index = validateStateSpatialIndex(await response.json() as StateSpatialBlockIndex, plan, summary);
      if (!abort.signal.aborted) setSpatialIndex(index);
    }).catch((cause: unknown) => { if (!abort.signal.aborted) setSpatialIndexError(cause instanceof Error ? cause.message : "Unable to load spatial block index."); });
    return () => abort.abort();
  }, [fine, summary, plan, spatialIndexUrl, summaryRetry]);

  React.useEffect(() => {
    if (!showDerived || !landDisplay || derived) return;
    const abort = new AbortController(); setDerivedError(null);
    loadDerivedConnections(plan, landDisplay, abort.signal).then((features) => { if (!abort.signal.aborted) setDerived(featureCollection(features)); })
      .catch((cause: unknown) => { if (!abort.signal.aborted) setDerivedError(cause instanceof Error ? cause.message : "Unable to load derived connections."); });
    return () => abort.abort();
  }, [plan, landDisplay, showDerived, derived, derivedRetry]);

  const countyShapes = React.useMemo(() => path && counties.data ? counties.data.features.map((feature) => ({ feature, fips: String(feature.properties.geoid).slice(2), bounds: path.bounds(feature) as MapBounds, center: path.centroid(feature), d: path(feature) ?? "" })) : [], [path, counties.data]);
  const countyBounds = React.useMemo(() => projection && summary ? summary.counties.map((c) => ({ fips: c.fips, bounds: projectedStateCountyBounds(c.bbox, projection) })) : [], [projection, summary]);
  const spatialBounds = React.useMemo(() => projection && spatialIndex ? spatialIndex.chunks.map((chunk) => ({ chunkId: chunk.chunkId, bounds: projectedStateCountyBounds(chunk.bbox, projection), rawBytes: chunk.asset.bytes + (chunk.assignments?.bytes ?? 0), blockCount: chunk.blockCount })) : [], [projection, spatialIndex]);
  budgetChunksRef.current = fine && projection && spatialIndex ? spatialBounds : null;
  const wantsBlocks = fine;
  const blockBudget = React.useMemo(() => wantsBlocks && spatialIndex && projection ? fitStateBlockBudget(view, spatialBounds) : null, [wantsBlocks, spatialIndex, projection, view, spatialBounds]);
  const budgetReady = !!blockBudget && !blockBudget.blocked && !blockBudget.adjusted;
  // On the first index response, never request the old, broad camera's chunks.
  // During correction keep the last affordable coverage until the camera lands.
  const candidates = wantsBlocks ? budgetReady ? blockBudget.chunkIds : retainedTargetRef.current : EMPTY_CHUNK_IDS;
  React.useEffect(() => { if (budgetReady) retainedTargetRef.current = candidates; }, [budgetReady, candidates]);
  React.useEffect(() => { if (blockBudget?.adjusted) scheduleView(blockBudget.view); }, [blockBudget, scheduleView]);
  const canZoomOut = React.useMemo(() => {
    if (view.k <= zoomLimits.min) return false;
    if (!wantsBlocks || !spatialIndex) return true;
    const result = fitStateBlockBudget(zoomAt(view, 1 / 1.5, [500, 310], { min: zoomLimits.min, max: zoomLimits.max }), spatialBounds);
    return !result.blocked && result.view.k < view.k * (1 - 1e-6);
  }, [view, zoomLimits.min, zoomLimits.max, wantsBlocks, spatialIndex, spatialBounds]);
  const visibleCounties = React.useMemo(() => wantsBlocks ? visibleStateCountyFips(countyBounds, view) : [], [wantsBlocks, countyBounds, view]);
  const wantedKey = candidates.join(",");
  const [, setCacheRevision] = React.useState(0);
  const [cacheOwner, setCacheOwner] = React.useState<{ session: number; cache: StateSpatialBlockCache } | null>(null);
  const cacheRef = React.useRef<StateSpatialBlockCache | null>(null);
  React.useEffect(() => {
    if (!wantsBlocks || !spatialIndex || !path) { setCacheOwner(null); return; }
    const owner = new StateSpatialBlockCache({ chunks: spatialIndex.chunks, onChange: () => setCacheRevision((revision) => revision + 1),
      load: async (chunk, signal) => {
        const fetched = await loadStateSpatialBlocks(plan, chunk, signal);
        if (signal.aborted) throw new DOMException("Spatial block request was canceled.", "AbortError");
        return prepareStateCountyAsync(fetched, path, signal);
      } });
    cacheRef.current = owner; setCacheOwner({ session: detailSession, cache: owner });
    return () => { owner.dispose(); if (cacheRef.current === owner) cacheRef.current = null; };
  }, [wantsBlocks, spatialIndex, path, plan, detailSession]);
  const blockCache = wantsBlocks && cacheOwner?.session === detailSession ? cacheOwner.cache : null;
  React.useEffect(() => { if (budgetReady) blockCache?.setNeeded(wantedKey ? wantedKey.split(",") : []); }, [blockCache, wantedKey, budgetReady]);
  const blockSnapshot = blockCache?.snapshot(candidates);
  const blocksError = spatialIndexError ?? blockSnapshot?.error ?? null;
  const blockBatchReady = wantsBlocks && budgetReady && !!blockSnapshot?.ready;
  const preparedData = blockSnapshot?.renderData;
  const activeChunks = React.useMemo(() => wantsBlocks && preparedData ? preparedData : [], [wantsBlocks, preparedData]);
  const blockFeatures = React.useMemo(() => activeChunks.flatMap((c) => c.collection.features), [activeChunks]);
  const blockShapes = React.useMemo(() => activeChunks.flatMap((c) => c.shapes), [activeChunks]);
  const shapes = React.useMemo(() => path && data ? data.features.map((feature) => ({ feature, id: Number(feature.properties.district_id), d: path(feature) ?? "", bounds: path.bounds(feature) as MapBounds })) : [], [data, path]);
  const dividerData = renderingFine ? detailDividers.data : dividers.data;
  const dividerPaths = React.useMemo(() => path && dividerData ? dividerData.features.map((feature) => path(feature) ?? "") : [], [path, dividerData]);
  const coastPaths = React.useMemo(() => path && coast.data ? coast.data.features.map((feature) => path(feature) ?? "") : [], [path, coast.data]);
  const derivedPaths = React.useMemo(() => path && showDerived && derived ? derived.features.map((feature) => path(feature) ?? "") : [], [path, showDerived, derived]);
  const recordedPaths = React.useMemo(() => path && recorded.data ? recorded.data.features.map((feature) => ({ id: connectionId(feature), kind: connectionKind(feature), d: path(feature) ?? "" })) : [], [path, recorded.data]);
  const activeConnection = recorded.data?.features.find((feature) => connectionId(feature) === selectedConnection) ?? recorded.data?.features[0];
  const visibleLandMask = React.useMemo(() => {
    if (!data || fullExtent) return undefined;
    const viewport = viewportBounds(view);
    return featureCollection(shapes.filter((shape) => boundsIntersect(shape.bounds, viewport)).map((shape) => shape.feature));
  }, [data, fullExtent, shapes, view]);
  function featureView(feature: MapFeature) { return path ? fitStateInspectionFeature(feature, path, zoomLimitsRef.current.min) : { ...INITIAL_VIEW }; }
  function fitFeature(feature: MapFeature) { scheduleView(featureView(feature)); }
  function countyFeature(value: StateExplorerSummary["counties"][number]) {
    const reference = !fullExtent ? countyShapes.find((shape) => shape.fips === value.fips)?.feature : null;
    return reference ?? bboxFeature(value.bbox);
  }
  function fitCounty(value: StateExplorerSummary["counties"][number]) { fitFeature(countyFeature(value)); }
  function cancelMapMotion() {
    cancelAnimationFrame(viewFrame.current); viewFrame.current = 0;
    const pointer = drag.current?.pointer;
    drag.current = null; setDragging(false);
    if (pointer !== undefined && svgRef.current?.hasPointerCapture(pointer)) svgRef.current.releasePointerCapture(pointer);
  }
  function chooseInspection(target: StateInspectionTarget) {
    if (target === inspectionRef.current) return;
    cancelMapMotion(); detailEpoch.current++; setDetailSession(detailEpoch.current);
    cacheRef.current?.dispose(); cacheRef.current = null; setCacheOwner(null); setSpatialIndex(null); setSpatialIndexError(null);
    budgetChunksRef.current = null; retainedTargetRef.current = EMPTY_CHUNK_IDS;
    inspectionRef.current = target; setInspection(target);
    zoomLimitsRef.current = stateZoomLimits(target);
    if (target !== "blocks") { setBlock(null); setBlockQuery(""); setExact(false); }
    let next = viewRef.current;
    if (target === "blocks" && next.k < 7 && path) {
      const selected = county ? countyFeature(county) : (data ?? overview.data)?.features.find((f) => f.properties.district_id === district);
      if (selected?.geometry.type === "MultiPolygon" && fitMapBounds(path.bounds(selected) as MapBounds).k < 7) {
        next = fitStateInspectionFeature(selected, path, 7);
      }
    }
    scheduleView(target === "blocks" ? constrainViewport(next, { min: 7, max: MAX_MAP_ZOOM }) : next);
  }
  function resetState(fullState = false) {
    cancelMapMotion();
    if (fullState) chooseInspection("districts");
    setDistrict(null); setCountyFips(null); setBlock(null); setCountyQuery(""); setBlockQuery("");
    scheduleView(constrainViewport({ ...INITIAL_VIEW }, zoomLimitsRef.current));
  }
  function selectDistrict(id: number) {
    const feature = (data ?? overview.data)?.features.find((f) => f.properties.district_id === id);
    if (!feature) return;
    cancelMapMotion(); setDistrict(id); setCountyFips(null); setBlock(null); setCountyQuery(""); setBlockQuery(""); fitFeature(feature);
  }
  function selectCounty(fips: string) {
    const value = summary?.counties.find((c) => c.fips === fips);
    if (!value) return;
    if (district !== null && !value.districtShares.some((share) => share.districtId === district)) setDistrict(null);
    cancelMapMotion(); setCountyFips(fips); setBlock(null); setBlockQuery(""); fitCounty(value);
  }
  function selectBlock(feature: MapFeature) {
    if (!renderingFine) return;
    setCountyFips(String(feature.properties.geoid).slice(2, 5)); setDistrict(Number(feature.properties.district_id));
    setBlock(feature); fitFeature(feature);
  }
  const canGoBack = block !== null || (county !== null && district !== null);
  function back() { if (block) { setBlock(null); if (county) fitCounty(county); } else if (county && district !== null) selectDistrict(district); }
  function pick(point: [number, number]) {
    if (!projection) return;
    if (inspection === "blocks") {
      if (!renderingFine || !activeChunks.length) return;
      if (!fullExtent && data && !data.features.some((f) => pointInProjectedGeometry(f.geometry, point, projection.projectPoint))) return;
      const hit = activeChunks.flatMap((chunk) => chunk.hitCandidates(point).map((i) => chunk.shapes[i])).find((s) => pointInProjectedGeometry(s.feature.geometry, point, projection.projectPoint));
      if (hit) selectBlock(hit.feature);
    } else if (inspection === "counties") {
      const hit = countyShapes.find((s) => pointInProjectedGeometry(s.feature.geometry, point, projection.projectPoint));
      if (hit) selectCounty(hit.fips);
    } else {
      const hit = (data ?? overview.data)?.features.find((feature) => pointInProjectedGeometry(feature.geometry, point, projection.projectPoint));
      if (hit) selectDistrict(Number(hit.properties.district_id));
    }
  }
  function fitSelection() {
    if (block) fitFeature(block); else if (county) fitCounty(county); else if (district !== null) selectDistrict(district); else scheduleView({ ...INITIAL_VIEW });
  }
  const mapReady = !!data;
  React.useEffect(() => {
    const svg = svgRef.current; if (!svg) return;
    const wheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) return;
      event.preventDefault();
      const rect = svg.getBoundingClientRect(), p = [1000 * (event.clientX - rect.left) / rect.width, 620 * (event.clientY - rect.top) / rect.height];
      scheduleView(zoomAt(viewRef.current, Math.exp(-Math.max(-120, Math.min(120, event.deltaY)) * 0.0025), p, zoomLimitsRef.current), p);
    };
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => svg.removeEventListener("wheel", wheel);
  }, [scheduleView, mapReady]);

  const visibleCities = React.useMemo(() => {
    if (!showCities || !cityLayer.data || !screenProjection) return [];
    const occupied: { x: number; y: number; w: number }[] = [];
    return [...cityLayer.data.features].filter((f) => f.geometry.type === "Point").sort((a, b) => Number(b.properties.population) - Number(a.properties.population)).flatMap((feature) => {
      if (feature.geometry.type !== "Point") return [];
      const [x, y] = screenProjection.projectPoint(feature.geometry.coordinates), name = String(feature.properties.name).replace(/ city$/, ""), w = Math.max(60, name.length * 8.5);
      if (x < 12 || y < 18 || x + w + 8 > 988 || y > 600 || occupied.some((p) => Math.abs(y - p.y) < 26 && x < p.x + p.w + 12 && x + w + 12 > p.x)) return [];
      if (occupied.length >= (view.k < 2 ? 9 : 22)) return [];
      occupied.push({ x, y, w }); return [{ name, x, y, population: Number(feature.properties.population), geoid: String(feature.properties.geoid) }];
    });
  }, [cityLayer.data, showCities, screenProjection, view.k]);
  const countyLabels = React.useMemo(() => {
    if (!showCounties || !path || view.k < 2.5) return [];
    const occupied: [number, number][] = [];
    return countyShapes.flatMap((shape) => {
      const x = shape.center[0] * view.k + view.x, y = shape.center[1] * view.k + view.y;
      if (x < 30 || y < 22 || x > 970 || y > 598 || occupied.some((p) => Math.abs(x - p[0]) < 75 && Math.abs(y - p[1]) < 22)) return [];
      occupied.push([x, y]); return [{ fips: shape.fips, name: String(shape.feature.properties.name), x, y }];
    });
  }, [showCounties, path, view, countyShapes]);
  const errors = [overview.error, fullOverview.error, coast.error, dividers.error, detail.error, detailDividers.error, summaryError].filter(Boolean);
  const chosenBlock = block ? String(block.properties.geoid) : null;
  const highlighted = React.useMemo(() => block && path ? path(block) ?? "" : null, [block, path]);
  const districtId = block ? Number(block.properties.district_id) : district;
  const ideal = plan.residentPopulation / plan.districtCount;
  const blockSearchResults = renderingFine && blockQuery ? blockFeatures.filter((f) => String(f.properties.geoid).includes(blockQuery)).slice(0, 12) : [];

  const layerCount = [showCounties, showCities, showDensity, showCongress, fullExtent, exact, showDerived, showRecorded].filter(Boolean).length;
  const crumbSeparator = <span aria-hidden="true" className="dd-crumb-sep">›</span>;

  return <section className="dd-instrument" data-layout="state-map-workspace" aria-label={`${stateName} interactive district explorer`}>
    <div className="dd-rail">
    <aside className="dd-primary" aria-label="Plan selection">
      {heading}
      {navigation}
    </aside>
    <div className="dd-explore" role="group" aria-label="Inspect geography controls">
      <div className="dd-section">
        <h3 className="dd-label">Inspect</h3>
        <div role="group" aria-label="Inspect geography" className="dd-segmented">{(["districts", "counties", "blocks"] as const).map((target) => <button key={target} type="button" aria-pressed={inspection === target} onClick={() => chooseInspection(target)} className="dd-segment py-2">{target[0].toUpperCase() + target.slice(1)}</button>)}</div>
        <p className="dd-meta">{inspection === "districts" ? "Click any district to inspect it." : inspection === "counties" ? "Click any county to see its population split." : "Click any loaded block to inspect its population, county, and computed district. Block detail starts closer in dense areas."} Drag to pan · scroll or use <span className="whitespace-nowrap">+/− to zoom.</span></p>
        <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-2">
          <label className="dd-field">District<select aria-label="Explore computed district" className="dd-input" value={district ?? ""} onChange={(event) => event.target.value === "" ? resetState() : selectDistrict(Number(event.target.value))}><option value="">Choose on the map</option>{plan.districtPopulations.map((_, id) => <option key={id} value={id}>District {id + 1}</option>)}</select></label>
          <label className="dd-field">County<input aria-label="Find a county by name" placeholder="Find a county…" className="dd-input" value={countyQuery} onChange={(event) => setCountyQuery(event.target.value)} /></label>
          {countyQuery && <div className="col-span-2 flex flex-wrap gap-1" aria-label="County search results">{(summary?.counties ?? []).filter((c) => c.name.toLowerCase().includes(countyQuery.toLowerCase())).slice(0, 12).map((c) => <button key={c.fips} className="dd-chip" onClick={() => { selectCounty(c.fips); setCountyQuery(""); }}>{countyLabel(c)}</button>)}</div>}
        </div>
        {fine && <div className="min-w-0"><label className="dd-field">Find a loaded census block<input aria-label="Find a census block by GEOID" placeholder="Census GEOID or final block digits" disabled={!renderingFine || !blockFeatures.length} className="dd-input" value={blockQuery} onChange={(event) => setBlockQuery(event.target.value)} /></label>{blockSearchResults.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{blockSearchResults.map((feature) => <button key={String(feature.properties.geoid)} className="dd-chip" onClick={() => selectBlock(feature)}>Block {String(feature.properties.geoid)} · {Number(feature.properties.population).toLocaleString()} residents</button>)}</div>}</div>}
      </div>
    </div>
    <aside className="dd-secondary" aria-label="Map display">
      <details className="dd-disclosure" data-panel="advanced-map-controls">
        <summary>Map layers<span className="dd-badge">{layerCount} on</span></summary>
        <div className="dd-disclosure-body">
          <div className="space-y-1">
            <h4 className="dd-group-title mb-1">Reference layers</h4>
            <ComparisonLayerControl compact kind="counties" layer={comparisonLayers?.counties} enabled={showCounties} onEnabled={setShowCounties} opacity={countyOpacity} onOpacity={setCountyOpacity} state={counties} />
            <div className="space-y-1 py-1"><label className="flex items-center gap-2 text-xs font-medium"><input type="checkbox" checked={showCities} onChange={(e) => setShowCities(e.target.checked)} />{cityLabel}</label>{showCities && <label className="flex items-center gap-2 pl-5 text-xs"><span className="text-muted-foreground">Opacity</span><input aria-label="City points opacity" className="min-w-0 flex-1" type="range" min="0" max="100" step="5" value={cityOpacity * 100} onChange={(e) => setCityOpacity(Number(e.target.value) / 100)} /><span className="w-9 text-right tabular-nums">{Math.round(cityOpacity * 100)}%</span></label>}</div>
            <ComparisonLayerControl compact kind="density" layer={comparisonLayers?.density} enabled={showDensity} onEnabled={setShowDensity} opacity={densityOpacity} onOpacity={setDensityOpacity} state={density} />
            <ComparisonLayerControl compact kind="congressional" layer={comparisonLayers?.congressional} enabled={showCongress} onEnabled={setShowCongress} opacity={congressOpacity} onOpacity={setCongressOpacity} state={congressional} />
          </div>
          {cityLayer.error && <p role="alert" className="text-xs text-destructive">{cityLayer.error} <button onClick={cityLayer.retry} className="underline">Retry cities</button></p>}
          <fieldset className="space-y-2 border-t pt-3 text-xs"><legend className="sr-only">Boundary display</legend><h4 className="dd-group-title">Boundary display</h4>{landDisplay && <label className="flex items-center gap-2"><input type="checkbox" checked={fullExtent} onChange={(e) => { setFullExtent(e.target.checked); setExact(false); }} />Full census extent</label>}<label className={`flex items-start gap-2 ${!fine || (!!landDisplay && !fullExtent) ? "text-muted-foreground" : ""}`}><input type="checkbox" className="mt-0.5" checked={exact} disabled={!fine || (!!landDisplay && !fullExtent)} onChange={(e) => setExact(e.target.checked)} /><span>Exact district outlines <span className="block text-[10px] text-muted-foreground">{landDisplay ? "Blocks + full census extent" : "Blocks inspection"}</span></span></label></fieldset>
          {(landDisplay || plan.assets.connections) && <fieldset className="space-y-2 border-t pt-3 text-xs"><legend className="sr-only">Connections</legend><h4 className="dd-group-title">Connections</h4>{landDisplay && <label className="flex items-center gap-2"><input type="checkbox" checked={showDerived} onChange={(e) => setShowDerived(e.target.checked)} />Derived water connections</label>}{plan.assets.connections && <label className="flex items-center gap-2"><input type="checkbox" checked={showRecorded} onChange={(e) => setShowRecorded(e.target.checked)} />Recorded connections ({plan.recordedLinkCount})</label>}</fieldset>}
          {derivedError && <p role="alert" className="text-xs text-destructive">{derivedError} <button onClick={() => setDerivedRetry((n) => n + 1)} className="underline">Retry water paths</button></p>}
          {showRecorded && plan.assets.connections && <details className="rounded-[3px] border border-[var(--dd-steel)] bg-[var(--dd-board-soft)] p-3 text-xs">
            <summary className="cursor-pointer font-medium">Inspect recorded connections ({plan.recordedLinkCount})</summary>
            <p className="mt-3 text-muted-foreground">Magenta water links and amber exclave links express the saved connection policy. They do not represent land, bridges, or travel routes; physical connectivity remains a separate result.</p>
            {recorded.error ? <p role="alert" className="mt-2 text-destructive">{recorded.error} <button className="underline" onClick={recorded.retry}>Retry recorded connections</button></p> : activeConnection ? <>
              <div className="my-3 flex flex-wrap gap-2"><select aria-label="Choose a recorded connection" className="dd-input flex-1" value={connectionId(activeConnection)} onChange={(event) => setSelectedConnection(event.target.value)}>
                {recorded.data?.features.map((feature) => <option key={connectionId(feature)} value={connectionId(feature)}>{connectionKind(feature)} · {connectionId(feature)} · {(Number(feature.properties.distance_m) / 1000).toFixed(2)} km</option>)}
              </select><button className="dd-tool" onClick={() => { setSelectedConnection(connectionId(activeConnection)); fitFeature(activeConnection); }}>Inspect connection</button></div>
              <p className="break-words text-muted-foreground">Endpoint blocks: {((activeConnection.properties.endpoints as { geoid?: string }[] | undefined) ?? []).map((endpoint) => endpoint.geoid).join(" ↔ ")}</p>
              <p className="mt-1 text-muted-foreground">{activeConnection.properties.used_by_district === null || activeConnection.properties.used_by_district === undefined ? "Endpoints are in different districts; this link does not contribute to district connectivity." : `Both endpoint blocks belong to District ${Number(activeConnection.properties.used_by_district) + 1}.`}</p>
            </> : <p role="status" className="mt-2 text-muted-foreground">Loading recorded connections…</p>}
          </details>}
        </div>
      </details>
      <details className="dd-disclosure">
        <summary>Sources and interpretation</summary>
        <div className="dd-disclosure-body leading-5 text-muted-foreground"><p>Districts and Counties keep simplified boundaries while you browse. Blocks loads finer geography, starts at least 7× closer, and allows zooming out to 6×. Switching back releases block detail. Selecting geography changes the card and fits it without changing what you are inspecting. Mixed land/water blocks retain their extent. All {plan.blockCount.toLocaleString()} saved blocks and {plan.residentPopulation.toLocaleString()} residents remain in the statistics.</p><p>Teal paths explain existing water-block adjacency; they are separate from recorded policy links and do not indicate bridges or travel routes.</p><p>{cityMetadata?.description ?? "City points show incorporated Michigan cities with at least 10,000 residents in 2020."} Labels thin out at wider views. A point does not show a place’s full boundary or assign its entire population to one district.</p>{comparisonLayers && Object.values(comparisonLayers).map((layer) => <p key={layer.asset.url}><a className="underline" href={layer.sourceUrl} target="_blank" rel="noreferrer">{layer.label}</a> · {layer.vintage}. {layer.description}</p>)}{cityMetadata?.sources.map((source) => <p key={source.url}><a className="underline" href={source.url} target="_blank" rel="noreferrer">{source.label}</a> · {source.vintage}</p>)}<p>Reference geography and display simplification do not change saved block assignments. Source hashes are retained in the generated data audit.</p></div>
      </details>
    </aside>
    </div>
    <div className="dd-stage">
    <div className="dd-stage-bar">
      <nav aria-label="Map location" className="dd-crumbs">
        {onExit && <><button type="button" onClick={onExit} className="dd-crumb">United States</button>{crumbSeparator}</>}
        <button type="button" onClick={() => resetState()} className="dd-crumb" aria-current={level === "state" ? "location" : undefined}>{stateName}</button>
        {district !== null && <>{crumbSeparator}<button type="button" onClick={() => selectDistrict(district)} className="dd-crumb" aria-current={level === "district" ? "location" : undefined}>District {district + 1}</button></>}
        {county && <>{crumbSeparator}<button type="button" onClick={() => selectCounty(county.fips)} className="dd-crumb" aria-current={level === "county" ? "location" : undefined}>{countyLabel(county)}</button></>}
        {block && <>{crumbSeparator}<span className="dd-crumb" aria-current="location">Block {String(block.properties.geoid).slice(-4)}</span></>}
      </nav>
      <div className="dd-tools">
        <button type="button" onClick={back} disabled={!canGoBack} className="dd-tool"><Undo2 aria-hidden="true" />Back</button>
        <div className="dd-tool-group">
          <button type="button" aria-label="Zoom out" onClick={() => scheduleView(zoomAt(viewRef.current, 1 / 1.5, [500, 310], zoomLimitsRef.current))} disabled={!canZoomOut} className="dd-tool"><Minus aria-hidden="true" /></button>
          <button type="button" aria-label="Zoom in" onClick={() => scheduleView(zoomAt(viewRef.current, 1.5, [500, 310], zoomLimitsRef.current))} disabled={view.k >= zoomLimits.max} className="dd-tool"><Plus aria-hidden="true" /></button>
        </div>
        <button type="button" onClick={fitSelection} className="dd-tool"><Scan aria-hidden="true" />Fit selection</button>
        <button type="button" onClick={() => resetState(true)} className="dd-tool"><RotateCcw aria-hidden="true" />Reset view</button>
      </div>
    </div>
    <div className="dd-map-area">
    <div className="dd-map-frame" data-map-inspection={inspection} data-map-level={level} data-boundary-detail={fullExtent ? renderingFine && exact ? "exact" : "census" : renderingFine ? "fine" : "simplified"}
      data-zoom-min={zoomLimits.min} data-zoom-max={zoomLimits.max} data-retained-detail-assets={Number(detail.retained) + Number(detailDividers.retained)} data-cached-chunks={blockSnapshot?.cacheSize ?? 0} data-block-chunks={activeChunks.length}
      data-inspection-target={inspection} data-block-detail-active={fine} data-block-batch-ready={blockBatchReady} data-visible-counties={visibleCounties.join(",")} data-visible-chunks={wantedKey}
      data-network-requests={blockSnapshot?.networkRequests ?? 0} data-prepared-chunks={blockSnapshot?.preparedChunks ?? 0} data-cached-raw-bytes={blockSnapshot?.cachedBytes ?? 0}
      data-block-budget-ready={budgetReady} data-block-budget-blocked={!!blockBudget?.blocked} data-block-view-raw-bytes={blockBudget?.rawBytes ?? 0} data-block-view-count={blockBudget?.blockCount ?? 0}>
      {overview.data && projection && path && <>
        <svg viewBox="0 0 1000 620" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true"><g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {shapes.map(({ id, d }) => <path key={id} d={d} fill={density.data ? MAP_COLORS.neutralLand : blockDistrictColor(id, plan.stateFips)} fillRule="evenodd" fillOpacity={0.88} />)}
        </g></svg>
        {density.data && screenProjection && <DensityCanvas data={density.data} projection={screenProjection} opacity={densityOpacity} clip={visibleLandMask} />}
        {wantsBlocks && screenProjection && detail.data && <StateBlockCanvas stateFips={plan.stateFips} shapes={blockShapes} view={view} projection={screenProjection} clip={visibleLandMask} outlinesOnly={!!density.data} complete={blockBatchReady} appearanceKey={`${plan.id}:${fullExtent}:${exact}:${!!density.data}`} />}
        <svg ref={svgRef} viewBox="0 0 1000 620" className={`absolute inset-0 h-full w-full touch-none outline-none ${dragging ? "cursor-grabbing" : "cursor-grab"}`} role="application" tabIndex={0}
          aria-label={`${stateName} map, ${plan.districtCount} districts, inspecting ${inspection}. Arrow keys pan; plus and minus zoom.`}
          onKeyDown={(event) => {
            const step = 45; let next = viewRef.current;
            if (event.key === "+" || event.key === "=") next = zoomAt(next, 1.5, [500, 310], zoomLimitsRef.current);
            else if (event.key === "-") next = zoomAt(next, 1 / 1.5, [500, 310], zoomLimitsRef.current);
            else if (event.key === "ArrowLeft") next = { ...next, x: next.x + step };
            else if (event.key === "ArrowRight") next = { ...next, x: next.x - step };
            else if (event.key === "ArrowUp") next = { ...next, y: next.y + step };
            else if (event.key === "ArrowDown") next = { ...next, y: next.y - step };
            else if (event.key === "Escape") { back(); return; } else return;
            event.preventDefault(); scheduleView(next);
          }}
          onPointerDown={(event) => { if (event.button !== 0) return; event.currentTarget.focus(); const rect = event.currentTarget.getBoundingClientRect(); drag.current = { pointer: event.pointerId, startX: event.clientX, startY: event.clientY, x: viewRef.current.x, y: viewRef.current.y, moved: false }; event.currentTarget.setPointerCapture(event.pointerId); event.preventDefault(); if (!rect.width) drag.current = null; }}
          onPointerMove={(event) => { const active = drag.current; if (!active || active.pointer !== event.pointerId) return; const dx = event.clientX - active.startX, dy = event.clientY - active.startY; if (Math.hypot(dx, dy) > 5) active.moved = true; if (active.moved) { setDragging(true); const rect = event.currentTarget.getBoundingClientRect(), previousZoom = viewRef.current.k; scheduleView({ ...viewRef.current, x: active.x + dx * 1000 / rect.width, y: active.y + dy * 620 / rect.height }); if (viewRef.current.k !== previousZoom) { active.startX = event.clientX; active.startY = event.clientY; active.x = viewRef.current.x; active.y = viewRef.current.y; } } }}
          onPointerUp={(event) => { const active = drag.current; if (!active || active.pointer !== event.pointerId) return; drag.current = null; setDragging(false); event.currentTarget.releasePointerCapture(event.pointerId); if (!active.moved) pick(mapPoint([event.clientX, event.clientY], event.currentTarget.getBoundingClientRect(), viewRef.current)); }}
          onPointerCancel={() => { drag.current = null; setDragging(false); }} onLostPointerCapture={() => { drag.current = null; setDragging(false); }}>
          <rect width="1000" height="620" fill="transparent" />
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`} pointerEvents="none">
            {showCounties && counties.data && <ComparisonBoundaries data={counties.data} projection={projection} kind="counties" opacity={countyOpacity} />}
            {congressional.data && <ComparisonBoundaries data={congressional.data} projection={projection} kind="congressional" opacity={congressOpacity} />}
            {fullExtent || exact ? shapes.map(({ id, d }) => <path key={id} d={d} data-map-layer="computed-district" fill="none" stroke={MAP_COLORS.line} strokeWidth={1.1} vectorEffect="non-scaling-stroke" />)
              : <>
                {renderingFine && shapes.map(({ id, d }) => <path key={`coast-${id}`} data-map-layer="state-coast" d={d} fill="none" stroke={MAP_COLORS.line} strokeOpacity={0.35} strokeWidth={0.6} vectorEffect="non-scaling-stroke" />)}
                {dividerPaths.map((d, i) => <g key={i} data-map-layer="computed-district-divider"><path d={d} fill="none" stroke={MAP_COLORS.casing} strokeWidth={3} vectorEffect="non-scaling-stroke" /><path d={d} fill="none" stroke={MAP_COLORS.line} strokeWidth={1.25} vectorEffect="non-scaling-stroke" /></g>)}
                {!renderingFine && coastPaths.map((d, i) => <path key={i} data-map-layer="state-coast" d={d} fill="none" stroke={MAP_COLORS.line} strokeOpacity={0.45} strokeWidth={0.65} vectorEffect="non-scaling-stroke" />)}
              </>}
            {district !== null && shapes.filter((shape) => shape.id === district).map(({ id, d }) => <g key={`selected-${id}`} opacity={county || block ? 0.5 : 1}><path d={d} fill="none" stroke={MAP_COLORS.selectionCasing} strokeWidth={4.6} vectorEffect="non-scaling-stroke" /><path d={d} data-map-layer="selected-district" fill="none" stroke={MAP_COLORS.selection} strokeWidth={2.2} vectorEffect="non-scaling-stroke" /></g>)}
            {county && countyShapes.filter((s) => s.fips === county.fips).map((shape) => <g key={shape.fips}><path d={shape.d} fill="none" stroke={MAP_COLORS.selectionCasing} strokeWidth={4.6} vectorEffect="non-scaling-stroke" /><path d={shape.d} fill="none" stroke={MAP_COLORS.selection} strokeWidth={2.2} vectorEffect="non-scaling-stroke" /></g>)}
            {highlighted && <><path d={highlighted} fill="none" stroke={MAP_COLORS.selectionCasing} strokeWidth={4.8} vectorEffect="non-scaling-stroke" /><path d={highlighted} data-map-layer="selected-block" fill={MAP_COLORS.casing} fillOpacity={0.45} stroke={MAP_COLORS.selection} strokeWidth={2.4} vectorEffect="non-scaling-stroke" /></>}
            {showDerived && derivedPaths.map((d, i) => <path key={i} data-map-layer="derived-water-connection" d={d} fill="none" stroke={MAP_COLORS.derivedWater} strokeWidth={1} strokeDasharray="3 5" vectorEffect="non-scaling-stroke" />)}
            {showRecorded && recordedPaths.map(({ id, kind, d }, i) => <path key={id || i} data-map-layer="recorded-connection" d={d} fill="none" stroke={kind === "Exclave" ? MAP_COLORS.recordedExclave : MAP_COLORS.recordedWater} strokeWidth={id === selectedConnection ? 3 : 2} strokeDasharray="8 5" vectorEffect="non-scaling-stroke"><title>{kind} connection {id}</title></path>)}
          </g>
          <g pointerEvents="none" data-map-layer="county-labels">{countyLabels.map((label) => <text key={label.fips} x={label.x} y={label.y} textAnchor="middle" fontSize={11} fontWeight={500} fill={MAP_COLORS.label} stroke={MAP_COLORS.labelHalo} strokeWidth={3} paintOrder="stroke" opacity={0.9}>{label.name}</text>)}</g>
          <g pointerEvents="none" opacity={cityOpacity} data-map-layer="cities">{visibleCities.map((city) => <g key={city.geoid}><circle cx={city.x} cy={city.y} r={4} fill={MAP_COLORS.casing} stroke={MAP_COLORS.line} strokeWidth={1.75} /><text x={city.x + 8} y={city.y + 5} fontSize={16} fill={MAP_COLORS.label} stroke={MAP_COLORS.labelHalo} strokeWidth={3.5} paintOrder="stroke" fontWeight={600}>{city.name}</text><title>{city.name}: {city.population.toLocaleString()} residents in 2020. Point location, not the full place boundary.</title></g>)}</g>
        </svg>
      </>}
      {(!data || (fine && !detail.data)) && <div className="dd-map-chip right-3 top-3 px-3 py-2 text-xs" role="status"><span className="dd-led" data-state="busy" />Loading {fine ? "fine boundaries" : `${stateName} boundaries`}…</div>}
      <span className="dd-map-chip bottom-2 right-3 text-[10px] tabular-nums">{view.k.toFixed(1)}× · {exact ? "Exact census boundaries" : fullExtent ? "Full census extent" : renderingFine ? landDisplay ? "Fine land detail" : "Fine census boundaries" : landDisplay ? "Simplified land boundaries" : "Simplified census boundaries"}</span>
    </div>
    </div>
    {/* The readout sits directly under the map so every click's result stays in view. */}
    <div className="dd-readout-strip" aria-label="Selected geography information" aria-live="polite">
      <div className="dd-readout-head"><h3 className="text-sm font-semibold">{block ? `Census block ${String(block.properties.geoid).slice(-4)}` : county ? `${countyLabel(county)}` : district !== null ? `Computed District ${district + 1}` : stateName}</h3><span className="dd-meta">2020 Census · House {plan.houseSizes.join(" / ")}</span></div>
      <dl className="dd-readout-metrics">
        <Metric label="Population" value={(block ? Number(block.properties.population) : county ? county.population : district !== null ? plan.districtPopulations[district] : plan.residentPopulation).toLocaleString()} />
        {block ? <><Metric label="Computed district" value={String(Number(block.properties.district_id) + 1)} /><Metric label="County" value={county?.name ?? ""} /><Metric label="Census block GEOID" value={String(block.properties.geoid)} /></>
          : county ? <><Metric label="Census blocks" value={county.blockCount.toLocaleString()} /><Metric label="Districts intersected" value={String(county.districtShares.length)} /><Metric label="Selected district context" value={district !== null ? `District ${district + 1}` : "All districts"} /></>
            : district !== null ? <><Metric label="Population deviation" value={`${signed(plan.districtPopulations[district] - ideal)} people`} /><Metric label="Deviation from ideal" value={`${signed((plan.districtPopulations[district] - ideal) / ideal * 100, 6)}%`} /><Metric label="Counties intersected" value={districtSummary ? String(districtSummary.countyFips.length) : "…"} /></>
              : <><Metric label="Computed districts" value={String(plan.districtCount)} /><Metric label="Ideal population per district" value={ideal.toLocaleString(undefined, { maximumFractionDigits: 2 })} /><Metric label="Largest population deviation" value={`${plan.maxDeviationPeople.toLocaleString(undefined, { maximumFractionDigits: 3 })} people`} /></>}
      </dl>
      {county && <>
        <p className="dd-meta self-start">These shares describe all residents of {countyLabel(county)}{block ? ", including those outside this block" : district !== null ? `, including those outside District ${district + 1}` : ""}. Shares are based on residents, not land area.</p>
        <div className="min-w-0 space-y-2 self-start">
          <div className="flex h-2.5 overflow-hidden rounded-full ring-1 ring-[var(--dd-steel)]" aria-hidden="true">{county.districtShares.filter((s) => s.population > 0).map((share) => <div key={share.districtId} style={{ width: `${share.percent}%`, background: blockDistrictColor(share.districtId, plan.stateFips) }} />)}</div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">{county.districtShares.map((share) => <span key={share.districtId}><span className="mr-1.5 inline-block h-2 w-2 rounded-full ring-1 ring-black/15" style={{ background: blockDistrictColor(share.districtId, plan.stateFips) }} />District {share.districtId + 1}: <strong>{share.percent.toFixed(2)}%</strong> · {share.population.toLocaleString()} residents</span>)}</div>
        </div>
      </>}
      {block && Number(block.properties.population) === 0 && <p className="dd-meta dd-readout-wide">The census records no residents in this block. That does not by itself identify its land use.</p>}
    </div>
    <div className="dd-stage-foot">
      <div className="dd-legend" aria-label="Map line legend">
        <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" />Computed district boundaries</span>
        {showCounties && <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="county" />Counties</span>}
        {showCities && <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="city" />{cityLabel}</span>}
        {congressional.data && <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="enacted" />Congressional districts</span>}
        {showDerived && <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="derived" />Derived water paths</span>}
        {showRecorded && <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="recorded" /><span aria-hidden="true" className="dd-swatch -ml-1.5" data-kind="exclave" />Recorded water / exclave connections</span>}
      </div>
      {density.data && <DensityLegend />}
      <p role={blocksError ? "alert" : "status"}>{!fine ? "Districts and Counties use simplified boundaries at every zoom. Choose Blocks to zoom closer and inspect census data." : blockBudget?.blocked ? <>Block detail is unavailable for this area. Pan to another area or <button className="underline" onClick={() => chooseInspection("counties")}>inspect counties</button>.</> : blockBudget?.adjusted ? "Preparing a closer view for block inspection…" : blocksError ? <>{blocksError} Previously loaded blocks remain available. <button className="underline" onClick={() => spatialIndexError ? setSummaryRetry((n) => n + 1) : blockCache?.retry()}>Retry block detail</button></> : !spatialIndex ? "Loading the block detail index…" : !candidates.length ? `No ${stateName} blocks intersect this view.` : !blockBatchReady ? `Loading block detail: ${blockSnapshot?.loaded ?? 0} of ${candidates.length} areas ready. Previously loaded blocks remain visible and selectable.` : `${blockFeatures.length.toLocaleString()} blocks loaded for this view. Visible blocks are included across county and district lines; county cards retain whole-county totals.`}</p>
      {errors.length > 0 && <p role="alert" className="text-sm text-destructive">{errors.join(" ")} <button className="underline" onClick={() => { overview.retry(); fullOverview.retry(); coast.retry(); dividers.retry(); detail.retry(); detailDividers.retry(); setSummaryRetry((n) => n + 1); }}>Retry map data</button></p>}
      {counties.error && <p role="alert" className="text-xs text-destructive">{counties.error} <button className="underline" onClick={counties.retry}>Retry counties</button></p>}
      {plan.stateFips === "02" && <p>Alaska keeps a continuous longitude frame across the date line. Islands remain separate; dashed links show the recorded connection policy. Widely scattered island groups open in Blocks on their largest map component; pan to explore the rest.</p>}
    </div>
    </div>
    <span className="sr-only" data-selected-district={districtId ?? ""} data-selected-county={countyFips ?? ""} data-selected-block={chosenBlock ?? ""}>Map selection: {level}</span>
  </section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="mt-0.5 break-words text-sm font-semibold tabular-nums">{value}</dd></div>;
}
