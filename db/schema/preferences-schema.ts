import {
  integer,
  jsonb,
  numeric,
  pgEnum,
  pgTable,
  text,
  timestamp,
  uuid,
} from "drizzle-orm/pg-core";
import { relations, sql } from "drizzle-orm";
import { users } from "./users-schema";

// -----------------------------------------------------------------------
// preference_session — one row per user elicitation session.
// `state_snapshot` stores the serialized PreferenceState (mu, sigma, item ids,
// responses, etc.) as JSONB for atomic read/write.
// -----------------------------------------------------------------------

export const preferenceSessionStatus = pgEnum("preference_session_status", [
  "active",
  "completed",
  "abandoned",
]);

export const preferenceSessions = pgTable("preference_session", {
  id: uuid("id")
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  userId: uuid("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  status: preferenceSessionStatus("status").notNull().default("active"),
  modelVersion: text("model_version").notNull().default("thurstone_v1"),
  stateSnapshot: jsonb("state_snapshot").notNull(),
  targetQuestions: integer("target_questions").notNull().default(25),
  nQuestions: integer("n_questions").notNull().default(0),
  // Currently pending question (null once session completes)
  currentQuestion: jsonb("current_question"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at")
    .defaultNow()
    .notNull()
    .$onUpdate(() => new Date()),
});

export const preferenceSessionsRelations = relations(
  preferenceSessions,
  ({ one, many }) => ({
    user: one(users, {
      fields: [preferenceSessions.userId],
      references: [users.id],
    }),
    responses: many(preferenceResponses),
  })
);

// -----------------------------------------------------------------------
// preference_response — one row per answered question (audit trail).
// -----------------------------------------------------------------------

export const preferenceResponses = pgTable("preference_response", {
  id: uuid("id")
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  sessionId: uuid("session_id")
    .notNull()
    .references(() => preferenceSessions.id, { onDelete: "cascade" }),
  questionId: text("question_id").notNull(),
  questionType: text("question_type").notNull(),
  questionPrompt: text("question_prompt").notNull(),
  optionsJson: jsonb("options_json").notNull(),
  chosenOptionId: text("chosen_option_id").notNull(),
  strength: numeric("strength", { precision: 4, scale: 1 }),
  responseTimeMs: integer("response_time_ms"),
  ordinal: integer("ordinal").notNull(),
  source: text("source").notNull().default("bank"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const preferenceResponsesRelations = relations(
  preferenceResponses,
  ({ one }) => ({
    session: one(preferenceSessions, {
      fields: [preferenceResponses.sessionId],
      references: [preferenceSessions.id],
    }),
  })
);

export type SelectPreferenceSession = typeof preferenceSessions.$inferSelect;
export type InsertPreferenceSession = typeof preferenceSessions.$inferInsert;
export type SelectPreferenceResponse = typeof preferenceResponses.$inferSelect;
export type InsertPreferenceResponse = typeof preferenceResponses.$inferInsert;
