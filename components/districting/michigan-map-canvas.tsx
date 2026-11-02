"use client";

import * as React from "react";
import type { Feature, Geometry } from "geojson";
import type { BlockMapCollection, BlockMapProjection, BlockMapProperties } from "@/lib/block-map-projection";
import { blockDistrictColor } from "@/lib/block-map-projection";
import { createBlockCanvasFrame } from "@/lib/block-canvas-frame";
import { MAP_COLORS } from "@/lib/districts-palette";
import { boundsIntersect, retainedMichiganFrameTransform, type MapBounds, type MapViewport, type MichiganCanvasFrame } from "@/lib/michigan-map-interaction";

export interface MichiganBlockShape { feature: Feature<Geometry, BlockMapProperties>; bounds: MapBounds; d: string }

/** Stable county shapes retain their paths across viewport batches; only visible
 * blocks allocate Path2D objects. Evicted shapes are not retained by the cache.
 */
export function MichiganBlockCanvas({ shapes, view, projection, clip, outlinesOnly, complete, appearanceKey, stateFips = "26" }: {
  shapes: MichiganBlockShape[]; view: MapViewport; projection: BlockMapProjection; clip?: BlockMapCollection; outlinesOnly: boolean; complete: boolean; appearanceKey: string; stateFips?: string;
}) {
  const ref = React.useRef<HTMLCanvasElement>(null);
  const paths = React.useRef(new WeakMap<MichiganBlockShape, Path2D>());
  const publishedFrame = React.useRef<MichiganCanvasFrame | null>(null);
  const [rendering, setRendering] = React.useState(false);
  const [retaining, setRetaining] = React.useState(false);
  React.useLayoutEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let frame = 0, generation = 0;
    let drawing: ReturnType<typeof createBlockCanvasFrame> = null;
    const draw = () => {
      cancelAnimationFrame(frame); drawing?.cancel();
      const token = ++generation;
      // Layout dimensions ignore a retained frame's CSS transform and exclude
      // the map container's border, matching the SVG's inner drawing surface.
      const viewport = { width: canvas.clientWidth, height: canvas.clientHeight };
      if (!viewport.width || !viewport.height) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.round(viewport.width * ratio), height = Math.round(viewport.height * ratio);
      const currentFrame = { view, appearanceKey, width: viewport.width, height: viewport.height };
      const transform = canvas.width === width && canvas.height === height ? retainedMichiganFrameTransform(publishedFrame.current, { ...currentFrame, complete }) : null;
      // The bitmap has no pixels outside its original viewport rectangle.
      // Retaining its transform therefore reveals the base map in new areas,
      // without stretching coverage or exposing unmasked offscreen pixels.
      canvas.style.transformOrigin = "0 0";
      canvas.style.transform = transform ? `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})` : "none";
      canvas.style.visibility = transform ? "visible" : "hidden"; setRetaining(!!transform);
      if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; publishedFrame.current = null; }
      // Draw the stable trusted overlap once, retaining the old raster until
      // publication. It may include cached new-area blocks not in that raster.
      // Individual chunk arrivals keep shapes stable; new chunks publish as a
      // group only when ready. With no cached overlap keep any retained pixels.
      if (!complete && shapes.length === 0) { setRendering(false); return; }
      drawing = createBlockCanvasFrame(canvas, projection, clip, true);
      if (!drawing) return;
      const target = drawing, context = drawing.context;
      context.translate(view.x, view.y); context.scale(view.k, view.k);
      const box: MapBounds = [[-view.x / view.k, -view.y / view.k], [(1000 - view.x) / view.k, (620 - view.y) / view.k]];
      const visible = shapes.filter((shape) => boundsIntersect(shape.bounds, box));
      setRendering(visible.length > 0);
      let cursor = 0;
      const batch = () => {
        if (token !== generation) return;
        const end = Math.min(cursor + 600, visible.length);
        const deadline = performance.now() + 8;
        while (cursor < end) {
          const shape = visible[cursor++];
          let prepared = paths.current.get(shape);
          if (!prepared) { prepared = new Path2D(shape.d); paths.current.set(shape, prepared); }
          if (!outlinesOnly) { context.fillStyle = blockDistrictColor(Number(shape.feature.properties.district_id), stateFips); context.globalAlpha = 0.88; context.fill(prepared, "evenodd"); }
          context.globalAlpha = outlinesOnly ? 0.5 : 0.3; context.strokeStyle = MAP_COLORS.line; context.lineWidth = 0.65 / view.k; context.stroke(prepared);
          if (performance.now() >= deadline) break;
        }
        if (cursor < visible.length) frame = requestAnimationFrame(batch);
        else {
          // The common mask is already projected into the viewport; undo only
          // the local map transform before its one-time composition.
          context.scale(1 / view.k, 1 / view.k); context.translate(-view.x, -view.y); context.globalAlpha = 1;
          if (target.publish()) {
            canvas.style.transform = "none"; canvas.style.visibility = "visible";
            publishedFrame.current = currentFrame; setRetaining(false); setRendering(false);
          }
        }
      };
      frame = requestAnimationFrame(batch);
    };
    const observer = new ResizeObserver(draw); observer.observe(canvas); draw();
    return () => { generation++; cancelAnimationFrame(frame); drawing?.cancel(); observer.disconnect(); };
  }, [shapes, view, projection, clip, outlinesOnly, complete, appearanceKey, stateFips]);
  return <><canvas ref={ref} aria-hidden="true" data-map-layer="census-blocks" data-render-state={retaining ? "retained-frame" : rendering ? "drawing" : !complete ? shapes.length ? "cached-detail" : "waiting-for-data" : "ready"} data-detail-complete={complete} className="pointer-events-none absolute inset-0 h-full w-full" />
    {rendering && !retaining && <span className="dd-map-chip right-3 top-3 px-3 py-2 text-xs"><span className="dd-led" data-state="busy" />Drawing block detail…</span>}</>;
}
