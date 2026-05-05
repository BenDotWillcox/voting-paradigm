---
name: voting-package-conventions
description: Use when adding or modifying anything under the Python voting/ package. Enforces the architectural rules (ballot/method separation, tiebreak injection, abstention handling, result types) that keep the package composable.
---

# Voting Package Conventions Skill

The `voting/` package has strict architectural rules. They're cheap to follow when writing new code and expensive to fix after the fact.

## The rules

### 1. Ballots ≠ methods
- `voting/ballots/<type>.py` defines **how voters express preferences** (data structures + validation only)
- `voting/methods/<method>.py` defines **how ballots are tallied** (resolution logic only)
- A ballot file should NEVER import from `voting/methods/`
- A method file imports the ballot type(s) it consumes

### 2. Tiebreak is always injectable
Every method signature accepts a `tiebreak` parameter:
```python
def resolve(ballots, candidates, tiebreak=random_tiebreak):
    ...
```
- Default to `random_tiebreak` (uses the `random` module — seedable for reproducibility)
- Custom tiebreak is a callable `(tied_candidates) -> Candidate`
- Never hardcode "pick the alphabetically first" or "pick the first in input order" — that's a hidden bias

### 3. Abstention is always allowed
- A null/empty ballot is valid input
- It must be excluded from tallies, not raise an exception
- Test coverage: every method should have at least one test with an abstaining voter mixed in

### 4. Result types extend `ElectionResult`
- Base class in `voting/types.py`
- Each method defines its own subclass with method-specific fields (e.g., `IRVResult` includes elimination rounds, `CondorcetResult` includes the pairwise matrix)
- Don't return raw tuples or dicts — return the typed result

### 5. Ranked choice ballots use dual representation
- `list` for O(1) positional access (who's the i-th choice?)
- `dict` for O(1) pairwise comparison (does A beat B?)
- Keep both in sync; don't mutate one without the other

## File layout when adding something new

**New ballot type:**
- `voting/ballots/<type>.py` — class definition + validation
- `voting/tests/test_<type>_ballot.py` — construction, validation, abstention

**New resolution method:**
- `voting/methods/<method>.py` — `resolve(ballots, candidates, tiebreak=...)` + result subclass
- `voting/tests/test_<method>.py` — happy path, ties, abstention, edge cases (single candidate, all-abstain)
- Include a docstring stating which criteria the method satisfies/violates (use the `voting-method-correctness` skill)

## Before committing voting/ changes

Run: `pytest voting/tests -v`

If tests pass count changes, update the count in AGENTS.md and the memory file (or remove the count to prevent drift).

## Anti-patterns to flag

- Tally logic in a ballot file
- Method that hardcodes a tiebreak strategy
- Method that crashes on empty/null ballots
- Returning a tuple/dict instead of an `ElectionResult` subclass
- New method without criteria docstring
- Test file that only covers the happy path
