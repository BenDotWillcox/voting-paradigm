"use client";

import { cn } from "@/lib/utils";
import { inspectIRVRound } from "@/lib/methods/inspector-state";
import type { ProfileMethodResult, ProfileResolveResponse, VoterBallots, VotingMethod } from "@/types/methods";

import { CandidateMark } from "./glyph";

const COUNT_AND_WINNER = [{ id: "count", label: "Count" }, { id: "winner", label: "Winner" }];

export function additionalMethodSteps(method: VotingMethod) {
  if (method === "irv") return [
    { id: "count", label: "Count" },
    { id: "eliminate", label: "Eliminate" },
    { id: "transfer", label: "Transfer" },
    { id: "winner", label: "Winner" },
  ];
  if (method === "quadratic") return [
    { id: "count", label: "Count" },
    { id: "credits", label: "Credits" },
    { id: "winner", label: "Winner" },
  ];
  return COUNT_AND_WINNER;
}

/** Reads recorded state and ballot inputs; never re-resolves a method. */
export function additionalStageExplanation(result: ProfileMethodResult, phase: string, roundIndex = 0) {
  const trace = result.trace;
  const winner = result.winner;
  const tie = result.tiebreaks.length ? "The saved result includes a seeded tiebreak." : "No tiebreak is needed in this count.";
  if (trace.kind === "irv") {
    const { round, next, previous, survivorReturn } = inspectIRVRound(trace, roundIndex);
    if (!round) return { title: "No recorded rounds", body: "The response contains no round state to inspect." };
    const eliminated = round.eliminated.join(", ");
    const active = Object.values(round.counts).reduce((sum, count) => sum + count, 0);
    if (phase === "count") return {
      title: `Round ${round.round_number}: count each active choice`,
      body: survivorReturn ? "After elimination leaves one candidate, the package records one final count. These are those recorded counts, not an additional majority decision." : `Each ballot counts for its highest-ranked remaining candidate. These are Python's round ${round.round_number} counts; exhausted ballots have no remaining choice.`,
    };
    if (phase === "eliminate") {
      if (!round.eliminated.length) return { title: "No elimination in this round", body: survivorReturn ? "This is the final count for the sole surviving candidate. The method returns that candidate without another elimination or majority check." : "The majority check ends the count in this round, so Python never enters the elimination branch." };
      if (round.elimination_was_tiebreak) return { title: "A tie determines who remains", body: `The saved elimination uses the seeded tiebreak. In this final-round tie, the selected winner remains and ${eliminated} ${round.eliminated.length === 1 ? "is" : "are"} eliminated. The next recorded round counts the survivor's ballots.` };
      return { title: `${eliminated} ${round.eliminated.length === 1 ? "has" : "share"} the fewest votes`, body: `No candidate has a majority in round ${round.round_number}. ${round.eliminated.length > 1 ? "The package eliminates all candidates tied at the minimum together because at least one candidate remains. This is a batch elimination, not a random tiebreak." : "The package eliminates the single candidate with the fewest votes."}` };
    }
    if (phase === "transfer") return next
      ? { title: `Round ${round.round_number} → ${next.round_number}`, body: `After eliminating ${eliminated}, the helper advances past eliminated choices. The bars compare these consecutive recorded rounds; it does not simulate transfers. Exhausted ballots change from ${round.exhausted_ballots} to ${next.exhausted_ballots}.` }
      : { title: "No next transfer", body: `Round ${round.round_number} is the final recorded count. ${trace.rounds.length === 1 ? "The winner was found immediately, so no ballots needed to transfer." : "There is no later round to compare."} The source shows the return path used here.` };
    if (survivorReturn) return {
      title: `${winner} is the sole remaining candidate`,
      body: `${previous?.elimination_was_tiebreak ? "The preceding round used the seeded tiebreak to select the survivor. " : "The preceding elimination left one candidate. "}Python records ${round.counts[winner]} active votes for ${winner} and returns the survivor. This return does not run another majority check.`,
    };
    return { title: `${winner} clears the majority threshold`, body: `${winner} has ${round.counts[winner]} of ${active} active ballots in round ${round.round_number}. The count exceeds ${active / 2}, so Python returns ${winner}. Exhausted ballots are excluded from that threshold.` };
  }
  if (trace.kind === "borda") return phase === "winner"
    ? { title: `${winner} has the most points`, body: `${winner} finishes with ${trace.points[winner]} points. The method chooses the largest accumulated point total. ${tie}` }
    : { title: "Ranking positions become points", body: `Each ballot gives ${trace.max_points_per_ballot} points to its first choice, then one fewer per position down to zero. The loop adds those points to each candidate's total; the totals shown are Python's saved result.` };
  if (trace.kind === "approval") return phase === "winner"
    ? { title: `${winner} has the most approvals`, body: `${winner} receives ${trace.approvals[winner]} approvals. A ballot may approve several candidates, so approval totals across candidates can exceed the number of voters. ${tie}` }
    : { title: "Each approved candidate gets one vote", body: "The counter adds one to every candidate named in a ballot's approval set. These approval choices were supplied by the ballot model; the counting method does not choose the approval threshold." };
  if (trace.kind === "score") return phase === "winner"
    ? { title: `${winner} has the highest score total`, body: `${winner} finishes with ${trace.totals[winner]} points. The method compares candidate totals after adding all ballot scores. ${tie}` }
    : { title: "Add each candidate's scores", body: `The recorded ballots contain scores from 0 to ${trace.max_score}. A score of zero contributes zero and is a valid rating. The method adds these supplied scores; the ballot model chose how preferences became scores.` };
  if (trace.kind === "quadratic") {
    if (phase === "credits") return { title: "Credit cost is separate from the vote total", body: "An allocation of v votes costs v² credits, including when v is negative. The ballot constructor enforces the credit budget. This resolver records the spent and available credits; candidate totals receive signed votes, not squared costs." };
    if (phase === "winner") return { title: `${winner} has the highest net vote total`, body: `${winner} finishes with ${signed(trace.net_votes[winner])} net votes. Negative allocations subtract from a candidate's total, while positive allocations add to it. ${tie}` };
    return { title: "Add signed vote allocations", body: "For each ballot, the loop adds its signed allocation to each candidate's total. The ballot model supplied these allocations under a credit budget; the resolver tallies them and records their cost." };
  }
  return { title: "Recorded count", body: "Inspect the result returned by Python." };
}

export function AdditionalMethodState({ result, phase, resolution, roundIndex = 0 }: {
  result: ProfileMethodResult;
  phase: string;
  resolution: ProfileResolveResponse;
  roundIndex?: number;
}) {
  const trace = result.trace;
  const candidates = resolution.rankings.candidates;
  const winner = phase === "winner" ? result.winner : undefined;
  if (trace.kind === "irv") {
    const { round, next } = inspectIRVRound(trace, roundIndex);
    if (!round) return null;
    if (phase === "transfer" && next) return <table className="w-full table-fixed border-collapse text-sm text-mi-ink">
      <caption className="mb-2 text-left text-mi-ink-2">Recorded counts in consecutive rounds</caption>
      <thead><tr className="border-b border-mi-rule"><th scope="col" className="w-1/3 py-2 text-left font-normal">Choice</th><th scope="col" className="py-2 text-center font-normal">Round {round.round_number}</th><th scope="col" className="py-2 text-center font-normal">Round {next.round_number}</th></tr></thead>
      <tbody>{candidates.filter((candidate) => round.counts[candidate] !== undefined).map((candidate) => {
        const after = next.counts[candidate];
        const gain = after === undefined ? 0 : after - round.counts[candidate];
        return <tr key={candidate} className="border-b border-mi-rule"><th scope="row" className="py-3 text-left font-normal"><CandidateMark id={candidate} size={14} className="min-w-0 [&>span]:break-all" /></th><td className="py-3 text-center font-mi-mono text-lg">{round.counts[candidate]}</td><td className={cn("py-3 text-center", gain > 0 && "bg-mi-wash")}><span className="font-mi-mono text-lg">{after ?? "—"}</span>{gain > 0 ? <span className="mt-1 block text-sm">+{gain}</span> : after === undefined ? <span className="mt-1 block text-sm">Out</span> : null}</td></tr>;
      })}</tbody>
    </table>;
    const active = Object.values(round.counts).reduce((sum, count) => sum + count, 0);
    return <><p className="font-mi-mono text-sm text-mi-ink-2">Round {round.round_number} · {active} active · {round.exhausted_ballots} exhausted</p><SavedTotals label="Saved IRV round counts" candidates={candidates.filter((candidate) => round.counts[candidate] !== undefined)} values={round.counts} winner={winner} eliminated={phase === "eliminate" ? round.eliminated : []} />{round.elimination_was_tiebreak && <p className="text-sm text-mi-ink-2">Recorded elimination: seeded tiebreak.</p>}{phase === "count" && <RankedBallots resolution={resolution} />}</>;
  }
  if (trace.kind === "borda") return <><SavedTotals label="Saved Borda point totals" values={trace.points} candidates={candidates} winner={winner} />{phase === "count" && <RankedBallots resolution={resolution} maxPoints={trace.max_points_per_ballot} />}</>;
  if (trace.kind === "approval") return <><SavedTotals label="Saved approval totals" values={trace.approvals} candidates={candidates} winner={winner} /><BallotModelNote resolution={resolution} />{phase === "count" && <RatedBallots resolution={resolution} kind="approval" />}</>;
  if (trace.kind === "score") return <><SavedTotals label="Saved score totals" values={trace.totals} candidates={candidates} winner={winner} /><BallotModelNote resolution={resolution} />{phase === "count" && <RatedBallots resolution={resolution} kind="score" />}</>;
  if (trace.kind === "quadratic") return <>{phase === "credits" ? <div className="space-y-2 rounded-[3px] bg-mi-wash p-3 text-sm text-mi-ink"><p className="font-medium">Saved credit metrics</p><p><strong className="font-mi-mono">{trace.credits_spent.toLocaleString("en-US")}</strong> spent across counted ballots</p><p><strong className="font-mi-mono">{trace.credits_available.toLocaleString("en-US")}</strong> available across counted ballots</p></div> : <SavedTotals label="Saved quadratic net vote totals" values={trace.net_votes} candidates={candidates} winner={winner} signedValues />}<BallotModelNote resolution={resolution} />{phase !== "winner" && <RatedBallots resolution={resolution} kind="quadratic" showCredits={phase === "credits"} />}</>;
  return null;
}

function SavedTotals({ label, values, candidates, winner, eliminated = [], signedValues = false }: {
  label: string;
  values: Record<string, number>;
  candidates: string[];
  winner?: string;
  eliminated?: string[];
  signedValues?: boolean;
}) {
  return <ul aria-label={label} className="space-y-2">{candidates.map((candidate) => <li key={candidate} className={cn("flex flex-wrap items-center justify-between gap-2 rounded-[3px] border border-mi-rule p-3 text-mi-ink", (candidate === winner || eliminated.includes(candidate)) && "bg-mi-wash border-mi-ink")}><CandidateMark id={candidate} size={17} className="min-w-0 max-w-full [&>span]:break-all" /><span className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1"><span className="font-mi-mono text-lg">{signedValues ? signed(values[candidate] ?? 0) : values[candidate] ?? 0}</span>{candidate === winner ? <span className="text-sm">Winner</span> : eliminated.includes(candidate) ? <span className="text-sm">Eliminated</span> : null}</span></li>)}</ul>;
}

function RankedBallots({ resolution, maxPoints }: { resolution: ProfileResolveResponse; maxPoints?: number }) {
  return <details className="rounded-[3px] border border-mi-rule px-3"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium text-mi-ink">{maxPoints === undefined ? "See the ranked ballot groups" : "See points contributed by each ballot"}</summary><ul className="space-y-3 pb-3">{resolution.rankings.rows.map((row) => <li key={row.ranking.join("|")} className="space-y-2 rounded-[3px] border border-mi-rule p-3"><p className="font-mi-mono text-sm text-mi-ink-2">{row.count} voters</p><div className="flex flex-wrap gap-x-3 gap-y-2 text-sm text-mi-ink">{row.ranking.map((candidate, position) => <span key={candidate} className="inline-flex min-w-0 max-w-full items-center gap-1.5">{maxPoints === undefined && position > 0 ? <span aria-label="preferred to">›</span> : null}<CandidateMark id={candidate} size={13} className="min-w-0 [&>span]:break-all" />{maxPoints !== undefined && <span className="font-mi-mono">{maxPoints - position} pt</span>}</span>)}</div></li>)}</ul></details>;
}

function BallotModelNote({ resolution }: { resolution: ProfileResolveResponse }) {
  return <p className="text-sm leading-relaxed text-mi-ink-2">Ballots supplied by <code className="font-mi-mono">{resolution.ballot_model ?? "the recorded input"}</code>. The counting method consumes these choices.</p>;
}

function RatedBallots({ resolution, kind, showCredits = false }: { resolution: ProfileResolveResponse; kind: "approval" | "score" | "quadratic"; showCredits?: boolean }) {
  const [first, ...rest] = resolution.voter_ballots;
  const rows = showCredits ? rest : resolution.voter_ballots;
  return <div className="space-y-3">
    {showCredits && first && <div className="space-y-2"><p className="text-sm font-medium text-mi-ink">One recorded ballot group</p><ul aria-label="Representative quadratic ballot"><RatedBallotCard ballot={first} candidates={resolution.rankings.candidates} kind={kind} showCredits /></ul></div>}
    {rows.length > 0 && <details className="rounded-[3px] border border-mi-rule px-3"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium text-mi-ink">{showCredits ? "See the other ballot groups" : "See the recorded ballots"}</summary><ul className="space-y-3 pb-3" aria-label="Recorded ballot groups">{rows.map((ballot) => <RatedBallotCard key={ballot.row} ballot={ballot} candidates={resolution.rankings.candidates} kind={kind} showCredits={showCredits} />)}</ul></details>}
  </div>;
}

function RatedBallotCard({ ballot, candidates, kind, showCredits }: { ballot: VoterBallots; candidates: string[]; kind: "approval" | "score" | "quadratic"; showCredits: boolean }) {
  return <li className="space-y-2 rounded-[3px] border border-mi-rule p-3"><p className="font-mi-mono text-sm text-mi-ink-2">{ballot.count} voters · each ballot</p><div className="flex flex-wrap gap-x-3 gap-y-2 text-sm text-mi-ink">{kind === "approval" ? (ballot.approvals.length ? ballot.approvals.map((candidate) => <span key={candidate} className="inline-flex min-w-0 max-w-full items-center gap-1.5"><CandidateMark id={candidate} size={13} className="min-w-0 [&>span]:break-all" /><span aria-label="approved">✓</span></span>) : <span>No approvals</span>) : candidates.map((candidate) => <span key={candidate} className="inline-flex min-w-0 max-w-full items-center gap-1.5"><CandidateMark id={candidate} size={13} className="min-w-0 [&>span]:break-all" /><span className="font-mi-mono">{kind === "score" ? ballot.scores[candidate] ?? 0 : signed(ballot.allocations[candidate] ?? 0)}</span></span>)}</div>{showCredits && <p className="text-sm text-mi-ink-2"><span className="font-mi-mono text-mi-ink">{ballot.credits_used} / {ballot.credit_budget}</span> credits used per ballot</p>}</li>;
}

function signed(value: number) {
  return value > 0 ? `+${value}` : String(value);
}
