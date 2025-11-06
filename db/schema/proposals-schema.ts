import {
  boolean,
  date,
  integer,
  numeric,
  pgEnum,
  pgTable,
  text,
  timestamp,
  uuid,
} from "drizzle-orm/pg-core";
import { relations, sql } from "drizzle-orm";
import { users } from "./users-schema";
import { domains, programs } from "./topics-schema";

export const proposalStatus = pgEnum("proposal_status", [
  "draft",
  "active",
  "passed",
  "failed",
  "archived",
]);

export const proposals = pgTable("proposal", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  authorId: uuid("author_id")
    .notNull()
    .references(() => users.id, { onDelete: "restrict" }),
  status: proposalStatus("status").notNull().default("draft"),
  title: text("title").notNull(),
  summary: text("summary").notNull(),
  problemPlain: text("problem_plain").notNull(),
  implementingOrg: text("implementing_org"),
  scopeGeojson: text("scope_geojson"),
  populationEstimate: integer("population_estimate"),
  populationSource: text("population_source"),
  budgetOneTimeUsd: integer("budget_one_time_usd").default(0).notNull(),
  budgetAnnualUsd: integer("budget_annual_usd").default(0).notNull(),
  fundingNotes: text("funding_notes"),
  legalCitation: text("legal_citation"),
  needsNewAuthority: boolean("needs_new_authority").default(false).notNull(),
  equityBeneficiaries: text("equity_beneficiaries"),
  equityCostBearers: text("equity_cost_bearers"),
  safeguardsRollbackTrigger: text("safeguards_rollback_trigger"),
  safeguardsRollbackSteps: text("safeguards_rollback_steps"),
  sunsetDate: date("sunset_date"),
  privacyNotes: text("privacy_notes"),
  retentionDays: integer("retention_days"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const proposalsRelations = relations(proposals, ({ one, many }) => ({
  author: one(users, {
    fields: [proposals.authorId],
    references: [users.id],
  }),
  topics: many(proposalTopics),
  metrics: many(proposalMetrics),
  actions: many(proposalActions),
  budgetItems: many(proposalBudgetItems),
}));

export const proposalTopics = pgTable(
  "proposal_topic",
  {
    proposalId: uuid("proposal_id")
      .notNull()
      .references(() => proposals.id, { onDelete: "cascade" }),
    domainId: uuid("domain_id")
      .notNull()
      .references(() => domains.id, { onDelete: "restrict" }),
    programId: uuid("program_id").references(() => programs.id, {
      onDelete: "restrict",
    }),
    isPrimary: boolean("is_primary").notNull().default(true),
  },
  (t) => ({
    pk: sql`PRIMARY KEY (${t.proposalId.name}, ${t.domainId.name})`,
  })
);

export const proposalTopicsRelations = relations(proposalTopics, ({ one }) => ({
  proposal: one(proposals, {
    fields: [proposalTopics.proposalId],
    references: [proposals.id],
  }),
  domain: one(domains, {
    fields: [proposalTopics.domainId],
    references: [domains.id],
  }),
  program: one(programs, {
    fields: [proposalTopics.programId],
    references: [programs.id],
  }),
}));

export const proposalMetrics = pgTable("proposal_metric", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  proposalId: uuid("proposal_id")
    .notNull()
    .references(() => proposals.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  unit: text("unit").notNull(),
  baselineVal: numeric("baseline_val", { precision: 12, scale: 4 }).notNull(),
  baselineYear: integer("baseline_year"),
  baselineSource: text("baseline_source"),
  targetVal: numeric("target_val", { precision: 12, scale: 4 }).notNull(),
  deadline: date("deadline").notNull(),
});

export const proposalMetricsRelations = relations(proposalMetrics, ({ one }) => ({
  proposal: one(proposals, {
    fields: [proposalMetrics.proposalId],
    references: [proposals.id],
  }),
}));

export const proposalActions = pgTable(
  "proposal_action",
  {
    id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
    proposalId: uuid("proposal_id")
      .notNull()
      .references(() => proposals.id, { onDelete: "cascade" }),
    ordinal: integer("ordinal").notNull(),
    text: text("text").notNull(),
  },
  (t) => ({
    uniq: sql`UNIQUE (${t.proposalId.name}, ${t.ordinal.name})`,
  })
);

export const proposalActionsRelations = relations(proposalActions, ({ one }) => ({
  proposal: one(proposals, {
    fields: [proposalActions.proposalId],
    references: [proposals.id],
  }),
}));

export const proposalBudgetItems = pgTable("proposal_budget_item", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  proposalId: uuid("proposal_id")
    .notNull()
    .references(() => proposals.id, { onDelete: "cascade" }),
  itemName: text("item_name").notNull(),
  oneTimeUsd: integer("one_time_usd").notNull().default(0),
  annualUsd: integer("annual_usd").notNull().default(0),
  confidence: numeric("confidence", { precision: 3, scale: 2 })
    .notNull()
    .default("0.50"),
});

export const proposalBudgetItemsRelations = relations(
  proposalBudgetItems,
  ({ one }) => ({
    proposal: one(proposals, {
      fields: [proposalBudgetItems.proposalId],
      references: [proposals.id],
    }),
  })
);

export type SelectProposal = typeof proposals.$inferSelect;
export type InsertProposal = typeof proposals.$inferInsert;
export type SelectProposalTopic = typeof proposalTopics.$inferSelect;
export type InsertProposalTopic = typeof proposalTopics.$inferInsert;
export type SelectProposalMetric = typeof proposalMetrics.$inferSelect;
export type InsertProposalMetric = typeof proposalMetrics.$inferInsert;
export type SelectProposalAction = typeof proposalActions.$inferSelect;
export type InsertProposalAction = typeof proposalActions.$inferInsert;
export type SelectProposalBudgetItem = typeof proposalBudgetItems.$inferSelect;
export type InsertProposalBudgetItem = typeof proposalBudgetItems.$inferInsert;
