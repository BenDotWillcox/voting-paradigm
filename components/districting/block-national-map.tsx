"use client";

import * as React from "react";
import type { BlockPlanManifest } from "@/types/block-districting";
import {
  BLOCK_MAP_WIDTH, BLOCK_NATIONAL_HEIGHT, BLOCK_MAP_INSETS,
  fetchBlockCollection, formatMapBytes,
} from "@/lib/block-map-projection";
import type { BlockMapCollection } from "@/lib/block-map-projection";
import { nationalLandView, validateMichiganNationalLayers, validateNationalLandLayers } from "@/lib/block-national-land-display";
import type { NationalLandState } from "@/lib/block-national-land-display";
import { matchingLandDisplay, validateDerivedConnections } from "@/lib/block-land-display";
import { MAP_COLORS } from "@/lib/districts-palette";
import { getStateByFips } from "@/lib/us-states";
import { getPreparedNationalMap, nationalPreparedKey, prepareNationalMap } from "@/lib/block-national-render";
import type { NationalPreparedMap, NationalStatePaths } from "@/lib/block-national-render";

const NORTHEAST_SHORTCUTS = new Map(
  ["50", "33", "25", "44", "09", "34", "10", "24"].map((fips, index) => [fips, {
    label: getStateByFips(fips)!.abbr,
    x: 888 + (index % 2) * 52,
    y: 214 + Math.floor(index / 2) * 48,
  }] as const)
);

// Only two national anchors are retained. County/block payloads never enter
// this cache and are never requested by the overview.
const nationalCache = new Map<string, BlockMapCollection>();
const stateBoundaryCache = new Map<string, BlockMapCollection>();
type LandOverview = { states: Map<string, NationalLandState> };
const landOverviewCache = new Map<string, LandOverview>();
function rememberNational(url: string, data: BlockMapCollection) {
  nationalCache.delete(url);
  nationalCache.set(url, data);
  while (nationalCache.size > 2) nationalCache.delete(nationalCache.keys().next().value!);
}

export interface BlockNationalMapProps {
  manifest: BlockPlanManifest;
  houseSize: number;
  selectedStateFips?: string | null;
  onSelectState: (stateFips: string) => void;
  navigation?: React.ReactNode;
  heading?: React.ReactNode;
}

export function BlockNationalMap({ manifest, houseSize, selectedStateFips, onSelectState, navigation, heading }: BlockNationalMapProps) {
  const anchor = manifest.anchors.find((value) => value.houseSize === houseSize);
  const asset = anchor?.national;
  const assetUrl = asset?.url;
  const boundaryUrl = manifest.stateOutlines?.url;
  const nationalLand = manifest.nationalLandAnchors?.[String(houseSize)] ?? manifest.landAnchors?.[String(houseSize)];
  const michiganPlanId = anchor?.planIds.find((id) => manifest.plans[id]?.stateFips === "26");
  const landDisplay = michiganPlanId
    ? matchingLandDisplay(manifest.plans[michiganPlanId], manifest.landDisplays?.[michiganPlanId]) : undefined;
  const cleanDisplay = michiganPlanId
    ? manifest.stateExplorers?.["26"]?.plans[michiganPlanId] ?? manifest.michiganExplorer?.plans[michiganPlanId]
    : undefined;
  const [fullExtent, setFullExtent] = React.useState(false);
  const landAvailable = !!nationalLand || (!!landDisplay && !!cleanDisplay);
  const landMode = landAvailable && !fullExtent;
  const landUrl = cleanDisplay?.overview.url;
  const landCoastUrl = cleanDisplay?.coast.url;
  const landDividersUrl = cleanDisplay?.dividers.url;
  const landConnectionsUrl = landDisplay?.connections.url;
  const landKey = nationalLand
    ? JSON.stringify([houseSize, nationalLand.planIds, nationalLand.outlines.url, nationalLand.coast.url,
      nationalLand.dividers.url, nationalLand.connections.url, nationalLand.recordedConnections?.url])
    : `${michiganPlanId}:${landUrl}:${landCoastUrl}:${landDividersUrl}:${landConnectionsUrl}`;
  const [land, setLand] = React.useState<{ key: string; data: LandOverview } | null>(null);
  const [landError, setLandError] = React.useState<string | null>(null);
  const [loaded, setLoaded] = React.useState<{ url: string; data: BlockMapCollection } | null>(null);
  const [boundaries, setBoundaries] = React.useState<{ url: string; data: BlockMapCollection } | null>(null);
  const [boundaryError, setBoundaryError] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [retry, setRetry] = React.useState(0);
  const [hovered, setHovered] = React.useState<string | null>(null);
  const [focused, setFocused] = React.useState<string | null>(null);
  const highlightState = React.useCallback((state: string) => setHovered(state), []);
  const clearHighlight = React.useCallback(() => setHovered(null), []);
  const focusState = React.useCallback((state: string) => setFocused(state), []);
  const clearFocus = React.useCallback(() => setFocused(null), []);
  const selectState = React.useCallback((state: string) => onSelectState(state), [onSelectState]);

  React.useEffect(() => {
    if (!assetUrl) return;
    const abort = new AbortController();
    let current = true;
    setError(null);
    const cached = nationalCache.get(assetUrl);
    if (cached) {
      setLoaded({ url: assetUrl, data: cached });
      return () => { current = false; abort.abort(); };
    }
    setLoaded(null);
    fetchBlockCollection(assetUrl, abort.signal).then((data) => {
      if (!current) return;
      rememberNational(assetUrl, data);
      setLoaded({ url: assetUrl, data });
    }).catch((cause: unknown) => {
      if (current && !abort.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load the national map.");
    });
    return () => { current = false; abort.abort(); };
  }, [assetUrl, retry]); // A stale response can never replace another anchor.

  React.useEffect(() => {
    if (!boundaryUrl) return;
    const abort = new AbortController();
    let current = true;
    setBoundaryError(null);
    const cached = stateBoundaryCache.get(boundaryUrl);
    if (cached) {
      setBoundaries({ url: boundaryUrl, data: cached });
      return () => { current = false; abort.abort(); };
    }
    setBoundaries(null);
    fetchBlockCollection(boundaryUrl, abort.signal).then((data) => {
      if (!current) return;
      stateBoundaryCache.clear();
      stateBoundaryCache.set(boundaryUrl, data);
      setBoundaries({ url: boundaryUrl, data });
    }).catch((cause: unknown) => {
      if (current && !abort.signal.aborted) setBoundaryError(cause instanceof Error ? cause.message : "Unable to load state borders.");
    });
    return () => { current = false; abort.abort(); };
  }, [boundaryUrl, retry]);

  React.useEffect(() => {
    if (!landMode || !anchor) return;
    const abort = new AbortController();
    let current = true;
    setLandError(null);
    const cached = landOverviewCache.get(landKey);
    if (cached) {
      setLand({ key: landKey, data: cached });
      return () => { current = false; abort.abort(); };
    }
    const loadLand = async (): Promise<LandOverview> => {
      if (nationalLand) {
        const [outlines, coast, dividers, connections, recordedConnections] = await Promise.all([
          nationalLand.outlines, nationalLand.coast, nationalLand.dividers, nationalLand.connections,
          nationalLand.recordedConnections,
        ].map((asset) => asset ? fetchBlockCollection(asset.url, abort.signal) : undefined));
        return { states: validateNationalLandLayers({ outlines: outlines!, coast: coast!, dividers: dividers!,
          connections: connections!, recordedConnections }, nationalLand, anchor, manifest.plans, manifest.landDisplays ?? {}) };
      }
      if (!landUrl || !landCoastUrl || !landDividersUrl || !landConnectionsUrl || !michiganPlanId || !landDisplay) {
        throw new Error("The selected land-focused map is incomplete.");
      }
      const [outlines, coast, dividers, connections] = await Promise.all(
        [landUrl, landCoastUrl, landDividersUrl, landConnectionsUrl].map((url) => fetchBlockCollection(url, abort.signal)));
      const plan = manifest.plans[michiganPlanId];
      const shoreline = validateMichiganNationalLayers(outlines, coast, dividers, plan);
      validateDerivedConnections(connections, plan, landDisplay.summary.derivedConnectionCount);
      return { states: new Map([["26", { plan, outlines, ...shoreline, dividers, connections,
        recordedConnections: { type: "FeatureCollection", features: [] } }]]) };
    };
    loadLand().then((value) => {
        if (!current) return;
        landOverviewCache.set(landKey, value);
        while (landOverviewCache.size > 2) landOverviewCache.delete(landOverviewCache.keys().next().value!);
        setLand({ key: landKey, data: value });
      }).catch((cause: unknown) => {
        if (current && !abort.signal.aborted) setLandError(cause instanceof Error ? cause.message : "Unable to load the land-focused map.");
      });
    return () => { current = false; abort.abort(); };
  }, [landMode, landUrl, landCoastUrl, landDividersUrl, landConnectionsUrl, landKey, retry, manifest.plans,
    manifest.landDisplays, michiganPlanId, landDisplay, nationalLand, anchor]);

  const census = loaded && loaded.url === asset?.url ? loaded.data : null;
  const activeLand = landMode && land?.key === landKey ? land.data : null;
  const combined = React.useMemo(() => {
    if (!census || (landMode && !activeLand)) return { data: null, error: null };
    try { return { data: activeLand ? nationalLandView(census, activeLand.states) : census, error: null }; }
    catch (cause) { return { data: null, error: cause instanceof Error ? cause.message : "Invalid land-focused display." }; }
  }, [census, landMode, activeLand]);
  const data = combined.data;
  const currentBoundaries = boundaries && boundaries.url === boundaryUrl ? boundaries.data : undefined;
  const preparedKey = nationalPreparedKey(houseSize, landMode ? "land" : "census", [asset, manifest.stateOutlines,
    ...(landMode ? nationalLand
      ? [nationalLand.outlines, nationalLand.coast, nationalLand.dividers, nationalLand.connections, nationalLand.recordedConnections]
      : [cleanDisplay?.overview, cleanDisplay?.coast, cleanDisplay?.dividers, landDisplay?.connections] : [])],
  anchor?.planIds.map((id) => manifest.plans[id]) ?? []);
  const prepared = React.useMemo(() => {
    if (!data || (boundaryUrl && !currentBoundaries && !boundaryError)) return { value: null, error: null };
    try {
      const factory = () => prepareNationalMap(data, currentBoundaries, activeLand?.states);
      // A failed border request may still show districts, but its incomplete
      // preparation must not displace a complete cached map.
      const value = boundaryUrl && !currentBoundaries ? { map: factory(), cacheHit: false }
        : getPreparedNationalMap(preparedKey, factory);
      return { value, error: null };
    } catch (cause) {
      return { value: null, error: cause instanceof Error ? cause.message : "Unable to prepare the national map." };
    }
  }, [data, currentBoundaries, boundaryUrl, boundaryError, activeLand, preparedKey]);
  const map = prepared.value?.map;
  const displayError = error ?? (landMode ? landError : null) ?? combined.error ?? prepared.error;
  const activeState = hovered ?? focused ?? selectedStateFips;
  const active = map?.states.find((group) => group.fips === activeState);

  if (!asset) return <p role="alert">This House size has no validated national map.</p>;

  return (
    <section aria-label="National census-block district map" className="dd-instrument"
      data-national-prepared-cache={prepared.value ? prepared.value.cacheHit ? "hit" : "miss" : "pending"}
      data-national-path-count={map?.pathCount} data-national-prepared-bytes={map?.estimatedBytes}>
      <div className="dd-rail">
        <div className="dd-primary" aria-label="Plan selection">{heading}{navigation}</div>
        <div className="dd-secondary" aria-label="National map settings">
          {landAvailable && <details className="dd-disclosure">
            <summary>Map layers{fullExtent && <span className="dd-badge">1 on</span>}</summary>
            <div className="dd-disclosure-body text-muted-foreground">
              <label className="flex items-center gap-2 text-xs font-medium text-foreground"><input type="checkbox" checked={fullExtent} onChange={(event) => setFullExtent(event.target.checked)} />Full census extent</label>
              <p className="leading-5">{nationalLand ? "Land-focused boundaries are shown by default. Saved populations and connections stay unchanged." : "Michigan land-focused pilot · other states retain their full census extent."}</p>
            </div>
          </details>}
          <details className="dd-disclosure">
            <summary>About this map</summary>
            <div className="dd-disclosure-body leading-5 text-muted-foreground">
              <p>Click a state to explore its districts, counties, cities and census blocks. Recorded connections and derived water paths can be inspected separately in state view.</p>
              <p>Alaska and Hawaii have clickable inset boxes. Use the state initials beside the Northeast to open smaller states.</p>
              <p>{formatMapBytes(asset.gzipBytes + (landMode && nationalLand
                ? [nationalLand.outlines, nationalLand.coast, nationalLand.dividers, nationalLand.connections, nationalLand.recordedConnections].reduce((sum, value) => sum + (value?.gzipBytes ?? 0), 0)
                : landMode && landDisplay && cleanDisplay ? cleanDisplay.overview.gzipBytes + cleanDisplay.coast.gzipBytes + cleanDisplay.dividers.gzipBytes + landDisplay.connections.gzipBytes : 0))} compressed map layers</p>
            </div>
          </details>
        </div>
      </div>
      <div className="dd-stage">
        <div className="dd-stage-bar">
          <nav aria-label="Map location" className="dd-crumbs"><span className="dd-crumb" aria-current="location">United States</span></nav>
        </div>
        <div className="dd-map-area">
          <div className="dd-map-frame" data-frame="national">
            {!map && (
              <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground" role={displayError ? "alert" : "status"}>
                {displayError ? <div>{displayError}<button type="button" className="dd-tool ml-3" onClick={() => setRetry((n) => n + 1)}>Retry map</button></div>
                  : <span className="dd-status"><span className="dd-led" data-state="busy" />Loading {houseSize.toLocaleString()} district outlines…</span>}
              </div>
            )}
            {map && <svg viewBox={`0 0 ${BLOCK_MAP_WIDTH} ${BLOCK_NATIONAL_HEIGHT}`} className="absolute inset-0 h-full w-full" aria-label={`District outlines for all 50 states at House size ${houseSize}. Select a state for detail.`}>
              {map.states.map((group) => <NationalStateButton key={group.fips} group={group}
                highlighted={group.fips === hovered || group.fips === focused || group.fips === selectedStateFips}
                selected={group.fips === selectedStateFips} onHighlight={highlightState} onClear={clearHighlight}
                onFocusState={focusState} onClearFocus={clearFocus} onSelect={selectState} />)}
              <NationalLandMeshes meshes={map.meshes} />
              {/* State exteriors are separate from district borders, including AK/HI. */}
              <g aria-hidden="true" pointerEvents="none" data-layer="state-boundaries" fill="none" strokeLinejoin="round">
                {map.borders.map((outline) => <NationalStateBorder key={outline.fips} outline={outline}
                  highlighted={outline.fips === hovered || outline.fips === focused || outline.fips === selectedStateFips} />)}
              </g>
              {landMode && <NationalConnections derived={map.derived} recorded={map.recorded} />}
            </svg>}
          </div>
        </div>
        {/* Same two-line shape hovered or not, so the strip never resizes the map. */}
        <div className="dd-readout-strip" aria-live="polite">
          <div className="dd-readout-head dd-readout-wide">
            <h3 className="truncate text-sm font-semibold">{active ? active.name : "United States"}</h3>
            <span className="dd-meta truncate">{active ? `${active.districts.length} districts · select to inspect` : "Select a state to inspect its districts and recorded connections."}</span>
          </div>
        </div>
        <div className="dd-stage-foot">
          <div className="dd-legend" aria-label="Map boundary legend">
            <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="state" />State boundary</span>
            <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="district" />District boundary</span>
            {landMode && <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="derived" />{nationalLand ? "Derived water paths" : "Michigan derived water connections"}</span>}
            {!!map?.recorded.length && <span className="dd-legend-item"><span aria-hidden="true" className="dd-swatch" data-kind="recorded" />Recorded water / exclave connections</span>}
            {data && boundaryUrl && !boundaries && !boundaryError && <span role="status">Loading state borders…</span>}
            {boundaryError && <span role="alert">State borders unavailable. <button type="button" className="underline underline-offset-2" onClick={() => setRetry((n) => n + 1)}>Retry borders</button></span>}
          </div>
        </div>
      </div>
    </section>
  );
}

const NationalDistrictFills = React.memo(function NationalDistrictFills({ group }: { group: NationalStatePaths }) {
  return <>{group.districts.map((district) => <path key={district.id} data-layer="district-fill" data-state={group.fips}
    d={district.d} fill={district.fill} fillRule="evenodd" stroke={group.landFocused ? "none" : MAP_COLORS.line}
    strokeOpacity={0.55} strokeWidth={0.55} vectorEffect="non-scaling-stroke" />)}</>;
});

const NationalStateButton = React.memo(function NationalStateButton({ group, highlighted, selected, onHighlight, onClear, onFocusState, onClearFocus, onSelect }: {
  group: NationalStatePaths; highlighted: boolean; selected: boolean;
  onHighlight: (state: string) => void; onClear: () => void;
  onFocusState: (state: string) => void; onClearFocus: () => void; onSelect: (state: string) => void;
}) {
  const inset = group.fips === "02" ? BLOCK_MAP_INSETS.alaska : group.fips === "15" ? BLOCK_MAP_INSETS.hawaii : null;
  const shortcut = NORTHEAST_SHORTCUTS.get(group.fips);
  return <g role="button" tabIndex={0} aria-label={`${group.name}, ${group.districts.length} districts. Open state map.`}
    aria-pressed={selected} data-state-highlighted={highlighted} className="cursor-pointer outline-none"
    onMouseEnter={() => onHighlight(group.fips)} onMouseLeave={onClear}
    onFocus={() => onFocusState(group.fips)} onBlur={onClearFocus} onClick={() => onSelect(group.fips)} onKeyDown={(event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(group.fips); }
    }}>
    <title>{group.name}: {group.districts.length} districts</title>
    {inset && <>
      <rect data-layer="state-inset" data-state={group.fips} x={inset.x} y={inset.y} width={inset.width} height={inset.height} rx="8"
        fill={highlighted ? MAP_COLORS.insetHover : MAP_COLORS.insetFill} stroke={highlighted ? MAP_COLORS.insetActive : MAP_COLORS.line} strokeOpacity={highlighted ? 1 : 0.35} strokeDasharray="3 5" />
      <text aria-hidden="true" pointerEvents="none" x={inset.x + 12} y={inset.y + 18} fill={MAP_COLORS.label} fillOpacity={0.7} fontSize="11" fontWeight="500" style={{ fontFamily: "var(--dd-mono)" }}>{inset.label}</text>
    </>}
    {shortcut && <>
      <rect data-layer="state-shortcut" data-state={group.fips} x={shortcut.x} y={shortcut.y} width="44" height="40" rx="6"
        fill={highlighted ? MAP_COLORS.insetHover : MAP_COLORS.insetFill} stroke={highlighted ? MAP_COLORS.insetActive : MAP_COLORS.line} strokeOpacity={highlighted ? 1 : 0.3} strokeWidth={highlighted ? 1.5 : 1} vectorEffect="non-scaling-stroke" />
      <text aria-hidden="true" pointerEvents="none" x={shortcut.x + 22} y={shortcut.y + 21} textAnchor="middle" dominantBaseline="middle"
        fill={highlighted ? MAP_COLORS.insetActive : MAP_COLORS.label} fontSize="15" fontWeight="600" style={{ fontFamily: "var(--dd-mono)" }}>{shortcut.label}</text>
    </>}
    {/* Inherited fill-opacity preserves per-path compositing; group opacity would change overlaps. */}
    <g data-layer="state-district-fills" data-state={group.fips} fillOpacity={highlighted ? 1 : 0.84}>
      <NationalDistrictFills key={group.fips} group={group} />
    </g>
  </g>;
});

const NationalLandMeshes = React.memo(function NationalLandMeshes({ meshes }: { meshes: NationalPreparedMap["meshes"] }) {
  return <>{meshes.map((lines) => <g key={lines.state} data-state={lines.state} aria-hidden="true" pointerEvents="none" fill="none" strokeLinejoin="round">
    <path data-layer={lines.state === "26" ? "michigan-interior-water" : "land-interior-water"} data-state={lines.state} d={lines.water} stroke={MAP_COLORS.derivedWater} strokeOpacity={0.4} strokeWidth={0.35} vectorEffect="non-scaling-stroke" />
    <path data-layer={lines.state === "26" ? "michigan-district-dividers" : "land-district-dividers"} data-state={lines.state} d={lines.dividers} stroke={MAP_COLORS.line} strokeOpacity={0.55} strokeWidth={0.55} vectorEffect="non-scaling-stroke" />
  </g>)}</>;
});

const NationalStateBorder = React.memo(function NationalStateBorder({ outline, highlighted }: { outline: NationalPreparedMap["borders"][number]; highlighted: boolean }) {
  return <g data-state={outline.fips}>
    <path d={outline.d} stroke={highlighted ? MAP_COLORS.selectionCasing : MAP_COLORS.casing} strokeWidth={highlighted ? 4.6 : 3} vectorEffect="non-scaling-stroke" />
    <path d={outline.d} stroke={highlighted ? MAP_COLORS.selection : MAP_COLORS.line} strokeWidth={highlighted ? 2.4 : 1.3} vectorEffect="non-scaling-stroke" />
  </g>;
});

const NationalConnections = React.memo(function NationalConnections({ derived, recorded }: { derived: NationalPreparedMap["derived"]; recorded: NationalPreparedMap["recorded"] }) {
  return <>
    <g fill="none" stroke={MAP_COLORS.derivedWater} strokeOpacity={0.5} strokeWidth="0.85" strokeDasharray="3 3" pointerEvents="none" aria-hidden="true" data-layer="derived-water-connections">
      {derived.map((connection) => <path key={connection.state} data-state={connection.state} data-connection-count={connection.count} d={connection.d} vectorEffect="non-scaling-stroke" />)}
    </g>
    <g fill="none" strokeWidth="1.1" strokeDasharray="5 3" pointerEvents="none" aria-hidden="true" data-layer="recorded-connections">
      {recorded.map((connection) => <path key={connection.id} data-state={connection.state} data-kind={connection.kind} d={connection.d}
        stroke={connection.kind === "exclave" ? MAP_COLORS.recordedExclave : MAP_COLORS.recordedWater} vectorEffect="non-scaling-stroke" />)}
    </g>
  </>;
});
