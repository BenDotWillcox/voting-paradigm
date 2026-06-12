import { Binary, Database, Focus, Orbit, Waypoints } from "lucide-react";

import type { CachedDistrictPlan } from "@/types/districting";

interface StatePlanReadinessProps {
  plan?: CachedDistrictPlan | null;
  seats: number;
  population: number;
}

export function StatePlanReadiness({
  plan,
  seats,
  population,
}: StatePlanReadinessProps) {
  const targetPopulation = seats > 0 ? Math.round(population / seats) : 0;
  const unitCount =
    plan?.unit_count ??
    plan?.feature_collection?.features.length ??
    // Summary artifacts carry dissolved district outlines, so their
    // geometry count is seats, not source tracts — don't fall back to it.
    (plan?.display_unit === "district"
      ? null
      : plan?.display_topology?.objects.districts.geometries.length ?? null);
  const pctDeviation =
    plan && plan.target_population > 0
      ? (plan.max_population_imbalance / plan.target_population) * 100
      : null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <div className="rounded-md border p-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Binary className="h-4 w-4 text-primary" />
          Target
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Apportionment gives this state {seats.toLocaleString()} districts,
          each targeting about {targetPopulation.toLocaleString()} people.
        </p>
      </div>
      <div className="rounded-md border p-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Database className="h-4 w-4 text-primary" />
          Tracts
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {unitCount ? unitCount.toLocaleString() : "Cached"} populated census{" "}
          {plan?.unit ?? "tract"} units enter with boundary geometry, centroids,
          IDs, and population.
        </p>
      </div>
      <div className="rounded-md border p-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Focus className="h-4 w-4 text-primary" />
          Seed
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Population-weighted k-means++ places the initial district centers
          near where people live.
        </p>
      </div>
      <div className="rounded-md border p-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Orbit className="h-4 w-4 text-primary" />
          Rebalance
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Tracts join the best center while weights push over- and under-target
          districts back toward balance.
        </p>
      </div>
      <div className="rounded-md border p-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Waypoints className="h-4 w-4 text-primary" />
          Stable
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          The plan converged after {plan?.iterations ?? "cached"} iterations
          {pctDeviation !== null
            ? `; max deviation is ${pctDeviation.toFixed(2)}%.`
            : "."}
        </p>
      </div>
    </div>
  );
}
