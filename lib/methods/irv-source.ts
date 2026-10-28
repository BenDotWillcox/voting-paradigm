import "server-only";

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { IRVSource } from "@/lib/methods/irv-inspector";

/** Read the package itself; the inspector never maintains a second implementation. */
export async function loadIRVSource(): Promise<IRVSource> {
  const path = "voting/methods/irv.py";
  const source = (await readFile(join(process.cwd(), path), "utf-8")).replace(/\r\n/g, "\n");
  const lines = source.split("\n");

  function excerpt(first: string, until: string): IRVSource["excerpts"]["count"] {
    // Exact anchors intentionally fail if a refactor changes this presentation's
    // mapping. Never silently display an unrelated source range.
    const start = lines.indexOf(first);
    const end = lines.indexOf(until, start + 1);
    if (start < 0 || end < 0) throw new Error(`IRV source excerpt no longer matches: ${first.trim()}`);
    const selected = lines.slice(start, end);
    while (selected[selected.length - 1] === "") selected.pop();
    return { startLine: start + 1, lines: selected };
  }

  return {
    path,
    sha256: createHash("sha256").update(source).digest("hex"),
    source,
    excerpts: {
      count: excerpt("        for index, ballot in enumerate(active_ballots):", "        # Check for majority winner"),
      eliminate: excerpt("        min_votes = min(vote_counts.values())", "        # Determine who to eliminate"),
      transfer: excerpt("    index = start_index", "def resolve_irv("),
      winner: excerpt("        # Check for majority winner", "        if winner is not None:"),
    },
  };
}
