/** Shared error contract for the stateless Python expressive-ballot API. */
import "server-only";

export class ExpressivePreviewError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ExpressivePreviewError";
  }
}
