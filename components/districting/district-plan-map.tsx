"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import { feature as topoFeature } from "topojson-client";
import type { Feature, FeatureCollection, Geometry } from "geojson";

import {
  districtColor,
  projectPlanCenters,
  tractName,
} from "@/lib/district-plans";
import { fetchDistrictPlanLayer } from "@/lib/fetch-district-plan";
import type { StateFeature } from "@/lib/load-states-geojson";
import {
  STATE_DETAIL_VIEWBOX,
  stateFittedAlbers,
} from "@/lib/state-projection";
import type {
  DistrictPlan,
  DistrictProperties,
  TractProperties,
} from "@/types/districting";

import { TractCanvasFigure, type TractFeature } from "./tract-canvas";

interface DistrictPlanMapProps {
  state: StateFeature;
  /** Plan metrics and centers; geometry layers are fetched as static assets. */
  plan: DistrictPlan;
}

type DistrictFeature = Feature<Geometry, DistrictProperties>;

interface HoveredTract {
  tract: TractProperties;
  point: [number, number];
}

/**
 * Cached district plan map. Paints the state outline and solver centers on
 * the server render, fills in dissolved district outlines (~10-20 KB gz)
 * as soon as they arrive, then streams tract detail onto a canvas layer for
 * hover inspection.
 */
export function DistrictPlanMap({ state, plan }: DistrictPlanMapProps) {
  const [districts, setDistricts] = React.useState<DistrictFeature[] | null>(null);
  const [tracts, setTracts] = React.useState<TractFeature[] | null>(null);
  const [failed, setFailed] = React.useState(false);
  const [hovered, setHovered] = React.useState<HoveredTract | null>(null);

  const { state_fips: fips, cap, seats } = plan;
  React.useEffect(() => {
    let cancelled = false;
    setDistricts(null);
    setTracts(null);
    setFailed(false);
    setHovered(null);
    fetchDistrictPlanLayer(fips, cap, seats, "districts")
      .then((topology) => {
        if (cancelled) return;
        setDistricts(toFeatures(topology, topology.objects.districts));
        return fetchDistrictPlanLayer(fips, cap, seats, "tracts");
      })
      .then((topology) => {
        if (cancelled || !topology) return;
        setTracts(toFeatures(topology, topology.objects.tracts));
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [fips, cap, seats]);

  const projection = React.useMemo(
    () => stateFittedAlbers(state, STATE_DETAIL_VIEWBOX.width, STATE_DETAIL_VIEWBOX.height),
    [state]
  );
  const path = React.useMemo(() => geoPath(projection), [projection]);
  const statePath = React.useMemo(() => path(state) ?? "", [path, state]);
  const districtPaths = React.useMemo(
    () =>
      (districts ?? []).map((district) => ({
        id: district.properties.district_id,
        d: path(district) ?? "",
      })),
    [districts, path]
  );
  const centers = React.useMemo(() => projectPlanCenters(plan, projection), [plan, projection]);
  const maxAbsWeight = Math.max(1, ...centers.map((center) => Math.abs(center.weight)));

  const tractFill = React.useCallback(
    (tract: TractProperties) => districtColor(tract.district_id, seats),
    [seats]
  );
  const handleHover = React.useCallback(
    (tract: TractProperties | null, point: [number, number] | null) => {
      setHovered(tract && point ? { tract, point } : null);
    },
    []
  );

  const showTracts = tracts !== null && tracts.length > 0;
  const hoveredDistrictPath = hovered
    ? districtPaths.find((district) => district.id === hovered.tract.district_id)?.d
    : undefined;
  const status = failed
    ? "District geometry could not be loaded."
    : districts === null
      ? "Loading district outlines…"
      : !showTracts
        ? "Streaming tract-level detail…"
        : `${tracts.length.toLocaleString()} census tracts. Hover a tract for its assignment.`;

  return (
    <div className="space-y-3">
      <div className="relative">
        <TractCanvasFigure
          tracts={tracts ?? EMPTY_TRACTS}
          projection={projection}
          viewBox={STATE_DETAIL_VIEWBOX}
          fill={tractFill}
          stroke="--background"
          strokeWidth={0.35}
          onHover={showTracts ? handleHover : undefined}
          ariaLabel={`${plan.state_name} tract-level balanced power district plan`}
          underlay={
            districts === null ? (
              <path
                d={statePath}
                style={{ fill: "var(--muted)", stroke: "var(--border)" }}
                strokeWidth={1}
              />
            ) : null
          }
        >
          <g pointerEvents="none">
            {districtPaths.map((district) => (
              <path
                key={district.id}
                d={district.d}
                fill={showTracts ? "none" : districtColor(district.id, seats)}
                style={{ stroke: showTracts ? "var(--foreground)" : "var(--background)" }}
                strokeOpacity={showTracts ? 0.55 : 1}
                strokeWidth={showTracts ? 0.9 : 0.6}
              />
            ))}
            {hoveredDistrictPath ? (
              <path
                d={hoveredDistrictPath}
                fill="none"
                style={{ stroke: "var(--foreground)" }}
                strokeWidth={2}
              />
            ) : null}
          </g>
          <g aria-label="Balanced power centers" pointerEvents="none">
            {centers.map((center) => {
              const [cx, cy] = center.point;
              const weightShare = Math.abs(center.weight) / maxAbsWeight;
              const radius = seats > 24 ? 3.25 : 4.75;
              const haloRadius = radius + 2.5 + weightShare * 5;
              return (
                <g key={center.districtId}>
                  <circle
                    cx={cx}
                    cy={cy}
                    r={haloRadius}
                    fill="none"
                    style={{ stroke: "var(--foreground)" }}
                    strokeOpacity={0.36}
                    strokeWidth={1.1}
                  />
                  <circle
                    cx={cx}
                    cy={cy}
                    r={radius}
                    style={{ fill: "var(--background)", stroke: "var(--foreground)" }}
                    strokeWidth={1.5}
                  />
                  <circle
                    cx={cx}
                    cy={cy}
                    r={Math.max(1.5, radius - 1.75)}
                    fill={districtColor(center.districtId, seats)}
                  />
                </g>
              );
            })}
          </g>
        </TractCanvasFigure>
        {hovered ? <TractTooltip hovered={hovered} plan={plan} /> : null}
      </div>
      <DistrictLegend seats={seats} />
      <p
        className="text-[11px] leading-snug text-muted-foreground"
        role="status"
        aria-live="polite"
      >
        {status}
      </p>
    </div>
  );
}

const EMPTY_TRACTS: TractFeature[] = [];

function toFeatures<P>(
  topology: Parameters<typeof topoFeature>[0],
  object: Parameters<typeof topoFeature>[1]
): Array<Feature<Geometry, P>> {
  return (topoFeature(topology, object) as FeatureCollection<Geometry, P>).features;
}

function TractTooltip({ hovered, plan }: { hovered: HoveredTract; plan: DistrictPlan }) {
  const { tract, point } = hovered;
  const districtPopulation = plan.district_populations[String(tract.district_id)] ?? 0;
  const left = (point[0] / STATE_DETAIL_VIEWBOX.width) * 100;
  const top = (point[1] / STATE_DETAIL_VIEWBOX.height) * 100;
  const flip = left > 60;
  return (
    <div
      className="pointer-events-none absolute z-10 w-max max-w-56 rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md"
      style={{
        left: `${left}%`,
        top: `${top}%`,
        transform: `translate(${flip ? "calc(-100% - 12px)" : "12px"}, -50%)`,
      }}
    >
      <div className="font-medium">{tractName(tract.geoid)}</div>
      <div className="tabular-nums text-muted-foreground">
        {tract.population.toLocaleString()} people
      </div>
      <div className="tabular-nums">
        District {tract.district_id + 1} · {districtPopulation.toLocaleString()} people
      </div>
    </div>
  );
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
