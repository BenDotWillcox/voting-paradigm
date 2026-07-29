---
name: pr-reviewer
description: Use when reviewing a pull request or feature branch in this repository. Applies the project-specific database, server-action, voting, evaluation, privacy, test, and documentation checks to the changed surface.
---

# Pull Request Reviewer

Review the proposed change against this repository's actual contracts. Keep the
review scoped to the diff while noting clearly separated follow-up concerns.

## Establish scope

1. Inspect the branch status and base branch.
2. Read the full diff and commit history.
3. Group changes by surface: database, actions, web UI, Python domain code,
   evaluation, fixtures, privacy, and documentation.
4. Read the relevant neighboring code and tests before calling something a
   defect.

## Apply relevant checks

### Database changes

Use `db-change`. Confirm the schema export, generated migration, query/action
fan-out, validation boundary, and consumers all agree.

### Server Actions

Use `server-action`. Confirm the action boundary, return type, validation,
error handling, and revalidation behavior.

### Voting package

Use `voting-package-conventions` and `voting-method-correctness`. Confirm
ballot/method separation, abstention, injectable tiebreaks, typed results,
criteria documentation, and edge-case tests.

### Human preference evaluation

- Preserve pre-answer chronology and evidence cutoffs.
- Confirm initial and retest presentations cannot leak answers into a scored
  prediction.
- Treat run records and evidence as private by default.
- Require public artifacts to be built from explicit allowlisted fields.
- Keep development fixtures clearly separated from research claims.

### Web application

- Client components do not import database queries.
- Form and JSON boundaries use the repository's Zod patterns.
- `"use client"` is present only where interaction requires it.
- UI changes follow the existing component and accessibility conventions.

### Cross-cutting

- New dependencies are justified.
- Deterministic paths record and use seeds.
- No secrets, private run data, debug logs, commented-out code, or stale
  generated output are committed.
- Tests exercise failure boundaries, not only the happy path.
- Documentation describes the implemented behavior rather than an aspiration.

## Verify proportionally

Run the narrowest relevant tests first, then the repository gates affected by
the diff. Typical final gates are:

```bash
pytest
npm run lint
npm run build
```

Do not report a hard-coded test count. Report the command and observed result.

## Output

Group findings as:

- Blocker: correctness, leakage, privacy, data loss, or build failure.
- Should-fix: a material contract, maintainability, or test gap in this change.
- Nit: optional polish.

For every actionable finding, cite the file and tight line range, explain the
failure mode, and propose the smallest sound correction. Separate verified
facts from open questions.
