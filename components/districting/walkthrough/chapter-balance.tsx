"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";

import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerData } from "@/lib/districting-explainer";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage, StageLayer, type StageBounds } from "./explainer-stage";
import { GraphEdges, GraphNodes, Silhouette } from "./layers";
import { PopulationBars, RoundTrace } from "./power-layers";
import { DISTRICT_COLORS, District, DistrictBlocks, FocusOutlines, Metrics, MoveMarks, PhaseBadge, districtBins, innerBounds, useBeforeAfter } from "./stage-layers";

const number = (value: number) => value.toLocaleString();
const gap = (value: number) => `±${value.toLocaleString(undefined, { maximumFractionDigits: value < 10 ? 2 : 0 })}`;

const MOVE_RULES = [
  ["Has residents", "An empty block cannot change the balance"],
  ["Touches the district it joins", "Checked on the block graph"],
  ["Leaves its district connected", "Its old district's blocks still link up without it"],
  ["Strictly improves balance", "The largest gap, then the sum of squared gaps"],
] as const;

/** Rebalancing: single-block moves that strictly improve balance and never disconnect a district. */
export function BalanceChapter({ data, projection, overview, coast }: {
  data: ExplainerData; projection: BlockMapProjection; overview: BlockMapCollection; coast: BlockMapCollection | null;
}) {
  const [step, setStep] = React.useState(0);
  const reduced = useReducedMotion();
  const after = useBeforeAfter(step <= 1, reduced);
  const { repair, labels, stats, points } = data;
  const view = repair.windows.firstBalance;
  const viewBounds = React.useMemo(() => innerBounds(view.bbox, 0.75, -0.125), [view]);
  const first = repair.rebalance[0];
  const county = (code: string) => stats.countyNames[code] ?? "Michigan";
  const finalBins = React.useMemo(() => districtBins(labels.final), [labels]);
  const moved = React.useMemo(() => new Map([[first.unit, first.target]]), [first]);
  const trace = React.useMemo(() => repair.rebalance.map((move) => move.maxDeviation), [repair]);
  const movePoints = React.useMemo(() => repair.rebalance.map((move) => move.point), [repair]);
  // The edges that touch the moved block, drawn over the window's whole graph.
  const focusEdges = React.useMemo(() => view.edges.filter(([a, b]) => a === first.unit || b === first.unit), [view, first]);
  const focusBlocks = React.useMemo(() => view.blocks.filter((block) => block.i === first.unit || focusEdges.some(([a, b]) => a === block.i || b === block.i)), [view, first, focusEdges]);

  const finals = repair.populations.final;
  const spread = Math.max(...finals) - Math.min(...finals);
  const fraction = repair.target - Math.floor(repair.target);
  const best = fraction === 0 ? 0 : Math.max(fraction, 1 - fraction);
  const early = repair.rebalance.slice(0, 3).map((move) => number(move.population));
  const laterLargest = Math.max(...repair.rebalance.slice(3).map((move) => move.population));

  const steps: (ChapterStep & { bounds: StageBounds })[] = [
    { title: "One block at a time", bounds: viewBounds,
      body: <><p>Balancing moves single populated blocks across district borders, one at a time. A move is accepted only if it strictly lowers the same score repair used:</p>
        <p className="dd-formula dd-formula-line">(max<sub>k</sub> |13P<sub>k</sub> − N|, Σ<sub>k</sub> (13P<sub>k</sub> − N)²)</p>
        <p>The first sends this {number(first.population)}-person block in {county(first.county)} from District {first.source + 1} to District {first.target + 1}, cutting the largest gap from {gap(repair.maxDeviation.repaired)} to {gap(first.maxDeviation)} people.</p></> },
    { title: "Never cut a district", bounds: viewBounds,
      body: <><p>A move is allowed only if the block touches the district it joins and the district it leaves stays connected without it, both checked on the block graph. The lines are this block&rsquo;s graph links: the district it leaves still holds together through its other blocks.</p>
        <p className="dd-meta mt-2">In graph terms, the block must not be a cut vertex of its district. Of the allowed moves, the one that improves balance most goes first.</p></> },
    { title: `${repair.rebalance.length} moves`, bounds: null,
      body: <p>{repair.rebalance.length} moves bring the largest gap from {gap(repair.maxDeviation.repaired)} people to <strong className="font-semibold text-foreground">{gap(repair.maxDeviation.final)} people</strong>: less than {Math.ceil(repair.maxDeviation.final)} people from the exact target. The first three move blocks of {early.join(", ")} people; after that, no block moved holds more than {laterLargest}.</p> },
    { title: "A local optimum", bounds: null,
      body: <p>The search stops when no single allowed move improves balance: a local optimum, not a proven best. Every district is within {gap(repair.maxDeviation.final)} people of the exact target, and the largest and smallest differ by {spread} people. With whole people the best possible is {gap(Math.round(best * 100) / 100)}, one person closer; swaps and multi-block moves that might reach it are not tried.</p> },
  ];
  const current = steps[step];
  const windowStep = step <= 1;

  const card = step === 0 ? <Metrics rows={[["From", <District key="s" id={first.source} />], ["To", <District key="t" id={first.target} />], ["Residents", number(first.population)], ["Largest gap", `${gap(repair.maxDeviation.repaired)} → ${gap(first.maxDeviation)}`]]} />
    : step === 1 ? <ul className="dd-rules mt-0">
      {MOVE_RULES.map(([rule, detail]) => <li key={rule} className="dd-rule" data-on>
        <span className="dd-led" data-state="on" aria-hidden="true" />
        <span><span className="font-medium text-foreground">{rule}</span><span className="dd-meta block">{detail}</span></span>
      </li>)}
    </ul>
      : step === 2 ? <div className="grid gap-2">
        <Metrics rows={[["Moves", String(repair.rebalance.length)], ["Largest gap", `${gap(repair.maxDeviation.final)} people`]]} />
        <p className="dd-meta">Less than {Math.ceil(repair.maxDeviation.final)} people from the exact target, in a district of {number(Math.round(repair.target))}.</p>
        <RoundTrace values={trace} current={trace.length - 1} label="largest gap after each move, log" />
      </div>
        : <div className="grid gap-2">
          <p className="dd-label">District population vs target</p>
          <PopulationBars populations={finals} target={repair.target} />
          <Metrics rows={[["Largest gap", gap(repair.maxDeviation.final)], ["Spread", `${spread} people`], ["Best possible", gap(Math.round(best * 100) / 100)], ["Target", number(Math.round(repair.target * 100) / 100)]]} />
        </div>;

  return (
    <ChapterConsole number={8} title="Rebalance" steps={steps} step={step} onStep={setStep}>
      <ExplainerStage projection={projection} bounds={current.bounds} padding={windowStep ? 0 : 0.12} points={points} showPoints={!windowStep}
        pointBins={finalBins} binColors={DISTRICT_COLORS} card={card}
        badge={windowStep ? <PhaseBadge after={after} /> : undefined}
        label={`Michigan rebalancing, step ${step + 1}: ${current.title}`}
        overlay={<StageLayer visible={step === 2}><MoveMarks points={movePoints} projection={projection} /></StageLayer>}>
        <Silhouette overview={overview} coast={coast} projection={projection} />
        <StageLayer visible={windowStep}>
          <DistrictBlocks blocks={view.blocks} projection={projection} stage={1} overrides={after ? moved : undefined} />
          <StageLayer visible={step === 1}>
            <GraphEdges blocks={view.blocks} edges={view.edges} projection={projection} opacity={0.35} />
            <GraphEdges blocks={focusBlocks} edges={focusEdges} projection={projection} width={2.4} opacity={1} />
            <GraphNodes blocks={focusBlocks} projection={projection} size={7} />
          </StageLayer>
          <FocusOutlines blocks={view.blocks} focus={view.focus} projection={projection} />
        </StageLayer>
      </ExplainerStage>
    </ChapterConsole>
  );
}
