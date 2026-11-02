"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import type { BlockComparisonLayer, BlockComparisonLayerKind } from "@/types/block-districting";
import { comparisonLayerKey, DENSITY_BINS, DENSITY_NO_LAND_COLOR, densityColor, loadComparisonLayer } from "@/lib/block-comparison-layers";
import { formatMapBytes } from "@/lib/block-map-projection";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import { createBlockCanvasFrame } from "@/lib/block-canvas-frame";
import { MAP_COLORS } from "@/lib/districts-palette";

export function useComparisonLayer(stateFips: string, kind: BlockComparisonLayerKind, layer: BlockComparisonLayer | undefined, enabled: boolean) {
  const [record, setRecord] = React.useState<{ key: string; data: BlockMapCollection } | null>(null);
  const [error, setError] = React.useState<{ key: string; message: string } | null>(null);
  const [retry, setRetry] = React.useState(0);
  const key = layer ? comparisonLayerKey(stateFips, kind, layer) : "";
  React.useEffect(() => {
    if (!enabled || !layer || record?.key === key) return;
    const abort = new AbortController();
    let current = true;
    setError(null);
    loadComparisonLayer(stateFips, kind, layer, abort.signal).then((data) => {
      if (current && !abort.signal.aborted) setRecord({ key, data });
    }).catch((cause: unknown) => {
      if (current && !abort.signal.aborted) setError({ key, message: cause instanceof Error ? cause.message : "Unable to load comparison layer." });
    });
    return () => { current = false; abort.abort(); };
  }, [stateFips, kind, layer, enabled, key, retry, record?.key]);
  return {
    data: enabled && record?.key === key ? record.data : null,
    error: enabled && error?.key === key ? error.message : null,
    loading: enabled && !!layer && record?.key !== key && error?.key !== key,
    retry: () => setRetry((value) => value + 1),
  };
}

const LABELS: Record<BlockComparisonLayerKind, string> = {
  density: "Population density", counties: "Counties", congressional: "Congressional districts",
};

export function ComparisonLayerControl({ kind, layer, enabled, onEnabled, opacity, onOpacity, state, compact = false }: {
  kind: BlockComparisonLayerKind; layer: BlockComparisonLayer | undefined;
  enabled: boolean; onEnabled: (value: boolean) => void; opacity: number; onOpacity: (value: number) => void;
  state: ReturnType<typeof useComparisonLayer>;
  compact?: boolean;
}) {
  const id = React.useId();
  return <div className={compact ? "min-w-0 space-y-1 py-1" : "min-w-0 space-y-2 rounded-lg border bg-background/70 p-3"}>
    <label className={`flex items-start gap-2 font-medium ${compact ? "text-xs" : "text-sm"}`}>
      <input type="checkbox" className="mt-0.5" checked={enabled} disabled={!layer} onChange={(event) => onEnabled(event.target.checked)} />
      <span>{LABELS[kind]}{!compact && <span className="mt-0.5 block text-xs font-normal text-muted-foreground">{kind === "density" ? "2020 Census · tract overview" : kind === "counties" ? "2020 county boundaries" : "119th Congress · 2025–2026"}</span>}</span>
    </label>
    {(!compact || enabled) && <div className={`flex items-center gap-2 text-xs ${compact ? "pl-5" : ""}`}>
      <label htmlFor={id} className="text-muted-foreground">Opacity</label>
      <input id={id} aria-label={`${LABELS[kind]} opacity`} className="min-w-0 flex-1" type="range" min={0} max={100} step={5}
        value={Math.round(opacity * 100)} disabled={!enabled || !layer} onChange={(event) => onOpacity(Number(event.target.value) / 100)} />
      <output htmlFor={id} className="w-9 text-right tabular-nums">{Math.round(opacity * 100)}%</output>
    </div>}
    {(!compact || state.error || state.loading || !layer) && <div className="min-h-4 text-xs text-muted-foreground" role={state.error ? "alert" : "status"}>
      {state.error ? <>{state.error} <button type="button" onClick={state.retry} className="underline">Retry {LABELS[kind].toLowerCase()}</button></>
        : state.loading ? "Loading this state’s reference…"
          : enabled && state.data ? `${layer!.featureCount.toLocaleString()} ${kind === "density" ? "tracts" : kind === "counties" ? "counties / equivalents" : layer!.featureCount === 1 ? "district" : "districts"} loaded`
            : layer ? `${formatMapBytes(layer.asset.gzipBytes)} · loads when enabled` : "Reference layer unavailable"}
    </div>}
  </div>;
}

/** Canvas keeps thousands of tracts out of the interactive SVG/accessibility tree. */
export function DensityCanvas({ data, projection, opacity, clip }: {
  data: BlockMapCollection; projection: BlockMapProjection; opacity: number; clip?: BlockMapCollection;
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
        const end = Math.min(cursor + 350, data.features.length);
        for (; cursor < end; cursor += 1) {
          const feature = data.features[cursor];
          context.beginPath(); path(feature);
          context.fillStyle = densityColor(feature.properties.densityPerKm2);
          context.fill("evenodd");
        }
        if (cursor < data.features.length) frame = requestAnimationFrame(batch);
        else drawing.publish();
      };
      frame = requestAnimationFrame(batch);
    };
    const observer = new ResizeObserver(draw);
    observer.observe(canvas); draw();
    return () => { generation += 1; activeFrame?.cancel(); cancelAnimationFrame(frame); observer.disconnect(); };
  }, [data, projection, clip]);
  return <canvas ref={ref} style={{ opacity }} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true" data-map-layer="population-density" />;
}

export function ComparisonBoundaries({ data, projection, kind, opacity }: {
  data: BlockMapCollection; projection: BlockMapProjection; kind: "counties" | "congressional"; opacity: number;
}) {
  const paths = React.useMemo(() => {
    const path = geoPath(projection);
    return data.features.map((feature) => ({ id: String(feature.properties.geoid), d: path(feature) ?? "" }));
  }, [data, projection]);
  return <g opacity={opacity} pointerEvents="none" aria-hidden="true" data-map-layer={kind}>
    {paths.map(({ id, d }) => <path key={id} d={d} fill="none" stroke={MAP_COLORS.line}
      strokeWidth={kind === "counties" ? 1.25 : 2.25} strokeDasharray={kind === "counties" ? "1 3" : "11 5"}
      vectorEffect="non-scaling-stroke" />)}
  </g>;
}

export function DensityLegend() {
  return <div className="space-y-1 text-xs">
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="font-medium text-foreground">2020 residents per km² of land · tract averages</span>
      {DENSITY_BINS.map((bin) => <span key={bin.label} className="inline-flex items-center gap-1.5 text-foreground"><span className="h-3 w-5 rounded-sm ring-1 ring-black/10" style={{ background: bin.color }} />{bin.label}</span>)}
      <span className="inline-flex items-center gap-1.5 text-foreground"><span className="h-3 w-5 rounded-sm ring-1 ring-black/10" style={{ background: DENSITY_NO_LAND_COLOR }} />No land area · N/A</span>
    </div>
    <p className="text-[11px] text-muted-foreground">Population divided by land area, excluding water. Tract averages do not show the distribution within a tract.</p>
  </div>;
}
