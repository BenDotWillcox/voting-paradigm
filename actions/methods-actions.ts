"use server";

import { ActionResult } from "@/types/actions/action-types";
import { AtlasResponse, ProfileResolveResponse } from "@/types/methods";
import { resolveAtlas, resolveAtlasPoint, resolveProfile } from "@/lib/methods-api";
import {
  atlasPointRequestSchema,
  atlasRequestSchema,
  profileResolveRequestSchema,
} from "@/lib/validations/methods-schemas";

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

/**
 * Map every method's winner across the atlas for a candidate layout. Read
 * only, like resolveProfileAction.
 */
export async function resolveAtlasAction(
  input: unknown
): Promise<ActionResult<AtlasResponse>> {
  const parsed = atlasRequestSchema.safeParse(input);
  if (!parsed.success) {
    return { isSuccess: false, message: parsed.error.issues[0]?.message ?? "Invalid layout" };
  }
  try {
    const data = await resolveAtlas(parsed.data);
    return { isSuccess: true, message: "Atlas mapped", data };
  } catch (error) {
    console.error("Error mapping the atlas:", { candidates: parsed.data.candidates.length, error });
    return { isSuccess: false, message: "Live counting is unavailable right now." };
  }
}

/** Count the electorate at one atlas cell, for the instrument to show. */
export async function resolveAtlasPointAction(
  input: unknown
): Promise<ActionResult<ProfileResolveResponse>> {
  const parsed = atlasPointRequestSchema.safeParse(input);
  if (!parsed.success) {
    return { isSuccess: false, message: parsed.error.issues[0]?.message ?? "Invalid point" };
  }
  try {
    const data = await resolveAtlasPoint(parsed.data);
    return { isSuccess: true, message: "Point resolved", data };
  } catch (error) {
    console.error("Error resolving an atlas point:", { cell: parsed.data.cell, error });
    return { isSuccess: false, message: "Live counting is unavailable right now." };
  }
}
