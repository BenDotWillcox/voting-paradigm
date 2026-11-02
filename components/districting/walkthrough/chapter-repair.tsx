"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";

import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerData } from "@/lib/districting-explainer";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage, StageLayer, type StageBounds } from "./explainer-stage";
import { Silhouette } from "./layers";
import { RoundTrace } from "./power-layers";
import { DISTRICT_COLORS, District, DistrictBlocks, FocusOutlines, Metrics, MoveMarks, NoTouch, PhaseBadge, districtBins, innerBounds, unitsPerPixel, useBeforeAfter } from "./stage-layers";

const number = (value: number) => value.toLocaleString();
const gap = (value: number) => `±${value.toLocaleString(undefined, { maximumFractionDigits: value < 10 ? 2 : 0 })}`;

/** Repair: every detached piece of the power diagram joins a district it touches. */
export function RepairChapter({ data, projection, overview, coast }: {
  data: ExplainerData; projection: BlockMapProjection; overview: BlockMapCollection; coast: BlockMapCollection | null;
}) {
  const [step, setStep] = React.useState(0);
  const reduced = useReducedMotion();
  const after = useBeforeAfter(step === 2 || step === 3, reduced);
  const { repair, labels, stats, points } = data;
  const { widestPiece: widest, heaviestPiece: heaviest } = repair.windows;
  const widestBounds = React.useMemo(() => innerBounds(widest.bbox), [widest]);
  const heaviestBounds = React.useMemo(() => innerBounds(heaviest.bbox), [heaviest]);
  const county = (code: string) => stats.countyNames[code] ?? "Michigan";
  const wide = repair.repair[widest.move - 1], heavy = repair.repair[heaviest.move - 1];
  const powerBins = React.useMemo(() => districtBins(labels.powerDiagram), [labels]);
  const repairedBins = React.useMemo(() => districtBins(labels.repaired), [labels]);
  const trace = React.useMemo(() => repair.repair.map((move) => move.maxDeviation), [repair]);
  const piecePoints = React.useMemo(() => repair.repair.map((move) => move.point), [repair]);
  const blocks = repair.repair.reduce((sum, move) => sum + move.units.length, 0);
  const residents = repair.repair.reduce((sum, move) => sum + move.population, 0);
  const affected = repair.piecesPerDistrict.filter((count) => count > 1).length;
  const gapBefore = (order: number) => order === 1 ? repair.maxDeviation.powerDiagram : repair.repair[order - 2].maxDeviation;

  const steps: (ChapterStep & { bounds: StageBounds })[] = [
    { title: "Cells ignore the graph", bounds: null,
      body: <p>The power diagram assigns each block by its center point and never consults the block graph. Where a straight cell border slices through water or oddly shaped blocks, some blocks land inside their district&rsquo;s cell but out of touch with the rest of it. Michigan&rsquo;s plan had {repair.detachedPieces} such pieces, {affected === DISTRICT_COLORS.length ? `in all ${affected} districts` : `in ${affected} of its ${DISTRICT_COLORS.length} districts`}: {blocks} blocks holding {number(residents)} people.</p> },
    { title: "Keep the largest piece", bounds: widestBounds,
      // The widest piece in this run is the west end of Belle Isle, checked against the block shapes.
      body: <p>Each district keeps the piece with the most residents as its anchor; every other piece has to move. The outlined {wide.units.length} blocks are the west end of Belle Isle, a park island in the Detroit River with no residents. Their center points fell in District {wide.source + 1}&rsquo;s cell, but on the block graph they touch only District {wide.target + 1}&rsquo;s blocks: the rest of the island. The nearest District {wide.source + 1} block is {number(widest.gap.distanceM)} m away, across District {wide.target + 1}&rsquo;s river blocks.</p> },
    { title: "Join a touching district", bounds: widestBounds,
      body: <><p>A piece joins a district it touches. Among every pending piece and every district each one touches, the move that hurts balance least goes first. With P<sub>k</sub> each district&rsquo;s population and N the state&rsquo;s, a move is scored in exact whole numbers by</p>
        <p className="dd-formula dd-formula-line">(max<sub>k</sub> |13P<sub>k</sub> − N|, Σ<sub>k</sub> (13P<sub>k</sub> − N)²)</p>
        <p>the largest gap first, then the sum of squared gaps. Empty pieces change nothing, so they go early: the west end of Belle Isle joined District {wide.target + 1}, the district it touches, as move {wide.order} of {repair.repair.length}.</p></> },
    { title: "The pieces with people", bounds: heaviestBounds,
      body: <p>The last moves carry people. These {heavy.units.length} blocks in {county(heavy.county)} hold {number(heavy.population)} residents and move from District {heavy.source + 1} to District {heavy.target + 1}. Each resident moved this way widens a gap, so repair ends further from balance than it began.</p> },
    { title: "Every district in one piece", bounds: null,
      body: <p>After {repair.repair.length} moves every district is a single connected piece of the block graph. The price is balance: the largest gap has grown from {gap(repair.maxDeviation.powerDiagram)} to {gap(repair.maxDeviation.repaired)} people. Rebalancing comes next.</p> },
  ];
  const current = steps[step];
  const windowStep = step >= 1 && step <= 3;

  const card = step === 0 ? <Metrics rows={[["Pieces", String(repair.detachedPieces)], ["Districts", `${affected} of ${DISTRICT_COLORS.length}`], ["Blocks", String(blocks)], ["Residents", number(residents)]]} />
    : step === 1 ? <Metrics rows={[["Blocks", String(wide.units.length)], ["Residents", number(wide.population)], ["Cut off from", <District key="d" id={wide.source} />]]} />
      : step === 2 ? <Metrics rows={[["Joins", <District key="d" id={wide.target} />], ["Move", `${wide.order} of ${repair.repair.length}`], ["Largest gap", `${gap(gapBefore(wide.order))} → ${gap(wide.maxDeviation)}`]]} />
        : step === 3 ? <Metrics rows={[["From", <District key="s" id={heavy.source} />], ["To", <District key="t" id={heavy.target} />], ["Residents", number(heavy.population)], ["Largest gap", `${gap(gapBefore(heavy.order))} → ${gap(heavy.maxDeviation)}`]]} />
          : <div className="grid gap-2">
            <Metrics rows={[["Pieces", `${DISTRICT_COLORS.length}, one each`], ["Largest gap", gap(repair.maxDeviation.repaired)]]} />
            <RoundTrace values={trace} current={trace.length - 1} label="largest gap after each move" log={false} />
          </div>;

  return (
    <ChapterConsole number={7} title="Repair" steps={steps} step={step} onStep={setStep}>
      <ExplainerStage projection={projection} bounds={current.bounds} padding={windowStep ? 0 : 0.12} points={points} showPoints={!windowStep}
        pointBins={step === 4 ? repairedBins : powerBins} binColors={DISTRICT_COLORS} card={card}
        badge={step === 2 || step === 3 ? <PhaseBadge after={after} /> : undefined}
        label={`Michigan repair, step ${step + 1}: ${current.title}`}
        overlay={<StageLayer visible={step === 0}><MoveMarks points={piecePoints} projection={projection} /></StageLayer>}>
        <Silhouette overview={overview} coast={coast} projection={projection} />
        <StageLayer visible={step === 1 || step === 2}>
          <DistrictBlocks blocks={widest.blocks} projection={projection} stage={step === 2 && after ? 1 : 0} />
          <FocusOutlines blocks={widest.blocks} focus={widest.focus} projection={projection} />
          <StageLayer visible={step === 1}>
            <NoTouch from={widest.gap.from} to={widest.gap.to} label={`${number(widest.gap.distanceM)} m · no shared edge`} projection={projection} unit={unitsPerPixel(widestBounds, projection)} />
          </StageLayer>
        </StageLayer>
        <StageLayer visible={step === 3}>
          <DistrictBlocks blocks={heaviest.blocks} projection={projection} stage={step === 3 && after ? 1 : 0} />
          <FocusOutlines blocks={heaviest.blocks} focus={heaviest.focus} projection={projection} />
        </StageLayer>
      </ExplainerStage>
    </ChapterConsole>
  );
}
