---
name: voting-method-correctness
description: Use when adding, modifying, or reviewing any voting resolution method in the Python voting/ package. Walks through the electoral criteria a method satisfies/violates so trade-offs are explicit and documented, not accidental.
---

# Voting Method Correctness Skill

The user is an expert in electoral methods. Voting method changes must be evaluated against established criteria, not just "does the test pass." Every method satisfies some criteria and violates others — the goal is **explicit, documented trade-offs**, never accidental ones.

## When to invoke

- Adding a new resolution method under `voting/methods/`
- Modifying tally logic, tiebreak behavior, or elimination rules in an existing method
- Reviewing a PR that touches `voting/methods/` or `voting/ballots/`
- Changing how a ballot type expresses preferences (this can violate criteria the methods rely on)

## The criteria checklist

For the method in question, state explicitly: **satisfies / violates / N/A** with a one-line reason.

**Majority criterion** — If a candidate is the first choice of a majority, do they win?
- Plurality: ✓  IRV: ✓  Borda: ✗  Approval: ✗ (depends on strategy)  Condorcet methods: ✓

**Condorcet criterion** — If a candidate beats every other head-to-head, do they win?
- Ranked Pairs / Schulze: ✓  IRV: ✗  Borda: ✗  Plurality: ✗

**Condorcet loser criterion** — A candidate who loses every head-to-head should NOT win.
- IRV: ✓  Borda: ✓  Plurality: ✗

**Monotonicity** — Ranking the winner higher should never cause them to lose.
- Plurality, Approval, Score, Borda, Ranked Pairs: ✓
- IRV: ✗ (classic failure mode — flag this loudly in IRV changes)

**Independence of Irrelevant Alternatives (IIA)** — Adding/removing a non-winning candidate shouldn't change the winner.
- Almost no method satisfies full IIA (Arrow's theorem). Approval and Score satisfy it under certain assumptions.

**Later-no-harm** — Ranking additional candidates shouldn't hurt your top choice.
- IRV: ✓  Borda: ✗  Condorcet methods: ✗

**Participation** — Voting honestly shouldn't produce a worse outcome than not voting.
- Plurality, Approval, Score, Borda: ✓
- IRV, Condorcet methods: ✗ (known failure)

**Clone independence** — Adding similar candidates shouldn't change the winner.
- Ranked Pairs, Schulze, IRV: ✓  Plurality, Borda: ✗

**No-show paradox** — Special case of participation failure where abstaining helps your preferred candidate. IRV and Condorcet are vulnerable.

## Process

1. Identify the method's category (positional, runoff, Condorcet, cardinal)
2. List which criteria it claims to satisfy — verify the implementation actually does
3. List which it violates — confirm tests cover at least one failure case (proves the violation is intentional)
4. If the change moves the method between categories or alters tiebreak/elimination, **re-check every criterion** — they often shift together

## Project-specific invariants (from CLAUDE.md)

Every method in `voting/methods/` must:
- Default to **random tiebreak**, accept an injectable custom tiebreak function
- Accept **abstention** (null/empty ballots) and exclude them from tallies, not crash
- Return a result type extending `ElectionResult` with method-specific metrics
- Preserve ballot/method separation — no tally logic in `voting/ballots/`, no ballot construction in `voting/methods/`

## Anti-patterns to flag

- New method without a criteria docstring — the user wants the trade-off explicit in code
- Test suite only covers happy path — at least one test should exercise a known criterion violation if the method has one
- Tiebreak hardcoded instead of injected — breaks reproducibility for simulations
- Abstention raises an exception instead of being ignored
- Borrowing logic from another method without re-evaluating criteria (e.g., adding a Condorcet check to IRV silently changes its criteria profile)

## Ask the user when unsure

The user knows electoral theory better than you. If a design choice has a non-obvious criterion implication (e.g., "should we batch-eliminate ties or eliminate one randomly in IRV?"), ask — don't guess. Cite the criterion at stake.
