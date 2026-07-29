---
name: server-action
description: Use when adding or modifying a Server Action under actions/. Enforces the ActionResult contract, server-boundary validation, error handling, cache revalidation, and the queries-versus-actions split.
---

# Server Action

Keep Server Actions as the typed boundary between UI code and server-side
queries or API clients.

## File contract

- Start the file with `"use server";`.
- Import database operations from `db/queries/` and shared types from their
  canonical modules.
- Import `ActionResult` from `@/types/actions/action-types`.
- Import `revalidatePath` from `next/cache` when a successful mutation changes
  cached UI.

## Function contract

- Name actions `<verb><Entity>Action`.
- Return `Promise<ActionResult<T>>`, where `T` is the smallest useful result.
- Validate untrusted input at the server boundary. Reuse the relevant Zod
  schema when one exists.
- Wrap infrastructure calls in `try/catch`.
- Return `{ isSuccess: true, message, data }` on success.
- Return `{ isSuccess: false, message }` on infrastructure failure.
- Treat an expected not-found result as successful `data: null`, not an
  infrastructure error.
- Log enough server-side context to diagnose a caught error without exposing
  private data to the client.
- Revalidate the narrowest affected path before returning a successful
  mutation.

## Layer boundary

| Layer | Responsibility | Failure behavior |
| --- | --- | --- |
| `db/queries/` | Database operations | Throw |
| `actions/` | Validation, orchestration, result envelope, revalidation | Catch and return `ActionResult` |

Client components never import `db/queries/` directly.

## Reject these patterns

- Returning a raw object or throwing through the UI boundary.
- Accepting `any` or an unvalidated arbitrary object.
- Swallowing an error without diagnostic context.
- Treating an expected empty lookup as a failed action.
- Revalidating nothing after a mutation, or revalidating `/` when a narrower
  path is sufficient.
