/**
 * Chapter 1 of the methods page: one electorate, its five ballots and seven
 * counts, one step at a time. Copy is written from the electorate's
 * resolution, so every number on a step is the artifact's. Display only.
 */

import { numberWord } from "@/lib/methods/claims";
import { METHOD_META } from "@/lib/methods/instrument";
import type { ProfileMethodResult, ProfileResolveResponse, VotingMethod } from "@/types/methods";

/** The preset chapter 1 walks through. */
export const WALK_PRESET = "center-squeeze";

export type BallotKind = "single" | "ranked" | "approval" | "score" | "quadratic";

export interface StepCopy {
  transition: string;
  title: string;
  takeaway: string;
}

/** The methods in the order chapter 1 counts them, which is result order. */
export const COUNT_ORDER: VotingMethod[] = [
  "plurality",
  "irv",
  "borda",
  "ranked_pairs",
  "approval",
  "score",
  "quadratic",
];

function result(resolution: ProfileResolveResponse, method: VotingMethod): ProfileMethodResult {
  const found = resolution.results.find((r) => r.method === method);
  if (!found) throw new Error(`No ${method} result in the walkthrough electorate`);
  return found;
}

/** Voters who rank a candidate last. */
function rankedLast(resolution: ProfileResolveResponse, id: string): number {
  return resolution.voter_ballots
    .filter((cast) => cast.ranking[cast.ranking.length - 1] === id)
    .reduce((sum, cast) => sum + cast.count, 0);
}

/** Whether every voter ranks a candidate first or second. */
function everyonesTopTwo(resolution: ProfileResolveResponse, id: string): boolean {
  return resolution.voter_ballots.every((cast) => cast.ranking.indexOf(id) <= 1);
}

/** The candidate after the winner by a tally, and its value. */
function runnerUp(tally: Record<string, number>, winner: string): [string, number] {
  const [id, value] = Object.entries(tally)
    .filter(([candidate]) => candidate !== winner)
    .sort(([, a], [, b]) => b - a)[0];
  return [id, value];
}

/** Every two-way race, winner first, largest margin first. */
export function races(resolution: ProfileResolveResponse): { winner: string; loser: string; for: number; against: number }[] {
  const candidates = resolution.rankings.candidates;
  const all = candidates.flatMap((a, i) =>
    candidates.slice(i + 1).map((b) => {
      const ab = resolution.pairwise[a]?.[b] ?? 0;
      const ba = resolution.pairwise[b]?.[a] ?? 0;
      return ab >= ba
        ? { winner: a, loser: b, for: ab, against: ba }
        : { winner: b, loser: a, for: ba, against: ab };
    })
  );
  return all.sort((x, y) => y.for - y.against - (x.for - x.against));
}

export function votersCopy(resolution: ProfileResolveResponse): StepCopy {
  return {
    transition: "Start with the voters, not the ballot.",
    title: "Meet the voters",
    takeaway: `${resolution.total_voters} voters in ${numberWord(resolution.voter_ballots.length)} groups. Each group places the candidates on a scale from 0 to 10, and every ballot in this chapter is read off these scales.`,
  };
}

export const BALLOT_RULES: Record<BallotKind, { name: string; readBy: string; rule: string }> = {
  single: { name: "Single choice", readBy: "Plurality", rule: "Mark one candidate: the top of your scale." },
  ranked: {
    name: "Ranked",
    readBy: "Instant runoff, Borda count, Ranked Pairs",
    rule: "Put every candidate in order, from the top of your scale down.",
  },
  approval: { name: "Approval", readBy: "Approval", rule: "Approve every candidate above your own average." },
  score: { name: "Score", readBy: "Score voting", rule: "Stretch your scale so your favorite gets 10 and your least favorite 0." },
  quadratic: {
    name: "Quadratic",
    readBy: "Quadratic voting",
    rule: "Spend credits for or against; v votes on one candidate cost v². Votes follow distance from your average.",
  },
};

export function ballotCopy(kind: BallotKind, resolution: ProfileResolveResponse): StepCopy {
  switch (kind) {
    case "single":
      return {
        transition: "The simplest ballot.",
        title: "Single choice: mark your favorite",
        takeaway:
          "Each group marks the top of its scale. Nothing else survives: not the second choice, not how far apart the candidates sit.",
      };
    case "ranked":
      return {
        transition: "A ballot that keeps the whole order.",
        title: "Ranked: put every candidate in order",
        takeaway: "Each group lists the candidates from the top of its scale down. The order survives; the distances between them do not.",
      };
    case "approval": {
      const everyone = resolution.rankings.candidates.filter((id) =>
        resolution.voter_ballots.every((cast) => cast.approvals.includes(id))
      );
      return {
        transition: "A ballot for every acceptable candidate.",
        title: "Approval: mark everyone acceptable",
        takeaway: `A sincere voter approves every candidate above their own average.${
          everyone.length === 1 ? ` ${everyone[0]} clears that bar for every group.` : ""
        }`,
      };
    }
    case "score":
      return {
        transition: "A ballot that keeps how much.",
        title: "Score: rate every candidate",
        takeaway:
          "Each voter's scale is stretched so the favorite gets 10 and the least favorite 0. How much a voter prefers one candidate now counts, not just the order.",
      };
    case "quadratic": {
      const budget = resolution.voter_ballots[0]?.credit_budget ?? 0;
      return {
        transition: "A budget, spent for or against.",
        title: "Quadratic: spend credits for or against",
        takeaway: `Each voter has ${budget} credits, and v votes on one candidate cost v². Votes against are possible, and strong feelings cost more.`,
      };
    }
  }
}

/** How each count works, in a sentence or two. */
export function countRule(method: VotingMethod, resolution: ProfileResolveResponse): string {
  switch (method) {
    case "plurality":
      return "Count each ballot's mark. Most marks wins.";
    case "irv":
      return "If no one has a majority of first choices, drop the candidate with the fewest and move those ballots to their next choice. Repeat until someone has a majority.";
    case "borda": {
      const trace = result(resolution, "borda").trace;
      const top = trace.kind === "borda" ? trace.max_points_per_ballot : 0;
      return `Each ballot gives ${top} points to its first choice, one fewer for each place down, and 0 to its last. Most points wins.`;
    }
    case "ranked_pairs":
      return "Take every two-way race. Lock in the wins from the largest margin down, skipping any that would close a cycle. The winner is the candidate no locked win beats.";
    case "approval":
      return "Count the approvals. Most approvals wins.";
    case "score":
      return "Add up the scores. Highest total wins.";
    case "quadratic":
      return "Add up each candidate's votes for, minus votes against. Highest net wins.";
  }
}

const COUNT_TRANSITIONS: Record<VotingMethod, string> = {
  plurality: "Count the single-choice ballots.",
  irv: "The first count that reads the whole order.",
  borda: "The same ranked ballots, counted by position.",
  ranked_pairs: "A count built from those races.",
  approval: "Count the approval ballots.",
  score: "Add up the score ballots.",
  quadratic: "The last of the seven counts.",
};

export function countCopy(method: VotingMethod, resolution: ProfileResolveResponse): StepCopy {
  const counted = result(resolution, method);
  const winner = counted.winner;
  const trace = counted.trace;
  const total = resolution.total_voters;
  const title = `${METHOD_META[method].label} elects ${winner}`;
  let takeaway = "";

  if (trace.kind === "plurality") {
    const last = rankedLast(resolution, winner);
    takeaway = `${winner} has the most first choices, ${trace.first_choices[winner]} of ${total}${
      last > 0 ? `, yet ${last} voters rank ${winner} last` : ""
    }.`;
  } else if (trace.kind === "irv") {
    const out = trace.rounds[0]?.eliminated[0];
    const final = trace.rounds[trace.rounds.length - 1]?.counts[winner] ?? 0;
    takeaway = out
      ? `${out} has the fewest first choices, so it goes out first${
          everyonesTopTwo(resolution, out) ? `, though every voter ranks ${out} first or second` : ""
        }. Its ballots move on, and ${winner} wins with ${final} of ${total}.`
      : `${winner} has a majority of first choices, so no one is eliminated.`;
  } else if (trace.kind === "borda") {
    const [second, points] = runnerUp(trace.points, winner);
    takeaway = `Second places now earn points. ${winner} has ${trace.points[winner]}, ahead of ${second} with ${points}${
      everyonesTopTwo(resolution, winner) ? `, because every voter ranks ${winner} first or second` : ""
    }.`;
  } else if (trace.kind === "ranked_pairs") {
    const cw = resolution.criteria.condorcet_winner;
    takeaway =
      cw === winner
        ? `${winner} wins every two-way race, so nothing locked ever beats it: Ranked Pairs elects the Condorcet winner whenever there is one.`
        : `No candidate wins every race, so the locking order decides: ${winner} is the one candidate no locked win beats.`;
  } else if (trace.kind === "approval") {
    const [second, approvals] = runnerUp(trace.approvals, winner);
    takeaway = `${winner} is approved by ${trace.approvals[winner]} of ${total} voters; the next, ${second}, by ${approvals}.`;
  } else if (trace.kind === "score") {
    const max = total * trace.max_score;
    takeaway = `${winner} totals ${trace.totals[winner]} of a possible ${max}, an average of ${(
      (trace.totals[winner] ?? 0) / Math.max(total, 1)
    ).toFixed(1)} out of ${trace.max_score}.`;
  } else if (trace.kind === "quadratic") {
    const [most, low] = Object.entries(trace.net_votes).sort(([, a], [, b]) => a - b)[0];
    takeaway = `${winner} ends at ${signed(trace.net_votes[winner] ?? 0)} net votes. ${most}, at ${signed(low)}, draws the most votes against.`;
  }

  return { transition: COUNT_TRANSITIONS[method], title, takeaway };
}

export function headToHeadCopy(resolution: ProfileResolveResponse): StepCopy {
  const { condorcet_winner: cw, condorcet_loser: cl } = resolution.criteria;
  const plurality = result(resolution, "plurality").winner;
  return {
    transition: "Ranked ballots also settle every two-way race.",
    title: cw ? `${cw} beats every rival one-on-one` : "No candidate beats every rival one-on-one",
    takeaway: `A candidate who wins every two-way race is the Condorcet winner${cw ? ` (here ${cw})` : ""}; one who loses every race is the Condorcet loser${
      cl ? ` (here ${cl}${cl === plurality ? ", plurality's winner" : ""})` : ""
    }.`,
  };
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}
