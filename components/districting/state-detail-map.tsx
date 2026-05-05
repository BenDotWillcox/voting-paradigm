"use client";

import * as React from "react";
import { geoPath } from "d3-geo";

import {
  STATE_DETAIL_VIEWBOX,
  stateFittedAlbers,
} from "@/lib/state-projection";
import type { StatesGeoJSON } from "@/lib/load-states-geojson";

interface StateDetailMapProps {
  /** GeoJSON FeatureCollection of all 50 states (raw lat/lon). */
  states: StatesGeoJSON;
  /** 2-char zero-padded FIPS of the state to render. */
  stateFips: string;
}

/**
 * Single-state SVG, projected with a state-fitted Albers Equal-Area
 * Conic and rendered into a fixed 4:3 card.
 *
 * Why a fixed aspect ratio: cropping each state to its own bbox (which
 * the earlier implementation did) meant tall states like ID rendered
 * in tall narrow cards while wide states like TN rendered in short
 * wide cards — geometrically honest, visually inconsistent. A 4:3 box
 * with `fitExtent`-style centering gives every state the same card
 * shape and lets layouts above this component reserve space without
 * surprises.
 *
 * Why state-fitted Albers (per state) rather than one shared
 * projection: distortion. Albers Conic with parallels chosen to bracket
 * the state's latitude range produces <0.1% area distortion within
 * any state — including AK and HI, which would render badly under a
 * single CONUS projection.
 */
export function StateDetailMap({
  states,
  stateFips,
}: StateDetailMapProps) {
  const result = React.useMemo(() => {
    const feature = states.features.find(
      (f) => String(f.id ?? "") === stateFips
    );
    if (!feature) return null;
    const projection = stateFittedAlbers(
      feature,
      STATE_DETAIL_VIEWBOX.width,
      STATE_DETAIL_VIEWBOX.height
    );
    const path = geoPath(projection);
    return { d: path(feature) ?? "", name: feature.properties?.name ?? stateFips };
  }, [states, stateFips]);

  if (!result) {
    return (
      <div className="aspect-[4/3] w-full rounded-md border bg-muted/40 flex items-center justify-center text-sm text-muted-foreground">
        No geometry for FIPS {stateFips}
      </div>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${STATE_DETAIL_VIEWBOX.width} ${STATE_DETAIL_VIEWBOX.height}`}
      className="w-full h-auto"
      role="img"
      aria-label={`Outline of ${result.name}`}
    >
      <path
        d={result.d}
        className="fill-primary/15 stroke-primary"
        strokeWidth={1}
      />
    </svg>
  );
}
