// Exact host names only. This feature is served by a dedicated loopback-bound dev process.
export function isJournalLoopbackHost(host: string | null): boolean {
  return host !== null && /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host);
}

export function journalRequestAllowed(request: Request): boolean {
  if (process.env.NODE_ENV !== "development" || process.env.PERSONAL_JOURNAL_LOCAL !== "1") return false;
  const host = request.headers.get("host");
  if (!isJournalLoopbackHost(host)) return false;
  const origin = request.headers.get("origin");
  if (origin && origin !== `http://${host}` && origin !== `https://${host}`) return false;
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  return true;
}
