/**
 * Server-side API client for the Python voting API.
 * Called from server components/actions — never exposed to the browser.
 */

import {
  VotingMethod,
  MethodScenario,
  AnyElectionResult,
  MethodDemo,
} from "@/types/methods";
import { methodOrder } from "@/lib/methods/method-descriptions";

const BASE_URL =
  process.env.VOTING_API_URL ||
  process.env.NEBULA_API_URL ||
  "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Voting API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

/** Fetch all 7 curated scenarios. */
export async function fetchScenarios(): Promise<
  Record<string, MethodScenario>
> {
  return apiFetch<Record<string, MethodScenario>>(
    "/api/elections/scenarios"
  );
}

/** Fetch a single scenario by method name. */
export async function fetchScenario(
  method: VotingMethod
): Promise<MethodScenario> {
  return apiFetch<MethodScenario>(
    `/api/elections/scenarios/${method}`
  );
}

/** Resolve a scenario by posting its ballots to the resolution endpoint. */
export async function resolveScenario(
  scenario: MethodScenario
): Promise<AnyElectionResult> {
  return apiFetch<AnyElectionResult>(
    `/api/elections/${scenario.method}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({
        candidates: scenario.candidates,
        ballots: scenario.ballots,
      }),
    }
  );
}

/** Fetch a scenario and resolve it, returning both. */
export async function fetchScenarioResult(
  method: VotingMethod
): Promise<MethodDemo> {
  const scenario = await fetchScenario(method);
  const result = await resolveScenario(scenario);
  return { scenario, result };
}

/** Fetch and resolve all 7 scenarios. */
export async function fetchAllScenarioResults(): Promise<
  Record<VotingMethod, MethodDemo>
> {
  const scenarios = await fetchScenarios();
  const results: Partial<Record<VotingMethod, MethodDemo>> = {};

  await Promise.all(
    methodOrder.map(async (method) => {
      const scenario = scenarios[method];
      if (!scenario) return;
      const result = await resolveScenario(scenario);
      results[method] = { scenario, result };
    })
  );

  return results as Record<VotingMethod, MethodDemo>;
}
