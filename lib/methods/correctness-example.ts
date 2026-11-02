/** A small public-API check, verified against the package used by this demo. */
export const CORRECTNESS_CHECK_EXCERPT = `first = resolve_plurality(
    candidates, ballots, random_tiebreak(7)
)
reordered = resolve_plurality(
    candidates[::-1], ballots[::-1], random_tiebreak(7)
)

for result in (first, reordered):
    assert result.vote_counts == {"A": 1, "B": 1}
    assert result.tiebreak_applied
assert first.winners == reordered.winners == ["B"]`;

export const CORRECTNESS_CHECK_EXAMPLE = `# Save as tie_check.py in the repository root.
# Run with Python 3.11+: python tie_check.py
from voting import (
    Candidate,
    create_single_choice_ballot,
    random_tiebreak,
    resolve_plurality,
)

candidates = [Candidate(id=key, name=key) for key in ["A", "B"]]
ballots = [
    create_single_choice_ballot("v1", "A"),
    create_single_choice_ballot("v2", "B"),
]

# Each run gets a fresh tiebreaker with the same seed.
${CORRECTNESS_CHECK_EXCERPT}

print("Checks passed: 1-1 tally, B wins both orders, tiebreak used.")
`;
