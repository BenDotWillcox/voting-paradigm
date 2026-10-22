/**
 * Server-side API client for the Python voting API.
 * Called from server components/actions — never exposed to the browser.
 */

import type { ProfileResolveRequest, ProfileResolveResponse } from "@/types/methods";

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

/**
 * Resolve a ranked or utility profile under every method its ballots allow.
 * Throws on an invalid profile (HTTP 422) like any other API error.
 */
export async function resolveProfile(
  request: ProfileResolveRequest
): Promise<ProfileResolveResponse> {
  return apiFetch<ProfileResolveResponse>("/api/voting/profile/resolve", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
