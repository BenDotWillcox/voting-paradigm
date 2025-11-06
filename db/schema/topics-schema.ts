import { pgTable, text, uuid, boolean } from "drizzle-orm/pg-core";
import { relations, sql } from "drizzle-orm";

export const domains = pgTable("domain", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull().unique(),
  active: boolean("active").notNull().default(true),
});

export const domainsRelations = relations(domains, ({ many }) => ({
  programs: many(programs),
}));

export const programs = pgTable("program", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  domainId: uuid("domain_id")
    .notNull()
    .references(() => domains.id, { onDelete: "restrict" }),
  name: text("name").notNull(),
  active: boolean("active").notNull().default(true),
});

export const programsRelations = relations(programs, ({ one }) => ({
  domain: one(domains, {
    fields: [programs.domainId],
    references: [domains.id],
  }),
}));

export type SelectDomain = typeof domains.$inferSelect;
export type InsertDomain = typeof domains.$inferInsert;
export type SelectProgram = typeof programs.$inferSelect;
export type InsertProgram = typeof programs.$inferInsert;
