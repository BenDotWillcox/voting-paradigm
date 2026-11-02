import type { IRVTrace, ProfileResolveResponse, RankedPairsTrace, Victory } from "@/types/methods";

/** Presentation of recorded rounds only: this does not count or transfer ballots. */
export function inspectIRVRound(trace: IRVTrace, requestedIndex: number) {
  const index = Math.max(0, Math.min(requestedIndex, trace.rounds.length - 1));
  const round = trace.rounds[index];
  const previous = trace.rounds[index - 1];
  const next = trace.rounds[index + 1];
  // The package records a separate, one-candidate final count after elimination.
  const survivorReturn = Boolean(previous && round && Object.keys(round.counts).length === 1);
  return { index, round, previous, next, survivorReturn };
}

export function irvSourcePhase(trace: IRVTrace, index: number, phase: string) {
  const { round, next, survivorReturn } = inspectIRVRound(trace, index);
  const decision = survivorReturn ? "survivor" : "winner";
  if (phase === "count") return survivorReturn ? "survivor_count" : "count";
  if (phase === "eliminate") return round?.eliminated.length ? (round.elimination_was_tiebreak ? "eliminate_tie" : "eliminate") : decision;
  if (phase === "transfer") return next ? "transfer" : decision;
  return decision;
}

/** A grouped view of saved edges, not a reconstruction of their processing order. */
export function recordedVictoryGroups(trace: RankedPairsTrace, pairwise: ProfileResolveResponse["pairwise"]) {
  const entries = [
    ...trace.locked.map((edge) => ({ ...edge, status: "locked" as const })),
    ...trace.skipped.map((edge) => ({ ...edge, status: "skipped" as const })),
  ];
  const groups = new Map<string, { margin: number; winningVotes: number; edges: typeof entries }>();
  for (const edge of entries) {
    const winningVotes = pairwise[edge.winner][edge.loser];
    const key = `${edge.margin}:${winningVotes}`;
    const group = groups.get(key) ?? { margin: edge.margin, winningVotes, edges: [] };
    group.edges.push(edge);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => b.margin - a.margin || b.winningVotes - a.winningVotes);
}

/** Reads the final recorded graph's incoming edges; does not choose a winner. */
export function recordedGraphSources(candidates: string[], locked: Victory[]) {
  const incoming = new Set(locked.map((edge) => edge.loser));
  return candidates.filter((candidate) => !incoming.has(candidate));
}
