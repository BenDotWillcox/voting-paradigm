import type { CountSource } from "@/lib/methods/count-inspector";
import { inspectIRVRound, recordedGraphSources } from "@/lib/methods/inspector-state";
import type { ProfileMethodResult, ProfileResolveResponse } from "@/types/methods";

/** One row of a source listing: a real line, or a fold over lines not shown. */
export type ListingRow =
  | { kind: "line"; number: number; text: string }
  | { kind: "fold"; from: number; to: number };

/** Outside the current stage, inside it, or one of the lines that drive it. */
export type RowState = "context" | "stage" | "drive";

export type TokenKind = "plain" | "keyword" | "number" | "call" | "type" | "string" | "comment";

/** Lines that drive each stage, matched only within that stage's excerpt. */
export const STAGE_EMPHASIS: Record<string, RegExp> = {
  count: /vote_counts\[.*\] \+=|point_totals\[.*\] \+=|score_totals\[.*\] \+=|vote_totals\[.*\] \+=|points = max_points|_advance_to_active_choice\(/,
  winner: /max_votes =|max_total =|max_approvals =|elif len\(tied\) == 1|winners = tied|sources =|winner_id = sources|majority_threshold =|if count >|winner = candidate_id/,
  eliminate: /min_votes =|if count == min_votes|to_eliminate = candidates_with_min/,
  eliminate_tie: /winner = tiebreak|to_eliminate =|elimination_was_tiebreak =/,
  transfer: /while index|index \+=|return index, ranking/,
  survivor_count: /_advance_to_active_choice\(|final_vote_counts\[choice\] \+=|final_exhausted \+=/,
  survivor: /if len\(remaining_candidates\) == 1|final_winner =|return IRVResult|winners=\[final_winner\]/,
  credits: /known_cost \+=|total_credits_spent \+=|total_credits_available \+=/,
  pairwise: /pref = prefers|matrix\[.*\] \+=/,
  condorcet: /_get_margin\(matrix|return candidate|return None/,
  condorcet_return: /if condorcet_winner|return RankedPairsResult|winners=|locked_victories=|skipped_victories=/,
  order: /ordered = sorted/,
  priority: /not _stays_acyclic|priority =|open_victories.sort/,
  lock: /_would_create_cycle\(|graph\[winner\].add|locked.append|skipped.append/,
  cycle: /current == winner|return True|stack.extend/,
};

/**
 * Every stage excerpt of one method as a single listing in file order, so
 * stepping through stages moves through one file. Gaps of three or more
 * lines fold; shorter gaps are shown.
 */
export function stageListing(source: CountSource): ListingRow[] {
  const lines = source.source.split("\n");
  const ranges = Object.values(source.excerpts)
    .map(({ startLine, lines: excerpt }) => [startLine, startLine + excerpt.length - 1])
    .sort((a, b) => a[0] - b[0]);
  const merged: number[][] = [];
  for (const [start, end] of ranges) {
    const last = merged[merged.length - 1];
    if (last && start <= last[1] + 3) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  return dedent(merged.flatMap(([start, end], index): ListingRow[] => [
    ...(index > 0 ? [{ kind: "fold" as const, from: merged[index - 1][1] + 1, to: start - 1 }] : []),
    ...lines.slice(start - 1, end).map((text, offset) => ({ kind: "line" as const, number: start + offset, text })),
  ]));
}

/** One contiguous run of source lines as listing rows. */
export function excerptListing(lines: string[], startLine: number): ListingRow[] {
  return dedent(lines.map((text, offset) => ({ kind: "line" as const, number: startLine + offset, text })));
}

function dedent(rows: ListingRow[]): ListingRow[] {
  const indents = rows.flatMap((row) => row.kind === "line" && row.text.trim() ? [row.text.match(/^ */)![0].length] : []);
  const indent = indents.length ? Math.min(...indents) : 0;
  return rows.map((row) => row.kind === "line" ? { ...row, text: row.text.slice(indent) } : row);
}

/** Rows inside the stage's excerpt are in the stage; those matching its emphasis drive it. */
export function stageRowStates(rows: ListingRow[], excerpt: { startLine: number; lines: string[] }, emphasis?: RegExp): RowState[] {
  const end = excerpt.startLine + excerpt.lines.length - 1;
  return rows.map((row) => row.kind !== "line" || row.number < excerpt.startLine || row.number > end ? "context"
    : emphasis?.test(row.text) ? "drive" : "stage");
}

const KEYWORDS = new Set(["False", "None", "True", "and", "as", "assert", "break", "class", "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"]);

/** A light Python tokenizer for display: enough for one line at a time, not a parser. */
export function pythonTokens(line: string): { text: string; kind: TokenKind }[] {
  const tokens: { text: string; kind: TokenKind }[] = [];
  let last = 0;
  for (const match of line.matchAll(/(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)/g)) {
    const index = match.index ?? 0;
    const [text, comment, string, number, word] = match;
    if (index > last) tokens.push({ text: line.slice(last, index), kind: "plain" });
    const kind: TokenKind = comment ? "comment" : string ? "string" : number ? "number"
      : KEYWORDS.has(word) ? "keyword" : /^_?[A-Z][a-z]/.test(word) ? "type"
      : line[index + text.length] === "(" ? "call" : "plain";
    tokens.push({ text, kind });
    last = index + text.length;
  }
  if (last < line.length) tokens.push({ text: line.slice(last), kind: "plain" });
  return tokens;
}

/** A value annotation: the first stage line matching `match` gets `# text`. */
export interface StageNote { match: RegExp; text: string }

/**
 * Values from the saved Python result, set against the lines that produce
 * them. Maxima, minima and thresholds are read off the recorded totals the
 * same way the stage explanations read them; nothing is recounted.
 */
export function stageNotes(result: ProfileMethodResult, resolution: ProfileResolveResponse, phase: string, roundIndex = 0): StageNote[] {
  const candidates = resolution.rankings.candidates;
  const tally = (values: Record<string, number>, signed = false) => candidates
    .filter((candidate) => values[candidate] !== undefined)
    .map((candidate) => `${candidate} ${signed && values[candidate] > 0 ? "+" : ""}${values[candidate]}`)
    .join(" · ");
  const list = (ids: string[]) => `[${ids.map((id) => `'${id}'`).join(", ")}]`;
  const winners = { match: result.tiebreaks.length ? /winners = \[tiebreak/ : /winners = tied/, text: `winners = ${list([result.winner])}` };
  const trace = result.trace;

  function totals(values: Record<string, number>, accumulator: RegExp, max: RegExp, maxName: string, signed = false): StageNote[] {
    if (phase === "count") return [{ match: accumulator, text: tally(values, signed) }];
    if (phase === "winner") return [{ match: max, text: `${maxName} = ${Math.max(...Object.values(values))}` }, winners];
    return [];
  }

  if (trace.kind === "plurality") return totals(trace.first_choices, /vote_counts\[ballot\.choice\] \+= 1/, /max_votes = /, "max_votes");
  if (trace.kind === "borda") return totals(trace.points, /point_totals\[candidate_id\] \+= points/, /max_total = /, "max_total");
  if (trace.kind === "approval") return totals(trace.approvals, /vote_counts\[candidate_id\] \+= 1/, /max_approvals = /, "max_approvals");
  if (trace.kind === "score") return totals(trace.totals, /score_totals\[cid\] \+= /, /max_total = /, "max_total");
  if (trace.kind === "quadratic") {
    if (phase === "credits") return [
      { match: /total_credits_spent \+= /, text: `total ${trace.credits_spent.toLocaleString("en-US")}` },
      { match: /total_credits_available \+= /, text: `total ${trace.credits_available.toLocaleString("en-US")}` },
    ];
    return totals(trace.net_votes, /vote_totals\[cid\] \+= votes/, /max_total = /, "max_total", true);
  }
  if (trace.kind === "irv") {
    const { round, next, survivorReturn } = inspectIRVRound(trace, roundIndex);
    if (!round) return [];
    const counts = Object.values(round.counts);
    const threshold = counts.reduce((sum, count) => sum + count, 0) / 2;
    const half = Number.isInteger(threshold) ? threshold.toFixed(1) : String(threshold);
    const decided = !round.eliminated.length && !survivorReturn;
    if (phase === "count") return [{ match: /vote_counts\[choice\] \+= 1/, text: `round ${round.round_number}: ${tally(round.counts)}` }];
    if (phase === "survivor_count") return [{ match: /final_vote_counts\[choice\] \+= 1/, text: `round ${round.round_number}: ${tally(round.counts)}` }];
    if (phase === "winner") return [
      { match: /majority_threshold = /, text: `majority_threshold = ${half}` },
      decided ? { match: /winner = candidate_id/, text: `winner = '${result.winner}'` } : { match: /if count > majority_threshold/, text: `no count > ${half}` },
    ];
    if (phase === "eliminate") return [
      { match: /min_votes = /, text: `min_votes = ${Math.min(...counts)}` },
      { match: /to_eliminate = candidates_with_min/, text: `to_eliminate = ${list(round.eliminated)}` },
    ];
    if (phase === "eliminate_tie") return [{ match: /to_eliminate = /, text: `to_eliminate = ${list(round.eliminated)}` }];
    if (phase === "transfer" && next) return [
      { match: /index \+= 1/, text: `skips ${round.eliminated.join(", ")}` },
      { match: /return index, ranking\[index\]/, text: `round ${next.round_number}: ${tally(next.counts)}` },
    ];
    if (phase === "survivor") return [{ match: /final_winner = /, text: `final_winner = '${result.winner}'` }];
    return [];
  }
  if (trace.kind === "ranked_pairs") {
    const sources = recordedGraphSources(candidates, trace.locked);
    const edges = (victories: typeof trace.locked) => victories.length ? victories.map((edge) => `${edge.winner}→${edge.loser}`).join(", ") : "none";
    if (phase === "condorcet") return [trace.had_condorcet_winner
      ? { match: /^\s*return candidate$/, text: `'${result.winner}' beats every rival` }
      : { match: /^\s*return None$/, text: "no candidate beats every rival" }];
    if (phase === "condorcet_return") return [{ match: /condorcet_winner = _find_condorcet_winner/, text: `condorcet_winner = ${trace.had_condorcet_winner ? `'${result.winner}'` : "None"}` }];
    if (phase === "order") return [{ match: /ordered = sorted/, text: `${trace.locked.length + trace.skipped.length} victories` }];
    if (phase === "lock") return [
      { match: /locked\.append/, text: `locked: ${edges(trace.locked)}` },
      { match: /skipped\.append/, text: `skipped: ${edges(trace.skipped)}` },
    ];
    if (phase === "winner") return [
      { match: /sources = /, text: `sources = ${list(sources)}` },
      sources.length === 1 ? { match: /winner_id = sources\[0\]/, text: `winner_id = '${result.winner}'` } : { match: /winner_id = tiebreak\(sources\)/, text: `winner_id = '${result.winner}'` },
    ];
  }
  return [];
}

/** Places each note on the first in-stage row its pattern matches. */
export function placeNotes(rows: ListingRow[], states: RowState[], notes: StageNote[]): Record<number, string> {
  const placed: Record<number, string> = {};
  for (const note of notes) {
    const index = rows.findIndex((row, i) => states[i] !== "context" && row.kind === "line" && placed[i] === undefined && note.match.test(row.text));
    if (index >= 0) placed[index] = note.text;
  }
  return placed;
}
