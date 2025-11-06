"use server";

import { eq } from "drizzle-orm";
import { db } from "@/db/db";
import {
  domains,
  InsertDomain,
  InsertProgram,
  programs,
  SelectDomain,
  SelectProgram,
} from "../schema/topics-schema";

// DOMAINS
export const createDomain = async (data: InsertDomain) => {
  try {
    const [newDomain] = await db.insert(domains).values(data).returning();
    return newDomain;
  } catch (error) {
    console.error("Error creating domain:", error);
    throw new Error("Failed to create domain");
  }
};

export const getDomainById = async (id: string) => {
  try {
    const domain = await db.query.domains.findFirst({
      where: eq(domains.id, id),
      with: {
        programs: true,
      },
    });
    if (!domain) {
      throw new Error("Domain not found");
    }
    return domain;
  } catch (error) {
    console.error("Error getting domain by ID:", error);
    throw new Error("Failed to get domain");
  }
};

export const getAllDomains = async (): Promise<SelectDomain[]> => {
  return db.query.domains.findMany();
};

export const updateDomain = async (id: string, data: Partial<InsertDomain>) => {
  try {
    const [updatedDomain] = await db
      .update(domains)
      .set(data)
      .where(eq(domains.id, id))
      .returning();
    return updatedDomain;
  } catch (error) {
    console.error("Error updating domain:", error);
    throw new Error("Failed to update domain");
  }
};

export const deleteDomain = async (id: string) => {
  try {
    await db.delete(domains).where(eq(domains.id, id));
  } catch (error) {
    console.error("Error deleting domain:", error);
    throw new Error("Failed to delete domain");
  }
};

// PROGRAMS
export const createProgram = async (data: InsertProgram) => {
  try {
    const [newProgram] = await db.insert(programs).values(data).returning();
    return newProgram;
  } catch (error) {
    console.error("Error creating program:", error);
    throw new Error("Failed to create program");
  }
};

export const getProgramById = async (id: string) => {
  try {
    const program = await db.query.programs.findFirst({
      where: eq(programs.id, id),
      with: {
        domain: true,
      },
    });
    if (!program) {
      throw new Error("Program not found");
    }
    return program;
  } catch (error) {
    console.error("Error getting program by ID:", error);
    throw new Error("Failed to get program");
  }
};

export const getAllPrograms = async (): Promise<SelectProgram[]> => {
  return db.query.programs.findMany();
};

export const getProgramsByDomain = async (
  domainId: string
): Promise<SelectProgram[]> => {
  return db.query.programs.findMany({
    where: eq(programs.domainId, domainId),
  });
};

export const updateProgram = async (
  id: string,
  data: Partial<InsertProgram>
) => {
  try {
    const [updatedProgram] = await db
      .update(programs)
      .set(data)
      .where(eq(programs.id, id))
      .returning();
    return updatedProgram;
  } catch (error) {
    console.error("Error updating program:", error);
    throw new Error("Failed to update program");
  }
};

export const deleteProgram = async (id: string) => {
  try {
    await db.delete(programs).where(eq(programs.id, id));
  } catch (error) {
    console.error("Error deleting program:", error);
    throw new Error("Failed to delete program");
  }
};
