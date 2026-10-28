import "server-only";

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { CountSource, CountSources, InspectableMethod } from "@/lib/methods/count-inspector";

/** Exact package excerpts, never a second educational implementation. */
async function loadSource(method: InspectableMethod): Promise<CountSource> {
  const path = `voting/methods/${method}.py`;
  const source = (await readFile(join(process.cwd(), path), "utf-8")).replace(/\r\n/g, "\n");
  const lines = source.split("\n");

  function excerpt(first: string, until: string): CountSource["excerpts"][string] {
    const start = lines.indexOf(first);
    const end = lines.indexOf(until, start + 1);
    if (start < 0 || end < 0) throw new Error(`${method} source excerpt no longer matches: ${first.trim()}`);
    const selected = lines.slice(start, end);
    while (selected[selected.length - 1] === "") selected.pop();
    return { startLine: start + 1, lines: selected };
  }

  const anchors: Record<InspectableMethod, Record<string, [string, string]>> = {
    plurality: {
      count: ["    # Count votes and abstentions", "    # Find the highest vote count"],
      winner: ["    # Find the highest vote count", "    return ElectionResult("],
    },
    irv: {
      count: ["        for index, ballot in enumerate(active_ballots):", "        # Check for majority winner"],
      eliminate: ["        min_votes = min(vote_counts.values())", "        # Record this round"],
      eliminate_tie: ["        if len(candidates_with_min) >= len(remaining_candidates):", "        elif len(remaining_candidates) - len(candidates_with_min) >= 1:"],
      transfer: ["    index = start_index", "def resolve_irv("],
      winner: ["        # Check for majority winner", "        if winner is not None:"],
      survivor_count: ["            # Count final round", "            rounds.append(IRVRound("],
      survivor: ["        # Check if only one candidate remains", "        if len(remaining_candidates) == 0:"],
    },
    borda: {
      count: ["    # Count abstentions and tally points", "    # Find highest point total"],
      winner: ["    # Find highest point total", "    # Calculate average points"],
    },
    approval: {
      count: ["    # Count approvals and abstentions", "    # Calculate metrics"],
      winner: ["    # Find the highest approval count", "    return ApprovalResult("],
    },
    score: {
      count: ["    # Count abstentions and tally scores", "    # Calculate metrics"],
      winner: ["    # Find highest score total", "    # Use score_totals as vote_counts for compatibility"],
    },
    quadratic: {
      count: ["    for ballot in ballots:", "        # Track credit metrics"],
      credits: ["        known_cost = 0", "    # Calculate aggregate utilization"],
      winner: ["    # Determine winner. If no known-candidate votes were cast, treat as no-result.", "    # Use vote_totals as vote_counts for base class compatibility"],
    },
    ranked_pairs: {
      pairwise: ["        # For each pair, check preference using O(1) lookup", "    return matrix"],
      condorcet: ["    for candidate in candidate_ids:", "def _get_all_victories("],
      // The caller can also expose the early return. No edges are locked on it.
      condorcet_return: ["    # Check for Condorcet winner", "    # No Condorcet winner - apply Ranked Pairs"],
      order: ["    ordered = sorted(victories, key=lambda v: (-v[2], -v[3]))", "def _priority_order("],
      priority: ["        # If the rest can all be locked, their order cannot matter; otherwise", "        for winner, loser, margin, _ in open_victories:"],
      lock: ["        for winner, loser, margin, _ in open_victories:", "    # Find winner: candidate with no incoming edges"],
      cycle: ["    # If adding winner→loser, check if loser can already reach winner", "def _stays_acyclic("],
      winner: ["    # Find winner: candidate with no incoming edges", "    return _LockOutcome("],
    },
  };
  const excerpts = Object.fromEntries(Object.entries(anchors[method]).map(([key, [first, until]]) => [key, excerpt(first, until)]));

  return { path, source, sha256: createHash("sha256").update(source).digest("hex"), excerpts };
}

export async function loadCountSources(): Promise<CountSources> {
  const [plurality, irv, borda, ranked_pairs, approval, score, quadratic] = await Promise.all([
    loadSource("plurality"), loadSource("irv"), loadSource("borda"), loadSource("ranked_pairs"),
    loadSource("approval"), loadSource("score"), loadSource("quadratic"),
  ]);
  return { plurality, irv, borda, ranked_pairs, approval, score, quadratic };
}
