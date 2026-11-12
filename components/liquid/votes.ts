import type { OpenVote } from "./account-provider";

/**
 * Whether an open question waits on the viewer: either their own vote stays
 * with them, or other people's votes have reached them.
 */
export function needsViewer(entry: OpenVote, viewer: string): boolean {
  const { receipt, inbox } = entry.result;
  return receipt ? receipt.resolver === viewer : inbox.votes_for_others > 0;
}
