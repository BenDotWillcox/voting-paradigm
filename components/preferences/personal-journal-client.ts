export class JournalRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function requestJournal<T>(
  method: "GET" | "POST" | "PUT" | "PATCH", body?: unknown, signal?: AbortSignal, path = ""
): Promise<T> {
  const response = await fetch("/api/preferences/journal" + path, {
    method, cache: "no-store", signal,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new JournalRequestError(typeof data?.error === "string" ? data.error : "The local journal is unavailable. Please try again.", response.status);
  }
  return response.json() as Promise<T>;
}
