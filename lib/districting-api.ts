/**
 * Server-side API client for the Python districting API.
 * Called from server components/actions — never exposed to the browser.
 *
 * Step 1 of the districting demo only ships apportionment. Endpoints for
 * the per-state district maps and the national composite land in step 4+.
 */

import type { ApportionmentDto } from "@/types/districting";

// Both voting and districting routers live in the single Nebula Civitas API
// process on :8000. Kept as a separate env var so deployments can split if
// needed, but defaults match the unified dev setup.
//
// Default uses 127.0.0.1 rather than `localhost` to dodge Node 18+'s undici
// fetch resolving `localhost` to ::1 first; uvicorn binds IPv4-only by
// default, so the IPv6 attempt would fail before falling back.
const BASE_URL =
  process.env.DISTRICTING_API_URL ||
  process.env.NEBULA_API_URL ||
  "http://127.0.0.1:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `Districting API error: ${res.status} ${res.statusText} ${text}`
    );
  }
  return res.json() as Promise<T>;
}

/**
 * Fetch the Method-of-Equal-Proportions apportionment of `cap` House seats
 * across the 50 states using 2020 census apportionment populations.
 *
 * Cheap on the server (sub-millisecond Python work + a tiny payload), so
 * it's safe for the UI to call on every settled slider value.
 */
export async function getApportionment(cap: number): Promise<ApportionmentDto> {
  const params = new URLSearchParams({ cap: String(cap) });
  return apiFetch<ApportionmentDto>(
    `/api/districting/apportionment?${params.toString()}`
  );
}
