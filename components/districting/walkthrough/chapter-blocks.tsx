"use client";

import * as React from "react";

import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerBlock, ExplainerCore } from "@/lib/districting-explainer";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage, StageLayer, type StageBounds } from "./explainer-stage";
import { BlockShapes, MICHIGAN_COUNTIES, Outline, Silhouette, boundsOf, formatArea } from "./layers";

const number = (value: number) => value.toLocaleString();

/** The 15-digit block ID, split into the geographies it nests inside. */
export function BlockIdCard({ block }: { block: ExplainerBlock }) {
  const county = block.geoid.slice(2, 5), tract = block.geoid.slice(5, 11);
  const parts = [
    { digits: block.geoid.slice(0, 2), label: "State", value: "Michigan" },
    { digits: county, label: "County", value: MICHIGAN_COUNTIES[county] ?? county },
    { digits: tract, label: "Tract", value: `${Number(tract.slice(0, 4))}.${tract.slice(4)}` },
    { digits: block.geoid.slice(11), label: "Block", value: block.geoid.slice(11) },
  ];
  return <div className="grid gap-2.5">
    <p className="dd-group-title">2020 census block</p>
    <div className="dd-geoid" aria-label={`Block ID ${block.geoid}`}>
      {parts.map((part) => <span key={part.label}><b>{part.digits}</b><small>{part.label}</small><small className="text-foreground">{part.value}</small></span>)}
    </div>
    <dl className="dd-card-metrics">
      <div><dt>Residents</dt><dd>{number(block.population)}</dd></div>
      {block.housingUnits !== undefined && <div><dt>Housing units</dt><dd>{number(block.housingUnits)}</dd></div>}
      <div><dt>Land</dt><dd>{formatArea(block.landM2)}</dd></div>
      {block.urban && <div><dt>Census class</dt><dd>{block.urban === "U" ? "Urban" : "Rural"}</dd></div>}
    </dl>
  </div>;
}

export function BlocksChapter({ data, projection, overview, coast }: {
  data: ExplainerCore; projection: BlockMapProjection; overview: BlockMapCollection; coast: BlockMapCollection | null;
}) {
  const [step, setStep] = React.useState(0);
  const { stats, windows: { windows: { detroit }, upperPeninsula } } = data;
  const featured = detroit.blocks.find((block) => block.geoid === detroit.featured)!;
  const featuredSet = React.useMemo(() => new Set([featured.geoid]), [featured.geoid]);
  const upSet = React.useMemo(() => new Set([upperPeninsula.geoid]), [upperPeninsula.geoid]);
  const landRatio = Math.round(upperPeninsula.landM2 / featured.landM2 / 100) * 100;
  const widthKm = (bbox: readonly number[]) => ((bbox[2] - bbox[0]) * 111.32 * Math.cos(((bbox[1] + bbox[3]) / 2) * Math.PI / 180)).toFixed(0);
  const heightKm = (bbox: readonly number[]) => ((bbox[3] - bbox[1]) * 111.32).toFixed(0);

  const steps: (ChapterStep & { bounds: StageBounds; padding?: number })[] = [
    { title: "Start with the state", bounds: null,
      body: <p>Every map on this page starts from the same source: the 2020 Census, which counted {number(stats.residents)} people in Michigan.</p> },
    { title: "Cut into census blocks", bounds: detroit.bbox, padding: 0.02,
      body: <p>The Census Bureau divides Michigan into {number(stats.blocks)} blocks, its smallest unit of geography. This slice of Detroit, about {widthKm(detroit.bbox)} by {heightKm(detroit.bbox)} km, holds {number(detroit.blocks.length)} of them.</p> },
    { title: "Zoom into one block", bounds: boundsOf(featured.geometry), padding: 1.1,
      body: <p>Block {featured.geoid.slice(11)} in Wayne County holds {number(featured.population)} residents and {number(featured.housingUnits ?? 0)} homes on {formatArea(featured.landM2)}. Its 15-digit ID nests it inside its state, county and tract.</p> },
    { title: "Lines follow roads, not people", bounds: boundsOf(upperPeninsula.geometry), padding: 0.45,
      body: <p>In {MICHIGAN_COUNTIES[upperPeninsula.geoid.slice(2, 5)]} County, one block covers {formatArea(upperPeninsula.landM2)} and holds {number(upperPeninsula.population)} residents: about {number(landRatio)} times the land of the Detroit block. Block lines follow roads, streams, shorelines and municipal limits. Population plays no part in drawing them.</p> },
    { title: "Every block becomes a point", bounds: null,
      body: <p>To place a block, the algorithm uses one point, the Census Bureau&rsquo;s internal point for that block, carrying its population. Dots are sized by residents. {number(stats.zeroPopulationBlocks)} blocks have none, and {number(stats.waterOnlyBlocks)} are entirely water.</p> },
  ];
  const current = steps[step];

  const card = step === 2 ? <BlockIdCard block={featured} />
    : step === 3 ? <BlockIdCard block={upperPeninsula} />
      : step === 4 ? <dl className="dd-card-metrics"><div><dt>Blocks</dt><dd>{number(stats.blocks)}</dd></div><div><dt>Residents</dt><dd>{number(stats.residents)}</dd></div><div><dt>No residents</dt><dd>{number(stats.zeroPopulationBlocks)}</dd></div><div><dt>Water only</dt><dd>{number(stats.waterOnlyBlocks)}</dd></div></dl>
        : null;

  return (
    <ChapterConsole number={1} title="Michigan, in census blocks" steps={steps} step={step} onStep={setStep}>
      <ExplainerStage projection={projection} bounds={current.bounds} padding={current.padding} points={data.points} showPoints={step === 4} card={card}
        label={`Michigan census blocks, step ${step + 1}: ${current.title}`}>
        <Silhouette overview={overview} coast={coast} projection={projection} />
        <StageLayer visible={step >= 1 && step <= 2}>
          <BlockShapes blocks={detroit.blocks} projection={projection} highlight={step === 2 ? featuredSet : undefined} />
          {step === 2 && <Outline geometry={featured.geometry} projection={projection} />}
        </StageLayer>
        <StageLayer visible={step === 3}>
          <BlockShapes blocks={upperPeninsula.neighbors} projection={projection} />
          <BlockShapes blocks={[upperPeninsula]} projection={projection} highlight={upSet} />
          <Outline geometry={upperPeninsula.geometry} projection={projection} />
        </StageLayer>
      </ExplainerStage>
    </ChapterConsole>
  );
}
