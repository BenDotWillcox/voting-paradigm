---
name: db-change
description: Use when adding or modifying any database table, column, or relation. Walks through the full Drizzle fan-out (schema → migration → query → action → validation → consumer) so no layer is forgotten.
---

# Database Change Skill

A schema change in this project fans out across 6 layers. Skipping one produces silent runtime breakage. Walk through every step explicitly.

## The fan-out checklist

For any schema add/modify/remove, verify each layer:

1. **Schema** — `db/schema/<feature>-schema.ts`
   - Define/modify table, export `Insert<Name>` and `Select<Name>` types
   - If a NEW schema file: add `export * from "./<feature>-schema"` to `db/schema/index.ts`

2. **Migration** — `db/migrations/`
   - Run `npm run db:generate` to produce a new SQL + snapshot
   - Inspect the generated SQL **before** applying; Drizzle sometimes infers destructive changes (drops, renames as drop+add)
   - Run `npm run db:migrate` only after inspection
   - If renaming a column, you may need to edit the generated SQL to use `ALTER ... RENAME` instead of drop+add

3. **Queries** — `db/queries/<feature>-queries.ts`
   - Pure DB functions, no `revalidatePath`, no try/catch swallowing — let errors throw
   - Convention: `createX`, `getXById`, `getAllX`, `updateX`, `deleteX`
   - Import types from the schema file, not re-defined

4. **Actions** — `actions/<feature>-actions.ts`
   - `"use server"` at top
   - Returns `Promise<ActionResult<T>>` from `@/types/actions/action-types`
   - Wraps query in try/catch, returns `{ isSuccess, message, data? }`
   - Mutations call `revalidatePath("/")` (or the relevant path) on success
   - Naming: `<verb><Entity>Action`

5. **Validation** — `lib/validations/<feature>-schema.ts` (only if forms touch this entity)
   - Zod schema separate from Drizzle types
   - Used by React Hook Form on the client; actions can re-validate at the boundary

6. **Consumers** — components, pages, forms
   - Update any TypeScript that destructures changed fields
   - `grep` for the column name to find every reference

## Before you start

Ask the user:
- Is this additive (safe) or breaking (rename/drop)? Breaking changes need a data plan.
- Does this affect existing rows? If NOT NULL with no default, the migration will fail on populated tables.
- Should this be backfilled? If yes, write the backfill as a separate migration step.

## After you finish

- Re-read `db/schema/index.ts` — is the new schema exported?
- Run `npm run lint` and `npm run build` to catch type drift in consumers
- If a query was added, was a corresponding action wrapper added? (queries are server-only and shouldn't be called from client components)

## Anti-patterns to flag

- Try/catch in queries that swallows the error — actions handle errors, queries throw
- Missing `revalidatePath` on a mutation action — UI will show stale data
- Editing a migration file that has already been applied — generate a new one instead
- Adding a query without a corresponding action wrapper, then importing the query from a client component
