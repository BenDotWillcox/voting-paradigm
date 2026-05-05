"use server";

import { ActionResult } from "@/types/actions/action-types";
import { VotingMethod, MethodDemo } from "@/types/methods";
import {
  fetchScenarioResult,
  fetchAllScenarioResults,
} from "@/lib/methods-api";

export async function getMethodDemoAction(
  method: VotingMethod
): Promise<ActionResult<MethodDemo>> {
  try {
    const demo = await fetchScenarioResult(method);
    return {
      isSuccess: true,
      message: "Election demo loaded",
      data: demo,
    };
  } catch (error) {
    console.error("Error fetching election demo:", error);
    return {
      isSuccess: false,
      message:
        error instanceof Error
          ? error.message
          : "Failed to fetch election demo. Is the Python API running?",
    };
  }
}

export async function getAllMethodDemosAction(): Promise<
  ActionResult<Record<VotingMethod, MethodDemo>>
> {
  try {
    const demos = await fetchAllScenarioResults();
    return {
      isSuccess: true,
      message: "All election demos loaded",
      data: demos,
    };
  } catch (error) {
    console.error("Error fetching election demos:", error);
    return {
      isSuccess: false,
      message:
        error instanceof Error
          ? error.message
          : "Failed to fetch election demos. Is the Python API running?",
    };
  }
}
