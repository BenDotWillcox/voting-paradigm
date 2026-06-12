---
name: server-action
description: Use when adding or modifying any Server Action under actions/. Enforces the ActionResult contract, error handling shape, revalidation, and the queries-vs-actions split.
---

# Server Action Skill

Server Actions in this project follow a strict shape. Inconsistencies leak through to UI error handling.

## The contract

Every action file:
1. Starts with `"use server";`
2. Imports queries from `@/db/queries/<feature>-queries`
3. Imports types from `@/db/schema/<feature>-schema`
4. Imports `ActionResult` from `@/types/actions/action-types`
5. Imports `revalidatePath` from `next/cache` (for mutations)

Every action function:
- Returns `Promise<ActionResult<T>>` where `T` is what the UI needs
- Wraps the query call in try/catch
- On success: `{ isSuccess: true, message: "<entity> <verb>ed successfully", data }`
- On failure: `{ isSuccess: false, message: "Failed to <verb> <entity>" }` (or a more specific error if available)
- Mutations call `revalidatePath(...)` on success **before** returning

## Naming

- File: `actions/<feature>-actions.ts` (kebab-plural)
- Function: `<verb><Entity>Action` — `createProposalAction`, `getProposalByIdAction`, `updateProposalAction`, `deleteProposalAction`
- `Action` suffix distinguishes from the underlying query of the same verb

## Queries vs actions — the split

| Layer | Responsibility | Error handling |
|-------|---------------|----------------|
| `db/queries/` | Raw DB operations | Throw — let the caller decide |
| `actions/` | Server boundary, validation, revalidation | Catch — return `ActionResult` |

A client component should NEVER import from `db/queries/`. If you find that pattern, wrap the query in an action.

## Validation

If the action takes form data:
- The form validates with Zod (`lib/validations/<feature>-schema.ts`) on the client
- The action can re-parse with the same Zod schema for defense-in-depth
- Don't accept arbitrary objects — type the parameter as `InsertX` or `XFormData`

## Revalidation paths

- Generic mutations: `revalidatePath("/")`
- Entity-specific page: `revalidatePath("/proposals")` or `revalidatePath(`/proposals/${id}`)`
- Be specific when possible — `revalidatePath("/")` is a sledgehammer

## Anti-patterns to flag

- Action that doesn't return `ActionResult<T>` (returns `T` directly, or throws)
- Mutation action that forgets `revalidatePath`
- Try/catch in the underlying query (it should throw; the action catches)
- Importing a query directly into a client component
- Generic error message that loses the actual error — at least `console.error(error)` before swallowing
- Action that takes `any` or an untyped object as input
