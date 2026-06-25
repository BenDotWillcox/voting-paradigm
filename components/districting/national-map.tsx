"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { geoPath } from "d3-geo";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { NATIONAL_VIEWBOX, nationalAlbers } from "@/lib/state-projection";
import type {
  StateFeature,
  StatesGeoJSON,
} from "@/lib/load-states-geojson";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { getStateByFips, isStateFips } from "@/lib/us-states";

interface NationalMapProps {
  /** GeoJSON FeatureCollection of all 50 states in raw lat/lon. */
  states: StatesGeoJSON;
  /** Current apportionment, FIPS -> seats. Drives the choropleth. */
  apportionment: Record<string, number>;
  /** The cap value behind `apportionment`, used in labels. */
  cap: number;
  /** State receiving the currently selected seat, if any. */
  highlightedFips?: string | null;
}

export function NationalMap({
  states,
  apportionment,
  cap,
  highlightedFips,
}: NationalMapProps) {
  const router = useRouter();

  const features: StateFeature[] = React.useMemo(
    () => states.features.filter((f) => isStateFips(String(f.id ?? ""))),
    [states]
  );

  const projection = React.useMemo(
    () => nationalAlbers(states, NATIONAL_VIEWBOX.width, NATIONAL_VIEWBOX.height),
    [states]
  );

  const pathGen = React.useMemo(() => geoPath(projection), [projection]);

  const { minSeats, maxSeats } = React.useMemo(() => {
    const vals = Object.values(apportionment);
    if (vals.length === 0) return { minSeats: 0, maxSeats: 1 };
    return {
      minSeats: Math.min(...vals),
      maxSeats: Math.max(...vals),
    };
  }, [apportionment]);

  const highlightedFeature = React.useMemo(
    () =>
      highlightedFips
        ? features.find((feature) => String(feature.id ?? "") === highlightedFips)
        : undefined,
    [features, highlightedFips]
  );

  return (
    <TooltipProvider delayDuration={100}>
      <div className="w-full">
        <svg
          viewBox={`0 0 ${NATIONAL_VIEWBOX.width} ${NATIONAL_VIEWBOX.height}`}
          className="h-auto w-full"
          role="img"
          aria-label={`US states colored by House seats at cap ${cap}`}
        >
          <g>
            {features
              .filter((feature) => String(feature.id ?? "") !== highlightedFips)
              .map((feature) => (
                <StatePath
                  key={String(feature.id ?? "")}
                  feature={feature}
                  pathGen={pathGen}
                  seats={apportionment[String(feature.id ?? "")] ?? 0}
                  minSeats={minSeats}
                  maxSeats={maxSeats}
                  cap={cap}
                  routerPush={(fips) => router.push(`/districts/${fips}`)}
                />
              ))}
            {highlightedFeature && (
              <AwardedStateLayer
                key={`${highlightedFips}-${cap}`}
                feature={highlightedFeature}
                pathGen={pathGen}
                seats={apportionment[highlightedFips ?? ""] ?? 0}
                cap={cap}
                routerPush={(fips) => router.push(`/districts/${fips}`)}
              />
            )}
          </g>
        </svg>
        <ColorLegend min={minSeats} max={maxSeats} />
      </div>
    </TooltipProvider>
  );
}

function StatePath({
  cap,
  feature,
  maxSeats,
  minSeats,
  pathGen,
  routerPush,
  seats,
}: {
  cap: number;
  feature: StateFeature;
  maxSeats: number;
  minSeats: number;
  pathGen: ReturnType<typeof geoPath>;
  routerPush: (fips: string) => void;
  seats: number;
}) {
  const fips = String(feature.id ?? "");
  const state = getStateByFips(fips);
  const fill = seatColor(seats, minSeats, maxSeats);
  const d = pathGen(feature) ?? "";
  const stateName = state?.name ?? feature.properties?.name ?? fips;
  const population = US_2020_APPORTIONMENT_POPULATIONS[fips] ?? 0;
  const peoplePerSeat = seats > 0 ? Math.round(population / seats) : 0;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <path
          d={d}
          fill={fill}
          stroke="var(--background)"
          strokeWidth={0.75}
          className="cursor-pointer transition-[fill,stroke,stroke-width] hover:stroke-foreground hover:stroke-[1.5px] focus:outline-none focus-visible:stroke-foreground focus-visible:stroke-[1.5px]"
          tabIndex={0}
          onClick={() => routerPush(fips)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              routerPush(fips);
            }
          }}
          aria-label={`${stateName}, ${seats} seat${seats === 1 ? "" : "s"}`}
        />
      </TooltipTrigger>
      <TooltipContent side="top">
        <div className="font-semibold">{stateName}</div>
        <div className="font-normal opacity-90 tabular-nums">
          Population {population.toLocaleString()}
        </div>
        <div className="font-normal opacity-90 tabular-nums">
          {seats} seat{seats === 1 ? "" : "s"} at cap {cap.toLocaleString()}
        </div>
        <div className="font-normal opacity-90 tabular-nums">
          1 seat / {peoplePerSeat.toLocaleString()} people
        </div>
        <div className="font-normal opacity-75">
          Open current 435-seat district map
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function AwardedStateLayer({
  cap,
  feature,
  pathGen,
  routerPush,
  seats,
}: {
  cap: number;
  feature: StateFeature;
  pathGen: ReturnType<typeof geoPath>;
  routerPush: (fips: string) => void;
  seats: number;
}) {
  const fips = String(feature.id ?? "");
  const state = getStateByFips(fips);
  const d = pathGen(feature) ?? "";
  const [cx, cy] = pathGen.centroid(feature);
  const stateName = state?.name ?? feature.properties?.name ?? fips;
  const population = US_2020_APPORTIONMENT_POPULATIONS[fips] ?? 0;
  const peoplePerSeat = seats > 0 ? Math.round(population / seats) : 0;
  const totalLabel = `${seats.toLocaleString()} seats`;
  const labelWidth = Math.max(78, totalLabel.length * 7 + 22);
  const labelX = stableSvgNumber(
    clamp(cx - labelWidth / 2, 6, NATIONAL_VIEWBOX.width - labelWidth - 6)
  );
  const labelY = stableSvgNumber(
    clamp(cy - 56, 6, NATIONAL_VIEWBOX.height - 46)
  );
  const labelCenterX = stableSvgNumber(labelX + labelWidth / 2);
  const labelTopY = stableSvgNumber(labelY + 16);
  const labelBottomY = stableSvgNumber(labelY + 31);

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <path
            d={d}
            fill="oklch(0.72 0.18 145)"
            stroke="oklch(0.32 0.13 145)"
            strokeWidth={2.5}
            className="district-award-state cursor-pointer focus:outline-none"
            tabIndex={0}
            onClick={() => routerPush(fips)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                routerPush(fips);
              }
            }}
            aria-label={`${stateName} gained one seat, now ${seats} seat${
              seats === 1 ? "" : "s"
            } at cap ${cap.toLocaleString()}`}
          />
        </TooltipTrigger>
        <TooltipContent side="top">
          <div className="font-semibold">{stateName}</div>
          <div className="font-normal opacity-90 tabular-nums">
            +1 seat, now {seats.toLocaleString()} total
          </div>
          <div className="font-normal opacity-90 tabular-nums">
            Population {population.toLocaleString()}
          </div>
          <div className="font-normal opacity-90 tabular-nums">
            1 seat / {peoplePerSeat.toLocaleString()} people
          </div>
          <div className="font-normal opacity-75">
            Open current 435-seat district map
          </div>
        </TooltipContent>
      </Tooltip>
      <g className="district-award-label" pointerEvents="none">
        <rect
          x={labelX}
          y={labelY}
          width={labelWidth}
          height={40}
          rx={6}
          fill="var(--background)"
          stroke="oklch(0.32 0.13 145)"
          strokeWidth={1.25}
        />
        <text
          x={labelCenterX}
          y={labelTopY}
          textAnchor="middle"
          className="fill-foreground text-[13px] font-semibold"
        >
          +1
        </text>
        <text
          x={labelCenterX}
          y={labelBottomY}
          textAnchor="middle"
          className="fill-muted-foreground text-[11px] tabular-nums"
        >
          {totalLabel}
        </text>
      </g>
    </>
  );
}

function seatColor(seats: number, min: number, max: number): string {
  if (max <= min) return "oklch(0.85 0.05 250)";
  const t =
    (Math.log(Math.max(seats, 1)) - Math.log(Math.max(min, 1))) /
    (Math.log(Math.max(max, 1)) - Math.log(Math.max(min, 1)));
  const clamped = Math.max(0, Math.min(1, t));
  const lightness = 0.92 - clamped * 0.45;
  const chroma = 0.04 + clamped * 0.16;
  return `oklch(${lightness.toFixed(3)} ${chroma.toFixed(3)} 265)`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function stableSvgNumber(value: number): number {
  return Number(value.toFixed(3));
}

function ColorLegend({ min, max }: { min: number; max: number }) {
  if (max <= min) return null;
  const gradientStops = Array.from({ length: 16 }, (_, i) => {
    const t = i / 15;
    const seats = Math.exp(Math.log(min) + t * (Math.log(max) - Math.log(min)));
    return `${seatColor(seats, min, max)} ${(t * 100).toFixed(1)}%`;
  }).join(", ");

  return (
    <div className="mt-3 space-y-1.5 text-xs text-muted-foreground">
      <div className="flex items-center justify-between">
        <span>Seats per state</span>
        <span className="tabular-nums">
          {min.toLocaleString()} to {max.toLocaleString()}
        </span>
      </div>
      <div
        className="h-3 w-full rounded-sm border"
        style={{ background: `linear-gradient(to right, ${gradientStops})` }}
        aria-hidden="true"
      />
      <div className="flex items-center justify-between tabular-nums">
        <span>{min.toLocaleString()}</span>
        <span>{max.toLocaleString()}</span>
      </div>
    </div>
  );
}
