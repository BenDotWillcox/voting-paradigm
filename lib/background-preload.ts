/**
 * Loading ahead of the reader: files a later part of a page will need,
 * fetched in turn while the browser has nothing else to do, so they come from
 * the HTTP cache when that part opens. Only for responses the server marks
 * cacheable; anything else would simply be downloaded twice.
 */

type NetworkInformation = { saveData?: boolean; effectiveType?: string };

/** False when the browser asks for less data: data saver is on, or the connection is 2G or 3G. */
export function canPreload(): boolean {
  const connection = (navigator as Navigator & { connection?: NetworkInformation }).connection;
  return !connection?.saveData && !/2g|3g/.test(connection?.effectiveType ?? "");
}

/** Resolves once the browser is idle (or within two seconds regardless), or at once when aborted. */
function whenIdle(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const done = () => {
      signal.removeEventListener("abort", done);
      resolve();
    };
    signal.addEventListener("abort", done, { once: true });
    if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(done, { timeout: 2000 });
    else window.setTimeout(done, 200);
  });
}

/**
 * Fetches each file in turn, at low priority and only when the browser is
 * idle, reading every body to the end so the cache keeps it. A file that
 * fails is left for its section to load as usual.
 */
export async function preloadInTurn(urls: readonly string[], signal: AbortSignal): Promise<void> {
  for (const url of urls) {
    await whenIdle(signal);
    if (signal.aborted) return;
    try {
      const response = await fetch(url, { signal, priority: "low" });
      if (response.ok) await response.arrayBuffer();
    } catch {
      if (signal.aborted) return;
    }
  }
}
