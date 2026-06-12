---
name: pr-reviewer
description: Use when reviewing a PR or open feature branch. Runs the project's quality checklist (db fan-out, server-action contract, voting-package conventions, criteria documentation, test coverage) and produces a punch list of issues by severity.
---

# PR Reviewer Skill

A focused review against *this project's* standards. Not generic code review — the goal is to catch the violations the other skills are designed to prevent, applied retroactively.

## How to invoke

Given a branch name or PR number:
1. Run `git diff main...<branch>` to see the full diff
2. Run `git log main..<branch>` to see commit history
3. Group the changes by area (web app vs voting package; schema vs UI vs tests)
4. Apply the relevant checklists below to each area
5. Produce a punch list grouped by **Blocker / Should-fix / Nit**

## Checklists by area

### If `db/schema/` changed → use `db-change` skill checklist
- New schema file exported from `db/schema/index.ts`?
- Migration generated AND inspected (no accidental drops)?
- Corresponding query functions added in `db/queries/`?
- Corresponding action wrappers added in `actions/`?
- Zod validation updated if forms touch this entity?
- Consumers updated (grep the changed column names)?

### If `actions/` changed → use `server-action` skill checklist
- `"use server"` at top of file?
- Returns `ActionResult<T>`?
- Try/catch wraps the query call?
- Mutations call `revalidatePath`?
- No `any` types on inputs?
- Naming: `<verb><Entity>Action`?

### If `voting/methods/` or `voting/ballots/` changed → use `voting-package-conventions` and `voting-method-correctness` skills
- Ballot/method separation respected?
- Tiebreak injectable, defaults to random?
- Abstention handled (not crashed on)?
- Returns an `ElectionResult` subclass?
- Method has a criteria docstring (satisfies/violates)?
- Tests cover happy path, ties, abstention, edge cases?
- `pytest voting/tests -v` passes?
- Test count in CLAUDE.md / memory still accurate? (Or removed entirely?)

### If `app/` or `components/` changed
- Client components don't import from `db/queries/` (must go through actions)?
- Form components use React Hook Form + Zod?
- Server vs client component boundary correct (`"use client"` only when needed)?
- New UI follows the existing shadcn/new-york style?

### Cross-cutting
- `npm run lint` clean?
- `npm run build` succeeds?
- No commented-out code, no `console.log` debug residue
- No new dependencies without justification (especially in `voting/` — pure Python is a goal)
- Commit messages follow project style (look at recent `git log`)

## Output format

Produce a structured report:

```
## PR Review: <branch>

### Blockers (must fix before merge)
- [file:line] <issue> — <why it's a blocker>

### Should-fix (address in this PR)
- [file:line] <issue> — <suggested fix>

### Nits (optional polish)
- [file:line] <issue>

### Verified
- ✓ <checklist item that passed and is worth calling out>

### Open questions for the author
- <anything that needs human judgment, especially voting-method criteria choices>
```

## Tone

- Cite specific files and lines — vague review is useless
- Distinguish opinion from violation — "this could be cleaner" is a nit; "this breaks the ActionResult contract" is a blocker
- For voting-method changes, ask the user about criteria trade-offs rather than asserting — they're the expert
- Don't recommend refactors outside the diff's scope; surface them as a separate flag instead
