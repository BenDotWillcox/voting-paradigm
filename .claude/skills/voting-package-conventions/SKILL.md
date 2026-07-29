---
name: voting-package-conventions
description: Use when adding or modifying code under voting/. Enforces ballot-method separation, abstention handling, injectable tiebreaks, typed results, and the package's composable architecture.
---

# Voting Package Conventions

## Architectural rules

### Ballots express; methods resolve

- `voting/ballots/` contains data structures, construction, and validation.
- `voting/methods/` contains tally and resolution logic.
- Ballot modules never import method modules.

### Tiebreaks are injectable

Method entry points accept a `TiebreakFunction` and default to
`random_tiebreak`. Tests inject deterministic tiebreaks when the selected
winner matters. Seed the Python random generator when exercising the default in
a reproducible simulation.

Never hide a positional or alphabetical tiebreak inside a method.

### Abstention is valid

Null or empty ballots represent abstention where the ballot constructor
documents it. Methods exclude abstentions from tallies, record them in the
result, and handle all-abstain input.

### Results are typed

Return `ElectionResult` or a method-specific subclass with the audit details
needed to explain the outcome. Do not return anonymous tuples or dictionaries.

### Ranked ballots keep both indexes consistent

`RankedChoiceBallot` stores ordered `ranking` and `rank_lookup`
representations. Construct them together and never mutate one independently.

## Adding a ballot type

- Add the data structure and validation under `voting/ballots/`.
- Export the public API through the package's existing export modules.
- Test valid construction, invalid input, and abstention.

## Adding a resolution method

- Add resolution code and any result subclass under `voting/methods/`.
- Export the public API consistently.
- Document electoral-criteria trade-offs using
  `voting-method-correctness`.
- Test the happy path, ties, abstention, all-abstain, a single candidate, and
  method-specific edge cases.

## Verify

Run focused tests while editing, then:

```bash
pytest voting/tests -v
```

Report the observed result instead of copying a test count into durable docs.
