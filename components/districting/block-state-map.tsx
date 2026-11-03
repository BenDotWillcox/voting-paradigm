"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import type { Feature, Geometry } from "geojson";
import type { BlockPlan, BlockDetailIndex, BlockStateComparisonLayers, BlockLandDisplay } from "@/types/block-districting";
import {
  BLOCK_MAP_WIDTH, BLOCK_MAP_HEIGHT, blockCoordinateBounds, blockDistrictColor,
  fetchBlockCollection, formatMapBytes, makeStateBlockProjection,
} from "@/lib/block-map-projection";
import type { BlockMapCollection, BlockMapProjection, BlockMapProperties } from "@/lib/block-map-projection";
import { ComparisonBoundaries, ComparisonLayerControl, DensityCanvas, DensityLegend, useComparisonLayer } from "./block-comparison-layers";
import { loadDerivedConnections, matchingLandDisplay, needsFineBlockDisplay, polygonExteriorStrokeGeometry, selectBlockDisplayAsset } from "@/lib/block-land-display";
import type { DerivedWaterFeature } from "@/lib/block-land-display";
import { createBlockCanvasFrame } from "@/lib/block-canvas-frame";
import { MAP_COLORS } from "@/lib/districts-palette";

type LinkEndpoint = { geoid?: string; coordinate?: number[] };
type LinkFeature = Feature<Geometry, BlockMapProperties>;
type County = BlockDetailIndex["counties"][number];
const EMPTY_LINKS: LinkFeature[] = [];
const EMPTY_DERIVED: DerivedWaterFeature[] = [];

function linkId(feature: LinkFeature) {
  return String(feature.properties.id ?? feature.id ?? "");
}
function linkKind(feature: LinkFeature) {
  return String(feature.properties.kind ?? "recorded-water-connection").includes("exclave") ? "Exclave" : "Water";
}
function focusArea(feature: LinkFeature, alaska: boolean): BlockMapCollection {
  const [west, south, east, north] = blockCoordinateBounds({ type: "FeatureCollection", features: [feature] }, alaska);
  const dx = Math.max((east - west) * 0.6, 0.04), dy = Math.max((north - south) * 0.6, 0.04);
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: {
    type: "Polygon", coordinates: [[[west - dx, south - dy], [east + dx, south - dy],
      [east + dx, north + dy], [west - dx, north + dy], [west - dx, south - dy]]],
  } }] };
}

function CountyCanvas({ data, projection, stateFips, outlinesOnly, clip }: {
  data: BlockMapCollection; projection: BlockMapProjection; stateFips: string; outlinesOnly: boolean; clip?: BlockMapCollection;
}) {
  const ref = React.useRef<HTMLCanvasElement>(null);
  React.useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let frame = 0, generation = 0;
    let activeFrame: ReturnType<typeof createBlockCanvasFrame> = null;
    const draw = () => {
      cancelAnimationFrame(frame);
      activeFrame?.cancel();
      const thisGeneration = ++generation;
      const size = canvas.getBoundingClientRect();
      if (!size.width || !size.height) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(size.width * ratio);
      canvas.height = Math.round(size.height * ratio);
      const drawing = createBlockCanvasFrame(canvas, projection, clip);
      activeFrame = drawing;
      if (!drawing) return;
      const { context } = drawing;
      const path = geoPath(projection, context);
      let cursor = 0;
      const batch = () => {
        if (thisGeneration !== generation) return;
        const end = Math.min(cursor + 700, data.features.length);
        for (; cursor < end; cursor += 1) {
          const feature = data.features[cursor];
          context.beginPath();
          path(feature);
          if (!outlinesOnly) {
            context.fillStyle = blockDistrictColor(Number(feature.properties.district_id), stateFips);
            context.globalAlpha = 0.88;
            context.fill("evenodd");
          }
          context.globalAlpha = 0.3;
          context.strokeStyle = MAP_COLORS.line;
          context.lineWidth = 0.5;
          context.stroke();
        }
        context.globalAlpha = 1;
        if (cursor < data.features.length) frame = requestAnimationFrame(batch);
        else drawing.publish();
      };
      frame = requestAnimationFrame(batch);
    };
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    draw();
    return () => { generation += 1; activeFrame?.cancel(); cancelAnimationFrame(frame); observer.disconnect(); };
  }, [data, projection, stateFips, outlinesOnly, clip]);
  return <canvas ref={ref} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true" />;
}

export interface BlockStateMapProps { plan: BlockPlan; comparisonLayers?: BlockStateComparisonLayers; landDisplay?: BlockLandDisplay }

export function BlockStateMap({ plan, comparisonLayers, landDisplay }: BlockStateMapProps) {
  const [exact, setExact] = React.useState(false);
  const [fullExtent, setFullExtent] = React.useState(false);
  const [fineDetail, setFineDetail] = React.useState(false);
  const [showLinks, setShowLinks] = React.useState(true);
  const [showDerived, setShowDerived] = React.useState(true);
  const [derivedScope, setDerivedScope] = React.useState<"all" | "district">("all");
  const [derived, setDerived] = React.useState<{ key: string; features: DerivedWaterFeature[] } | null>(null);
  const [derivedError, setDerivedError] = React.useState<string | null>(null);
  const [derivedRetry, setDerivedRetry] = React.useState(0);
  const [selectedDerived, setSelectedDerived] = React.useState("");
  const [outline, setOutline] = React.useState<{ key: string; data: BlockMapCollection } | null>(null);
  const [details, setDetails] = React.useState<{ key: string; index: BlockDetailIndex; links: BlockMapCollection | null } | null>(null);
  const [outlineError, setOutlineError] = React.useState<string | null>(null);
  const [detailError, setDetailError] = React.useState<string | null>(null);
  const [retry, setRetry] = React.useState(0);
  const [countyFips, setCountyFips] = React.useState("");
  const [county, setCounty] = React.useState<{ planId: string; meta: County; data: BlockMapCollection } | null>(null);
  const [countyLoading, setCountyLoading] = React.useState(false);
  const [countyError, setCountyError] = React.useState<string | null>(null);
  const [selectedLink, setSelectedLink] = React.useState("");
  const [focus, setFocus] = React.useState<"state" | "county" | "connection" | "derived">("state");
  const [district, setDistrict] = React.useState<number | null>(null);
  const [showDensity, setShowDensity] = React.useState(false);
  const [showCounties, setShowCounties] = React.useState(false);
  const [showCongress, setShowCongress] = React.useState(false);
  const [densityOpacity, setDensityOpacity] = React.useState(0.9);
  const [countyOpacity, setCountyOpacity] = React.useState(0.65);
  const [congressOpacity, setCongressOpacity] = React.useState(0.9);
  const density = useComparisonLayer(plan.stateFips, "density", comparisonLayers?.density, showDensity);
  const counties = useComparisonLayer(plan.stateFips, "counties", comparisonLayers?.counties, showCounties);
  const congressional = useComparisonLayer(plan.stateFips, "congressional", comparisonLayers?.congressional, showCongress);
  const countyRequest = React.useRef<AbortController | null>(null);
  const countyGeneration = React.useRef(0);
  const availableLand = matchingLandDisplay(plan, landDisplay);
  const automaticFineDetail = needsFineBlockDisplay(false, focus, county?.planId === plan.id);
  const showFineDetail = fineDetail || automaticFineDetail;
  const { asset, landFocused } = selectBlockDisplayAsset(plan, availableLand, fullExtent, exact, showFineDetail);
  const outlineKey = `${plan.id}:${asset.url}`;
  const connectionsUrl = plan.assets.connections?.url;
  const derivedKey = availableLand ? `${plan.id}:${availableLand.connections.url}` : "";

  React.useEffect(() => {
    setExact(false); setFineDetail(false); setShowLinks(true); setCountyFips(""); setCounty(null);
    setCountyError(null); setCountyLoading(false); setSelectedLink(""); setFocus("state"); setDistrict(null);
    setSelectedDerived(""); setDerivedScope("all"); setDerivedError(null);
    countyGeneration.current += 1;
    countyRequest.current?.abort();
    return () => { countyGeneration.current += 1; countyRequest.current?.abort(); };
  }, [plan.id]);

  React.useEffect(() => {
    const abort = new AbortController();
    let current = true;
    setOutline(null); setOutlineError(null);
    fetchBlockCollection(asset.url, abort.signal).then((data) => {
      if (current) setOutline({ key: outlineKey, data });
    }).catch((cause: unknown) => {
      if (current && !abort.signal.aborted) setOutlineError(cause instanceof Error ? cause.message : "Unable to load district outlines.");
    });
    return () => { current = false; abort.abort(); };
  }, [outlineKey, asset.url, retry]);

  React.useEffect(() => {
    const abort = new AbortController();
    let current = true;
    setDetails(null); setDetailError(null);
    const index = fetch(plan.assets.detailIndex.url, { signal: abort.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`County index request failed (${response.status}).`);
      const value = await response.json() as BlockDetailIndex;
      if (value.planId !== plan.id || !Array.isArray(value.counties)) throw new Error("County index does not match the selected plan.");
      return value;
    });
    const links = connectionsUrl ? fetchBlockCollection(connectionsUrl, abort.signal) : Promise.resolve(null);
    Promise.all([index, links]).then(([index, links]) => {
      if (!current) return;
      setDetails({ key: plan.id, index, links });
      setSelectedLink(links?.features[0] ? linkId(links.features[0]) : "");
    }).catch((cause: unknown) => {
      if (current && !abort.signal.aborted) setDetailError(cause instanceof Error ? cause.message : "Unable to load map detail index.");
    });
    return () => { current = false; abort.abort(); };
  }, [plan.id, plan.assets.detailIndex.url, connectionsUrl, retry]);

  React.useEffect(() => {
    if (!availableLand || !showDerived || derived?.key === derivedKey) return;
    const abort = new AbortController();
    let current = true;
    setDerivedError(null);
    loadDerivedConnections(plan, availableLand, abort.signal).then((features) => {
      if (!current || abort.signal.aborted) return;
      setDerived({ key: derivedKey, features });
      setSelectedDerived(features[0]?.properties.id ?? "");
    }).catch((cause: unknown) => {
      if (current && !abort.signal.aborted) setDerivedError(cause instanceof Error ? cause.message : "Unable to load derived water connections.");
    });
    return () => { current = false; abort.abort(); };
  }, [availableLand, plan, showDerived, derivedKey, derivedRetry, derived?.key]);

  const data = outline?.key === outlineKey ? outline.data : null;
  const detail = details?.key === plan.id ? details : null;
  const activeCounty = county?.planId === plan.id ? county : null;
  const links = detail?.links?.features ?? EMPTY_LINKS;
  const activeLink = links.find((feature) => linkId(feature) === selectedLink) ?? null;
  const derivedLinks = derived?.key === derivedKey ? derived.features : EMPTY_DERIVED;
  const activeDerived = derivedLinks.find((feature) => feature.properties.id === selectedDerived) ?? null;
  const projection = React.useMemo(() => {
    if (!data) return null;
    const target = focus === "county" && activeCounty ? activeCounty.data
      : focus === "connection" && activeLink ? focusArea(activeLink, plan.stateFips === "02")
        : focus === "derived" && activeDerived ? focusArea(activeDerived, plan.stateFips === "02") : data;
    return makeStateBlockProjection(target, plan.stateFips);
  }, [data, focus, activeCounty, activeLink, activeDerived, plan.stateFips]);
  const paths = React.useMemo(() => {
    if (!data || !projection) return [];
    const path = geoPath(projection);
    return data.features.map((feature) => {
      const d = path(feature) ?? "";
      const exterior = landFocused ? polygonExteriorStrokeGeometry(feature.geometry) : null;
      return { feature, id: Number(feature.properties.district_id), d,
        strokeD: landFocused ? (exterior ? path(exterior) ?? "" : "") : d };
    });
  }, [data, projection, landFocused]);
  const connectionPaths = React.useMemo(() => {
    if (!projection) return [];
    const path = geoPath(projection);
    return links.map((feature) => ({ feature, id: linkId(feature), d: path(feature) ?? "" }));
  }, [links, projection]);
  const derivedPaths = React.useMemo(() => {
    if (!projection) return [];
    const path = geoPath(projection);
    return derivedLinks.filter((feature) => derivedScope === "all" || feature.properties.district_id === district)
      .map((feature) => ({ feature, id: feature.properties.id, d: path(feature) ?? "" }));
  }, [derivedLinks, projection, derivedScope, district]);
  const chosenCounty = detail?.index.counties.find((value) => value.fips === countyFips);

  async function loadCounty() {
    if (!chosenCounty) return;
    countyRequest.current?.abort();
    const abort = new AbortController();
    countyRequest.current = abort;
    const generation = ++countyGeneration.current;
    const requestedPlan = plan.id;
    setCounty(null); setCountyLoading(true); setCountyError(null);
    try {
      const collection = await fetchBlockCollection(chosenCounty.asset.url, abort.signal);
      if (abort.signal.aborted || generation !== countyGeneration.current) return;
      setCounty({ planId: requestedPlan, meta: chosenCounty, data: collection });
      setFocus("county");
    } catch (cause: unknown) {
      if (!abort.signal.aborted && generation === countyGeneration.current) setCountyError(cause instanceof Error ? cause.message : "Unable to load county blocks.");
    } finally {
      if (generation === countyGeneration.current) setCountyLoading(false);
    }
  }

  return (
    <section className="space-y-4" aria-label={`${plan.stateName} census-block map`}>
      <fieldset className="space-y-3 rounded-xl border bg-muted/20 p-4">
        <legend className="px-1 text-sm font-semibold">Comparison layers</legend>
        <p className="text-xs text-muted-foreground">Add geographic context beneath our district outlines. Each reference loads only when enabled.</p>
        <div className="grid gap-3 md:grid-cols-3">
          <ComparisonLayerControl kind="density" layer={comparisonLayers?.density} enabled={showDensity} onEnabled={setShowDensity} opacity={densityOpacity} onOpacity={setDensityOpacity} state={density} />
          <ComparisonLayerControl kind="counties" layer={comparisonLayers?.counties} enabled={showCounties} onEnabled={setShowCounties} opacity={countyOpacity} onOpacity={setCountyOpacity} state={counties} />
          <ComparisonLayerControl kind="congressional" layer={comparisonLayers?.congressional} enabled={showCongress} onEnabled={setShowCongress} opacity={congressOpacity} onOpacity={setCongressOpacity} state={congressional} />
        </div>
        {comparisonLayers && <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Reference sources and interpretation</summary>
          <div className="mt-2 space-y-2 leading-5">
            {Object.entries(comparisonLayers).map(([kind, layer]) => <p key={kind}><a className="underline underline-offset-2" href={layer.sourceUrl} target="_blank" rel="noreferrer">{layer.label}</a> · {layer.vintage}. {layer.description}</p>)}
            <p>The congressional reference is the serving 119th Congress (2025–2026), with 435 districts nationally. It provides geographic context at every House size; it is not a district-for-district population comparison. Reference coastlines are simplified independently of our block boundaries.</p>
          </div>
        </details>}
      </fieldset>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-4 text-sm">
          {availableLand && <label className="flex items-center gap-2"><input type="checkbox" checked={fullExtent} onChange={(event) => { setFullExtent(event.target.checked); setExact(false); setFocus("state"); }} />Full census extent</label>}
          {landFocused && <label className="flex items-center gap-2"><input type="checkbox" checked={showFineDetail} disabled={automaticFineDetail} onChange={(event) => setFineDetail(event.target.checked)} />Fine boundary detail</label>}
          <label className={`flex items-center gap-2 ${landFocused ? "text-muted-foreground" : ""}`}><input type="checkbox" checked={!landFocused && exact} disabled={landFocused} onChange={(event) => setExact(event.target.checked)} />Exact district outlines</label>
          {availableLand && <label className="flex items-center gap-2"><input type="checkbox" checked={showDerived} onChange={(event) => setShowDerived(event.target.checked)} />Derived water connections</label>}
          {plan.assets.connections && <label className="flex items-center gap-2"><input type="checkbox" checked={showLinks} onChange={(event) => setShowLinks(event.target.checked)} />Recorded connections</label>}
        </div>
        <button type="button" onClick={() => setFocus("state")} disabled={focus === "state"} className="rounded border px-3 py-1.5 text-xs disabled:opacity-40">Show whole state</button>
      </div>
      {availableLand && <p className="text-xs leading-5 text-muted-foreground">{landFocused ? "Land-focused boundaries hide water-only census blocks; blocks with both land and water remain visible. This is a display change, not an exact shoreline." : "Full census extent includes water-only blocks. Enable exact outlines to inspect their unsimplified boundaries."} All saved assignments and population totals remain unchanged, including {availableLand.summary.zeroLandPopulation.toLocaleString()} residents in water-only blocks.</p>}
      {landFocused && <p className="text-xs leading-5 text-muted-foreground">Overview boundaries are generalized for clarity. County and connection inspection automatically restore finer edges{automaticFineDetail ? " (active now)" : ""}; block assignments stay unchanged.</p>}
      <div className="relative aspect-[1000/620] overflow-hidden rounded-xl bg-white ring-1 ring-[var(--dd-steel)]"
        data-boundary-detail={landFocused ? showFineDetail ? "fine" : "overview" : exact ? "exact" : "standard"}>
        {!data && <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-muted-foreground" role={outlineError ? "alert" : "status"}>
          {outlineError ? <div>{outlineError}<button type="button" onClick={() => setRetry((value) => value + 1)} className="ml-3 rounded border px-3 py-1">Retry map</button></div>
            : `Loading ${landFocused ? showFineDetail ? "fine land-focused" : "smooth overview" : exact ? "exact" : "state"} district outlines…`}
        </div>}
        {data && projection && <>
          <svg viewBox={`0 0 ${BLOCK_MAP_WIDTH} ${BLOCK_MAP_HEIGHT}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
            {paths.map(({ id, d }) => <path key={id} d={d} fill={density.data ? MAP_COLORS.neutralLand : blockDistrictColor(id, plan.stateFips)} fillRule="evenodd" fillOpacity={density.data ? 1 : activeCounty ? 0.12 : 0.88} />)}
          </svg>
          {density.data && <DensityCanvas data={density.data} projection={projection} opacity={densityOpacity} clip={landFocused ? data : undefined} />}
          {activeCounty && <CountyCanvas data={activeCounty.data} projection={projection} stateFips={plan.stateFips} outlinesOnly={!!density.data} clip={landFocused ? data : undefined} />}
          <svg viewBox={`0 0 ${BLOCK_MAP_WIDTH} ${BLOCK_MAP_HEIGHT}`} className="absolute inset-0 h-full w-full" aria-label={`${plan.stateName}, ${plan.districtCount} districts${activeCounty ? ` with county ${activeCounty.meta.fips} block detail` : ""}`}>
            {counties.data && <ComparisonBoundaries data={counties.data} projection={projection} kind="counties" opacity={countyOpacity} />}
            {congressional.data && <ComparisonBoundaries data={congressional.data} projection={projection} kind="congressional" opacity={congressOpacity} />}
            <g pointerEvents="none" aria-hidden="true" data-map-layer="computed-district-halos">
              {paths.map(({ id, strokeD }) => <path key={id} d={strokeD} fill="none" stroke={district === id ? MAP_COLORS.selectionCasing : MAP_COLORS.casing} strokeWidth={district === id ? 4.4 : 2.75} vectorEffect="non-scaling-stroke" />)}
            </g>
            {paths.map(({ feature, id, d }) => <path key={id} d={d} fill="transparent" fillRule="evenodd" data-map-layer="computed-district"
              stroke={landFocused ? "none" : district === id ? MAP_COLORS.selection : MAP_COLORS.line} strokeWidth={district === id ? 2 : 0.9}
              vectorEffect="non-scaling-stroke" role="button" tabIndex={0} className="cursor-pointer outline-none"
              aria-label={`District ${id + 1}, ${Number(feature.properties.population).toLocaleString()} residents`}
              onClick={() => setDistrict(id)} onFocus={() => setDistrict(id)} onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setDistrict(id); }
              }}><title>District {id + 1}: {Number(feature.properties.population).toLocaleString()} residents</title></path>)}
            {landFocused && <g pointerEvents="none" aria-hidden="true" data-map-layer="computed-district-exterior-strokes">
              {paths.map(({ id, strokeD }) => <path key={id} d={strokeD} fill="none" stroke={district === id ? MAP_COLORS.selection : MAP_COLORS.line}
                strokeWidth={district === id ? 2 : 0.9} vectorEffect="non-scaling-stroke" />)}
            </g>}
            {showDerived && derivedPaths.map(({ feature, id, d }) => <g key={id} data-map-layer="derived-water-connection">
              <path d={d} fill="none" stroke={MAP_COLORS.casing} strokeWidth={selectedDerived === id ? 4 : 2.5} vectorEffect="non-scaling-stroke" pointerEvents="none" />
              <path d={d} fill="none" stroke={MAP_COLORS.derivedWater} strokeOpacity={selectedDerived === id ? 1 : 0.7} strokeWidth={selectedDerived === id ? 2 : 0.8}
                strokeDasharray="3 5" vectorEffect="non-scaling-stroke" role="button" tabIndex={0} className="cursor-pointer outline-none"
                aria-label={`Derived water connection ${id}, District ${feature.properties.district_id + 1}`}
                onClick={() => { setSelectedDerived(id); setDistrict(feature.properties.district_id); }} onFocus={() => setSelectedDerived(id)} onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedDerived(id); setDistrict(feature.properties.district_id); }
                }}><title>Derived from saved water-block adjacency · District {feature.properties.district_id + 1} · {feature.properties.water_block_count} water-only blocks</title></path>
              {selectedDerived === id && feature.properties.endpoints.map((endpoint, index) => {
                const point = projection.projectPoint(endpoint.coordinate);
                return <circle key={index} cx={point[0]} cy={point[1]} r="3" fill={MAP_COLORS.derivedWater} stroke={MAP_COLORS.casing} strokeWidth="1" pointerEvents="none" />;
              })}
            </g>)}
            {showLinks && connectionPaths.map(({ feature, id, d }) => <g key={id} data-map-layer="recorded-connection">
              <path d={d} fill="none" stroke={MAP_COLORS.casing} strokeWidth="6" vectorEffect="non-scaling-stroke" pointerEvents="none" />
              <path d={d} fill="none" stroke={linkKind(feature) === "Exclave" ? MAP_COLORS.recordedExclave : MAP_COLORS.recordedWater} strokeWidth={selectedLink === id ? 3 : 2}
                strokeDasharray={linkKind(feature) === "Exclave" ? "3 5" : "8 5"} vectorEffect="non-scaling-stroke" role="button" tabIndex={0}
                className="cursor-pointer outline-none" aria-label={`${linkKind(feature)} connection ${id}`}
                onClick={() => setSelectedLink(id)} onFocus={() => setSelectedLink(id)} onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedLink(id); }
                }}><title>{linkKind(feature)} connection {id}</title></path>
              {(feature.properties.endpoints as LinkEndpoint[] | undefined)?.map((endpoint, index) => {
                if (!endpoint.coordinate) return null;
                const point = projection.projectPoint(endpoint.coordinate);
                return <circle key={index} cx={point[0]} cy={point[1]} r="3" fill={MAP_COLORS.casing} stroke={MAP_COLORS.line} strokeWidth="1" pointerEvents="none" />;
              })}
            </g>)}
          </svg>
        </>}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2 rounded-md border bg-card px-3 py-2 text-xs" aria-label="Map line legend">
        <span><span className="mr-2 inline-block w-6 border-t border-[#454545] align-middle" />Our computed districts · solid</span>
        {counties.data && <span><span className="mr-2 inline-block w-6 border-t-2 border-dotted border-[#454545] align-middle" />2020 counties · dotted</span>}
        {congressional.data && <span><span className="mr-2 inline-block w-6 border-t-2 border-dashed border-[#454545] align-middle" />119th Congress · dashed</span>}
        {showDerived && availableLand && <span><span className="mr-2 inline-block w-6 border-t border-dashed border-[var(--dd-map-derived)] align-middle" />Derived water connections · teal dashes</span>}
        {showLinks && plan.assets.connections && <span><span className="mr-2 inline-block w-6 border-t-2 border-dashed border-[var(--dd-map-recorded)] align-middle" />Recorded connections · drawn above all layers</span>}
      </div>
      {density.data && <DensityLegend />}
      <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
        <p aria-live="polite">{district !== null ? `District ${district + 1}: ${plan.districtPopulations[district]?.toLocaleString()} residents` : "Select a district to inspect its population."}</p>
        <p>{landFocused ? showFineDetail ? "Fine boundary detail · land-focused" : "Smooth overview · land-focused" : exact ? "Unsimplified source boundaries" : "Simplified display boundaries"} · {formatMapBytes(asset.gzipBytes)} compressed</p>
      </div>
      {plan.stateFips === "02" && <p className="text-xs text-muted-foreground">Alaska uses a continuous longitude frame across the date line. Islands stay separate; dashed connections express the recorded policy.</p>}

      {availableLand && <div className="space-y-3 rounded-lg border border-[var(--dd-steel)] bg-[var(--dd-board-soft)] p-4">
        <h3 className="text-sm font-medium">Derived water connections</h3>
        <p className="text-xs leading-5 text-muted-foreground">Cyan dashes illustrate paths through water-only blocks already assigned to the same district. They add no policy edges and do not claim land contiguity, bridges, or travel routes. Recorded policy connections remain separate ({plan.recordedLinkCount} for this plan).</p>
        <p className="text-xs text-muted-foreground">{availableLand.summary.derivedConnectionCount.toLocaleString()} derived connections · {availableLand.summary.zeroLandBlockCount.toLocaleString()} water-only blocks · {availableLand.summary.zeroLandPopulation.toLocaleString()} residents retained in the saved totals.</p>
        {derivedError && <p role="alert" className="text-xs text-destructive">{derivedError} <button type="button" onClick={() => { setShowDerived(true); setDerivedRetry((value) => value + 1); }} className="underline">Retry derived connections</button></p>}
        {showDerived && !derivedError && derived?.key !== derivedKey && <p role="status" className="text-xs text-muted-foreground">Loading saved water-block paths…</p>}
        {derivedLinks.length > 0 && <>
          <div className="flex flex-wrap gap-2">
            <label className="text-xs"><span className="sr-only">Visible derived connections</span><select value={derivedScope} onChange={(event) => setDerivedScope(event.target.value as "all" | "district")} className="h-full rounded-md border bg-background px-3 py-2">
              <option value="all">All derived connections</option><option value="district">Selected district only</option>
            </select></label>
            <label className="min-w-0 flex-1"><span className="sr-only">Choose a derived connection</span><select value={selectedDerived} onChange={(event) => {
              setSelectedDerived(event.target.value);
              const feature = derivedLinks.find((value) => value.properties.id === event.target.value);
              if (feature) setDistrict(feature.properties.district_id);
              if (focus === "derived") setFocus("state");
            }} className="w-full rounded-md border bg-background px-3 py-2 text-sm">
              {derivedLinks.map((feature) => <option key={feature.properties.id} value={feature.properties.id}>District {feature.properties.district_id + 1} · {feature.properties.id} · {feature.properties.water_block_count} water blocks</option>)}
            </select></label>
            <button type="button" disabled={!activeDerived} onClick={() => { setShowDerived(true); if (activeDerived) setDistrict(activeDerived.properties.district_id); setFocus("derived"); }} className="rounded-md border px-3 py-2 text-sm disabled:opacity-40">Inspect derived connection</button>
          </div>
          {derivedScope === "district" && district === null && <p className="text-xs text-muted-foreground">Select a district or a derived connection to show its paths.</p>}
          {activeDerived && <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Saved block-path evidence · District {activeDerived.properties.district_id + 1}</summary><div className="mt-2 space-y-1 break-all leading-5">
            <p>Land-bearing endpoint blocks: {activeDerived.properties.endpoints.map((endpoint) => endpoint.geoid).join(" ↔ ")}</p>
            <p>Saved path: {activeDerived.properties.block_path.join(" → ")}</p>
          </div></details>}
        </>}
      </div>}

      {plan.assets.connections && <div className="space-y-3 rounded-lg border border-[var(--dd-steel)] bg-[var(--dd-board-soft)] p-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-medium">Recorded connections</span>
          <span className="text-xs text-muted-foreground"><span className="mr-1 text-[var(--dd-map-recorded)]">┄┄</span>Water <span className="ml-3 mr-1 text-[var(--dd-map-exclave)]">┄┄</span>Exclave</span>
        </div>
        <p className="text-xs text-muted-foreground">These lines add policy connections. They do not add land, bridges, or travel routes. Physical polygon connectivity is reported separately.</p>
        {links.length > 0 && <>
          <div className="flex flex-wrap gap-2">
            <label className="min-w-0 flex-1"><span className="sr-only">Choose a recorded connection</span><select value={selectedLink} onChange={(event) => { setSelectedLink(event.target.value); if (focus === "connection") setFocus("state"); }} className="w-full rounded-md border bg-background px-3 py-2 text-sm">
              {links.map((feature) => <option key={linkId(feature)} value={linkId(feature)}>{linkKind(feature)} · {linkId(feature)} · {(Number(feature.properties.distance_m) / 1000).toFixed(2)} km</option>)}
            </select></label>
            <button type="button" onClick={() => { setShowLinks(true); setFocus("connection"); }} className="rounded-md border px-3 py-2 text-sm">Inspect connection</button>
          </div>
          {activeLink && <div className="text-xs text-muted-foreground">
            <p>Endpoint blocks: {((activeLink.properties.endpoints as LinkEndpoint[]) ?? []).map((endpoint) => endpoint.geoid).join(" ↔ ")}</p>
            <p>{activeLink.properties.used_by_district === null || activeLink.properties.used_by_district === undefined ? "Endpoints are in different districts; this link does not contribute to district connectivity." : `Both endpoint blocks belong to District ${Number(activeLink.properties.used_by_district) + 1}.`}</p>
          </div>}
        </>}
      </div>}

      <div className="space-y-3 rounded-lg border p-4">
        <div><h3 className="text-sm font-medium">Inspect census blocks</h3><p className="mt-1 text-xs text-muted-foreground">Choose one county to load its blocks. Density uses a tract overview; individual blocks remain on demand.{density.data ? " Loaded block boundaries overlay the density background." : ""}{landFocused ? " Block and density layers are clipped to the land-focused display; full census extent reveals the saved water geometry." : ""}</p></div>
        {detailError && <p role="alert" className="text-sm text-destructive">{detailError} <button type="button" className="underline" onClick={() => setRetry((value) => value + 1)}>Retry details</button></p>}
        <div className="flex flex-wrap gap-2">
          <label className="min-w-0 flex-1"><span className="sr-only">County for block detail</span><select value={countyFips} disabled={!detail} onChange={(event) => {
            setCountyFips(event.target.value); setCounty(null); setFocus("state"); setCountyError(null); setCountyLoading(false);
            countyGeneration.current += 1; countyRequest.current?.abort();
          }} className="w-full rounded-md border bg-background px-3 py-2 text-sm">
            <option value="">{detail ? "Choose a county" : "Loading county index…"}</option>
            {detail?.index.counties.map((value) => <option key={value.fips} value={value.fips}>County {value.fips} · {value.blockCount.toLocaleString()} blocks · {formatMapBytes(value.asset.gzipBytes)}</option>)}
          </select></label>
          <button type="button" disabled={!chosenCounty || countyLoading} onClick={loadCounty} className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-40">{countyLoading ? "Loading blocks…" : "Load blocks"}</button>
          {activeCounty && <button type="button" className="rounded-md border px-3 py-2 text-sm" onClick={() => { setCounty(null); setFocus("state"); }}>Clear blocks</button>}
        </div>
        {countyError && <p role="alert" className="text-sm text-destructive">{countyError}</p>}
        <p className="text-xs text-muted-foreground" role="status">{activeCounty ? `County ${activeCounty.meta.fips}: ${activeCounty.meta.blockCount.toLocaleString()} blocks, ${activeCounty.meta.population.toLocaleString()} residents. One county is retained in memory.`
          : countyLoading ? "Loading the selected county; the other counties remain unloaded." : "No census-block detail loaded."}</p>
      </div>
    </section>
  );
}
