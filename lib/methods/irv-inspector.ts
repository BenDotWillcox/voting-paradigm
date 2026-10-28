import type { Story } from "@/lib/methods/stories";
import type { ProfileResolveResponse } from "@/types/methods";

export type IRVPhase = "count" | "eliminate" | "transfer" | "winner";

export interface IRVSource {
  path: string;
  /** SHA-256 of the actual implementation, with line endings normalized to LF. */
  sha256: string;
  source: string;
  excerpts: Record<IRVPhase, { startLine: number; lines: string[] }>;
}

/** A reproducible package call, using the exact inputs and expected saved trace. */
export function buildIRVExample(story: Story, source: IRVSource): string {
  const change = story.specimen.transformation;
  if (change?.kind !== "add_voters") throw new Error("IRV example requires an add-voters experiment");

  const expected = (label: string, resolution: ProfileResolveResponse) => {
    const result = resolution.results.find((item) => item.method === "irv");
    if (result?.trace.kind !== "irv") throw new Error("IRV example is missing its saved trace");
    const rounds = result.trace.rounds.map((round) =>
      `            (${round.round_number}, ${JSON.stringify(round.counts)}, ${round.exhausted_ballots}, ${JSON.stringify(round.eliminated)}, ${round.elimination_was_tiebreak ? "True" : "False"}),`
    ).join("\n");
    return `    ${JSON.stringify(label)}: {
        "winner": ${JSON.stringify(result.winner)},
        "total_ballots": ${resolution.total_voters},
        "winning_round": ${result.trace.winning_round},
        "tiebreak_applied": ${result.tiebreaks.length > 0 ? "True" : "False"},
        "rounds": [
${rounds}
        ],
    },`;
  };
  const beforeRows = story.before.rankings.rows.map(({ count, ranking }) => [count, ranking]);
  const expectations = [expected("Before", story.before), expected("After", story.after)].join("\n");

  return `# IRV: two more voters change the winner.
# Requires Python 3.11+ and this repository's voting/ directory.
# Save as irv_example.py in the repository root; run: python irv_example.py
# No third-party Python dependencies are needed for this example.
# Expected results below are the saved counts shown in the demo.
# IRV implementation SHA-256 (LF-normalized): ${source.sha256}

import hashlib
import inspect
from pathlib import Path

from voting.ballots.ranked_choice import create_ranked_choice_ballot
from voting.methods.irv import resolve_irv
from voting.types import Candidate, random_tiebreak

candidate_ids = ${JSON.stringify(story.before.rankings.candidates)}
candidates = [Candidate(id=cid, name=cid) for cid in candidate_ids]
before_rows = ${JSON.stringify(beforeRows)}
added_ranking = ${JSON.stringify(change.ranking)}
added_voters = ${change.voters}


def make_ballots(rows, prefix):
    ballots = []
    for count, ranking in rows:
        for _ in range(count):
            ballots.append(create_ranked_choice_ballot(
                voter_id=f"{prefix}-{len(ballots)}",
                ranking=ranking,
                candidates=candidate_ids,
            ))
    return ballots


before = make_ballots(before_rows, "existing")
# Append new ballots; every existing ballot stays the same.
after = before + make_ballots([(added_voters, added_ranking)], "new")

# Check which implementation is installed; the assertions below check outcomes.
implementation = Path(inspect.getfile(resolve_irv)).read_text(encoding="utf-8")
source_hash = hashlib.sha256(implementation.encode("utf-8")).hexdigest()
if source_hash != "${source.sha256}":
    print("Note: your irv.py differs from the version shown in the demo.")

# Round tuples: (number, counts, exhausted, eliminated, elimination_was_tiebreak).
expected = {
${expectations}
}

for label, ballots, seed in (
    ("Before", before, ${story.before.tiebreak_seed}),
    ("After", after, ${story.after.tiebreak_seed}),
):
    # Each resolution gets a fresh seeded tiebreaker.
    result = resolve_irv(candidates, ballots, tiebreak=random_tiebreak(seed))
    rounds = [
        (item.round_number, item.vote_counts, item.exhausted_ballots,
         item.eliminated, item.elimination_was_tiebreak)
        for item in result.rounds
    ]
    actual = {
        "winner": result.winners[0],
        "total_ballots": result.total_ballots,
        "winning_round": result.winning_round,
        "tiebreak_applied": result.tiebreak_applied,
        "rounds": rounds,
    }
    assert actual == expected[label], (label, actual, expected[label])
    print(f"{label}: {result.total_ballots} voters -> {result.winners[0]} wins")
    for item in result.rounds:
        eliminated = ", ".join(item.eliminated) or "none"
        print(f"  Round {item.round_number}: {item.vote_counts}; eliminated: {eliminated}")

print("Both winners and every round match the demo.")
`;
}
