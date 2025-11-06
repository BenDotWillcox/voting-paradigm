"use server";

import {
  createProposal,
  createProposalWithRelations,
  deleteProposal,
  getAllProposals,
  getProposalById,
  updateProposal,
} from "@/db/queries/proposals-queries";
import {
  InsertProposal,
  SelectProposal,
} from "@/db/schema/proposals-schema";
import { ActionResult } from "@/types/actions/action-types";
import { ProposalFormData } from "@/lib/validations/proposal-schema";
import { revalidatePath } from "next/cache";

export async function createProposalAction(
  data: InsertProposal
): Promise<ActionResult<SelectProposal>> {
  try {
    const newProposal = await createProposal(data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "Proposal created successfully",
      data: newProposal,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to create proposal" };
  }
}

export async function createProposalFormAction(
  data: ProposalFormData
): Promise<ActionResult<SelectProposal>> {
  try {
    const newProposal = await createProposalWithRelations(data);
    if (!newProposal) {
      throw new Error("Failed to create proposal");
    }
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "Proposal created successfully",
      data: newProposal,
    };
  } catch (error) {
    console.error("Error creating proposal:", error);
    return {
      isSuccess: false,
      message: error instanceof Error ? error.message : "Failed to create proposal",
    };
  }
}

export async function getProposalByIdAction(
  id: string
): Promise<ActionResult<SelectProposal | null>> {
  try {
    const proposal = await getProposalById(id);
    return {
      isSuccess: true,
      message: "Proposal retrieved successfully",
      data: proposal,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get proposal" };
  }
}

export async function getAllProposalsAction(): Promise<
  ActionResult<SelectProposal[]>
> {
  try {
    const proposals = await getAllProposals();
    return {
      isSuccess: true,
      message: "Proposals retrieved successfully",
      data: proposals,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get proposals" };
  }
}

export async function updateProposalAction(
  id: string,
  data: Partial<InsertProposal>
): Promise<ActionResult<SelectProposal>> {
  try {
    const updatedProposal = await updateProposal(id, data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "Proposal updated successfully",
      data: updatedProposal,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to update proposal" };
  }
}

export async function deleteProposalAction(
  id: string
): Promise<ActionResult<void>> {
  try {
    await deleteProposal(id);
    revalidatePath("/");
    return { isSuccess: true, message: "Proposal deleted successfully" };
  } catch (error) {
    return { isSuccess: false, message: "Failed to delete proposal" };
  }
}
