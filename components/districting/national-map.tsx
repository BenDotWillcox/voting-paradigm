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
import { getStateByFips, isStateFips } from "@/lib/us-states";

interface NationalMapProps {
  /** GeoJSON FeatureCollection of all 50 states in raw lat/lon. */
  states: StatesGeoJSON;
  /** Current apportionment, FIPS -> seats. Drives the choropleth. */
  apportionment: Record<string, number>;
  /** The cap value behind `apportionment`, used in click-through links. */
  cap: number;
}

/**
 * SVG choropleth of the 50 US states, colored by seat count at the
 * current cap.  Click a state to drill into its detail page.
 *
 * Rendering pipeline:
 *   - Raw lat/lon GeoJSON in (`states`) →
 *   - `geoAlbersUsa().fitExtent(...)` projects into the SVG viewBox
 *     (the canonical 975×610 d3-geo space, with AK/HI as insets in the
 *     lower-left corner) →
 *   - `geoPath(projection)` emits SVG `d` strings.
 *
 * Earlier iterations consumed pre-projected TopoJSON; we now project
 * at render time so the same source data feeds both this component
 * and the per-state Albers used in `StateDetailMap`.
 */
export function NationalMap({
  states,
  apportionment,
  cap,
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

  return (
    <TooltipProvider delayDuration={100}>
      <div className="w-full">
        <svg
          viewBox={`0 0 ${NATIONAL_VIEWBOX.width} ${NATIONAL_VIEWBOX.height}`}
          className="w-full h-auto"
          role="img"
          aria-label={`US states colored by House seats at cap ${cap}`}
        >
          <g>
            {features.map((f) => {
              const fips = String(f.id ?? "");
              const state = getStateByFips(fips);
              const seats = apportionment[fips] ?? 0;
              const fill = seatColor(seats, minSeats, maxSeats);
              const d = pathGen(f) ?? "";
              const stateName = state?.name ?? f.properties?.name ?? fips;

              return (
                <Tooltip key={fips}>
                  <TooltipTrigger asChild>
                    <path
                      d={d}
                      fill={fill}
                      stroke="var(--background)"
                      strokeWidth={0.75}
                      className="cursor-pointer transition-[fill,stroke] hover:stroke-foreground hover:stroke-[1.5px] focus:outline-none focus-visible:stroke-foreground focus-visible:stroke-[1.5px]"
                      tabIndex={0}
                      onClick={() =>
                        router.push(`/districts/${fips}?cap=${cap}`)
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          router.push(`/districts/${fips}?cap=${cap}`);
                        }
                      }}
                      aria-label={`${stateName}, ${seats} seat${seats === 1 ? "" : "s"}`}
                    />
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <div className="font-semibold">{stateName}</div>
                    <div className="font-normal opacity-90 tabular-nums">
                      {seats} seat{seats === 1 ? "" : "s"} at cap {cap.toLocaleString()}
                    </div>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </g>
        </svg>
        <ColorLegend min={minSeats} max={maxSeats} />
      </div>
    </TooltipProvider>
  );
}

/**
 * Sequential color scale on the seat count, log-spaced.
 *
 * Logarithmic interpolation because seat counts span ~3 orders of
 * magnitude at high caps (Wyoming with 1 vs California with ~1,316).
 * A linear scale would push every state except CA and TX to the
 * bottom of the palette and lose all visible signal.
 */
function seatColor(seats: number, min: number, max: number): string {
  if (max <= min) return "oklch(0.85 0.05 250)";
  const t =
    (Math.log(Math.max(seats, 1)) - Math.log(Math.max(min, 1))) /
    (Math.log(Math.max(max, 1)) - Math.log(Math.max(min, 1)));
  const clamped = Math.max(0, Math.min(1, t));
  // Indigo ramp: light at low seat counts, deep indigo at high.
  // OKLch keeps perceptual lightness uniform.
  const lightness = 0.92 - clamped * 0.45; // 0.92 → 0.47
  const chroma = 0.04 + clamped * 0.16; // 0.04 → 0.20
  return `oklch(${lightness.toFixed(3)} ${chroma.toFixed(3)} 265)`;
}

function ColorLegend({ min, max }: { min: number; max: number }) {
  if (max <= min) return null;
  // 6 buckets, geometrically spaced.
  const stops = 6;
  const ticks: { seats: number; color: string }[] = [];
  for (let i = 0; i < stops; i += 1) {
    const t = i / (stops - 1);
    const seats = Math.round(
      Math.exp(Math.log(min) + t * (Math.log(max) - Math.log(min)))
    );
    ticks.push({ seats, color: seatColor(seats, min, max) });
  }
  return (
    <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
      <span>Seats per state</span>
      <div className="flex items-center gap-1">
        {ticks.map((t, i) => (
          <div key={i} className="flex flex-col items-center">
            <div
              className="w-8 h-3 rounded-sm border"
              style={{ background: t.color }}
            />
            <span className="tabular-nums mt-0.5">{t.seats}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
