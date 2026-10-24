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
import type { ProfileResolveResponse, UtilityProfile, VotingMethod } from "@/types/methods";

import { BallotBody } from "./ballots-panel";
import { CandidateGlyph, CandidateMark } from "./glyph";
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
    <div className={cn("relative mx-2", compact ? "h-7" : "h-10")}>
      <div className="absolute inset-x-0 top-1/2 h-px bg-mi-rule">
        {Array.from({ length: 11 }, (_, i) => (
          <span
            key={i}
            aria-hidden
            className={cn("absolute top-1/2 w-px -translate-y-1/2 bg-mi-rule", i % 5 === 0 ? "h-2.5" : "h-1.5")}
            style={{ left: `${i * 10}%` }}
          />
        ))}
        {compact ? null : (
          <>
            <span className="absolute top-2 left-0 -translate-x-1/2 font-mi-mono text-[0.625rem] text-mi-muted">0</span>
            <span className="absolute top-2 left-full -translate-x-1/2 font-mi-mono text-[0.625rem] text-mi-muted">10</span>
          </>
        )}
        {candidates.map((id) => (
          <span
            key={id}
            className="absolute flex -translate-x-1/2 flex-col items-center"
            style={{ left: `${utilities[id] ?? 0}%`, bottom: `${2 + lane[id] * 14}px` }}
            title={`${id}: ${formatUtility(utilities[id] ?? 0)} of 10`}
          >
            {compact ? null : (
              <span className="font-mi-mono text-[0.625rem] leading-none text-mi-ink-2">
                {formatUtility(utilities[id] ?? 0)}
              </span>
            )}
            <CandidateGlyph id={id} size={compact ? 12 : 16} />
          </span>
        ))}
      </div>
    </div>
  );
}

export function VotersView({ profile }: { profile: UtilityProfile }) {
  return (
    <div className="space-y-2">
      <ul className="space-y-1">
        {profile.rows.map((row, index) => (
          <li key={index} className="grid grid-cols-[7rem_minmax(0,1fr)_minmax(0,14rem)] items-center gap-4">
            <span className="font-mi-mono text-sm text-mi-ink">{row.count} voters</span>
            <Scale candidates={profile.candidates} utilities={row.utilities} />
            <span className="flex items-center gap-1 font-mi-mono text-xs text-mi-muted">
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
      </ul>
      <p className="text-xs text-mi-muted">
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
      <p className="text-sm text-mi-ink-2">
        <span className="font-medium text-mi-ink">{rule.name}.</span> {rule.rule}{" "}
        <span className="text-mi-muted">Read by {rule.readBy}.</span>
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        {profile.rows.map((row, index) => {
          const cast = resolution.voter_ballots[index];
          return (
            <section key={index} className="rounded-[3px] border border-mi-rule p-3">
              <p className="font-mi-mono text-xs text-mi-muted">{row.count} voters</p>
              <Scale candidates={profile.candidates} utilities={row.utilities} compact />
              <div className="mt-2 border-t border-mi-rule pt-2">
                {cast ? <BallotBody kind={kind} candidates={profile.candidates} cast={cast} /> : null}
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
}: {
  method: VotingMethod;
  resolution: ProfileResolveResponse;
  failures: GalleryFailure[];
}) {
  const result = resolution.results.find((r) => r.method === method);
  if (!result) return null;
  return (
    <div className="space-y-4">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0">
          {method === "ranked_pairs" ? (
            <LockView resolution={resolution} winner={result.winner} />
          ) : (
            <TraceView result={result} resolution={resolution} />
          )}
        </div>
        <div className="space-y-3 text-sm leading-relaxed text-mi-ink-2">
          <p>
            <span className="font-medium text-mi-ink">How it counts.</span> {countRule(method, resolution)}
          </p>
          <MethodProfile method={method} failures={failures} />
        </div>
      </div>
      <Scoreboard resolution={resolution} upTo={method} />
    </div>
  );
}

/** Ranked Pairs' locking, shown even when a Condorcet winner makes it a formality. */
function LockView({ resolution, winner }: { resolution: ProfileResolveResponse; winner: string }) {
  const trace = resolution.results.find((r) => r.method === "ranked_pairs")?.trace;
  const skipped = new Set(
    trace?.kind === "ranked_pairs" ? trace.skipped.map((v) => `${v.winner}${v.loser}`) : []
  );
  return (
    <div className="space-y-2">
      <p className="text-xs text-mi-muted">Two-way wins, largest margin first</p>
      <ol className="space-y-1.5">
        {races(resolution).map((race) => {
          const out = skipped.has(`${race.winner}${race.loser}`);
          return (
            <li key={`${race.winner}${race.loser}`} className="flex items-center gap-3 font-mi-mono text-sm">
              <span className={cn("inline-flex items-center gap-1", out && "text-mi-muted line-through")}>
                <CandidateMark id={race.winner} size={12} />
                <span className="text-mi-muted">beats</span>
                <CandidateMark id={race.loser} size={12} />
              </span>
              <span className="text-mi-ink-2">
                by {race.for - race.against} ({race.for}–{race.against})
              </span>
              <span className="text-xs text-mi-muted">{out ? "skipped: closes a cycle" : "locked"}</span>
            </li>
          );
        })}
      </ol>
      <p className="text-xs text-mi-muted">
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
        <li className="text-xs leading-relaxed text-mi-muted">
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
    <ol className="grid grid-cols-7 gap-1.5 border-t border-mi-rule pt-3" aria-label="Winners so far">
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
            <span className="truncate text-[0.6875rem] text-mi-muted">{METHOD_META[method].label}</span>
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
  return (
    <div className="space-y-2">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">The seven counts of one electorate</caption>
        <thead>
          <tr className="border-b border-mi-rule text-left text-xs text-mi-muted">
            <th scope="col" className="py-1.5 pr-3 font-normal">Method</th>
            <th scope="col" className="py-1.5 pr-3 font-normal">Counted</th>
            <th scope="col" className="py-1.5 pr-3 font-normal">Winner</th>
            <th scope="col" className="py-1.5 text-center font-normal" title="Elects the majority winner">Maj.</th>
            <th scope="col" className="py-1.5 text-center font-normal" title="Elects the Condorcet winner">Cond.</th>
            <th scope="col" className="py-1.5 text-center font-normal" title="Avoids the Condorcet loser">Loser</th>
          </tr>
        </thead>
        <tbody>
          {COUNT_ORDER.map((method) => {
            const result = resolution.results.find((r) => r.method === method);
            if (!result) return null;
            const checks = criteriaChecks(result, criteria);
            const tally = channelTally(result);
            return (
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
                <td className="py-1 pr-3 font-mi-mono text-xs text-mi-ink-2">
                  {tally
                    ? resolution.rankings.candidates
                        .filter((id) => id in tally)
                        .map((id) => `${id} ${tally[id]}`)
                        .join(" · ")
                    : "two-way races"}
                </td>
                <td className="py-1 pr-3">
                  <CandidateMark id={result.winner} size={12} className="font-semibold text-mi-ink" />
                </td>
                <CheckCell check={checks.majority} />
                <CheckCell check={checks.condorcetWinner} />
                <CheckCell check={checks.condorcetLoser} />
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs leading-relaxed text-mi-muted">
        Maj. elects a candidate more than half the voters rank first; Cond. elects the Condorcet
        winner; Loser avoids the Condorcet loser (step 1.7).
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
                  <dd className="text-xs leading-relaxed text-mi-ink-2">{criterion.definition}</dd>
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
        <p className="text-xs leading-relaxed text-mi-muted">
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
      <p className="flex items-baseline justify-between text-xs text-mi-muted">
        <span className="font-medium text-mi-ink">{label}</span>
        <span>
          {resolution.total_voters} voters · {METHOD_META[method].label.toLowerCase()} elects{" "}
          <span className="font-semibold text-mi-ink">{result?.winner}</span>
        </span>
      </p>
      <ul className="mt-2 space-y-0.5 font-mi-mono text-xs text-mi-ink-2">
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
