import type { ActionResult } from "@/types/actions/action-types";
import type {
  AtlasPointRequest,
  AtlasRequest,
  AtlasResponse,
  ProfileResolveRequest,
  ProfileResolveResponse,
} from "@/types/methods";

/** Read-only calculations use abortable HTTP instead of the serialized action queue. */
async function request<T>(path: string, input: unknown, signal: AbortSignal): Promise<ActionResult<T>> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Methods request failed: ${response.status}`);
  const result: unknown = await response.json();
  if (
    !result || typeof result !== "object" ||
    !("isSuccess" in result) || typeof result.isSuccess !== "boolean" ||
    !("message" in result) || typeof result.message !== "string" ||
    (result.isSuccess && (!("data" in result) || result.data == null || typeof result.data !== "object" || Array.isArray(result.data)))
  ) throw new Error("Methods returned an invalid response");
  return result as ActionResult<T>;
}

export function requestProfile(input: ProfileResolveRequest, signal: AbortSignal) {
  return request<ProfileResolveResponse>("/api/methods/profile", input, signal);
}

export function requestAtlas(input: AtlasRequest, signal: AbortSignal) {
  return request<AtlasResponse>("/api/methods/atlas", input, signal);
}

export function requestAtlasPoint(input: AtlasPointRequest, signal: AbortSignal) {
  return request<ProfileResolveResponse>("/api/methods/atlas/point", input, signal);
}
