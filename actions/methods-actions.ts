"use server";

import { ActionResult } from "@/types/actions/action-types";
import {
  VotingMethod,
  MethodDemo,
  DemoScenario,
  DemoScenarioResolution,
} from "@/types/methods";
import {
  fetchDemoScenarios,
  fetchScenarioResult,
  fetchAllScenarioResults,
  resolveDemoScenario,
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

export async function getDemoScenariosAction(): Promise<
  ActionResult<DemoScenario[]>
> {
  try {
    const scenarios = await fetchDemoScenarios();
    return {
      isSuccess: true,
      message: "Interactive scenarios loaded",
      data: scenarios,
    };
  } catch (error) {
    console.error("Error fetching interactive scenarios:", error);
    return {
      isSuccess: false,
      message:
        error instanceof Error
          ? error.message
          : "Failed to fetch interactive scenarios. Is the Python API running?",
    };
  }
}

export async function resolveDemoScenarioAction(
  scenarioId: string,
  controls: Record<string, number>
): Promise<ActionResult<DemoScenarioResolution>> {
  try {
    const result = await resolveDemoScenario(scenarioId, controls);
    return {
      isSuccess: true,
      message: "Interactive scenario resolved",
      data: result,
    };
  } catch (error) {
    console.error("Error resolving interactive scenario:", error);
    return {
      isSuccess: false,
      message:
        error instanceof Error
          ? error.message
          : "Failed to resolve interactive scenario. Is the Python API running?",
    };
  }
}
