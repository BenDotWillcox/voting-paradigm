import type { OpenVote } from "./account-provider";

/** How close to closing a vote must be before a silent delegate is flagged. */
export const LATE_WITHIN_DAYS = 7;

/**
 * Whether an open question waits on the viewer: either their own vote stays
 * with them, or other people's votes have reached them.
 */
export function needsViewer(entry: OpenVote, viewer: string): boolean {
  const { receipt, inbox } = entry.result;
  return receipt ? receipt.resolver === viewer : inbox.votes_for_others > 0;
}

/**
 * Whether the viewer's vote sits with a delegate, nothing has been cast for
 * it, and the ballot closes within the week. The delegate may have passed
 * the vote on; either way the viewer's ballot is empty so far.
 */
export function delegateIsLate(entry: OpenVote, viewer: string): boolean {
  const receipt = entry.result.receipt;
  return (
    receipt !== null &&
    receipt.resolver !== viewer &&
    receipt.choice === null &&
    entry.paper.closes_in_days <= LATE_WITHIN_DAYS
  );
}
