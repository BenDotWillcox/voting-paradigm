import { pgTable, text, timestamp, numeric, json } from "drizzle-orm/pg-core";
import { profilesTable } from "./profiles-schema"; // Assuming profilesTable is defined as in your code.

export const userPreferencesTable = pgTable("user_preferences", {
  // Link each preferences row to a profile via userId (clerk's auth id)
  userId: text("user_id")
    .primaryKey()
    .references(() => profilesTable.userId)
    .notNull(),
    
  // Each axis is captured as a numeric value. For example, if we choose a scale of -10 to +10:
  federalVsUnitary: numeric("federal_vs_unitary").notNull().default("0"), // 0 as neutral
  democraticVsAuthoritarian: numeric("democratic_vs_authoritarian").notNull().default("0"),
  globalistVsIsolationist: numeric("globalist_vs_isolationist").notNull().default("0"),
  militaristVsPacifist: numeric("militarist_vs_pacifist").notNull().default("0"),
  securityVsFreedom: numeric("security_vs_freedom").notNull().default("0"),
  equalityVsMarkets: numeric("equality_vs_markets").notNull().default("0"),
  secularVsReligious: numeric("secular_vs_religious").notNull().default("0"),
  progressiveVsTraditional: numeric("progressive_vs_traditional").notNull().default("0"),
  assimilationistVsMulticulturalist: numeric("assimilationist_vs_multiculturalist").notNull().default("0"),
  
  // Optional: Store additional topics as a JSON field (if you decide to capture specific issues later)
  additionalTopics: json("additional_topics"),
  
  // Optional: Store axis importance weights as JSON.
  // For instance: { "federalVsUnitary": 1.2, "democraticVsAuthoritarian": 1.0, ... }
  axisImportance: json("axis_importance"),
  
  updatedAt: timestamp("updated_at")
    .defaultNow()
    .notNull()
    .$onUpdate(() => new Date())
});

export type InsertUserPreferences = typeof userPreferencesTable.$inferInsert;
export type SelectUserPreferences = typeof userPreferencesTable.$inferSelect;
