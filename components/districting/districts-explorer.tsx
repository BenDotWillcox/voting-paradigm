"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  getRecentAllocations,
  getSeatCountsAfter,
} from "@/lib/apportionment-sequence";
import { CAP_MAX, CAP_MIN } from "@/lib/districting-cap-scale";
import type { StatesGeoJSON } from "@/lib/load-states-geojson";
import type { ApportionmentDto } from "@/types/districting";

import { AllocationExplainer } from "./allocation-explainer";
import { CapPicker } from "./cap-picker";
import { NationalMap } from "./national-map";
import { RepresentationMetrics } from "./representation-metrics";

interface DistrictsExplorerProps {
  /** Initial apportionment fetched on the server (cap = `initialCap`). */
  initialApportionment: ApportionmentDto;
  /** Cap value behind `initialApportionment`. Drives picker initial state. */
  initialCap: number;
  /** GeoJSON of all 50 states, loaded once on the server. */
  states: StatesGeoJSON;
}

/**
 * Top-level client component for the national apportionment overview.
 *
 * Owns the selected House size, mirrors it to `?cap=`, and derives the
 * apportionment locally from the deterministic priority sequence.
 */
export function DistrictsExplorer({
  initialApportionment,
  initialCap,
  states,
}: DistrictsExplorerProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [cap, setCap] = React.useState(initialCap);
  const displayedApportionment = React.useMemo(
    () => getSeatCountsAfter(cap),
    [cap]
  );
  const baselineApportionment = React.useMemo(
    () => getSeatCountsAfter(CAP_MIN),
    []
  );
  const lastAwarded = React.useMemo(
    () => getRecentAllocations(cap, 1)[0] ?? null,
    [cap]
  );

  const handleCapChange = React.useCallback(
    (nextCap: number) => {
      const bounded = Math.max(CAP_MIN, Math.min(CAP_MAX, Math.round(nextCap)));
      setCap(bounded);
    },
    []
  );

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      const currentCapParam = searchParams.get("cap");
      if (
        (cap === CAP_MIN && currentCapParam === null) ||
        currentCapParam === String(cap)
      ) {
        return;
      }

      // Mirror to the URL so a reload stays at the same anchor.
      const params = new URLSearchParams(searchParams.toString());
      if (cap === CAP_MIN) {
        params.delete("cap");
      } else {
        params.set("cap", String(cap));
      }
      router.replace(
        `/districts${params.size ? `?${params.toString()}` : ""}`,
        { scroll: false }
      );
    }, 250);

    return () => window.clearTimeout(timer);
  }, [cap, router, searchParams]);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
      <div className="space-y-4">
        <div className="rounded-xl border bg-card p-2.5 shadow-sm">
          <CapPicker
            cap={cap}
            maxCap={CAP_MAX}
            onCapChange={handleCapChange}
          />
        </div>

        <RepresentationMetrics
          cap={cap}
          apportionment={displayedApportionment}
          baselineApportionment={baselineApportionment}
          totalPopulation={initialApportionment.total_apportionment_population}
        />

        <div className="rounded-xl border bg-card p-2 shadow-sm">
          <NationalMap
            states={states}
            apportionment={displayedApportionment}
            cap={cap}
            highlightedFips={lastAwarded?.stateFips}
          />
        </div>

        <p className="text-[11px] leading-snug text-muted-foreground">
          State outlines are colored by the seat count each state would receive
          at the selected House size. The outlined state received the selected
          seat. Click a state to inspect its current 435-seat districting plan.
        </p>
      </div>

      <aside className="space-y-2">
        <AllocationExplainer cap={cap} />
      </aside>
    </div>
  );
}
