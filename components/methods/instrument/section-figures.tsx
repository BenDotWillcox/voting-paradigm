import type { ReactNode } from "react";

import { excerptListing } from "@/lib/methods/code-listing";
import type { CountSource } from "@/lib/methods/count-inspector";
import { METHOD_META } from "@/lib/methods/instrument";
import { SHORT_LABELS } from "@/lib/methods/simulation";
import type { ProfileResolveResponse, SimulationSummary, UtilityProfile, VotingMethod } from "@/types/methods";

import { CodeView } from "./code-view";
import { CandidateGlyph, GlyphShapeSvg } from "./glyph";

/*
 * One small figure per section band, each drawn from saved data the section
 * itself uses. They preview a section; none is the only place a fact appears.
 */

const COMPARED: VotingMethod[] = ["plurality", "irv", "ranked_pairs"];

function Figure({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <figure className="space-y-2">
      {children}
      <figcaption className="font-mi-mono text-sm text-mi-ink-2">{caption}</figcaption>
    </figure>
  );
}

/** The plurality line that does the counting, with the totals it produced. */
export function CodeFigure({ source, resolution }: { source: CountSource; resolution: ProfileResolveResponse }) {
  const result = resolution.results.find((item) => item.method === "plurality");
  const lines = source.source.split("\n");
  const at = lines.findIndex((line) => /vote_counts\[ballot\.choice\] \+= 1/.test(line));
  if (!result || result.trace.kind !== "plurality" || at < 2) return null;
  const counts = result.trace.first_choices;
  const tally = resolution.rankings.candidates.map((candidate) => `${candidate} ${counts[candidate] ?? 0}`).join(" · ");
  return (
    <Figure caption={`${source.path} · line ${at + 1}`}>
      <CodeView rows={excerptListing(lines.slice(at - 2, at + 1), at - 1)} states={["context", "context", "drive"]} notes={{ 2: tally }} label={`Plurality's counting line, line ${at + 1}, with the saved totals ${tally}`} className="py-2" />
    </Figure>
  );
}

/** The opening comparison's three winners, one per method. */
export function WinnersFigure({ label, resolution }: { label: string; resolution: ProfileResolveResponse }) {
  const distinct = new Set(resolution.results.map((result) => result.winner)).size;
  return (
    <Figure caption={`${label} · ${resolution.total_voters} voters · ${distinct} winners`}>
      <ul className="grid grid-cols-3 gap-2 rounded-[4px] border border-mi-rule bg-mi-surface p-4">
        {COMPARED.map((method) => {
          const winner = resolution.results.find((result) => result.method === method)?.winner;
          if (!winner) return null;
          return (
            <li key={method} className="flex flex-col items-center gap-1.5 text-center">
              <CandidateGlyph id={winner} size={30} title={`${METHOD_META[method].label} elects ${winner}`} />
              <span className="text-sm text-mi-ink-2">{METHOD_META[method].label}</span>
            </li>
          );
        })}
      </ul>
    </Figure>
  );
}

/** Condorcet efficiency at the largest field, as one strip of dots. */
export function EfficiencyFigure({ simulation }: { simulation: SimulationSummary }) {
  const group = simulation.by_candidates.reduce((largest, item) => item.candidates > largest.candidates ? item : largest);
  const rates = simulation.methods.flatMap((method) => {
    const rate = group.condorcet_efficiency[method];
    return rate && rate.of > 0 ? [{ method, value: rate.count / rate.of }] : [];
  });
  if (!rates.length) return null;
  const low = rates.reduce((a, b) => b.value < a.value ? b : a);
  const high = rates.reduce((a, b) => b.value > a.value ? b : a);
  const floor = Math.min(0.5, Math.floor(low.value * 10) / 10);
  const x = (value: number) => 20 + (value - floor) / (1 - floor) * 300;
  const pct = (value: number) => `${(value * 100).toFixed(value === 1 ? 0 : 1)}%`;
  const description = rates.map(({ method, value }) => `${METHOD_META[method].label} ${pct(value)}`).join(", ");
  return (
    <Figure caption={`Condorcet efficiency · ${group.candidates} candidates · seed ${simulation.config.seed}`}>
      <div className="rounded-[4px] border border-mi-rule bg-mi-surface px-4 py-3">
        <svg viewBox="0 0 340 92" className="block h-auto w-full" role="img" aria-label={`How often each method elects the Condorcet winner with ${group.candidates} candidates: ${description}`}>
          <line x1={20} y1={50} x2={320} y2={50} stroke="var(--mi-rule)" />
          {[floor, (floor + 1) / 2, 1].map((tick) => <g key={tick}>
            <line x1={x(tick)} y1={45} x2={x(tick)} y2={55} stroke="var(--mi-muted)" />
            <text x={x(tick)} y={78} textAnchor="middle" fontSize={11} fill="var(--mi-ink-2)" className="font-mi-mono">{Math.round(tick * 100)}%</text>
          </g>)}
          {rates.filter((rate) => rate !== low && rate !== high).map(({ method, value }) => <circle key={method} cx={x(value)} cy={50} r={5} fill="var(--mi-muted)" />)}
          {[low, high].map(({ method, value }) => <g key={method}>
            <circle cx={x(value)} cy={50} r={6.5} fill="var(--mi-ink)" />
            <text x={x(value)} y={30} textAnchor={value > 0.9 ? "end" : "middle"} fontSize={12} fill="var(--mi-ink)" className="font-mi-mono">{SHORT_LABELS[method]} {pct(value)}</text>
          </g>)}
        </svg>
      </div>
    </Figure>
  );
}

/** One voter group's preference track, as the playground's editor draws it. */
export function PreferenceFigure({ label, profile }: { label: string; profile: UtilityProfile }) {
  const row = profile.rows[0];
  if (!row) return null;
  const order = [...profile.candidates].sort((a, b) => (row.utilities[b] ?? 0) - (row.utilities[a] ?? 0));
  const x = (utility: number) => 20 + utility / 100 * 300;
  return (
    <Figure caption={`${label} · voter group 1 · ${row.count} voters`}>
      <div className="rounded-[4px] border border-mi-rule bg-mi-surface px-4 py-3">
        <svg viewBox="0 0 340 92" className="block h-auto w-full" role="img" aria-label={`${row.count} voters rank ${order.join(" over ")}: ${profile.candidates.map((candidate) => `${candidate} at ${(row.utilities[candidate] ?? 0) / 10}`).join(", ")} on a 0 to 10 scale`}>
          <text x={20} y={16} fontSize={12} fill="var(--mi-ink)" className="font-mi-mono">{row.count} voters · {order.join(" › ")}</text>
          <line x1={20} y1={50} x2={320} y2={50} stroke="var(--mi-rule)" strokeWidth={2} />
          <line x1={170} y1={44} x2={170} y2={56} stroke="var(--mi-muted)" />
          {profile.candidates.map((candidate) => <GlyphShapeSvg key={candidate} id={candidate} cx={x(row.utilities[candidate] ?? 0)} cy={50} r={10} />)}
          <text x={20} y={84} fontSize={11} fill="var(--mi-ink-2)" className="font-mi-mono">0 worst</text>
          <text x={170} y={84} textAnchor="middle" fontSize={11} fill="var(--mi-ink-2)" className="font-mi-mono">5</text>
          <text x={320} y={84} textAnchor="end" fontSize={11} fill="var(--mi-ink-2)" className="font-mi-mono">best 10</text>
        </svg>
      </div>
    </Figure>
  );
}
