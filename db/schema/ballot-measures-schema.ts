import {
  bigint,
  boolean,
  date,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  primaryKey,
  text,
  timestamp,
  unique,
  uuid,
} from "drizzle-orm/pg-core";
import { relations, sql } from "drizzle-orm";
import { users } from "./users-schema";
import { domains, programs } from "./topics-schema";

// -----------------------------------------------------------------------
// ballot_measure — a single vote-able question (user-created or imported).
//
// "Measure" not "election": a measure is the *question*. Resolving it under
// a specific method with a specific electorate is a `resolution_run`. A
// single ranked-choice measure can be resolved by IRV, Borda, and Ranked
// Pairs for side-by-side comparison.
//
// Imported measures (e.g. source = "ballotpedia") are authored by a
// dedicated system user (handle "ballotpedia") seeded separately.
// createdBy is NOT NULL with onDelete restrict, so deleting the
// ballotpedia user would require first reassigning or removing imported
// measures.
//
// (source, external_id) is the idempotency key for ingest upserts. For
// user-created measures external_id is NULL; Postgres treats NULLs as
// distinct under UNIQUE so user rows never collide.
// -----------------------------------------------------------------------

export const ballotType = pgEnum("ballot_type", [
  "single_choice",
  "approval",
  "ranked_choice",
  "score",
  "quadratic",
]);

export const measureStatus = pgEnum("measure_status", [
  "draft",
  "open",
  "closed",
]);

export const measureSource = pgEnum("measure_source", [
  "user",
  "ballotpedia",
]);

export const ballotMeasures = pgTable(
  "ballot_measure",
  {
    id: uuid("id")
      .primaryKey()
      .default(sql`gen_random_uuid()`),

    // --- authorship / provenance
    createdBy: uuid("created_by")
      .notNull()
      .references(() => users.id, { onDelete: "restrict" }),
    source: measureSource("source").notNull().default("user"),
    externalId: text("external_id"),
    sourceUrl: text("source_url"),
    // Raw scraped payload, kept so the scraper can be re-parsed without
    // re-fetching. Nullable because user-created measures have no source.
    sourceData: jsonb("source_data"),

    // --- content
    title: text("title").notNull(),
    summary: text("summary").notNull(),
    description: text("description"),

    // --- mechanics
    // Ballot type is stored on the measure (constrains what voters can cast);
    // resolution method is chosen per `resolution_run` and may differ across runs.
    ballotType: ballotType("ballot_type").notNull().default("single_choice"),
    status: measureStatus("status").notNull().default("draft"),

    // --- context
    jurisdiction: text("jurisdiction"),
    measureDate: date("measure_date"),

    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at")
      .defaultNow()
      .notNull()
      .$onUpdate(() => new Date()),
  },
  (t) => ({
    uniqSource: unique("ballot_measure_source_external_id_unique").on(
      t.source,
      t.externalId
    ),
  })
);

export const ballotMeasuresRelations = relations(
  ballotMeasures,
  ({ one, many }) => ({
    author: one(users, {
      fields: [ballotMeasures.createdBy],
      references: [users.id],
    }),
    options: many(measureOptions),
    topics: many(measureTopics),
    resolutionRuns: many(resolutionRuns),
  })
);

// -----------------------------------------------------------------------
// measure_option — one row per vote-able choice on a measure.
// Ordered by `ordinal` for stable display. Yes/no measure = 2 rows;
// candidate races / score ballots = N rows.
// -----------------------------------------------------------------------

export const measureOptions = pgTable(
  "measure_option",
  {
    id: uuid("id")
      .primaryKey()
      .default(sql`gen_random_uuid()`),
    measureId: uuid("measure_id")
      .notNull()
      .references(() => ballotMeasures.id, { onDelete: "cascade" }),
    ordinal: integer("ordinal").notNull(),
    label: text("label").notNull(),
    description: text("description"),
  },
  (t) => ({
    uniq: unique("measure_option_measure_id_ordinal_unique").on(
      t.measureId,
      t.ordinal
    ),
  })
);

export const measureOptionsRelations = relations(measureOptions, ({ one }) => ({
  measure: one(ballotMeasures, {
    fields: [measureOptions.measureId],
    references: [ballotMeasures.id],
  }),
}));

// -----------------------------------------------------------------------
// measure_topic — junction table.
// Measures may be tagged with multiple domains; each may optionally
// specify a program within that domain.
// -----------------------------------------------------------------------

export const measureTopics = pgTable(
  "measure_topic",
  {
    measureId: uuid("measure_id")
      .notNull()
      .references(() => ballotMeasures.id, { onDelete: "cascade" }),
    domainId: uuid("domain_id")
      .notNull()
      .references(() => domains.id, { onDelete: "restrict" }),
    programId: uuid("program_id").references(() => programs.id, {
      onDelete: "restrict",
    }),
    isPrimary: boolean("is_primary").notNull().default(true),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.measureId, t.domainId] }),
  })
);

export const measureTopicsRelations = relations(measureTopics, ({ one }) => ({
  measure: one(ballotMeasures, {
    fields: [measureTopics.measureId],
    references: [ballotMeasures.id],
  }),
  domain: one(domains, {
    fields: [measureTopics.domainId],
    references: [domains.id],
  }),
  program: one(programs, {
    fields: [measureTopics.programId],
    references: [programs.id],
  }),
}));

// -----------------------------------------------------------------------
// electorate — a named, simulated voter population.
//
// Reproducibility invariant: `seed` + `generation_params` fully determine
// the sampled voters. Regenerating the same electorate_id produces
// byte-identical output.
//
// `generation_params` is opaque jsonb — different generators (preference
// distribution sampling, persona-based, future LLM-personas) carry
// different shapes. Always Zod-validate on read.
// -----------------------------------------------------------------------

export const electorates = pgTable("electorate", {
  id: uuid("id")
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  description: text("description"),
  generator: text("generator").notNull(), // identifier for the generator implementation
  generationParams: jsonb("generation_params").notNull(),
  seed: bigint("seed", { mode: "bigint" }).notNull(),
  voterCount: integer("voter_count").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const electoratesRelations = relations(electorates, ({ many }) => ({
  resolutionRuns: many(resolutionRuns),
}));

// -----------------------------------------------------------------------
// resolution_run — the thesis artifact.
//
// (measure_id, electorate_id, method, seed) is the cache key. Given the
// tuple, the result is deterministic. Multiple runs of the same measure
// with different methods produce the side-by-side comparison.
//
// `result` is opaque jsonb — shape depends on the method (ApprovalResult,
// IRVResult, etc.). Always Zod-validate on read.
// -----------------------------------------------------------------------

export const resolutionRuns = pgTable(
  "resolution_run",
  {
    id: uuid("id")
      .primaryKey()
      .default(sql`gen_random_uuid()`),
    measureId: uuid("measure_id")
      .notNull()
      .references(() => ballotMeasures.id, { onDelete: "cascade" }),
    electorateId: uuid("electorate_id")
      .notNull()
      .references(() => electorates.id, { onDelete: "restrict" }),
    method: text("method").notNull(), // plurality | approval | irv | borda | ranked_pairs | score | quadratic
    seed: bigint("seed", { mode: "bigint" }).notNull(),
    result: jsonb("result").notNull(),
    computedAt: timestamp("computed_at").defaultNow().notNull(),
  },
  (t) => ({
    uniq: unique("resolution_run_cache_key_unique").on(
      t.measureId,
      t.electorateId,
      t.method,
      t.seed
    ),
  })
);

export const resolutionRunsRelations = relations(resolutionRuns, ({ one }) => ({
  measure: one(ballotMeasures, {
    fields: [resolutionRuns.measureId],
    references: [ballotMeasures.id],
  }),
  electorate: one(electorates, {
    fields: [resolutionRuns.electorateId],
    references: [electorates.id],
  }),
}));

export type SelectBallotMeasure = typeof ballotMeasures.$inferSelect;
export type InsertBallotMeasure = typeof ballotMeasures.$inferInsert;
export type SelectMeasureOption = typeof measureOptions.$inferSelect;
export type InsertMeasureOption = typeof measureOptions.$inferInsert;
export type SelectMeasureTopic = typeof measureTopics.$inferSelect;
export type InsertMeasureTopic = typeof measureTopics.$inferInsert;
export type SelectElectorate = typeof electorates.$inferSelect;
export type InsertElectorate = typeof electorates.$inferInsert;
export type SelectResolutionRun = typeof resolutionRuns.$inferSelect;
export type InsertResolutionRun = typeof resolutionRuns.$inferInsert;
