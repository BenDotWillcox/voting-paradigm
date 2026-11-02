/**
 * Slide claims: the sentence each slide's graph proves, written from the
 * electorate being shown so the copy stays true when the electorate changes.
 * Display only.
 */

import { METHOD_META } from "@/lib/methods/instrument";
import type { ProfileResolveResponse, SimulationSummary, VotingMethod } from "@/types/methods";

export interface Claim {
  title: string;
  takeaway: string;
}

const NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven"];

export function numberWord(n: number): string {
  return NUMBER_WORDS[n] ?? String(n);
}

// Borda and Ranked Pairs are named after people and keep their capitals
function methodName(method: VotingMethod): string {
  const label = METHOD_META[method].label;
  return method === "borda" || method === "ranked_pairs" ? label : label.toLowerCase();
}

function listOf(items: string[]): string {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function elects(methods: VotingMethod[]): string {
  return `${listOf(methods.map(methodName))} ${methods.length === 1 ? "elects" : "elect"}`;
}

/** Who each method elects, e.g. "Plurality elects A, instant runoff elects B, the other five elect C". */
export function winnersTitle(winners: [VotingMethod, string][]): string {
  const n = winners.length;
  // Each winner with the methods that elect it, in method order
  const byWinner = new Map<string, VotingMethod[]>();
  for (const [method, winner] of winners) byWinner.set(winner, [...(byWinner.get(winner) ?? []), method]);
  const groups = [...byWinner.entries()];

  if (groups.length === 1) return `All ${numberWord(n)} methods elect ${groups[0][0]}`;
  if (groups.length > 3) return `${capitalize(numberWord(n))} counts, ${numberWord(groups.length)} different winners`;
  // The largest group, when it is a clear majority of methods, reads as "the other k"
  const largest = groups.reduce((a, b) => (b[1].length > a[1].length ? b : a));
  const others = largest[1].length >= 3 ? largest : null;
  const parts = groups
    .filter((group) => group !== others)
    .map(([winner, methods]) => `${elects(methods)} ${winner}`);
  if (others) parts.push(`the other ${numberWord(others[1].length)} elect ${others[0]}`);
  return capitalize(parts.join(", "));
}

/** The claim for one electorate's seven counts. */
export function countsClaim(resolution: ProfileResolveResponse): Claim {
  const n = resolution.results.length;
  const cw = resolution.criteria.condorcet_winner;
  const title = winnersTitle(resolution.results.map((result) => [result.method, result.winner]));

  const electing = resolution.results.filter((result) => result.winner === cw).length;
  const takeaway =
    cw === null
      ? "No candidate beats every rival head to head, so each method settles the disagreement its own way."
      : electing === n
        ? `${cw} beats every rival head to head, and every method elects it.`
        : `${cw} beats every rival head to head, yet ${numberWord(n - electing)} of the ${numberWord(n)} methods elect someone else.`;

  return { title, takeaway };
}

/** How often the methods disagree, from the simulation's largest candidate count. */
export function disagreementTakeaway(summary: SimulationSummary): string {
  const group = summary.by_candidates[summary.by_candidates.length - 1];
  const most = group.disagreement.reduce((a, b) => ((b.rate ?? 0) > (a.rate ?? 0) ? b : a));
  return (
    `With ${group.candidates} candidates, ${methodName(most.a)} and ${methodName(most.b)} elect ` +
    `different winners in ${((most.rate ?? 0) * 100).toFixed(0)}% of ` +
    `${group.elections.toLocaleString("en-US")} random elections.`
  );
}

/** Which methods always find the Condorcet winner, and how often the worst misses it. */
export function efficiencyClaim(summary: SimulationSummary): Claim {
  const methods = summary.methods;
  const always = methods.filter((method) =>
    summary.by_candidates.every((g) => g.condorcet_efficiency[method].rate === 1)
  );
  const group = summary.by_candidates[summary.by_candidates.length - 1];
  const worst = methods.reduce((a, b) =>
    (group.condorcet_efficiency[b].rate ?? 1) < (group.condorcet_efficiency[a].rate ?? 1) ? b : a
  );
  const missed = 1 - (group.condorcet_efficiency[worst].rate ?? 1);
  return {
    title:
      always.length === 0
        ? "No method always finds the Condorcet winner"
        : `Only ${listOf(always.map(methodName))} always ${always.length === 1 ? "finds" : "find"} the Condorcet winner`,
    takeaway: `With ${group.candidates} candidates, ${methodName(worst)} misses the Condorcet winner in ${(
      missed * 100
    ).toFixed(0)}% of the elections that have one.`,
  };
}
