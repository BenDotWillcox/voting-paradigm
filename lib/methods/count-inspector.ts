import type { ProfileResolveResponse, VotingMethod } from "@/types/methods";

export type InspectableMethod = VotingMethod;

export interface CountSource {
  path: string;
  /** SHA-256 of the actual implementation, with line endings normalized to LF. */
  sha256: string;
  source: string;
  excerpts: Record<string, { startLine: number; lines: string[] }>;
}

export type CountSources = Record<InspectableMethod, CountSource>;

const NAMES: Record<InspectableMethod, string> = {
  plurality: "Plurality", irv: "Instant runoff", borda: "Borda count",
  ranked_pairs: "Ranked Pairs", approval: "Approval", score: "Score voting", quadratic: "Quadratic voting",
};

/** Python literals keep the copied example independent of web/API dependencies. */
function python(value: unknown, depth = 0): string {
  if (value === null) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "string" || typeof value === "number") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => python(item, depth)).join(", ")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return "{}";
    const pad = "    ".repeat(depth + 1);
    return `{\n${entries.map(([key, item]) => `${pad}${JSON.stringify(key)}: ${python(item, depth + 1)},`).join("\n")}\n${"    ".repeat(depth)}}`;
  }
  throw new Error("Cannot represent an unsupported example value in Python");
}

interface BallotSetup {
  module: string;
  constructor: string;
  extraImports?: string;
  rows: unknown[][];
  description: string;
  bindings: string;
  args: string;
  abstentions: number;
  rated?: boolean;
}

function ballotSetup(method: InspectableMethod, resolution: ProfileResolveResponse): BallotSetup {
  if (method === "plurality") return {
    module: "single_choice", constructor: "create_single_choice_ballot",
    rows: resolution.rankings.rows.map(({ count, ranking }) => [count, ranking[0] ?? null]),
    description: "marked candidate", bindings: "choice", args: "            choice=choice,",
    abstentions: resolution.rankings.rows.reduce((sum, row) => sum + (row.ranking.length ? 0 : row.count), 0),
  };
  if (method === "irv" || method === "borda" || method === "ranked_pairs") return {
    module: "ranked_choice", constructor: "create_ranked_choice_ballot",
    rows: resolution.rankings.rows.map(({ count, ranking }) => [count, ranking]),
    description: "ranking from favorite to last", bindings: "ranking",
    args: "            ranking=ranking or None,\n            candidates=candidate_ids,",
    abstentions: resolution.rankings.rows.reduce((sum, row) => sum + (row.ranking.length ? 0 : row.count), 0),
  };
  if (!resolution.voter_ballots.length && resolution.total_voters > 0) {
    throw new Error(`${method} example requires the returned cast ballots`);
  }
  if (method === "approval") return {
    module: "approval", constructor: "create_approval_ballot", rated: true,
    rows: resolution.voter_ballots.map(({ count, approvals }) => [count, approvals]),
    description: "approved candidates", bindings: "approvals", args: "            approvals=approvals,",
    abstentions: resolution.voter_ballots.reduce((sum, row) => sum + (row.approvals.length ? 0 : row.count), 0),
  };
  if (method === "score") return {
    module: "score", constructor: "create_score_ballot", extraImports: ", MAX_SCORE", rated: true,
    rows: resolution.voter_ballots.map(({ count, scores }) => [count, scores]),
    description: "scores", bindings: "scores", args: "            scores=scores,",
    // Zero scores still form a scored ballot; only an empty mapping abstains.
    abstentions: resolution.voter_ballots.reduce((sum, row) => sum + (Object.keys(row.scores).length ? 0 : row.count), 0),
  };
  return {
    module: "quadratic", constructor: "create_quadratic_ballot", rated: true,
    rows: resolution.voter_ballots.map(({ count, allocations, credit_budget }) => [count, allocations, credit_budget]),
    description: "signed vote allocations, credit budget per voter", bindings: "allocations, credit_budget",
    args: "            allocations=allocations,\n            credit_budget=credit_budget,\n            allow_negative=True,",
    abstentions: resolution.voter_ballots.reduce((sum, row) => sum + (Object.keys(row.allocations).length ? 0 : row.count), 0),
  };
}

/** Reproduce the selected result with the public package, not a browser tally. */
export function buildCountExample(method: InspectableMethod, resolution: ProfileResolveResponse, source: CountSource): string {
  const result = resolution.results.find((item) => item.method === method);
  if (!result || result.trace.kind !== method) throw new Error(`Missing ${method} result`);
  const setup = ballotSetup(method, resolution);
  const expected: Record<string, unknown> = {
    winners: [result.winner],
    total_ballots: resolution.total_voters,
    abstentions: setup.abstentions,
    tiebreak_applied: result.tiebreaks.length > 0,
    tiebreaks: result.tiebreaks,
  };
  const actual: Record<string, string> = {
    winners: "result.winners", total_ballots: "result.total_ballots", abstentions: "result.abstentions",
    tiebreak_applied: "result.tiebreak_applied",
    tiebreaks: "tiebreak_events",
  };
  let report = 'print(f"Tallies: {result.vote_counts}")';
  const add = (key: string, value: unknown, expression: string) => {
    expected[key] = value;
    actual[key] = expression;
  };
  const trace = result.trace;
  switch (trace.kind) {
    case "plurality":
      add("vote_counts", trace.first_choices, "result.vote_counts");
      break;
    case "irv":
      add("vote_counts", trace.rounds[trace.rounds.length - 1]?.counts ?? {}, "result.vote_counts");
      add("winning_round", trace.winning_round, "result.winning_round");
      add("rounds", trace.rounds, `[
        {
            "round_number": item.round_number,
            "counts": item.vote_counts,
            "exhausted_ballots": item.exhausted_ballots,
            "eliminated": item.eliminated,
            "elimination_was_tiebreak": item.elimination_was_tiebreak,
        }
        for item in result.rounds
    ]`);
      report = `for item in result.rounds:
    print(f"  Round {item.round_number}: {item.vote_counts}; eliminated: {item.eliminated}")`;
      break;
    case "borda":
      add("points", trace.points, "result.point_totals");
      add("max_points_per_ballot", trace.max_points_per_ballot, "result.max_points_per_ballot");
      break;
    case "approval":
      expected.abstentions = trace.abstentions;
      add("approvals", trace.approvals, "result.vote_counts");
      break;
    case "score":
      add("totals", trace.totals, "result.score_totals");
      add("max_score", trace.max_score, "MAX_SCORE");
      break;
    case "quadratic":
      add("net_votes", trace.net_votes, "result.vote_totals");
      add("credits_spent", trace.credits_spent, "result.total_credits_spent");
      add("credits_available", trace.credits_available, "result.total_credits_available");
      report += '\nprint(f"Credits spent: {result.total_credits_spent} of {result.total_credits_available}")';
      break;
    case "ranked_pairs":
      add("vote_counts", Object.fromEntries(resolution.rankings.candidates.map((candidate) => [
        candidate,
        resolution.rankings.candidates.filter((opponent) => opponent !== candidate &&
          resolution.pairwise[candidate][opponent] > resolution.pairwise[opponent][candidate]).length,
      ])), "result.vote_counts");
      add("pairwise_matrix", resolution.pairwise, "result.pairwise_matrix");
      add("had_condorcet_winner", trace.had_condorcet_winner, "result.had_condorcet_winner");
      add("locked", trace.locked.map(({ winner, loser, margin }) => [winner, loser, margin]), "[list(edge) for edge in result.locked_victories]");
      add("skipped", trace.skipped.map(({ winner, loser, margin }) => [winner, loser, margin]), "[list(edge) for edge in result.skipped_victories]");
      add("tiebreak_priority", trace.tiebreak_priority, "result.tiebreak_priority");
      report = `print(f"Condorcet winner exists: {result.had_condorcet_winner}")
for candidate, counts in result.pairwise_matrix.items():
    print(f"  {candidate} preferred to: {counts}")
print(f"Locked victories: {result.locked_victories}")
print(f"Skipped victories: {result.skipped_victories}")`;
      break;
  }

  return `# ${NAMES[method]}: reproduce the electorate shown in the inspector.
# Requires Python 3.11+ and this repository's voting/ directory.
# Repository: https://github.com/BenDotWillcox/voting-paradigm
# Save as ${method}_example.py in the repository root.
# Run: python ${method}_example.py
# No third-party Python dependencies or API server are needed.
# Implementation SHA-256 (LF-normalized): ${source.sha256}

import hashlib
import inspect
from pathlib import Path

from voting.ballots.${setup.module} import ${setup.constructor}${setup.extraImports ?? ""}
from voting.methods.${method} import resolve_${method}
from voting.types import Candidate, random_tiebreak

candidate_ids = ${python(resolution.rankings.candidates)}
candidates = [Candidate(id=cid, name=cid) for cid in candidate_ids]
# Each row is (number of voters, ${setup.description}).
${setup.rated ? "# These are the returned cast ballots; the preference-to-ballot model is not rerun.\n" : ""}rows = [
${setup.rows.map((row) => `    (${row.map((value) => python(value, 1)).join(", ")}),`).join("\n")}
]

ballots = []
for count, ${setup.bindings} in rows:
    for _ in range(count):
        ballots.append(${setup.constructor}(
            voter_id=f"voter-{len(ballots)}",
${setup.args}
        ))

# Check the source version; the assertions below check the computed result.
implementation = Path(inspect.getfile(resolve_${method})).read_text(encoding="utf-8")
source_hash = hashlib.sha256(implementation.encode("utf-8")).hexdigest()
if source_hash != "${source.sha256}":
    print("Note: your ${method}.py differs from the version shown in the demo.")

# Start the same random stream and record every tie exactly as the API does.
seeded_tiebreak = random_tiebreak(${resolution.tiebreak_seed})
tiebreak_events = []

def recorded_tiebreak(tied):
    choice = seeded_tiebreak(tied)
    tiebreak_events.append({"tied": sorted(tied), "chose": choice})
    return choice

result = resolve_${method}(
    candidates,
    ballots,
    tiebreak=recorded_tiebreak,
)

# Expected output is the Python result displayed by the demo.
expected = ${python(expected)}
actual = {
${Object.entries(actual).map(([key, expression]) => `    ${JSON.stringify(key)}: ${expression},`).join("\n")}
}
assert actual == expected, (actual, expected)
print(f"${NAMES[method]}: {result.total_ballots} voters -> {result.winners[0]} wins")
${report}
print("Winner, ballot counts, tiebreaks, and method trace match the demo.")
`;
}
