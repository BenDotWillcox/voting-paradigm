"use client";

import { candidateColor } from "@/lib/methods/candidates";
import { formatUtility } from "@/lib/methods/profile";
import { cn } from "@/lib/utils";
import type { UtilityProfile, VoterBallots } from "@/types/methods";

import { CandidateGlyph, CandidateMark } from "./glyph";

/**
 * What one voter type casts in each of the five ballot formats, under the
 * sincere ballot model (model v1). Each card names the methods that read it.
 */
export function BallotsPanel({
  profile,
  ballots,
  selected,
  onSelect,
}: {
  profile: UtilityProfile;
  ballots: VoterBallots[] | null;
  selected: number;
  onSelect: (row: number) => void;
}) {
  const row = profile.rows[selected];
  const cast = ballots?.[selected] ?? null;
  const candidates = profile.candidates;
  const mean = row
    ? candidates.reduce((sum, id) => sum + (row.utilities[id] ?? 0), 0) / candidates.length
    : 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Voter type">
        {profile.rows.map((r, index) => (
          <button
            key={index}
            type="button"
            aria-pressed={index === selected}
            onClick={() => onSelect(index)}
            className={cn(
              "rounded-[3px] border px-2 py-0.5 font-mi-mono text-xs",
              index === selected
                ? "border-mi-ink bg-mi-ink text-mi-surface"
                : "border-mi-rule text-mi-ink-2 hover:border-mi-ink"
            )}
          >
            type {index + 1} · {r.count}
          </button>
        ))}
      </div>

      {!row || !cast ? (
        <p className="text-sm text-mi-muted">Counting this voter type…</p>
      ) : (
        <>
          <p className="text-sm text-mi-ink-2">
            Each of these {row.count} {row.count === 1 ? "voter casts" : "voters cast"} the
            ballots below. Their average utility is{" "}
            <span className="font-mi-mono">{formatUtility(Math.round(mean))}</span>.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Card title="Single choice" readBy="Plurality" rule="Mark one: the favorite.">
              <CandidateMark id={cast.choice} size={18} className="text-lg font-semibold" />
            </Card>

            <Card title="Ranked" readBy="IRV, Borda, Ranked Pairs" rule="Order every candidate.">
              <span className="flex flex-wrap items-center gap-1 font-mi-mono text-sm">
                {cast.ranking.map((id, position) => (
                  <span key={id} className="inline-flex items-center gap-1">
                    {position > 0 ? <span className="text-mi-muted">›</span> : null}
                    <CandidateMark id={id} size={13} />
                  </span>
                ))}
              </span>
            </Card>

            <Card
              title="Approval"
              readBy="Approval"
              rule="Approve every candidate above your average."
            >
              <ul className="flex flex-wrap gap-x-3 gap-y-1 font-mi-mono text-sm">
                {candidates.map((id) => {
                  const approved = cast.approvals.includes(id);
                  return (
                    <li key={id} className={cn("inline-flex items-center gap-1", !approved && "text-mi-muted")}>
                      <CandidateGlyph id={id} size={12} />
                      {id} {approved ? "✓" : "–"}
                    </li>
                  );
                })}
              </ul>
              {cast.approvals.length === 0 ? (
                <p className="mt-1 text-xs text-mi-muted">Indifferent, so this ballot is blank.</p>
              ) : null}
            </Card>

            <Card title="Score" readBy="Score" rule="Rescale worst to 0 and favorite to 10.">
              <ul className="space-y-0.5">
                {candidates.map((id) => (
                  <li key={id} className="grid grid-cols-[2.25rem_minmax(0,1fr)_1.5rem] items-center gap-2 font-mi-mono text-sm">
                    <CandidateMark id={id} size={12} />
                    <span className="h-2">
                      <span
                        className="block h-full rounded-r-[3px]"
                        style={{ width: `${(cast.scores[id] ?? 0) * 10}%`, background: candidateColor(id) }}
                      />
                    </span>
                    <span className="text-right">{cast.scores[id] ?? 0}</span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card
              title="Quadratic"
              readBy="Quadratic voting"
              rule="Votes in proportion to distance from your average; v votes cost v² credits."
              wide
            >
              <QuadraticBallot candidates={candidates} cast={cast} />
            </Card>
          </div>
          <p className="text-xs text-mi-muted">
            Ballot model: {`sincere-v1`}. Equal utilities rank in candidate order.
          </p>
        </>
      )}
    </div>
  );
}

function Card({
  title,
  readBy,
  rule,
  wide,
  children,
}: {
  title: string;
  readBy: string;
  rule: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("rounded-[3px] border border-mi-rule p-2.5", wide && "sm:col-span-2")}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-mi-ink">{title}</h3>
        <span className="text-[0.6875rem] text-mi-muted">read by {readBy}</span>
      </div>
      <p className="mb-2 text-xs text-mi-muted">{rule}</p>
      {children}
    </section>
  );
}

function QuadraticBallot({ candidates, cast }: { candidates: string[]; cast: VoterBallots }) {
  const max = Math.max(1, ...candidates.map((id) => Math.abs(cast.allocations[id] ?? 0)));
  return (
    <div className="space-y-1">
      <ul className="space-y-0.5">
        {candidates.map((id) => {
          const votes = cast.allocations[id] ?? 0;
          const width = (50 * Math.abs(votes)) / max;
          return (
            <li key={id} className="grid grid-cols-[2.25rem_minmax(0,1fr)_2.5rem] items-center gap-2 font-mi-mono text-sm">
              <CandidateMark id={id} size={12} />
              <span className="relative h-2">
                <span aria-hidden className="absolute inset-y-[-3px] left-1/2 w-px bg-mi-rule" />
                <span
                  className={cn("absolute inset-y-0", votes >= 0 ? "left-1/2 rounded-r-[3px]" : "rounded-l-[3px]")}
                  style={{
                    width: `${width}%`,
                    right: votes < 0 ? "50%" : undefined,
                    background: candidateColor(id),
                  }}
                />
              </span>
              <span className="text-right">{votes > 0 ? `+${votes}` : votes}</span>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-mi-muted">
        {cast.credits_used} of {cast.credit_budget} credits
        {cast.credits_used === 0 ? ": indifferent, so no votes." : "."}
      </p>
    </div>
  );
}
