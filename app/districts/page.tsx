import Link from "next/link";
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
import { DistrictsExplorer } from "@/components/districting/districts-explorer";
import { DistrictingMethodPanel } from "@/components/districting/districting-method-panel";
import { DistrictingStateLayout } from "@/components/districting/districting-state-layout";
import { StateDistrictSidebar } from "@/components/districting/state-district-sidebar";
import { StateDetailMap } from "@/components/districting/state-detail-map";
import { StatePlanReadiness } from "@/components/districting/state-plan-readiness";
import { getSeatCountsAfter } from "@/lib/apportionment-sequence";
import { CAP_MAX, CAP_MIN } from "@/lib/districting-cap-scale";
import { districtPlanLayerUrl } from "@/lib/district-plans";
import { loadDistrictPlan } from "@/lib/load-district-plan";
import {
  loadStatesGeoJSON,
  type StatesGeoJSON,
} from "@/lib/load-states-geojson";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { getStateByFips, isStateFips } from "@/lib/us-states";

interface DistrictsPageProps {
  searchParams: Promise<{ cap?: string; state?: string; tab?: string }>;
}

const MICHIGAN_FIPS = "26";

/**
 * Both tabs are self-contained: the deterministic local apportionment
 * sequence plus prebuilt static artifacts. No Python API round-trip, and no
 * plan geometry in the server payload — maps fetch it as static assets.
 */
export default async function DistrictsPage({ searchParams }: DistrictsPageProps) {
  const { cap: capParam, state: stateParam, tab: tabParam } = await searchParams;
  const initialCap = parseCapParam(capParam);
  const activeTab = tabParam === "districting" ? "districting" : "apportionment";
  const selectedStateFips = parseStateParam(stateParam);
  const states = await loadStatesGeoJSON();

  if (activeTab === "districting") {
    return (
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <div className="space-y-6">
          <TabIntro
            title="Districting"
            body="Districting turns each state's representatives into actual geographic districts. Today, that process is often optimized around political boundaries, incumbency, and litigation risk before compactness or equal representation. This demo uses a neutral balanced power-diagram pipeline to show what a population-balanced, geography-first plan looks like, currently at tract level with block-level plans as the intended next step."
          />
          <TopLevelTabs
            activeTab={activeTab}
            initialCap={initialCap}
            selectedStateFips={selectedStateFips}
          />
          <DistrictingTab states={states} stateFips={selectedStateFips} />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <div className="space-y-6">
        <TabIntro
          title="Apportionment"
          body="Increasing the size of the House lowers the number of people represented by each member and reduces the representation gap between large and small states. The current 435-seat cap locks in unusually large districts; a larger House would make representatives closer to their constituents. This demo shows how added seats would be assigned under the existing apportionment logic: one seat at a time, by the Method of Equal Proportions."
        />
        <TopLevelTabs
          activeTab={activeTab}
          initialCap={initialCap}
          selectedStateFips={selectedStateFips}
        />
        <DistrictsExplorer
          initialCap={initialCap}
          states={states}
          totalPopulation={TOTAL_APPORTIONMENT_POPULATION}
        />
      </div>
    </div>
  );
}

const TOTAL_APPORTIONMENT_POPULATION = Object.values(
  US_2020_APPORTIONMENT_POPULATIONS
).reduce((sum, population) => sum + population, 0);

function TabIntro({ body, title }: { body: string; title: string }) {
  return (
    <section className="mx-auto max-w-3xl text-center">
      <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
    </section>
  );
}

function TopLevelTabs({
  activeTab,
  initialCap,
  selectedStateFips,
}: {
  activeTab: "apportionment" | "districting";
  initialCap: number;
  selectedStateFips: string;
}) {
  return (
    <div className="flex justify-center">
      <div className="inline-flex rounded-xl bg-muted p-1.5 text-base">
        <Link
          href={`/districts${initialCap === CAP_MIN ? "" : `?cap=${initialCap}`}`}
          className={`rounded-lg px-6 py-2.5 font-medium ${
            activeTab === "apportionment"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Apportionment
        </Link>
        <Link
          href={`/districts?tab=districting&state=${selectedStateFips}`}
          className={`rounded-lg px-6 py-2.5 font-medium ${
            activeTab === "districting"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Districting
        </Link>
      </div>
    </div>
  );
}

async function DistrictingTab({
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

function parseCapParam(raw: string | undefined): number {
  if (!raw) return CAP_MIN;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) return CAP_MIN;
  return Math.max(CAP_MIN, Math.min(CAP_MAX, n));
}

function parseStateParam(raw: string | undefined): string {
  const fips = (raw ?? "20").padStart(2, "0");
  return isStateFips(fips) ? fips : "20";
}
