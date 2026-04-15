import { pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

// --- users
export const users = pgTable("app_user", {
    id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
    handle: text("handle").notNull().unique(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at")
    .defaultNow()
    .notNull()
    .$onUpdate(() => new Date()),
  });

export type SelectUser = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;
