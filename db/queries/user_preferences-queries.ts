"use server";

import { db } from "@/db/db"; // Your database instance
import { eq } from "drizzle-orm";
import { InsertUserPreferences, userPreferencesTable, SelectUserPreferences } from "../schema/user_preferences-schema";

// Create or upsert user preferences
export const createOrUpdateUserPreferences = async (data: InsertUserPreferences) => {
  try {
    // If a row already exists for userId, update it. Otherwise, insert a new row.
    // This can be implemented as an upsert (depending on your db support)
    const existing = await db.query.userPreferences.findFirst({
      where: eq(userPreferencesTable.userId, data.userId)
    });

    if (existing) {
      const [updated] = await db.update(userPreferencesTable)
        .set(data)
        .where(eq(userPreferencesTable.userId, data.userId))
        .returning();
      return updated;
    } else {
      const [newPref] = await db.insert(userPreferencesTable)
        .values(data)
        .returning();
      return newPref;
    }
  } catch (error) {
    console.error("Error creating/updating user preferences:", error);
    throw new Error("Failed to set preferences");
  }
};

export const getUserPreferencesByUserId = async (userId: string): Promise<SelectUserPreferences | null> => {
  try {
    const result = await db.query.userPreferences.findFirst({
      where: eq(userPreferencesTable.userId, userId)
    });
    return result || null;
  } catch (error) {
    console.error("Error retrieving user preferences:", error);
    throw new Error("Failed to get preferences");
  }
};

export const deleteUserPreferences = async (userId: string): Promise<void> => {
  try {
    await db.delete(userPreferencesTable).where(eq(userPreferencesTable.userId, userId));
  } catch (error) {
    console.error("Error deleting user preferences:", error);
    throw new Error("Failed to delete preferences");
  }
};
