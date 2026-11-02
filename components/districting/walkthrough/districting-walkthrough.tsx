"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowDown } from "lucide-react";

import { canPreload, preloadInTurn } from "@/lib/background-preload";
import { fetchBlockCollection, makeStateBlockProjection } from "@/lib/block-map-projection";
import { blockPlanUrl } from "@/lib/block-plan-selection";
import type { BlockMapCollection } from "@/lib/block-map-projection";
import { loadExplainer, type ExplainerCore, type ExplainerRest } from "@/lib/districting-explainer";
import { jumpToSection } from "../defer-until-near";
import { BlocksChapter } from "./chapter-blocks";
import { GraphChapter } from "./chapter-graph";
import { LinksChapter } from "./chapter-links";
import { BalanceChapter } from "./chapter-balance";
import { ChecksChapter } from "./chapter-checks";
import { PowerChapter } from "./chapter-power";
import { RepairChapter } from "./chapter-repair";
import { RulesChapter } from "./chapter-rules";
import { SeedsChapter } from "./chapter-seeds";
import { LazyChapter } from "./lazy-chapter";

type Core = { data: ExplainerCore; overview: BlockMapCollection; coast: BlockMapCollection | null };

/**
 * "How the maps are computed": Michigan's 13-district plan followed from
 * census blocks to a finished map (prompts/demo-3-explainer.md). Loading runs
 * down the page: the opening chapters' data first, then the later chapters',
 * then, while the browser is idle, the files the 50-state explorer opens
 * with, so each part is ready by the time the reader reaches it. Each chapter
 * mounts as it nears the screen, with a skeleton holding its place until then.
 */
export function DistrictingWalkthrough({ overviewUrl, coastUrl, explorerUrls = [] }: {
  overviewUrl: string;
  coastUrl?: string;
  /** The explorer's opening files, fetched in the background after the walkthrough's own. */
  explorerUrls?: string[];
}) {
  const [core, setCore] = React.useState<Core | null>(null);
  const [rest, setRest] = React.useState<ExplainerRest | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [retry, setRetry] = React.useState(0);

  React.useEffect(() => {
    const abort = new AbortController();
    const fail = (cause: unknown) => { if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load the walkthrough."); };
    setError(null);
    const load = loadExplainer(abort.signal);
    Promise.all([
      load.core,
      fetchBlockCollection(overviewUrl, abort.signal),
      coastUrl ? fetchBlockCollection(coastUrl, abort.signal) : Promise.resolve(null),
    ]).then(([data, overview, coast]) => { if (!abort.signal.aborted) setCore({ data, overview, coast }); }).catch(fail);
    load.rest.then((data) => { if (!abort.signal.aborted) setRest(data); }).catch(fail);
    return () => abort.abort();
  }, [overviewUrl, coastUrl, retry]);

  // Skipped when the browser asks for less data; the explorer then loads as the reader nears it.
  const preload = explorerUrls.join(" ");
  React.useEffect(() => {
    if (!rest || !preload || !canPreload()) return;
    const abort = new AbortController();
    void preloadInTurn(preload.split(" "), abort.signal);
    return () => abort.abort();
  }, [rest, preload]);

  const projection = React.useMemo(() => core ? makeStateBlockProjection(core.overview, "26") : null, [core]);
  const full = React.useMemo(() => core && rest ? { ...core.data, ...rest } : null, [core, rest]);
  const map = core && projection ? { projection, overview: core.overview, coast: core.coast } : null;

  return (
    <section className="dd-walkthrough" aria-labelledby="dd-walkthrough-title">
      {/* The introduction and the jump button share one row, aligned on their bottom edges. */}
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="dd-walkthrough-head">
          <p className="dd-kicker">The algorithm · Michigan</p>
          <h2 id="dd-walkthrough-title" className="text-xl font-semibold tracking-tight">How the maps are computed</h2>
          <p className="dd-sub max-w-2xl">Michigan&rsquo;s 13-district plan, followed from raw census blocks to the finished map in the explorer below. Every figure uses the same data the saved plan was computed from.</p>
        </div>
        {/* Opens the explorer on the national view, even if the address still names a state. */}
        <Link href={`${blockPlanUrl(435)}#explorer`} scroll={false} className="dd-jump mt-0"
          onClick={() => jumpToSection("explorer")}>
          <ArrowDown className="h-4 w-4" aria-hidden="true" />Jump to the 50-state solved map</Link>
      </header>
      {error && <p role="alert" className="dd-notice">{error} <button type="button" className="underline" onClick={() => setRetry((n) => n + 1)}>Retry</button></p>}
      <LazyChapter number={1} title="Michigan, in census blocks" render={core && map ? () => <BlocksChapter data={core.data} {...map} /> : null} />
      <LazyChapter number={2} title="The block graph" render={core && map ? () => <GraphChapter data={core.data} {...map} /> : null} />
      <LazyChapter number={3} title="Special cases: when land doesn't touch" render={core ? () => <LinksChapter data={core.data} /> : null} />
      <LazyChapter number={4} title="The rules" render={core ? () => <RulesChapter stats={core.data.stats} /> : null} />
      <LazyChapter number={5} title="Seeds" render={full && map ? () => <SeedsChapter data={full} {...map} /> : null} />
      <LazyChapter number={6} title="The power diagram, running" render={full && map ? () => <PowerChapter data={full} {...map} /> : null} />
      <LazyChapter number={7} title="Repair" render={full && map ? () => <RepairChapter data={full} {...map} /> : null} />
      <LazyChapter number={8} title="Rebalance" render={full && map ? () => <BalanceChapter data={full} {...map} /> : null} />
      <LazyChapter number={9} title="What was checked, and what wasn't" render={full && map ? () => <ChecksChapter data={full} {...map} /> : null} />
    </section>
  );
}
