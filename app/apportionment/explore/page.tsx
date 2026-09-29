import type { Metadata } from "next";

import { ApportionmentExplorer } from "@/components/apportionment/apportionment-explorer";
import { CAP_MAX, CAP_MIN } from "@/lib/districting-cap-scale";
import { loadStatesGeoJSON } from "@/lib/load-states-geojson";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";

export const metadata: Metadata = {
  title: "Apportionment explorer · Nebula Civitas",
};

interface ApportionmentExplorePageProps {
  searchParams: Promise<{ cap?: string }>;
}

const TOTAL_APPORTIONMENT_POPULATION = Object.values(
  US_2020_APPORTIONMENT_POPULATIONS
).reduce((sum, population) => sum + population, 0);

/**
 * Interactive House-size explorer. Seat counts come from the deterministic
 * local priority sequence; no Python API round-trip.
 */
export default async function ApportionmentExplorePage({
  searchParams,
}: ApportionmentExplorePageProps) {
  const { cap } = await searchParams;
  const states = await loadStatesGeoJSON();

  return (
    <div className="container mx-auto max-w-7xl space-y-6 px-4 py-8">
      <section className="mx-auto max-w-3xl text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Apportionment explorer</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Increasing the size of the House lowers the number of people each
          member represents and changes how evenly seats divide among states.
          Resize the House and watch seats assigned one at a time by the
          Method of Equal Proportions, the rule used since 1941.
        </p>
      </section>
      <ApportionmentExplorer
        initialCap={parseCapParam(cap)}
        states={states}
        totalPopulation={TOTAL_APPORTIONMENT_POPULATION}
      />
    </div>
  );
}

function parseCapParam(raw: string | undefined): number {
  if (!raw) return CAP_MIN;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) return CAP_MIN;
  return Math.max(CAP_MIN, Math.min(CAP_MAX, n));
}
