"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, Info } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { BLOCK_HOUSE_SIZES, blockHouseSize, blockPlanAt, blockPlanUrl, isBlockHouseSize } from "@/lib/block-plan-selection";
import { US_STATES } from "@/lib/us-states";
import type { BlockHouseSize, BlockPlan, BlockPlanManifest } from "@/types/block-districting";
import { BlockNationalMap } from "./block-national-map";
import { BlockStateMap } from "./block-state-map";
import { StateBlockExplorer } from "./state-block-explorer";

const anchorLabels: Record<BlockHouseSize, string> = {
  435: "Current House Size", 574: "Wyoming Rule", 692: "Cube Root Rule", 1000: "A Round 1,000",
};

export function BlockDistrictExplorer({ manifest }: { manifest: BlockPlanManifest }) {
  const router = useRouter();
  const params = useSearchParams();
  const [pending, startTransition] = React.useTransition();
  const rawCap = params.get("cap");
  const houseSize = blockHouseSize(rawCap);
  const selectedState = params.get("state")?.padStart(2, "0") ?? null;
  const plan = blockPlanAt(manifest, houseSize, selectedState);
  const stateExplorer = plan ? manifest.stateExplorers?.[plan.stateFips] : undefined;
  const explorerAssets = plan ? stateExplorer?.plans[plan.id] ?? (plan.stateFips === "26" ? manifest.michiganExplorer?.plans[plan.id] : undefined) : undefined;
  const cityAsset = stateExplorer?.cities ?? (plan?.stateFips === "26" ? manifest.michiganExplorer?.cities : undefined);
  const unsupportedCap = rawCap !== null && !isBlockHouseSize(Number(rawCap));
  const invalidState = selectedState !== null && plan === null;
  const navigate = React.useCallback((cap: BlockHouseSize, state: string | null) => {
    startTransition(() => router.push(blockPlanUrl(cap, state), { scroll: false }));
  }, [router, startTransition]);
  const selectNationalState = React.useCallback((fips: string) => navigate(houseSize, fips), [houseSize, navigate]);

  const exitState = React.useCallback(() => navigate(houseSize, null), [houseSize, navigate]);

  // Plan controls come first in the rail on every view: they choose which saved plan is on the map.
  const navigation = <div className="dd-section gap-3.5" aria-busy={pending}>
      <div className="grid gap-2">
        <div>
          <div className="dd-label-row">
            <h3 className="dd-label">House size</h3>
            <span className="dd-status" role="status"><span className="dd-led" data-state={pending ? "busy" : "on"} />{pending ? "Opening saved plan…" : `${houseSize.toLocaleString()} districts nationwide`}</span>
          </div>
          <p className="dd-meta">Today&rsquo;s House has 435 seats. Pick a larger size to see how the districts would change.</p>
        </div>
        <div className="dd-segmented" role="group" aria-label="Computed House sizes">
          {BLOCK_HOUSE_SIZES.map((cap) => (
            <Tooltip key={cap} delayDuration={100}>
              <TooltipTrigger asChild>
                <button type="button" className="dd-segment" aria-pressed={houseSize === cap}
                  onClick={() => navigate(cap, plan?.stateFips ?? null)}>
                  <span className="dd-segment-value">{cap.toLocaleString()}</span>
                </button>
              </TooltipTrigger>
              {/* Portaled outside .districts-ui, so the palette is set here; the arrow inherits it. */}
              <TooltipContent sideOffset={6} className="px-2 py-1 text-[11px] font-medium [--primary:#464a3b] [--primary-foreground:#ffffff]">{anchorLabels[cap]}</TooltipContent>
            </Tooltip>
          ))}
        </div>
        <details className="dd-meta"><summary className="w-fit cursor-pointer hover:text-foreground">About these sizes</summary><p className="mt-1">{BLOCK_HOUSE_SIZES.map((cap) => `${cap.toLocaleString()} ${anchorLabels[cap]}`).join(" · ")}.</p><p className="mt-1">The 574-seat benchmark is a saved comparison size. The apportionment demo calculates the Wyoming Rule separately at 573 seats.</p><p className="mt-1">How seats are divided among the states: <Link href="/apportionment" className="underline underline-offset-2 hover:text-foreground">Apportionment Demo</Link>.</p></details>
        {unsupportedCap && <p className="dd-notice" role="status">That House size has no computed block plan. Showing the 435-seat anchor; choose one of the four available sizes.</p>}
        {invalidState && <p className="dd-notice" role="status">That state is not in the 50-state catalog. Showing the national view.</p>}
      </div>

      <div className="grid gap-2">
        <div className="dd-label-row">
          <label htmlFor="block-state" className="dd-label">State</label>
          {plan && <button type="button" className="dd-link" onClick={exitState}><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />All 50 states</button>}
        </div>
        <select id="block-state" value={plan?.stateFips ?? ""} className="dd-input"
          onChange={(event) => navigate(houseSize, event.target.value || null)}>
          <option value="">National overview</option>
          {[...US_STATES].sort((a, b) => a.name.localeCompare(b.name)).map((state) => <option key={state.fips} value={state.fips}>{state.name}</option>)}
        </select>
        {!plan && <p className="dd-meta">Select a state on the map or from this list to inspect its districts.</p>}
      </div>
    </div>;

  const mapHeading = <div className="dd-rail-head">
    <p className="dd-kicker">House {houseSize.toLocaleString()} · 2020 Census</p>
    <h2 className="dd-title">{plan ? plan.stateName : "United States"}</h2>
    <p className="dd-sub">{plan ? `${plan.districtCount} district${plan.districtCount === 1 ? "" : "s"} · ${plan.blockCount.toLocaleString()} saved census blocks` : "All 50 states · select a state to explore"}</p>
  </div>;

  return (
    <div className="space-y-6" aria-busy={pending}>
      {plan ? (
        <>
          {explorerAssets && cityAsset
              ? <StateBlockExplorer key={`${houseSize}:${plan.id}`} navigation={navigation} heading={mapHeading} onExit={exitState} plan={plan} comparisonLayers={manifest.comparisonLayers?.[plan.stateFips]} landDisplay={manifest.landDisplays?.[plan.id]} explorer={explorerAssets} cities={cityAsset} cityMetadata={stateExplorer?.cityMetadata} />
              : <section className="dd-instrument" aria-label={`${plan.stateName} district map`}>
                  <div className="dd-rail"><div className="dd-primary">{mapHeading}{navigation}</div></div>
                  <div className="dd-stage overflow-y-auto p-3"><BlockStateMap key={plan.stateFips} plan={plan} comparisonLayers={manifest.comparisonLayers?.[plan.stateFips]} landDisplay={manifest.landDisplays?.[plan.id]} /></div>
                </section>}
          {explorerAssets
            ? <details className="dd-disclosure"><summary>Saved plan validation and benchmarks</summary><div className="dd-disclosure-body"><BlockPlanMetrics plan={plan} className="border-0 py-0 shadow-none" /></div></details>
            : <BlockPlanMetrics plan={plan} />}
        </>
      ) : (
        <BlockNationalMap key={houseSize} navigation={navigation} heading={mapHeading} manifest={manifest} houseSize={houseSize} onSelectState={selectNationalState} />
      )}
    </div>
  );
}

function BlockPlanMetrics({ plan, className }: { plan: BlockPlan; className?: string }) {
  const optimizer = plan.optimizer;
  const isCorrection = plan.runtimeScope === "correction_only_original_solve_reused";
  const policyName = plan.stateFips === "21" ? "exclave connection" : plan.stateFips === "36" ? "water and exclave connections" : "water connections";
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-[var(--dd-olive-deep)]" />Verified final plan</CardTitle>
        <CardDescription>Population balance and connectivity are checked independently of optimizer convergence.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <dl className="grid grid-cols-2 gap-5 lg:grid-cols-4">
          <Metric label="Resident population" value={plan.residentPopulation.toLocaleString()} />
          <Metric label="Ideal per district" value={(plan.residentPopulation / plan.districtCount).toLocaleString(undefined, { maximumFractionDigits: 3 })} />
          <Metric label="Largest population deviation" value={`${plan.maxDeviationPeople.toFixed(3)} ${plan.maxDeviationPeople === 1 ? "person" : "people"}`} detail={`${plan.maxDeviationPercent.toFixed(6)}% of ideal`} />
          <Metric label="Largest–smallest district" value={`${plan.populationRangePeople.toLocaleString()} ${plan.populationRangePeople === 1 ? "person" : "people"}`} />
        </dl>
        <div className="rounded-lg bg-muted/50 p-4 text-sm leading-6">
          <p className="font-medium">{plan.strictConnectivity ? "Every district is physically connected by shared edges." : `Every district is connected under the recorded ${policyName} policy.`}</p>
          {plan.strictConnectivity && <p className="text-muted-foreground">This check uses the complete census-block polygons, including water. It does not establish connectivity exclusively over land.</p>}
          {!plan.strictConnectivity && <p className="text-muted-foreground">{plan.recordedLinkCount} explicit connection{plan.recordedLinkCount === 1 ? " supplements" : "s supplement"} the shared-edge graph. Separate polygons remain separate across the gap; the dashed links do not change the geography.</p>}
          {plan.coordinateFrame === "alaska-continuous" && <p className="text-muted-foreground">Alaska is shown in a continuous longitude frame so the Aleutians stay together across the antimeridian. Display seams do not count as physical connections.</p>}
        </div>
        <details className="rounded-lg border p-4 text-sm">
          <summary className="cursor-pointer font-medium">Computation and validation details</summary>
          <div className="mt-3 space-y-3 text-muted-foreground">
            <p>{optimizer.kind === "direct_all_blocks_assignment" ? "This one-district plan assigns every block directly; no numerical optimization is needed." : optimizer.centersConverged
              ? `District centers converged after ${optimizer.outerIterations} outer iterations.`
              : optimizer.outerIterationLimitReached ? `The optimizer reached its ${optimizer.outerIterations}-iteration outer limit. The final assignments still passed the independent population and geometry checks.` : "The saved numerical record is retained with this plan."}</p>
            {optimizer.unsuccessfulInnerPassCount > 0 && <p className="flex items-start gap-2 text-[var(--dd-warn)]"><Info className="mt-1 h-4 w-4 shrink-0" />The historical solve contains {optimizer.unsuccessfulInnerPassCount} unsuccessful inner pass{optimizer.unsuccessfulInnerPassCount === 1 ? "" : "es"}. This is a validated final map, not a claim that every optimization pass converged.</p>}
            <p>{isCorrection ? "Correction" : "Measured pipeline"}: {(plan.pipelineSeconds / 60).toFixed(2)} minutes · peak process memory {(plan.peakMemoryBytes / 2 ** 20).toFixed(1)} MiB.{isCorrection ? " The original numerical solve was reused and is excluded from this correction timing." : " Timings come from historical runs with different execution conditions."}</p>
            <p>Whole blocks remain indivisible. Local repair and balancing need not find a global optimum, and the corrected boundaries are not exact power cells. No district computation runs in this browser.</p>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd>{detail && <dd className="text-xs text-muted-foreground">{detail}</dd>}</div>;
}
