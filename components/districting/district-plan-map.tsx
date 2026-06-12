"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import { feature as topoFeature } from "topojson-client";
import type { FeatureCollection, Geometry } from "geojson";

import {
  STATE_DETAIL_VIEWBOX,
  stateFittedAlbers,
} from "@/lib/state-projection";
import type { StateFeature } from "@/lib/load-states-geojson";
import type {
  CachedDistrictPlan,
  DistrictPlanFeatureProperties,
} from "@/types/districting";

interface DistrictPlanMapProps {
  state: StateFeature;
  plan: CachedDistrictPlan;
}

export function DistrictPlanMap({ state, plan }: DistrictPlanMapProps) {
  const projection = React.useMemo(
    () =>
      stateFittedAlbers(
        state,
        STATE_DETAIL_VIEWBOX.width,
        STATE_DETAIL_VIEWBOX.height
      ),
    [state]
  );
  const path = React.useMemo(() => geoPath(projection), [projection]);
  const featureCollection = React.useMemo(() => {
    if (plan.display_topology) {
      return topoFeature(
        plan.display_topology,
        plan.display_topology.objects.districts
      ) as FeatureCollection<Geometry, DistrictPlanFeatureProperties>;
    }
    return plan.feature_collection ?? null;
  }, [plan.display_topology, plan.feature_collection]);
  const features = featureCollection?.features ?? [];
  const centers = React.useMemo(
    () => {
      const projectionMeta = plan.projection;
      if (!projectionMeta || !plan.centers) return [];
      return plan.centers
        .map((center) => {
          const lonLat = unprojectEquirectangular(
            center.x,
            center.y,
            projectionMeta.lon0,
            projectionMeta.lat0
          );
          const point = projection(lonLat);
          // Round to 0.01px: transcendental math (Math.cos) can differ in
          // the last float digits between Node and the browser, which would
          // otherwise trip React hydration on SSR'd cx/cy attributes.
          return point
            ? { ...center, point: [roundCoord(point[0]), roundCoord(point[1])] as [number, number] }
            : null;
        })
        .filter((center) => center !== null);
    },
    [plan.centers, plan.projection, projection]
  );
  const maxAbsWeight = Math.max(
    1,
    ...(plan.centers ?? []).map((center) => Math.abs(center.weight))
  );

  return (
    <div className="space-y-3">
      <svg
        viewBox={`0 0 ${STATE_DETAIL_VIEWBOX.width} ${STATE_DETAIL_VIEWBOX.height}`}
        className="w-full h-auto"
        role="img"
        aria-label={`${plan.state_name} tract-level balanced power district plan`}
      >
        <g>
          {features.map((feature) => {
            const districtId = feature.properties.district_id;
            const title =
              plan.display_unit === "district"
                ? `${feature.properties.name}: ${feature.properties.population.toLocaleString()} people`
                : `${feature.properties.name}: District ${districtId + 1}, ${feature.properties.population.toLocaleString()} people`;
            return (
              <path
                key={feature.properties.geoid}
                d={path(feature) ?? ""}
                fill={districtColor(districtId, plan.seats)}
                stroke="var(--background)"
                strokeWidth={0.35}
              >
                <title>{title}</title>
              </path>
            );
          })}
        </g>
        <g aria-label="Balanced power centers">
          {centers.map((center) => {
            const [cx, cy] = center.point;
            const districtPopulation =
              plan.district_populations[String(center.district_id)] ?? 0;
            const weightShare = Math.abs(center.weight) / maxAbsWeight;
            const radius = plan.seats > 24 ? 3.25 : 4.75;
            const haloRadius = radius + 2.5 + weightShare * 5;

            return (
              <g key={center.district_id}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={haloRadius}
                  fill="none"
                  stroke="hsl(var(--foreground))"
                  strokeOpacity={0.36}
                  strokeWidth={1.1}
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill="hsl(var(--background))"
                  stroke="hsl(var(--foreground))"
                  strokeWidth={1.5}
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r={Math.max(1.5, radius - 1.75)}
                  fill={districtColor(center.district_id, plan.seats)}
                >
                  <title>
                    {`District ${center.district_id + 1} center: ${districtPopulation.toLocaleString()} people, weight ${formatWeight(center.weight)}`}
                  </title>
                </circle>
              </g>
            );
          })}
        </g>
      </svg>
      <DistrictLegend seats={plan.seats} />
    </div>
  );
}

function districtColor(districtId: number, seats: number): string {
  const hue = (districtId * 137.508) % 360;
  const lightness = seats > 24 ? 0.72 : 0.66;
  const chroma = seats > 24 ? 0.11 : 0.14;
  return `oklch(${lightness} ${chroma} ${hue.toFixed(1)})`;
}

function DistrictLegend({ seats }: { seats: number }) {
  const visible = Array.from({ length: Math.min(seats, 12) }, (_, i) => i);
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span>Districts</span>
      {visible.map((districtId) => (
        <span key={districtId} className="inline-flex items-center gap-1">
          <span
            className="h-2.5 w-2.5 rounded-sm border"
            style={{ background: districtColor(districtId, seats) }}
          />
          {districtId + 1}
        </span>
      ))}
      {seats > visible.length && <span>+{seats - visible.length} more</span>}
      <span className="inline-flex items-center gap-1">
        <span className="h-2.5 w-2.5 rounded-full border border-foreground bg-background" />
        center / weight
      </span>
    </div>
  );
}

function unprojectEquirectangular(
  x: number,
  y: number,
  lon0: number,
  lat0: number
): [number, number] {
  const earthRadiusM = 6_371_000;
  const lat = lat0 + radiansToDegrees(y / earthRadiusM);
  const lon =
    lon0 +
    radiansToDegrees(
      x / (earthRadiusM * Math.cos(degreesToRadians(lat0)))
    );
  return [lon, lat];
}

function degreesToRadians(value: number): number {
  return (value * Math.PI) / 180;
}

function radiansToDegrees(value: number): number {
  return (value * 180) / Math.PI;
}

function roundCoord(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatWeight(weight: number): string {
  const abs = Math.abs(weight);
  if (abs >= 1_000_000_000) return `${(weight / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${(weight / 1_000_000).toFixed(2)}M`;
  return Math.round(weight).toLocaleString();
}
