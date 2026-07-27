"use server";

import { desc, eq } from "drizzle-orm";
import { db } from "@/db/db";
import {
  InsertPreferenceResponse,
  InsertPreferenceSession,
  preferenceResponses,
  preferenceSessions,
  SelectPreferenceSession,
} from "../schema/preferences-schema";

export const createPreferenceSession = async (
  data: InsertPreferenceSession
): Promise<SelectPreferenceSession> => {
  const [row] = await db.insert(preferenceSessions).values(data).returning();
  return row;
};

export const getPreferenceSessionById = async (
  id: string
): Promise<SelectPreferenceSession | null> => {
  const row = await db.query.preferenceSessions.findFirst({
    where: eq(preferenceSessions.id, id),
  });
  return row ?? null;
};

export const updatePreferenceSession = async (
  id: string,
  data: Partial<InsertPreferenceSession>
): Promise<SelectPreferenceSession> => {
  const [row] = await db
    .update(preferenceSessions)
    .set(data)
    .where(eq(preferenceSessions.id, id))
    .returning();
  return row;
};

export const getSessionsForUser = async (
  userId: string
): Promise<SelectPreferenceSession[]> => {
  return db.query.preferenceSessions.findMany({
    where: eq(preferenceSessions.userId, userId),
    orderBy: [desc(preferenceSessions.createdAt)],
  });
};

export const getActiveSessions = async (): Promise<
  SelectPreferenceSession[]
> => {
  return db.query.preferenceSessions.findMany({
    where: eq(preferenceSessions.status, "active"),
    orderBy: [desc(preferenceSessions.createdAt)],
  });
};

export const insertPreferenceResponse = async (
  data: InsertPreferenceResponse
) => {
  const [row] = await db.insert(preferenceResponses).values(data).returning();
  return row;
};

export const getResponsesForSession = async (sessionId: string) => {
  return db.query.preferenceResponses.findMany({
    where: eq(preferenceResponses.sessionId, sessionId),
    orderBy: [preferenceResponses.ordinal],
  });
};
