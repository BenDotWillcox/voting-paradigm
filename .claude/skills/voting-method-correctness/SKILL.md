---
name: voting-method-correctness
description: Use when adding, modifying, or reviewing a resolution method in voting/. Makes electoral-criteria trade-offs explicit and checks that the implementation and tests match the documented method.
---

# Voting Method Correctness

Passing examples are not enough for an electoral method. Review both the
algorithm and the criteria trade-offs it intentionally makes.

## Process

1. Identify the method family: plurality, positional, runoff, cardinal, or
   Condorcet.
2. State the implemented assumptions about complete or partial ballots,
   abstention, ties, duplicate scores, exhausted ballots, and candidate sets.
3. Evaluate each relevant criterion as satisfies, violates, conditional, or
   not applicable, with a short reason:
   - majority;
   - Condorcet winner and Condorcet loser;
   - monotonicity;
   - independence of irrelevant alternatives;
   - later-no-harm;
   - participation or no-show;
   - clone independence.
4. Confirm the implementation matches those claims.
5. Add a regression case for each changed rule and at least one documented
   failure mode when practical. A known criterion violation should be explicit,
   not disguised as an accidental bug.

Do not rely on a memorized criteria table when the distinction matters. Check
the method definition and, when needed, an authoritative voting-theory source.
Ask the user when a design choice changes a non-obvious criterion trade-off.

## Project invariants

Every method under `voting/methods/` must:

- keep tally logic out of ballot modules;
- accept the ballot types it documents;
- handle abstention and all-abstain inputs without crashing;
- accept an injectable tiebreak function and default to
  `voting.types.random_tiebreak`;
- return `ElectionResult` or a method-specific subclass; and
- document the criteria it satisfies or violates.

## Pay special attention to

- elimination order and tied elimination in IRV;
- cycle handling and lock order in Condorcet methods;
- normalization, score ranges, and unscored options in cardinal methods;
- integer and credit-budget semantics in quadratic voting; and
- reproducibility when the default random tiebreak is used.

Run `pytest voting/tests -v` after focused method tests pass.
