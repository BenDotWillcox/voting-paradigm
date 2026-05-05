"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { fetchApportionmentAction } from "@/actions/districting-actions";
import { CAP_MIN } from "@/lib/districting-cap-scale";
import type { StatesGeoJSON } from "@/lib/load-states-geojson";
import type { ApportionmentDto } from "@/types/districting";

import { ApportionmentSummary } from "./apportionment-summary";
import { CapPicker } from "./cap-picker";
import { NationalMap } from "./national-map";

interface DistrictsExplorerProps {
  /** Initial apportionment fetched on the server (cap = `initialCap`). */
  initialApportionment: ApportionmentDto;
  /** The 435-baseline apportionment, used for "vs. current" deltas. */
  baselineApportionment: ApportionmentDto;
  /** Cap value behind `initialApportionment`. Drives picker initial state. */
  initialCap: number;
  /** GeoJSON of all 50 states, loaded once on the server. */
  states: StatesGeoJSON;
}

/**
 * Top-level client component for the districting overview.
 *
 * Owns:
 *  - the cap state (mirrored to `?cap=` in the URL so reloads stick)
 *  - the in-flight apportionment for the *currently displayed* cap
 *  - one server-action call per anchor selection
 *
 * The cap picker is a discrete-anchor toggle group rather than a slider:
 * we only ever compute results at the five educational anchors, so a
 * continuous control would imply commitments we don't keep.
 */
export function DistrictsExplorer({
  initialApportionment,
  baselineApportionment,
  initialCap,
  states,
}: DistrictsExplorerProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [apportionment, setApportionment] = React.useState<ApportionmentDto>(
    initialApportionment
  );
  const [pending, startTransition] = React.useTransition();
  const [error, setError] = React.useState<string | null>(null);

  // Track the most recent requested cap so out-of-order responses (user
  // clicks anchor B before anchor A's fetch finishes) can be discarded.
  const latestCapRef = React.useRef(initialCap);

  const handleCapChange = React.useCallback(
    (nextCap: number) => {
      latestCapRef.current = nextCap;

      // Mirror to the URL so a reload stays at the same anchor.
      const params = new URLSearchParams(searchParams.toString());
      if (nextCap === CAP_MIN) {
        params.delete("cap");
      } else {
        params.set("cap", String(nextCap));
      }
      router.replace(
        `/districts${params.size ? `?${params.toString()}` : ""}`,
        { scroll: false }
      );

      // If the data we already have matches, skip the round trip.
      if (apportionment.cap === nextCap) return;

      startTransition(async () => {
        const result = await fetchApportionmentAction(nextCap);
        // Bail if the user moved on while we were waiting.
        if (latestCapRef.current !== nextCap) return;
        if (!result.isSuccess || !result.data) {
          setError(result.message);
          return;
        }
        setError(null);
        setApportionment(result.data);
      });
    },
    [apportionment.cap, router, searchParams]
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="space-y-6">
        <div className="rounded-xl border bg-card p-6 shadow-sm">
          <CapPicker cap={apportionment.cap} onCapChange={handleCapChange} />
        </div>

        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <NationalMap
            states={states}
            apportionment={apportionment.apportionment}
            cap={apportionment.cap}
          />
        </div>

        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            Districting API error: {error}
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          Maps shown are state outlines colored by the seat count each state
          would receive at the chosen House size. Real congressional-district
          polygons land in step 4 alongside the algorithmic redistricting
          pipeline. Click a state for its detail page.
        </p>
      </div>

      <aside className="space-y-4">
        <ApportionmentSummary
          apportionment={apportionment}
          baseline={baselineApportionment}
          loading={pending}
        />
      </aside>
    </div>
  );
}
