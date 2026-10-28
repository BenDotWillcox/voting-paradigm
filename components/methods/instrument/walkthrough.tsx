"use client";

import { candidateColor } from "@/lib/methods/candidates";
import { CRITERIA, describeTransformation } from "@/lib/methods/gallery";
import { METHOD_META, channelTally, criteriaChecks, type CriterionCheck } from "@/lib/methods/instrument";
import { formatUtility } from "@/lib/methods/profile";
import { CRITERION_GROUPS, type Story } from "@/lib/methods/stories";
import { cn } from "@/lib/utils";
import {
  BALLOT_RULES,
  COUNT_ORDER,
  countRule,
  races,
  type BallotKind,
} from "@/lib/methods/walkthrough";
import type { ProfileResolveResponse, SampleElection, UtilityProfile, VotingMethod } from "@/types/methods";

import { BallotBody } from "./ballots-panel";
import { CandidateGlyph, CandidateMark, GlyphShapeSvg } from "./glyph";
import { MethodProfile, TraceView, type GalleryFailure } from "./method-trace";
import { TournamentGraph } from "./tournament-graph";

/**
 * The views of chapter 1: the voters on their scales, one ballot at a time
 * for every group, one count at a time with a scoreboard of the winners so
 * far, and the two-way races. Each fits a step on a 1280×720 screen.
 */

/** One voter group's 0–10 scale, read only. */
function Scale({
  candidates,
  utilities,
  compact = false,
}: {
  candidates: string[];
  utilities: Record<string, number>;
  compact?: boolean;
}) {
  // Candidates at the same point stack instead of hiding each other
  const seen = new Map<number, number>();
  const lane = Object.fromEntries(
    candidates.map((id) => {
      const value = utilities[id] ?? 0;
      const at = seen.get(value) ?? 0;
      seen.set(value, at + 1);
      return [id, at];
    })
  );
  return (
    <div className={cn("relative mx-2", compact ? "h-7" : "h-16")}>
      <div className="absolute inset-x-0 top-1/2 h-px bg-mi-rule">
        {Array.from({ length: 11 }, (_, i) => (
          <span
            key={i}
            aria-hidden
            className={cn("absolute top-1/2 w-px -translate-y-1/2 bg-mi-rule", i % 5 === 0 ? "h-2.5" : "h-1.5")}
            style={{ left: `${i * 10}%` }}
          />
        ))}
        {candidates.map((id) => (
          <span
            key={id}
            className="absolute flex -translate-x-1/2 flex-col items-center"
            style={{ left: `${utilities[id] ?? 0}%`, bottom: `${2 + lane[id] * 14}px` }}
            title={`${id}: ${formatUtility(utilities[id] ?? 0)} of 10`}
          >
            {compact ? null : (
              <span className="mb-0.5 font-mi-mono text-sm leading-none text-mi-ink">
                {formatUtility(utilities[id] ?? 0)}
              </span>
            )}
            <CandidateGlyph id={id} size={compact ? 12 : 22} />
          </span>
        ))}
      </div>
    </div>
  );
}

export function VotersView({ profile }: { profile: UtilityProfile }) {
  return (
    <div className="space-y-4">
      {/* Room above the first scale for its value labels */}
      <ul className="space-y-5 pt-3">
        {profile.rows.map((row, index) => (
          <li key={index} className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-1 sm:grid-cols-[7rem_minmax(0,1fr)_minmax(0,14rem)] sm:gap-4">
            <span className="font-mi-mono text-base text-mi-ink">{row.count} voters</span>
            <div className="col-span-2 row-start-2 min-w-0 sm:col-span-1 sm:col-start-2 sm:row-start-1">
              <Scale candidates={profile.candidates} utilities={row.utilities} />
            </div>
            <span className="col-start-2 row-start-1 flex flex-wrap items-center justify-end gap-1 font-mi-mono text-sm text-mi-muted sm:col-start-3 sm:justify-start">
              {[...profile.candidates]
                .sort((a, b) => (row.utilities[b] ?? 0) - (row.utilities[a] ?? 0))
                .map((id, position) => (
                  <span key={id} className="inline-flex items-center gap-1">
                    {position > 0 ? <span>›</span> : null}
                    <CandidateMark id={id} size={11} />
                  </span>
                ))}
            </span>
          </li>
        ))}
        {/* One axis for all three scales, aligned to them */}
        <li aria-hidden className="grid gap-4 sm:grid-cols-[7rem_minmax(0,1fr)_minmax(0,14rem)]">
          <span className="hidden sm:block" />
          <span className="relative mx-2 h-4 font-mi-mono text-sm text-mi-muted">
            {[0, 5, 10].map((tick) => (
              <span key={tick} className="absolute -translate-x-1/2" style={{ left: `${tick * 10}%` }}>
                {tick}
              </span>
            ))}
          </span>
          <span className="hidden sm:block" />
        </li>
      </ul>
      <p className="text-sm text-mi-muted">
        0 is the worst a voter can imagine, 10 the best. The order on each scale is that group&apos;s
        ranking; the spacing is how much more they like one candidate than another.
      </p>
    </div>
  );
}

export function BallotView({
  kind,
  profile,
  resolution,
}: {
  kind: BallotKind;
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
}) {
  const rule = BALLOT_RULES[kind];
  return (
    <div className="space-y-3">
      <p className="text-base text-mi-ink-2">
        <span className="font-medium text-mi-ink">{rule.name}.</span> {rule.rule}{" "}
        <span className="text-mi-muted">Read by {rule.readBy}.</span>
      </p>
      <div className="grid gap-4 sm:grid-cols-3">
        {profile.rows.map((row, index) => {
          const cast = resolution.voter_ballots[index];
          return (
            <section key={index} className="rounded-[3px] border border-mi-rule p-4">
              <p className="font-mi-mono text-sm text-mi-muted">{row.count} voters</p>
              <div className="mt-3">
                <Scale candidates={profile.candidates} utilities={row.utilities} />
              </div>
              <div className="mt-3 border-t border-mi-rule pt-4">
                {cast ? <BallotBody kind={kind} candidates={profile.candidates} cast={cast} large /> : null}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

export function CountView({
  method,
  resolution,
  failures,
  controls,
  inspector,
}: {
  method: VotingMethod;
  resolution: ProfileResolveResponse;
  failures: GalleryFailure[];
  controls?: React.ReactNode;
  inspector?: React.ReactNode;
}) {
  const result = resolution.results.find((r) => r.method === method);
  if (!result) return null;
  return (
    <div className="space-y-4">
      {controls}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0">
          {method === "ranked_pairs" ? (
            <LockView resolution={resolution} winner={result.winner} />
          ) : (
            <TraceView result={result} resolution={resolution} large />
          )}
        </div>
        <div className="space-y-3 text-base leading-relaxed text-mi-ink-2">
          <p>
            <span className="font-medium text-mi-ink">How it counts.</span> {countRule(method, resolution)}
          </p>
          <MethodProfile method={method} failures={failures} />
        </div>
      </div>
      {inspector}
      <Scoreboard resolution={resolution} upTo={method} />
    </div>
  );
}

/** Show only recorded locks; the actual implementation returns early for a Condorcet winner. */
function LockView({ resolution, winner }: { resolution: ProfileResolveResponse; winner: string }) {
  const trace = resolution.results.find((r) => r.method === "ranked_pairs")?.trace;
  if (trace?.kind === "ranked_pairs" && trace.had_condorcet_winner) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-mi-ink-2">Head-to-head results</p>
        <ul className="space-y-3">
          {races(resolution).map((race) => (
            <li key={`${race.winner}${race.loser}`} className="flex flex-wrap items-center gap-2 font-mi-mono text-base text-mi-ink">
              <CandidateMark id={race.winner} size={17} />
              <span className="text-mi-ink-2">beats</span>
              <CandidateMark id={race.loser} size={17} />
              <span className="text-mi-ink-2">{race.for}–{race.against}</span>
            </li>
          ))}
        </ul>
        <p className="text-sm leading-relaxed text-mi-ink-2">
          {winner} beats every rival. The Python implementation returns this Condorcet winner immediately, so no edges are locked or skipped in this count.
        </p>
      </div>
    );
  }
  const skipped = new Set(
    trace?.kind === "ranked_pairs" ? trace.skipped.map((v) => `${v.winner}${v.loser}`) : []
  );
  return (
    <div className="space-y-2">
      <p className="text-sm text-mi-muted">Two-way wins, largest margin first</p>
      <ol className="space-y-3">
        {races(resolution).map((race) => {
          const out = skipped.has(`${race.winner}${race.loser}`);
          return (
            <li key={`${race.winner}${race.loser}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mi-mono text-base">
              <span className={cn("inline-flex items-center gap-1.5", out && "text-mi-muted line-through")}>
                <CandidateMark id={race.winner} size={17} />
                <span className="text-mi-muted">beats</span>
                <CandidateMark id={race.loser} size={17} />
              </span>
              <span className="text-mi-ink-2">
                by {race.for - race.against} ({race.for}–{race.against})
              </span>
              <span className="text-sm text-mi-muted">{out ? "skipped: closes a cycle" : "locked"}</span>
            </li>
          );
        })}
      </ol>
      <p className="text-sm text-mi-muted">
        No locked win beats {winner}, so {winner} wins.
      </p>
    </div>
  );
}

export function HeadToHeadView({ resolution }: { resolution: ProfileResolveResponse }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,16rem)] lg:items-start">
      <ul className="space-y-3">
        {races(resolution).map((race) => {
          const total = race.for + race.against;
          return (
            <li key={`${race.winner}${race.loser}`} className="space-y-1">
              <p className="flex items-center gap-1.5 text-sm text-mi-ink">
                <CandidateMark id={race.winner} size={12} />
                <span className="text-mi-ink-2">beats</span>
                <CandidateMark id={race.loser} size={12} />
                <span className="font-mi-mono text-mi-ink-2">
                  {race.for}–{race.against}
                </span>
              </p>
              <span className="flex h-2.5 overflow-hidden rounded-[3px]">
                <span style={{ width: `${(100 * race.for) / total}%`, background: candidateColor(race.winner) }} />
                <span style={{ width: `${(100 * race.against) / total}%`, background: candidateColor(race.loser), opacity: 0.45 }} />
              </span>
            </li>
          );
        })}
        <li className="text-sm leading-relaxed text-mi-muted">
          Each race counts the voters who rank one candidate above the other, from the same ranked
          ballots. In the graph, arrows point from each race&apos;s winner and numbers are the
          margins; a ring marks the Condorcet winner.
        </li>
      </ul>
      <TournamentGraph
        candidates={resolution.rankings.candidates}
        pairwise={resolution.pairwise}
        condorcetWinner={resolution.criteria.condorcet_winner}
        caption={false}
      />
    </div>
  );
}

/** The seven counts' winners, filled in up to the count on screen. */
function Scoreboard({ resolution, upTo }: { resolution: ProfileResolveResponse; upTo: VotingMethod }) {
  const reached = COUNT_ORDER.indexOf(upTo);
  return (
    <ol className="grid grid-cols-2 gap-2 border-t border-mi-rule pt-3 sm:grid-cols-4 xl:grid-cols-7" aria-label="Winners so far">
      {COUNT_ORDER.map((method, at) => {
        const winner = resolution.results.find((r) => r.method === method)?.winner;
        const shown = at <= reached && winner;
        return (
          <li
            key={method}
            className={cn(
              "flex flex-col items-center gap-1 rounded-[3px] border px-1 py-1.5 text-center",
              at === reached ? "border-mi-ink" : "border-mi-rule"
            )}
          >
            <span className="text-sm text-mi-ink-2">{METHOD_META[method].label}</span>
            {shown ? (
              <CandidateMark id={winner} size={13} className="text-sm font-semibold text-mi-ink" />
            ) : (
              <span className="font-mi-mono text-sm text-mi-muted" aria-label="not counted yet">
                ·
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * The seven counts at one line each: what was counted, the winner, and the
 * three single-profile criteria. Choosing a row asks to revisit its count.
 */
export function CompactCounts({
  resolution,
  onOpen,
}: {
  resolution: ProfileResolveResponse;
  onOpen?: (method: VotingMethod) => void;
}) {
  const { criteria } = resolution;
  const missing = [
    criteria.majority_winner === null ? "majority winner" : null,
    criteria.condorcet_winner === null ? "Condorcet winner" : null,
    criteria.condorcet_loser === null ? "Condorcet loser" : null,
  ].filter((name): name is string => name !== null);
  const counts = COUNT_ORDER.flatMap((method) => {
    const result = resolution.results.find((r) => r.method === method);
    if (!result) return [];
    const tally = channelTally(result);
    return [{
      method,
      result,
      checks: criteriaChecks(result, criteria),
      counted: tally
        ? resolution.rankings.candidates.filter((id) => id in tally).map((id) => `${id} ${tally[id]}`).join(" · ")
        : "two-way races",
    }];
  });
  return (
    <div className="min-w-0 space-y-3">
      <ul className="space-y-3 sm:hidden" aria-label="The seven counts of one electorate">
        {counts.map(({ method, result, checks, counted }) => (
          <li key={method} className="rounded-[3px] border border-mi-rule p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              {onOpen ? (
                <button
                  type="button"
                  onClick={() => onOpen(method)}
                  className="min-h-11 text-left text-base font-medium text-mi-ink underline decoration-mi-rule underline-offset-2 hover:decoration-mi-ink"
                >
                  {METHOD_META[method].label}
                </button>
              ) : (
                <p className="text-base font-medium text-mi-ink">{METHOD_META[method].label}</p>
              )}
              <span className="inline-flex items-center gap-2 text-sm text-mi-ink-2">
                Winner <CandidateMark id={result.winner} size={16} className="font-semibold text-mi-ink" />
              </span>
            </div>
            <p className="mt-2 break-words font-mi-mono text-sm text-mi-ink-2">{counted}</p>
            <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-mi-rule pt-2 text-sm">
              {[
                { label: "Majority", check: checks.majority },
                { label: "Condorcet", check: checks.condorcetWinner },
                { label: "Avoids loser", check: checks.condorcetLoser },
              ].map(({ label, check }) => (
                <div key={label}>
                  <dt className="text-mi-muted">{label}</dt>
                  <dd className="mt-1 font-mi-mono text-mi-ink" aria-label={check === "pass" ? "yes" : check === "fail" ? "no" : "does not apply"}>
                    {check === "pass" ? "Yes" : check === "fail" ? "No" : "–"}
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
      <div className="hidden min-w-0 overflow-x-auto sm:block">
      <table className="w-full min-w-[36rem] border-collapse text-sm">
        <caption className="sr-only">The seven counts of one electorate</caption>
        <thead>
          <tr className="border-b border-mi-rule text-left text-sm text-mi-muted">
            <th scope="col" className="py-1.5 pr-3 font-normal">Method</th>
            <th scope="col" className="py-1.5 pr-3 font-normal">Counted</th>
            <th scope="col" className="py-1.5 pr-3 font-normal">Winner</th>
            <th scope="col" className="py-1.5 text-center font-normal" title="Elects the majority winner">Maj.</th>
            <th scope="col" className="py-1.5 text-center font-normal" title="Elects the Condorcet winner">Cond.</th>
            <th scope="col" className="py-1.5 text-center font-normal" title="Avoids the Condorcet loser">Loser</th>
          </tr>
        </thead>
        <tbody>
          {counts.map(({ method, result, checks, counted }) => (
              <tr key={method} className="border-b border-mi-rule last:border-0">
                <th scope="row" className="py-1 pr-3 text-left font-normal">
                  {onOpen ? (
                    <button
                      type="button"
                      onClick={() => onOpen(method)}
                      className="text-mi-ink underline decoration-mi-rule underline-offset-2 hover:decoration-mi-ink"
                    >
                      {METHOD_META[method].label}
                    </button>
                  ) : (
                    <span className="text-mi-ink">{METHOD_META[method].label}</span>
                  )}
                </th>
                <td className="py-1 pr-3 font-mi-mono text-sm text-mi-ink-2">
                  {counted}
                </td>
                <td className="py-1 pr-3">
                  <CandidateMark id={result.winner} size={12} className="font-semibold text-mi-ink" />
                </td>
                <CheckCell check={checks.majority} />
                <CheckCell check={checks.condorcetWinner} />
                <CheckCell check={checks.condorcetLoser} />
              </tr>
          ))}
        </tbody>
      </table>
      </div>
      <p className="text-sm leading-relaxed text-mi-ink-2">
        Maj. elects a candidate more than half the voters rank first; Cond. elects the Condorcet
        winner; Loser avoids a candidate who loses every head-to-head race. These checks describe
        this electorate, not a method’s guarantees for all elections.
        {missing.length > 0 ? ` This electorate has no ${missing.join(" or ")}, so a dash marks nothing to check.` : ""}
      </p>
    </div>
  );
}

function CheckCell({ check }: { check: CriterionCheck }) {
  const label = check === "pass" ? "yes" : check === "fail" ? "no" : "does not apply";
  return (
    <td className="py-1 text-center font-mi-mono text-sm" aria-label={label} title={label}>
      {check === "pass" ? (
        <span className="text-mi-ink">✓</span>
      ) : check === "fail" ? (
        <span className="rounded-[2px] bg-mi-ink px-1 text-mi-surface">✗</span>
      ) : (
        <span className="text-mi-muted">–</span>
      )}
    </td>
  );
}

/** The eight criteria in plain words, in three groups. */
export function FairnessView() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {CRITERION_GROUPS.map((group) => (
        <section key={group.title} className="rounded-[3px] border border-mi-rule p-3">
          <h3 className="text-sm font-medium text-mi-ink">{group.title}</h3>
          <dl className="mt-2 space-y-2">
            {group.criteria.map((id) => {
              const criterion = CRITERIA.find((c) => c.id === id);
              return criterion ? (
                <div key={id}>
                  <dt className="text-sm text-mi-ink">{criterion.label}</dt>
                  <dd className="text-sm leading-relaxed text-mi-ink-2">{criterion.definition}</dd>
                </div>
              ) : null;
            })}
          </dl>
        </section>
      ))}
    </div>
  );
}

/** One paradox: the electorate and its count before, what changes, and after. */
export function StoryView({ story, onGallery }: { story: Story; onGallery: () => void }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_12rem_minmax(0,1fr)] lg:items-start">
      <StorySide label="Before" resolution={story.before} method={story.specimen.method} />
      <div className="space-y-2 self-center">
        <p className="rounded-[3px] bg-mi-wash p-3 text-sm leading-relaxed text-mi-ink">
          <span aria-hidden className="mb-1 block font-mi-mono text-mi-muted">→</span>
          {describeTransformation(story.specimen)}
        </p>
        <p className="text-sm leading-relaxed text-mi-muted">
          The smallest electorate the search found for this failure.{" "}
          <button
            type="button"
            onClick={onGallery}
            className="underline decoration-mi-rule underline-offset-2 hover:text-mi-ink hover:decoration-mi-ink"
          >
            Open it in the gallery
          </button>
        </p>
      </div>
      <StorySide label="After" resolution={story.after} method={story.specimen.method} />
    </div>
  );
}

function StorySide({
  label,
  resolution,
  method,
}: {
  label: string;
  resolution: ProfileResolveResponse;
  method: VotingMethod;
}) {
  const result = resolution.results.find((r) => r.method === method);
  return (
    <section className="min-w-0 rounded-[3px] border border-mi-rule p-3">
      <p className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm text-mi-muted">
        <span className="font-medium text-mi-ink">{label}</span>
        <span>
          {resolution.total_voters} voters · {METHOD_META[method].label.toLowerCase()} elects{" "}
          <span className="font-semibold text-mi-ink">{result?.winner}</span>
        </span>
      </p>
      <ul className="mt-2 space-y-0.5 font-mi-mono text-sm text-mi-ink-2">
        {resolution.rankings.rows.map((row, index) => (
          <li key={index} className="flex items-center gap-1">
            <span className="w-7 text-right">{row.count} ×</span>
            {row.ranking.map((id, position) => (
              <span key={id} className="inline-flex items-center gap-1">
                {position > 0 ? <span className="text-mi-muted">›</span> : null}
                <CandidateMark id={id} size={10} />
              </span>
            ))}
          </li>
        ))}
      </ul>
      {result ? (
        <div className="mt-3 border-t border-mi-rule pt-2">
          <TraceView result={result} resolution={resolution} />
        </div>
      ) : null}
    </section>
  );
}

// The plane a sample election is drawn in: standard-normal draws, clipped
const PLANE = 3;
const PLANE_PX = 240;

/** One simulated election: its voters and candidates in the plane, and the seven winners. */
export function SampleElectionView({ sample }: { sample: SampleElection }) {
  const at = (value: number) => ((Math.max(-PLANE, Math.min(PLANE, value)) + PLANE) / (2 * PLANE)) * PLANE_PX;
  return (
    <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
      <svg
        viewBox={`0 0 ${PLANE_PX} ${PLANE_PX}`}
        className="w-full rounded-[3px] border border-mi-rule bg-mi-page"
        role="img"
        aria-label={`${sample.voter_positions.length} voters and ${sample.candidates} candidates in the plane`}
      >
        <line x1={PLANE_PX / 2} y1={0} x2={PLANE_PX / 2} y2={PLANE_PX} stroke="var(--mi-rule)" />
        <line x1={0} y1={PLANE_PX / 2} x2={PLANE_PX} y2={PLANE_PX / 2} stroke="var(--mi-rule)" />
        {sample.voter_positions.map(([x, y], index) => (
          <circle key={index} cx={at(x)} cy={at(-y)} r={2.2} fill="var(--mi-muted)" opacity={0.55} />
        ))}
        {Object.entries(sample.candidate_positions).map(([id, [x, y]]) => (
          <g key={id}>
            <circle cx={at(x)} cy={at(-y)} r={11} fill="var(--mi-surface)" stroke="var(--mi-ink)" />
            <GlyphShapeSvg id={id} cx={at(x)} cy={at(-y)} r={7} strokeWidth={1.4} />
            <text x={at(x) + 13} y={at(-y) - 9} className="fill-mi-ink font-mi-mono text-[11px]">
              {id}
            </text>
          </g>
        ))}
      </svg>
      <div className="space-y-3">
        <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7" aria-label="The seven winners">
          {COUNT_ORDER.map((method) => (
            <li key={method} className="flex flex-col items-center gap-1 rounded-[3px] border border-mi-rule px-1 py-1.5 text-center">
              <span className="text-sm text-mi-ink-2">{METHOD_META[method].label}</span>
              <CandidateMark id={sample.winners[method]} size={13} className="text-sm font-semibold text-mi-ink" />
            </li>
          ))}
        </ol>
        <p className="text-sm leading-relaxed text-mi-ink-2">
          Each dot is a voter. A voter likes a candidate less the farther away it sits, so the
          seven ballots and counts follow from the positions alone.
          {sample.condorcet ? ` ${sample.condorcet} is the Condorcet winner.` : " There is no Condorcet winner."}
        </p>
        <p className="font-mi-mono text-sm leading-relaxed text-mi-muted">
          Election {sample.index} of the study&apos;s {sample.of.toLocaleString("en-US")} with{" "}
          {sample.candidates} candidates: {sample.rule}. Drawn from a standard Gaussian; axes clipped at ±{PLANE}.
        </p>
      </div>
    </div>
  );
}
