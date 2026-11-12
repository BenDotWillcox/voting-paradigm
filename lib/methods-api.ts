/**
 * Server-side API client for the Python voting API.
 * Called from server components/actions — never exposed to the browser.
 */

import type {
  AtlasPointRequest,
  AtlasRequest,
  AtlasResponse,
  ProfileResolveRequest,
  ProfileResolveResponse,
} from "@/types/methods";
import { withRequestDeadline } from "@/lib/request-deadline";

const BASE_URL =
  process.env.VOTING_API_URL ||
  process.env.NEBULA_API_URL ||
  "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit, timeoutMs = 10_000): Promise<T> {
  // Bound body consumption as well as the wait for response headers. The
  // action can then return its ordinary unavailable result before the host
  // terminates the request.
  return withRequestDeadline(async (signal) => {
    const res = await fetch(`${BASE_URL.replace(/\/$/, "")}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options?.headers },
      cache: "no-store",
      signal,
    });
    if (!res.ok) {
      throw new Error(`Voting API error: ${res.status} ${res.statusText}`);
    }
    return res.json() as Promise<T>;
  }, { timeoutMs });
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

/** Every method's winner across the atlas grid for a candidate layout. */
export async function resolveAtlas(request: AtlasRequest): Promise<AtlasResponse> {
  return apiFetch<AtlasResponse>("/api/voting/atlas", {
    method: "POST",
    body: JSON.stringify(request),
  }, 60_000);
}

/** The electorate at one atlas cell, resolved as resolveProfile would. */
export async function resolveAtlasPoint(
  request: AtlasPointRequest
): Promise<ProfileResolveResponse> {
  return apiFetch<ProfileResolveResponse>("/api/voting/atlas/point", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
