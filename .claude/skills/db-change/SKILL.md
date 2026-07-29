---
name: db-change
description: Use when adding or modifying a database table, column, relation, or migration. Checks the full Drizzle fan-out from schema through migration, queries, actions, validation, and consumers.
---

# Database Change

Treat a schema change as a coordinated change across every affected layer.

## Before editing

- Determine whether the change is additive or breaking.
- For a rename, drop, new `NOT NULL` column, or type change, identify the
  existing-row and rollback plan before generating a migration.
- Search for every consumer of the affected table and fields.

## Fan-out checklist

1. Update `db/schema/<feature>-schema.ts`.
   - Export `Insert<Name>` and `Select<Name>` types.
   - Export a new schema module from `db/schema/index.ts`.
2. Run `npm run db:generate`.
   - Inspect the generated SQL and journal before applying it.
   - If Drizzle infers a destructive or incorrect operation, stop. Adjust the
     schema or generation inputs and regenerate.
   - Do not hand-edit generated migrations. Never rewrite a migration that may
     already have been applied. Ask before introducing an exceptional,
     separately authored data migration.
3. Update `db/queries/<feature>-queries.ts`.
   - Keep queries as pure database operations that throw on failure.
   - Reuse schema-exported types instead of redefining them.
4. Update `actions/<feature>-actions.ts`.
   - Follow the `server-action` skill.
   - Mutations revalidate the narrowest relevant path.
5. Update `lib/validations/<feature>-schema.ts` when a form or external boundary
   touches the entity.
6. Update pages, components, API clients, and other consumers.

## Verify

- Recheck `db/schema/index.ts`.
- Inspect the full generated migration for accidental drops or data loss.
- Run `npm run lint` and `npm run build`.
- Run focused tests for the changed query/action behavior.

## Reject these patterns

- Applying a migration before inspecting it.
- Editing an already-applied migration.
- Swallowing database errors in the query layer.
- Calling `db/queries/` directly from a client component.
- Adding a mutation action without appropriate cache revalidation.
