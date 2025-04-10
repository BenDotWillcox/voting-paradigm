"use server";

import { createOrUpdateUserPreferences, deleteUserPreferences, getUserPreferencesByUserId } from "@/db/queries/user_preferences-queries";
import { InsertUserPreferences } from "@/db/schema/user_preferences-schema";
import { ActionState } from "@/types";
import { revalidatePath } from "next/cache";

export async function setUserPreferencesAction(data: InsertUserPreferences): Promise<ActionState> {
  try {
    const newOrUpdatedPreferences = await createOrUpdateUserPreferences(data);
    revalidatePath("/profile/preferences"); // Adjust the path as needed
    return {
      status: "success",
      message: "Preferences saved successfully",
      data: newOrUpdatedPreferences,
    };
  } catch (error) {
    return { status: "error", message: "Failed to save preferences" };
  }
}

export async function getUserPreferencesByUserIdAction(userId: string): Promise<ActionState> {
  try {
    const preferences = await getUserPreferencesByUserId(userId);
    return { status: "success", message: "Preferences retrieved successfully", data: preferences };
  } catch (error) {
    return { status: "error", message: "Failed to retrieve preferences" };
  }
}

export async function deleteUserPreferencesAction(userId: string): Promise<ActionState> {
  try {
    await deleteUserPreferences(userId);
    revalidatePath("/profile/preferences");
    return { status: "success", message: "Preferences deleted successfully" };
  } catch (error) {
    return { status: "error", message: "Failed to delete preferences" };
  }
}
