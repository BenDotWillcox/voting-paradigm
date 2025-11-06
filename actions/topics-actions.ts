"use server";

import {
  createDomain,
  deleteDomain,
  getAllDomains,
  getDomainById,
  updateDomain,
  createProgram,
  deleteProgram,
  getAllPrograms,
  getProgramsByDomain,
  getProgramById,
  updateProgram,
} from "@/db/queries/topics-queries";
import {
  InsertDomain,
  SelectDomain,
  InsertProgram,
  SelectProgram,
} from "@/db/schema/topics-schema";
import { ActionResult } from "@/types/actions/action-types";
import { revalidatePath } from "next/cache";

// DOMAINS
export async function createDomainAction(
  data: InsertDomain
): Promise<ActionResult<SelectDomain>> {
  try {
    const newDomain = await createDomain(data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "Domain created successfully",
      data: newDomain,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to create domain" };
  }
}

export async function getDomainByIdAction(
  id: string
): Promise<ActionResult<SelectDomain | null>> {
  try {
    const domain = await getDomainById(id);
    return {
      isSuccess: true,
      message: "Domain retrieved successfully",
      data: domain,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get domain" };
  }
}

export async function getAllDomainsAction(): Promise<ActionResult<SelectDomain[]>> {
  try {
    const domains = await getAllDomains();
    return {
      isSuccess: true,
      message: "Domains retrieved successfully",
      data: domains,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get domains" };
  }
}

export async function updateDomainAction(
  id: string,
  data: Partial<InsertDomain>
): Promise<ActionResult<SelectDomain>> {
  try {
    const updatedDomain = await updateDomain(id, data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "Domain updated successfully",
      data: updatedDomain,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to update domain" };
  }
}

export async function deleteDomainAction(
  id: string
): Promise<ActionResult<void>> {
  try {
    await deleteDomain(id);
    revalidatePath("/");
    return { isSuccess: true, message: "Domain deleted successfully" };
  } catch (error) {
    return { isSuccess: false, message: "Failed to delete domain" };
  }
}

// PROGRAMS
export async function createProgramAction(
  data: InsertProgram
): Promise<ActionResult<SelectProgram>> {
  try {
    const newProgram = await createProgram(data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "Program created successfully",
      data: newProgram,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to create program" };
  }
}

export async function getProgramByIdAction(
  id: string
): Promise<ActionResult<SelectProgram | null>> {
  try {
    const program = await getProgramById(id);
    return {
      isSuccess: true,
      message: "Program retrieved successfully",
      data: program,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get program" };
  }
}

export async function getAllProgramsAction(): Promise<ActionResult<SelectProgram[]>> {
  try {
    const programs = await getAllPrograms();
    return {
      isSuccess: true,
      message: "Programs retrieved successfully",
      data: programs,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get programs" };
  }
}

export async function getProgramsByDomainAction(
  domainId: string
): Promise<ActionResult<SelectProgram[]>> {
  try {
    const programs = await getProgramsByDomain(domainId);
    return {
      isSuccess: true,
      message: "Programs retrieved successfully",
      data: programs,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get programs" };
  }
}

export async function updateProgramAction(
  id: string,
  data: Partial<InsertProgram>
): Promise<ActionResult<SelectProgram>> {
  try {
    const updatedProgram = await updateProgram(id, data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "Program updated successfully",
      data: updatedProgram,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to update program" };
  }
}

export async function deleteProgramAction(
  id: string
): Promise<ActionResult<void>> {
  try {
    await deleteProgram(id);
    revalidatePath("/");
    return { isSuccess: true, message: "Program deleted successfully" };
  } catch (error) {
    return { isSuccess: false, message: "Failed to delete program" };
  }
}
