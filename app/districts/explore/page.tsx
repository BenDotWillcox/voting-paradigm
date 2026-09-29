import type { Metadata } from "next";
import { preload } from "react-dom";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AlgorithmPlaybackPanel } from "@/components/districting/algorithm-playback-panel";
import { DistrictPlanMap } from "@/components/districting/district-plan-map";
import { DistrictPlanMetrics } from "@/components/districting/district-plan-metrics";
import { DistrictingMethodPanel } from "@/components/districting/districting-method-panel";
import { DistrictingStateLayout } from "@/components/districting/districting-state-layout";
import { StateDistrictSidebar } from "@/components/districting/state-district-sidebar";
import { StateDetailMap } from "@/components/districting/state-detail-map";
import { StatePlanReadiness } from "@/components/districting/state-plan-readiness";
import { getSeatCountsAfter } from "@/lib/apportionment-sequence";
import { CAP_MIN } from "@/lib/districting-cap-scale";
import { districtPlanLayerUrl } from "@/lib/district-plans";
import { loadDistrictPlan } from "@/lib/load-district-plan";
import {
  loadStatesGeoJSON,
  type StatesGeoJSON,
} from "@/lib/load-states-geojson";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { getStateByFips, isStateFips } from "@/lib/us-states";

export const metadata: Metadata = {
  title: "Districting explorer · Nebula Civitas",
};

interface DistrictsExplorePageProps {
  searchParams: Promise<{ state?: string }>;
}

const MICHIGAN_FIPS = "26";

/**
 * State-by-state explorer for the cached 435-seat balanced power-diagram
 * plans. Self-contained: the deterministic local apportionment sequence
 * plus prebuilt static artifacts; maps fetch geometry as static assets.
 */
export default async function DistrictsExplorePage({
  searchParams,
}: DistrictsExplorePageProps) {
  const { state } = await searchParams;
  const states = await loadStatesGeoJSON();

  return (
    <div className="container mx-auto max-w-7xl space-y-6 px-4 py-8">
      <section className="mx-auto max-w-3xl text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Districting explorer</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Districting turns each state&rsquo;s representatives into geographic
          districts. Today that process is often shaped by party, incumbency,
          and litigation risk before compactness or equal population. These
          plans come from a neutral balanced power-diagram pipeline over census
          tracts: population-balanced and geography-first, with block-level
          plans as the next quality step.
        </p>
      </section>
      <DistrictingView states={states} stateFips={parseStateParam(state)} />
    </div>
  );
}

async function DistrictingView({
  stateFips,
  states,
}: {
  stateFips: string;
  states: StatesGeoJSON;
}) {
  const state = getStateByFips(stateFips) ?? getStateByFips("20");
  const fips = state?.fips ?? "20";
  const seatCounts = getSeatCountsAfter(CAP_MIN);
  const seats = seatCounts[fips] ?? 0;
  const population = US_2020_APPORTIONMENT_POPULATIONS[fips] ?? 0;
  const michiganSeats = seatCounts[MICHIGAN_FIPS] ?? 13;
  const [plan, michiganPlan] = await Promise.all([
    loadDistrictPlan(fips, CAP_MIN, seats),
    loadDistrictPlan(MICHIGAN_FIPS, CAP_MIN, michiganSeats),
  ]);
  const stateFeature = states.features.find((feature) => String(feature.id ?? "") === fips);
  const michiganFeature = states.features.find(
    (feature) => String(feature.id ?? "") === MICHIGAN_FIPS
  );

  // Start the small outline fetch alongside the HTML instead of after
  // hydration. `as: "fetch"` + anonymous CORS matches a same-origin fetch().
  if (plan) {
    preload(districtPlanLayerUrl(fips, CAP_MIN, seats, "districts"), {
      as: "fetch",
      crossOrigin: "anonymous",
    });
  }

  return (
    <>
      <DistrictingStateLayout
        sidebar={<StateDistrictSidebar activeFips={fips} />}
      >
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {state?.name ?? fips} districting
              </CardTitle>
              <CardDescription>
                Current 435-seat plan. These cached artifacts are tract-level;
                block-level plans are the next quality step.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {plan && stateFeature ? (
                <DistrictPlanMap state={stateFeature} plan={plan} />
              ) : stateFeature ? (
                <StateDetailMap
                  states={{ type: "FeatureCollection", features: [stateFeature] }}
                  stateFips={fips}
                />
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">District metrics</CardTitle>
              <CardDescription>Current 435-seat plan.</CardDescription>
            </CardHeader>
            <CardContent>
              {plan ? (
                <DistrictPlanMetrics plan={plan} />
              ) : (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <dt className="text-muted-foreground">Seats</dt>
                  <dd className="text-right tabular-nums">{seats}</dd>
                  <dt className="text-muted-foreground">Population</dt>
                  <dd className="text-right tabular-nums">
                    {population.toLocaleString()}
                  </dd>
                </dl>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">How this was computed</CardTitle>
            <CardDescription>
              The algorithm path behind the {state?.name ?? fips} cached plan.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <StatePlanReadiness
              plan={plan}
              seats={seats}
              population={population}
            />
          </CardContent>
        </Card>
      </DistrictingStateLayout>

      {michiganFeature && michiganPlan ? (
        <AlgorithmPlaybackPanel michigan={michiganFeature} plan={michiganPlan} />
      ) : null}
      <DistrictingMethodPanel />
    </>
  );
}

function parseStateParam(raw: string | undefined): string {
  const fips = (raw ?? "20").padStart(2, "0");
  return isStateFips(fips) ? fips : "20";
}
