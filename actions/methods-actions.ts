"use server";

import { ActionResult } from "@/types/actions/action-types";
import { ProfileResolveResponse } from "@/types/methods";
import { resolveProfile } from "@/lib/methods-api";
import { profileResolveRequestSchema } from "@/lib/validations/methods-schemas";

/**
 * Count a profile under every method its ballots allow (the methods
 * instrument). Read only: nothing is stored, so nothing is revalidated.
 */
export async function resolveProfileAction(
  input: unknown
): Promise<ActionResult<ProfileResolveResponse>> {
  const parsed = profileResolveRequestSchema.safeParse(input);
  if (!parsed.success) {
    return {
      isSuccess: false,
      message: parsed.error.issues[0]?.message ?? "Invalid profile",
    };
  }
  try {
    const data = await resolveProfile(parsed.data);
    return { isSuccess: true, message: "Profile resolved", data };
  } catch (error) {
    console.error("Error resolving profile:", {
      candidates: parsed.data.profile.candidates.length,
      rows: parsed.data.profile.rows.length,
      error,
    });
    return {
      isSuccess: false,
      message: "Live counting is unavailable right now.",
    };
  }
}
