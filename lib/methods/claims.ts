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

/** Each winner with the methods that elect it, in result order. */
function winnerGroups(resolution: ProfileResolveResponse): [string, VotingMethod[]][] {
  const groups = new Map<string, VotingMethod[]>();
  for (const result of resolution.results) {
    groups.set(result.winner, [...(groups.get(result.winner) ?? []), result.method]);
  }
  return [...groups.entries()];
}

/** Who each method elects, e.g. "Plurality elects A, instant runoff elects B, the other five elect C". */
export function countsClaim(resolution: ProfileResolveResponse): Claim {
  const n = resolution.results.length;
  const groups = winnerGroups(resolution);
  const cw = resolution.criteria.condorcet_winner;

  let title: string;
  if (groups.length === 1) {
    title = `All ${numberWord(n)} methods elect ${groups[0][0]}`;
  } else if (groups.length <= 3) {
    // The largest group, when it is a clear majority of methods, reads as "the other k"
    const largest = groups.reduce((a, b) => (b[1].length > a[1].length ? b : a));
    const others = largest[1].length >= 3 ? largest : null;
    const parts = groups
      .filter((group) => group !== others)
      .map(([winner, methods]) => `${elects(methods)} ${winner}`);
    if (others) parts.push(`the other ${numberWord(others[1].length)} elect ${others[0]}`);
    title = capitalize(parts.join(", "));
  } else {
    title = `${capitalize(numberWord(n))} counts, ${numberWord(groups.length)} different winners`;
  }

  const electing = resolution.results.filter((result) => result.winner === cw).length;
  const takeaway =
    cw === null
      ? "No candidate beats every rival head to head, so each method settles the disagreement its own way."
      : electing === n
        ? `${cw} beats every rival head to head, and every method elects it.`
        : `${cw} beats every rival head to head, yet ${numberWord(n - electing)} of the ${numberWord(n)} methods elect someone else.`;

  return { title, takeaway };
}

/** The headline numbers of the simulation, from its largest candidate count. */
export function atScaleTakeaway(summary: SimulationSummary): string {
  const group = summary.by_candidates[summary.by_candidates.length - 1];
  const most = group.disagreement.reduce((a, b) => ((b.rate ?? 0) > (a.rate ?? 0) ? b : a));
  const methods = Object.keys(group.condorcet_efficiency) as VotingMethod[];
  const worst = methods.reduce((a, b) =>
    (group.condorcet_efficiency[b].rate ?? 1) < (group.condorcet_efficiency[a].rate ?? 1) ? b : a
  );
  const missed = 1 - (group.condorcet_efficiency[worst].rate ?? 1);
  return (
    `With ${group.candidates} candidates, ${methodName(most.a)} and ${methodName(most.b)} elect ` +
    `different winners in ${((most.rate ?? 0) * 100).toFixed(0)}% of ` +
    `${group.elections.toLocaleString("en-US")} elections, and ${methodName(worst)} misses the ` +
    `Condorcet winner in ${(missed * 100).toFixed(0)}% of those that have one. ` +
    "Cycles are rare in this model; disagreement is not."
  );
}
