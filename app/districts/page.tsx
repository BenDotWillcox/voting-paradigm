import type { Metadata } from "next";
import { Suspense } from "react";

import { BlockDistrictExplorer } from "@/components/districting/block-district-explorer";
import { CircuitBackdrop } from "@/components/districting/circuit-backdrop";
import { DeferUntilNear } from "@/components/districting/defer-until-near";
import { DistrictingWalkthrough } from "@/components/districting/walkthrough/districting-walkthrough";
import { blockPlanAt, nationalOverviewUrls } from "@/lib/block-plan-selection";
import { districtsMono } from "@/lib/districting-fonts";
import { loadBlockPlanManifest } from "@/lib/load-block-plans";

export const metadata: Metadata = {
  title: "Districting · Nebula Civitas",
  description:
    "Congressional lines are drawn by hand. Explore census-block district plans an algorithm computed for all 50 states at four House sizes, with population and connectivity checks.",
};

// Validated map payloads live in the configured runtime data root.
export const dynamic = "force-dynamic";

/**
 * Demo 3 in one page: how the plans are computed, walked through on Michigan
 * (prompts/demo-3-explainer.md), followed by the national/state block explorer
 * with every finished plan.
 */
export default async function DistrictsPage() {
  const manifest = await loadBlockPlanManifest();
  // The walkthrough draws Michigan with the explorer's own K13 outline and projection.
  const michiganPlan = manifest ? blockPlanAt(manifest, 435, "26") : null;
  const michigan = michiganPlan ? manifest?.stateExplorers?.["26"]?.plans[michiganPlan.id] : undefined;

  const explorerLoading = <div role="status" className="dd-explorer-skeleton"><span className="dd-spinner" aria-hidden="true" /><span className="dd-status">Opening the 50-state map…</span></div>;

  return (
    <div className={`districts-ui relative isolate min-h-[calc(100dvh-4rem)] ${districtsMono.variable}`}>
    <CircuitBackdrop />
    <div className="mx-auto max-w-[1920px] space-y-4 px-4 py-4 xl:px-6">
      <section>
        <p className="dd-kicker">Districting</p>
        <h1 className="mt-0.5 text-2xl font-semibold tracking-tight">A practical, apolitical algorithm</h1>
      </section>
      {manifest ? (<>
        {michigan && <DistrictingWalkthrough overviewUrl={michigan.overview.url} coastUrl={michigan.coast.url}
          explorerUrls={nationalOverviewUrls(manifest, 435)} />}
        <section id="explorer" className="scroll-mt-4 space-y-3" aria-labelledby="dd-explorer-title">
          <header className="dd-walkthrough-head">
            <p className="dd-kicker">The result · all 50 states</p>
            <h2 id="dd-explorer-title" className="text-xl font-semibold tracking-tight">Every state, computed the same way</h2>
          </header>
          {/* The explorer's national payloads are large: it mounts two screens ahead, by which
              time the walkthrough has usually fetched them into the cache in the background. */}
          <DeferUntilNear anchor="explorer" fallback={explorerLoading}>
            <Suspense fallback={explorerLoading}>
              <BlockDistrictExplorer manifest={manifest} />
            </Suspense>
          </DeferUntilNear>
        </section>
      </>) : (
        <div role="status" className="rounded-xl border bg-card p-8 text-center">
          <h2 className="font-semibold">District plans are unavailable</h2>
          <p className="mt-2 text-sm text-muted-foreground">The saved plan collection is not connected to this preview. Please try again after the map data is available.</p>
        </div>
      )}
    </div>
    </div>
  );
}
