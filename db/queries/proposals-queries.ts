"use server";

import { eq } from "drizzle-orm";
import { db } from "@/db/db";
import {
  InsertProposal,
  InsertProposalAction,
  InsertProposalBudgetItem,
  InsertProposalMetric,
  InsertProposalTopic,
  proposalActions,
  proposalBudgetItems,
  proposalMetrics,
  proposals,
  proposalTopics,
  SelectProposal,
} from "../schema/proposals-schema";
import { ProposalFormData } from "@/lib/validations/proposal-schema";

export const createProposal = async (data: InsertProposal) => {
  try {
    const [newProposal] = await db.insert(proposals).values(data).returning();
    return newProposal;
  } catch (error) {
    console.error("Error creating proposal:", error);
    throw new Error("Failed to create proposal");
  }
};

export const createProposalWithRelations = async (
  formData: ProposalFormData
) => {
  try {
    // Calculate budget totals
    const budgetOneTimeUsd = formData.budgetItems.reduce(
      (sum, item) => sum + item.oneTimeUsd,
      0
    );
    const budgetAnnualUsd = formData.budgetItems.reduce(
      (sum, item) => sum + item.annualUsd,
      0
    );

    // Create proposal
    const proposalData: InsertProposal = {
      authorId: formData.authorId,
      status: "draft",
      title: formData.title,
      summary: formData.summary,
      problemPlain: formData.problemPlain,
      implementingOrg: formData.implementingOrg,
      scopeGeojson: formData.scopeGeojson,
      populationEstimate: formData.populationEstimate,
      populationSource: formData.populationSource,
      budgetOneTimeUsd,
      budgetAnnualUsd,
      fundingNotes: formData.fundingNotes,
      legalCitation: formData.legalCitation,
      needsNewAuthority: formData.needsNewAuthority,
      equityBeneficiaries: formData.equityBeneficiaries,
      equityCostBearers: formData.equityCostBearers,
      safeguardsRollbackTrigger: formData.safeguardsRollbackTrigger,
      safeguardsRollbackSteps: formData.safeguardsRollbackSteps,
      sunsetDate: formData.sunsetDate || undefined,
      privacyNotes: formData.privacyNotes,
      retentionDays: formData.retentionDays,
    };

    return await db.transaction(async (tx) => {
      // Insert proposal
      const [newProposal] = await tx
        .insert(proposals)
        .values(proposalData)
        .returning();

      // Insert topics
      const topicInserts: InsertProposalTopic[] = formData.topics.map(
        (topic) => ({
          proposalId: newProposal.id,
          domainId: topic.domainId,
          programId: topic.programId,
          isPrimary: topic.isPrimary,
        })
      );
      if (topicInserts.length > 0) {
        await tx.insert(proposalTopics).values(topicInserts);
      }

      // Insert metrics
      const metricInserts: InsertProposalMetric[] = formData.metrics.map(
        (metric) => ({
          proposalId: newProposal.id,
          name: metric.name,
          unit: metric.unit,
          baselineVal: metric.baselineVal,
          baselineYear: metric.baselineYear,
          baselineSource: metric.baselineSource,
          targetVal: metric.targetVal,
          deadline: metric.deadline,
        })
      );
      if (metricInserts.length > 0) {
        await tx.insert(proposalMetrics).values(metricInserts);
      }

      // Insert actions
      const actionInserts: InsertProposalAction[] = formData.actions.map(
        (action, index) => ({
          proposalId: newProposal.id,
          ordinal: index + 1,
          text: action.text,
        })
      );
      if (actionInserts.length > 0) {
        await tx.insert(proposalActions).values(actionInserts);
      }

      // Insert budget items
      const budgetInserts: InsertProposalBudgetItem[] =
        formData.budgetItems.map((item) => ({
          proposalId: newProposal.id,
          itemName: item.itemName,
          oneTimeUsd: item.oneTimeUsd,
          annualUsd: item.annualUsd,
          confidence: item.confidence.toString(),
        }));
      if (budgetInserts.length > 0) {
        await tx.insert(proposalBudgetItems).values(budgetInserts);
      }

      // Return proposal with relations
      return await tx.query.proposals.findFirst({
        where: eq(proposals.id, newProposal.id),
        with: {
          author: true,
          topics: {
            with: {
              domain: true,
              program: true,
            },
          },
          metrics: true,
          actions: true,
          budgetItems: true,
        },
      });
    });
  } catch (error) {
    console.error("Error creating proposal with relations:", error);
    throw new Error("Failed to create proposal");
  }
};

export const getProposalById = async (id: string) => {
  try {
    const proposal = await db.query.proposals.findFirst({
      where: eq(proposals.id, id),
      with: {
        author: true,
        topics: {
          with: {
            domain: true,
            program: true,
          },
        },
        metrics: true,
        actions: true,
        budgetItems: true,
      },
    });
    if (!proposal) {
      throw new Error("Proposal not found");
    }
    return proposal;
  } catch (error) {
    console.error("Error getting proposal by ID:", error);
    throw new Error("Failed to get proposal");
  }
};

export const getAllProposals = async (): Promise<SelectProposal[]> => {
  return db.query.proposals.findMany({
    with: {
      author: true,
      topics: {
        with: {
          domain: true,
          program: true,
        },
      },
    },
  });
};

export const updateProposal = async (
  id: string,
  data: Partial<InsertProposal>
) => {
  try {
    const [updatedProposal] = await db
      .update(proposals)
      .set(data)
      .where(eq(proposals.id, id))
      .returning();
    return updatedProposal;
  } catch (error) {
    console.error("Error updating proposal:", error);
    throw new Error("Failed to update proposal");
  }
};

export const deleteProposal = async (id: string) => {
  try {
    await db.delete(proposals).where(eq(proposals.id, id));
  } catch (error) {
    console.error("Error deleting proposal:", error);
    throw new Error("Failed to delete proposal");
  }
};
