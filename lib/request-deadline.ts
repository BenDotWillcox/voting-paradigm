/** A deadline covers the whole request, including reading its response body. */
export class RequestTimeoutError extends Error {
  constructor() {
    super("The request took too long. Please try again.");
    this.name = "RequestTimeoutError";
  }
}

/**
 * Abort cancellable work and stop waiting even when a transport (such as a
 * Server Action) ignores AbortSignal. The caller's signal remains separate:
 * supersession/unmount can be silent, while a deadline needs visible recovery.
 * Late completion cannot settle this promise again. Callers still guard which
 * request owns UI state when a newer request replaces an older one.
 */
export function withRequestDeadline<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  { timeoutMs, signal }: { timeoutMs: number; signal?: AbortSignal },
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const controller = new AbortController();
    let settled = false;
    const timer = setTimeout(() => {
      const error = new RequestTimeoutError();
      finish(() => {
        reject(error);
        controller.abort(error);
      });
    }, timeoutMs);

    function finish(callback: () => void) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", cancel);
      callback();
    }

    function cancel() {
      const reason = signal?.reason ?? new DOMException("Request cancelled", "AbortError");
      finish(() => {
        reject(reason);
        controller.abort(reason);
      });
    }

    if (signal?.aborted) {
      cancel();
      return;
    }
    signal?.addEventListener("abort", cancel, { once: true });

    // Also catch synchronous failures while starting the request.
    try {
      operation(controller.signal).then(
        (value) => finish(() => resolve(value)),
        (error: unknown) => finish(() => reject(error)),
      );
    } catch (error) {
      finish(() => reject(error));
    }
  });
}
