"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowDown, Info } from "lucide-react";

import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import { blockPlanUrl } from "@/lib/block-plan-selection";
import { jumpToSection } from "../defer-until-near";
import type { EnactedFeature, ExplainerData } from "@/lib/districting-explainer";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { MAP_COLORS } from "@/lib/districts-palette";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage, StageLayer } from "./explainer-stage";
import { Silhouette, WALKTHROUGH_COLORS, usePath } from "./layers";
import { StateClip } from "./power-layers";
import { DISTRICT_COLORS, Metrics } from "./stage-layers";
import { PanelStage, StatePair } from "./extremes-figure";

const number = (value: number) => value.toLocaleString();
const gap = (value: number) => `±${value.toLocaleString(undefined, { maximumFractionDigits: value < 10 ? 2 : 0 })}`;
const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;

function Checklist({ items }: { items: { on: boolean; label: string; detail: React.ReactNode }[] }) {
  return <ul className="dd-rules mt-0">
    {items.map((item) => <li key={item.label} className="dd-rule" data-on={item.on || undefined}>
      <span className="dd-led" data-state={item.on ? "on" : undefined} aria-hidden="true" />
      <span><span className="font-medium text-foreground">{item.label}</span><span className="dd-meta block">{item.detail}</span></span>
      <span className="sr-only">{item.on ? "(checked)" : "(not claimed)"}</span>
    </li>)}
  </ul>;
}

/** The computed plan, from the explorer's own district outlines. */
const ComputedDistricts = React.memo(function ComputedDistricts({ overview, projection }: { overview: BlockMapCollection; projection: BlockMapProjection }) {
  const path = usePath(projection);
  return <g>{overview.features.map((feature, index) => <path key={index} d={path(feature) ?? ""} fillRule="evenodd"
    fill={DISTRICT_COLORS[Number(feature.properties?.district_id)]} fillOpacity={0.72}
    stroke={MAP_COLORS.line} strokeOpacity={0.55} strokeWidth={0.8} vectorEffect="non-scaling-stroke" />)}</g>;
});

/** The enacted districts, clipped to the explorer's land outline so both maps share one coastline. */
const EnactedDistricts = React.memo(function EnactedDistricts({ features, projection, clipId, filled }: {
  features: EnactedFeature[]; projection: BlockMapProjection; clipId: string; filled: boolean;
}) {
  const path = usePath(projection);
  const shapes = React.useMemo(() => features.map((feature) => path(feature) ?? ""), [features, path]);
  return <g clipPath={`url(#${clipId})`} strokeLinejoin="round">
    {shapes.map((d, index) => <path key={index} d={d} fill={filled ? WALKTHROUGH_COLORS.land : "none"} fillRule="evenodd"
      stroke={MAP_COLORS.selectionCasing} strokeWidth={filled ? 0 : 3.6} vectorEffect="non-scaling-stroke" />)}
    {shapes.map((d, index) => <path key={`line-${index}`} d={d} fill="none" stroke={MAP_COLORS.selection} strokeWidth={filled ? 1.2 : 1.6} vectorEffect="non-scaling-stroke" />)}
  </g>;
});

function EnactedLabels({ features, projection }: { features: EnactedFeature[]; projection: BlockMapProjection }) {
  return <g>{features.map((feature) => {
    const [x, y] = projection.projectPoint(feature.properties.labelPoint);
    return <text key={feature.properties.district} x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={14} fontWeight={700}
      fontFamily="var(--dd-mono)" fill={MAP_COLORS.selection} stroke={MAP_COLORS.selectionCasing} strokeWidth={3.5} paintOrder="stroke">{feature.properties.district}</text>;
  })}</g>;
}

/** Each design choice behind what the method leaves out, with its reason and its cost. */
function Decisions({ items }: { items: { label: string; why: React.ReactNode }[] }) {
  return <ul className="dd-decisions">
    {items.map((item) => <li key={item.label}>
      <span className="font-medium text-foreground">{item.label}</span>
      <span className="dd-meta block">{item.why}</span>
    </li>)}
  </ul>;
}

/** What each table measure means and which direction is better, shown on hover or focus. */
const TIPS: Record<string, string> = {
  "Polsby-Popper, mean": "Compactness, 4πA ÷ P²: a district's area against a circle with the same perimeter. 1 is a perfect circle; near 0 is long or tangled. Higher is more compact. This is the average over all districts.",
  "Least compact": "The lowest Polsby-Popper score on the map: its most sprawling district. Higher is better.",
  near: "Districts that reach within 10 km of downtown. More districts means the city is split more ways.",
};

function Measure({ label, tip }: { label: string; tip?: string }) {
  if (!tip) return <>{label}</>;
  return <Tooltip delayDuration={100}>
    <TooltipTrigger asChild>
      <button type="button" className="dd-measure" aria-label={`${label}: ${tip}`}>{label}<Info aria-hidden="true" /></button>
    </TooltipTrigger>
    {/* Portaled outside .districts-ui, so the palette is set here, as in the explorer. */}
    <TooltipContent side="top" sideOffset={6} className="max-w-64 px-2.5 py-1.5 text-[11px] leading-4 font-normal [--primary:#464a3b] [--primary-foreground:#ffffff]">{tip}</TooltipContent>
  </Tooltip>;
}

function Source({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">{children}</a>;
}

/** Why each serving map is on this page, with its source; Rucho v. Common Cause sits in the intro. */
const CASES: Record<string, React.ReactNode> = {
  "37": <>North Carolina&rsquo;s supreme court struck the state&rsquo;s maps in 2022, then reversed itself 5–2 in 2023 after its majority changed; the legislature then drew this map. <Source href="https://law.justia.com/cases/north-carolina/supreme-court/2023/413pa21-2.html">Harper v. Hall</Source></>,
  "17": <>Democrats drew this map in 2021 for 14 of 17 seats, up from 13 of 18, and the Princeton Gerrymandering Project graded it F. <Source href="https://gerrymander.princeton.edu/reforms/IL">Report card</Source></>,
  "48": <>Republicans drew this map in 2021. In 2025 Texas redrew it mid-decade; a federal panel blocked that map as a racial gerrymander, and the Supreme Court let it stand for 2026. <Source href="https://thearp.org/litigation/lulac-v-abbott/">LULAC v. Abbott</Source></>,
  "24": <>A state judge struck Maryland&rsquo;s 2021 Democratic map in 2022 as an extreme partisan gerrymander; this is the court-ordered replacement. <Source href="https://redistricting.lls.edu/case/szeliga-v-lamone/">Szeliga v. Lamone</Source></>,
};
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
const list = (items: string[]) => items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
const GERRYMANDERS = 2;

/** What the saved plan was checked for, the decisions behind what it leaves out, and enacted maps beside it. */
export function ChecksChapter({ data, projection, overview, coast }: {
  data: ExplainerData; projection: BlockMapProjection; overview: BlockMapCollection; coast: BlockMapCollection | null;
}) {
  const [step, setStep] = React.useState(0);
  const [pick, setPick] = React.useState(0);
  const { validation, enacted, extremes } = data.checks;
  const { result, officialTotals, geometry } = validation;
  const { computed, enacted: drawn, compactness } = enacted;
  const clipId = `dd-clip-${React.useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const districts = result.district_populations.length;
  const connected = result.policy_components.filter((count) => count === 1).length;
  const onePolygon = result.physical_polygon_components.filter((count) => count === 1).length;
  const fraction = data.repair.target - Math.floor(data.repair.target);
  const best = Math.round((fraction === 0 ? 0 : Math.max(fraction, 1 - fraction)) * 100) / 100;
  const compact = { computed: mean(compactness.computed), enacted: mean(compactness.enacted) };
  const chosen = extremes[pick];
  const { focus, leastCompact } = chosen.callouts;

  const checked = [
    { on: officialTotals.validated, label: "Census totals match", detail: `${number(officialTotals.blockCount)} blocks and ${number(officialTotals.residentPopulation)} residents, as published` },
    { on: result.checks.all_saved_assignments_reconciled === true, label: "Every block assigned once", detail: `All ${number(result.block_count)} blocks, each to one district` },
    { on: result.checks.official_dbf_populations_recomputed === true, label: "Populations re-added", detail: `From the Census source file: largest gap ${gap(result.max_absolute_deviation_people)}` },
    { on: connected === districts, label: "Each district connected", detail: `${connected} of ${districts} on the block graph` },
    { on: onePolygon === districts && geometry.district_coverage_is_valid && geometry.district_overlap_area_square_meters === 0, label: "One valid polygon each", detail: "No gaps or overlaps between districts" },
  ];
  const decisions = [
    { label: "Stop at a local optimum", why: `A fast, repeatable search: the same inputs give the same map. The cost: ${gap(best)} was possible and ${gap(result.max_absolute_deviation_people)} was reached.` },
    { label: "No compactness score", why: "Choosing among competing compactness measures is itself a judgment call. Squared distances favor compact shapes on their own." },
    { label: "County and city lines ignored", why: `Respecting lines means choosing which ones matter, an opening for bias. The cost: ${computed.countiesSplit} of ${computed.counties} counties split.` },
    { label: "Nothing beyond people and places", why: "Communities of interest, race and election results are left out on purpose, so the map cannot be steered toward or against any group or party." },
  ];

  const steps: ChapterStep[] = [
    { title: "Checked after the solve",
      body: <><p>A separate validator re-read the saved plan; it never solves or repairs anything. It just checks that every rule is satisfied.</p>
        <div className="mt-3"><Checklist items={checked} /></div></> },
    { title: "Decisions, not oversights",
      body: <><p>Passing those checks means the map follows its rules. What the method leaves out was decided on purpose, and each choice has a cost.</p>
        <div className="mt-3"><Decisions items={decisions} /></div></> },
    { title: "Gerrymandering, side by side",
      body: <><p>Partisan gerrymandering is not hypothetical. In 2019 the Supreme Court ruled 5–4 that federal courts cannot police it, leaving it to the states (<Source href="https://en.wikipedia.org/wiki/Rucho_v._Common_Cause">Rucho v. Common Cause</Source>). Both parties draw maps to win. Here are four serving maps beside this method&rsquo;s plans for the same states.</p>
        <div className="dd-segmented dd-segmented-2 mt-3" role="group" aria-label="State">
          {extremes.map((state, index) => <button key={state.stateFips} type="button" className="dd-segment" aria-pressed={pick === index} onClick={() => setPick(index)}>
            <span className="dd-segment-value">{state.state}</span>
          </button>)}
        </div>
        <p className="dd-meta mt-3">Odd shapes alone do not prove intent; they show how far lines bend to reach or avoid particular voters. Shown: maps serving the 119th Congress (2025–26), from Census cartographic boundaries.</p></> },
    { title: "Michigan's enacted map",
      body: <p>Michigan took the job away from its legislature: a 2018 ballot initiative created an Independent Citizens Redistricting Commission, which drew this map in 2021 under criteria ranked in the state constitution: equal population and the Voting Rights Act first, then contiguity, communities of interest, partisan fairness, no favoring of incumbents, county, city and township lines, and compactness.</p> },
    { title: "Side by side",
      body: <><p>The black lines are the enacted borders over the computed districts. The computed map is far closer to equal population ({gap(computed.maxDeviation)} against {gap(drawn.maxDeviation)}); the enacted map splits fewer counties ({drawn.countiesSplit} against {computed.countiesSplit}), and on compactness the two are close ({compact.enacted.toFixed(2)} against {compact.computed.toFixed(2)}). The commission weighed lines and shapes; this method did not.</p>
        <p className="dd-formula">Polsby-Popper = 4πA / P²</p>
        <p className="dd-meta">1 for a circle, near 0 for a sprawling shape. Measured on land shapes simplified to about 500 m, so block-edge zigzags do not count. Neither column measures fairness.</p></> },
    { title: "Explore all 50 states",
      body: <><p>Every state was computed the same way. The explorer below opens on the whole country at House 435; pick any state to inspect its districts county by county, or try a larger House.</p>
        <Link href={`${blockPlanUrl(435)}#explorer`} scroll={false} className="dd-tool mt-3 inline-flex"
          onClick={() => jumpToSection("explorer")}>
          <ArrowDown aria-hidden="true" />Explore all 50 states</Link></> },
  ];

  const compare: [string, string, string][] = [
    ["Largest gap", gap(computed.maxDeviation), gap(drawn.maxDeviation)],
    ["Spread, people", number(computed.spread), number(drawn.spread)],
    [`Counties split, of ${computed.counties}`, String(computed.countiesSplit), String(drawn.countiesSplit)],
    ["Polsby-Popper, mean", compact.computed.toFixed(2), compact.enacted.toFixed(2)],
    ["Least compact", Math.min(...compactness.computed).toFixed(2), Math.min(...compactness.enacted).toFixed(2)],
  ];
  const pairRows: [string, string, string][] = [
    ["Polsby-Popper, mean", mean(chosen.computed.pp).toFixed(2), mean(chosen.enacted.pp).toFixed(2)],
    ["Least compact", Math.min(...chosen.computed.pp).toFixed(2), Math.min(...chosen.enacted.pp).toFixed(2)],
    [`Districts near ${focus.city}`, String(focus.computed), String(focus.enacted)],
  ];
  const table = (rows: [string, string, string][], right: string) => <table className="dd-compare">
    <thead><tr><th scope="col"><span className="sr-only">Measure</span></th><th scope="col">Computed</th><th scope="col">{right}</th></tr></thead>
    <tbody>{rows.map(([label, a, b]) => <tr key={label}><th scope="row"><Measure label={label} tip={TIPS[label] ?? (label.startsWith("Districts near") ? TIPS.near : undefined)} /></th><td>{a}</td><td>{b}</td></tr>)}</tbody>
  </table>;
  const card = step === 0 ? <Metrics rows={[["Blocks", number(result.block_count)], ["Residents", number(result.total_population)], ["Largest gap", gap(result.max_absolute_deviation_people)], ["Connected", `${connected} of ${districts}`]]} />
    : step === 1 ? <Metrics rows={[["Counties split", `${computed.countiesSplit} of ${computed.counties}`], ["Tracts split", number(validation.tractsSplit)]]} />
      : step === GERRYMANDERS ? <div className="grid gap-2">{table(pairRows, "Serving")}<p className="dd-meta">Michigan, same measure: {compact.computed.toFixed(2)} computed, {compact.enacted.toFixed(2)} enacted.</p></div>
        : step === 3 ? <Metrics rows={[["Largest gap", gap(drawn.maxDeviation)], ["Spread", `${number(drawn.spread)} people`], ["Counties split", `${drawn.countiesSplit} of ${drawn.counties}`], ["Source", "Census TIGER 2023"]]} />
          : step === 4 ? table(compare, "Enacted")
            : <Metrics rows={[["States", "50"], ["House sizes", "435 to 1,000"], ["Districts at 435", "435"], ["Michigan's gap", gap(result.max_absolute_deviation_people)]]} />;
  const label = `District maps, step ${step + 1}: ${steps[step].title}`;
  // Each state's story sits on the figure, beside the map it describes.
  const stateInfo = <div className="grid gap-1.5">
    <p className="dd-label">{chosen.state}</p>
    <ul className="dd-sources mt-0">
      <li>{CASES[chosen.stateFips]}</li>
      <li>Within {focus.radiusKm} km of downtown {focus.city}, the serving map has {focus.enacted} district{focus.enacted === 1 ? "" : "s"}; the computed plan has {focus.computed}.</li>
      <li>The outlined {ordinal(leastCompact.district)} district is the serving map&rsquo;s least compact (Polsby-Popper {leastCompact.pp.toFixed(2)}, where 1 is a circle and lower is more sprawling){leastCompact.cities.length > 1 ? `, stretching to take in ${list(leastCompact.cities)}` : leastCompact.cities.length === 1 ? `, around ${leastCompact.cities[0]}` : ""}.</li>
    </ul>
  </div>;

  return (
    <ChapterConsole number={9} title="What was checked, and what wasn't" steps={steps} step={step} onStep={setStep} onwardLabel="50-state map">
      {step === GERRYMANDERS ? <PanelStage key={`pair-${chosen.stateFips}`} label={`${label}, ${chosen.state}`} card={card} aside={stateInfo}><StatePair state={chosen} /></PanelStage>
        : <ExplainerStage projection={projection} bounds={null} card={card} label={label}>
          <StateClip id={clipId} overview={overview} projection={projection} />
          <Silhouette overview={overview} coast={coast} projection={projection} />
          <StageLayer visible={step !== 3}><ComputedDistricts overview={overview} projection={projection} /></StageLayer>
          <StageLayer visible={step === 3}>
            <EnactedDistricts features={enacted.features} projection={projection} clipId={clipId} filled />
            <EnactedLabels features={enacted.features} projection={projection} />
          </StageLayer>
          <StageLayer visible={step === 4}><EnactedDistricts features={enacted.features} projection={projection} clipId={clipId} filled={false} /></StageLayer>
        </ExplainerStage>}
    </ChapterConsole>
  );
}
