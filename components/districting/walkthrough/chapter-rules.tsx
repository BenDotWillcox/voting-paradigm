import Link from "next/link";

import { blockDistrictColor } from "@/lib/block-map-projection";
import type { ExplainerStats } from "@/lib/districting-explainer";
import { NextChapterButton } from "./chapter-console";

const number = (value: number) => value.toLocaleString();
const INK = "#464a3b";
const color = (district: number) => blockDistrictColor(district, "26");

function Mark({ x, y, ok }: { x: number; y: number; ok: boolean }) {
  return <g transform={`translate(${x} ${y})`}>
    <circle r={6.5} fill="#ffffff" stroke={INK} strokeWidth={1.4} />
    <path d={ok ? "M-3 0.2l2 2.2 4-4.4" : "M-2.6-2.6l5.2 5.2M2.6-2.6l-5.2 5.2"} fill="none" stroke={INK} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
  </g>;
}

/** Small schematic for each rule, in the explorer's district colors. */
function RuleArt({ rule }: { rule: number }) {
  return <svg viewBox="0 0 72 52" className="dd-rule-art" aria-hidden="true">
    {rule === 0 && Array.from({ length: 13 }, (_, i) => <rect key={i} x={4 + (i % 7) * 9.4} y={i < 7 ? 12 : 23} width={8} height={8} rx={1} fill={color(i)} />)}
    {rule === 1 && <>
      {Array.from({ length: 6 }, (_, i) => <rect key={i} x={6 + i * 10.5} y={14} width={8} height={28} fill={color(i * 2)} />)}
      <path d="M2 14h68" stroke={INK} strokeWidth={1.2} strokeDasharray="3 2" />
    </>}
    {rule === 2 && <>
      <path d="M10 8h40l10 14-6 22H14L6 26z" fill="#f1f3ea" stroke={INK} strokeWidth={1.2} />
      <path d="M38 4L26 48" stroke={INK} strokeWidth={1.2} strokeDasharray="3 2.5" />
      <Mark x={58} y={42} ok={false} />
    </>}
    {rule === 3 && Array.from({ length: 12 }, (_, i) => <rect key={i} x={8 + (i % 4) * 14} y={6 + Math.floor(i / 4) * 14} width={14} height={14}
      fill={color([0, 0, 3, 3, 0, 5, 5, 3, 5, 5, 5, 3][i])} stroke="#ffffff" strokeWidth={1} />)}
    {rule === 4 && <>
      <path d="M4 14q8-8 18-2t8 14-6 12-14 2T4 14z" fill={color(4)} />
      <Mark x={18} y={46} ok />
      <path d="M40 10q8-4 12 4t-4 10-8-4 0-10zM54 28q8-2 10 6t-6 8-6-6 2-8z" fill={color(4)} />
      <path d="M48 24l8 6" stroke={INK} strokeWidth={1} strokeDasharray="2 2" />
      <Mark x={58} y={46} ok={false} />
    </>}
  </svg>;
}

function Seen({ on, children }: { on: boolean; children: React.ReactNode }) {
  return <li className="dd-rule" data-on={on || undefined}>
    <span className="dd-led" data-state={on ? "on" : undefined} aria-hidden="true" />
    <span className="font-medium text-foreground">{children}</span>
    <span className="sr-only">{on ? "(used)" : "(never used)"}</span>
  </li>;
}

/** The rules every computed map must satisfy, and why each exists: the turn from data to algorithm. */
export function RulesChapter({ stats }: { stats: ExplainerStats }) {
  const rules: { title: string; fact: React.ReactNode; why: React.ReactNode }[] = [
    { title: `Exactly ${stats.districts} districts`,
      fact: <>Michigan&rsquo;s share of a 435-seat House</>,
      why: <>The number of seats is settled before any line is drawn, by apportionment. <Link href="/apportionment" className="underline underline-offset-2">Apportionment Demo</Link></> },
    { title: "Equal population",
      fact: <>{number(stats.residents)} ÷ {stats.districts} = <b>{stats.targetPerDistrict.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b> residents each</>,
      why: <>One person, one vote: congressional districts must be as nearly equal in population as practicable (<i>Wesberry v. Sanders</i>, 1964). Whole blocks make exact equality impossible, so the question is how close a map gets.</> },
    { title: "Whole blocks only",
      fact: <>{number(stats.blocks)} blocks, none ever split</>,
      why: <>A block is the smallest area with an official count. Splitting one would mean guessing where its residents live.</> },
    { title: "Every block, exactly once",
      fact: <>Including {number(stats.waterOnlyBlocks)} water blocks and {number(stats.zeroPopulationBlocks)} with no residents</>,
      why: <>No one is left out or counted twice, and the finished map has no holes or overlaps.</> },
    { title: "Each district in one piece",
      fact: <>Connected in the block graph from chapter 2</>,
      why: <>A district should be one place: you can cross it without leaving it. This is the rule the graph exists to check.</> },
  ];
  return (
    <section className="dd-chapter dd-rules-stage" aria-labelledby="dd-rules-title">
      <header className="dd-chapter-head">
        <span className="dd-chapter-number">Chapter 04</span>
        <h3 id="dd-rules-title" className="dd-chapter-title">The rules</h3>
      </header>
      <div className="dd-rules-hero">
        <p className="dd-kicker">Starting point reached</p>
        <p className="dd-rules-headline">Every state is now one connected graph of census blocks. From here on, five rules decide what counts as a valid map, and the algorithm may look at only two things.</p>
      </div>
      <div className="dd-rules-body">
        <aside className="dd-rules-inputs flex flex-col" aria-label="Inputs">
          <h4 className="dd-label">What the algorithm sees</h4>
          <ul className="dd-rules">
            <Seen on>Block shapes</Seen>
            <Seen on>Population counts</Seen>
          </ul>
          <h4 className="dd-label mt-5">What it never sees</h4>
          <ul className="dd-rules">
            <Seen on={false}>Party or past votes</Seen>
            <Seen on={false}>Race or ethnicity</Seen>
            <Seen on={false}>Where incumbents live</Seen>
          </ul>
          <p className="dd-rule-why mt-5"><span>Why</span>A map can&rsquo;t be tuned to favor what the algorithm never sees.</p>
          <div className="mt-auto flex justify-end pt-6"><NextChapterButton /></div>
        </aside>
        <ol className="dd-rule-list">
          {rules.map((rule, index) => <li key={rule.title} className="dd-rule-row">
            <span className="dd-rule-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <RuleArt rule={index} />
            <div className="min-w-0">
              <h4 className="dd-rule-title">{rule.title}</h4>
              <p className="dd-rule-fact">{rule.fact}</p>
              <p className="dd-rule-why"><span>Why</span>{rule.why}</p>
            </div>
          </li>)}
        </ol>
      </div>
      <p className="dd-chapter-note">
        Not required: compactness, which the method favors only indirectly through squared distances, and county or city lines. Block counts in the 2020 Census include deliberate noise from the Census Bureau&rsquo;s privacy protection; state totals are exact.
      </p>
    </section>
  );
}
