"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ScalarBallot } from "./scalar-ballot";
import { IncomeTaxBallot } from "./income-tax-ballot";
import { ElectorateResults } from "./electorate-results";
import { scalarComparisonResponseSchema } from "@/lib/validations/expressive-comparison";
import { TAX_MEASURE } from "@/lib/expressive-tax-measure";
import type { BinaryVote, ScalarComparisonRequest, ScalarComparisonResponse } from "@/types/expressive-comparison";
import type { ScalarBallotState } from "@/types/expressive-scalar";
import styles from "./scalar-comparison.module.css";

const rateText = (value: number) => `${value.toFixed(2)}%`;
type Submission = { request: ScalarComparisonRequest; data: ScalarComparisonResponse };

export function ScalarComparison() {
  const [vote, setVote] = useState<BinaryVote | null>(null);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [lastRequest, setLastRequest] = useState<ScalarComparisonRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const ballotId = useId();

  useEffect(() => () => controller.current?.abort(), []);

  async function compare(request: ScalarComparisonRequest) {
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    setLastRequest(request);
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/expressive/scalar/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: active.signal,
      });
      const body: unknown = await response.json();
      if (!response.ok) {
        const message = typeof body === "object" && body !== null && "message" in body && typeof body.message === "string"
          ? body.message : "The comparison is unavailable. Your answers are still here.";
        throw new Error(message);
      }
      const parsed = scalarComparisonResponseSchema.safeParse(body);
      if (!parsed.success) throw new Error("The comparison could not be read. Please try again.");
      if (active.signal.aborted) return;
      setSubmission({ request, data: parsed.data });
      resultRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    } catch (caught) {
      if (!active.signal.aborted) setError(caught instanceof Error ? caught.message : "The comparison is unavailable. Please try again.");
    } finally {
      if (!active.signal.aborted) setBusy(false);
    }
  }

  function submitBallot(ballot: ScalarBallotState) {
    if (vote) void compare({ ballot, binary_vote: vote });
  }

  const voteChanged = submission && vote !== submission.request.binary_vote;

  return <div className={styles.walkthrough}>
    <section id="rate-ballot" className="scroll-mt-6" aria-labelledby={`${ballotId}-heading`}>
      <p className={styles.step}>01 · Two ways to answer</p>
      <div className={styles.sectionHeading}>
        <h2 id={`${ballotId}-heading`}>One policy question. How much can your answer say?</h2>
        <p>In 2022, Colorado voters were asked whether to reduce the statutory income tax rate from {rateText(TAX_MEASURE.statusQuo)} to {rateText(TAX_MEASURE.proposal)}. Answer that ballot question, then explore a richer way to express your preferences.</p>
      </div>
      <IncomeTaxBallot vote={vote} onVoteChange={setVote} />
      <div className={styles.richerIntro}>
        <h3>A possible richer ballot</h3>
        <p>The 2022 ballot was binary. This experimental curve starts at the then-current statutory rate of {rateText(TAX_MEASURE.statusQuo)}.</p>
      </div>
      <ScalarBallot onSubmitBallot={submitBallot} canSubmit={vote !== null} isSubmitting={busy} submittedBallot={submission?.request.ballot}
        submissionHint={!vote ? "Choose Yes or No above, then shape your curve and compare." : voteChanged ? "Yes/no answer edited. The comparison still uses your submitted answers." : undefined} />
    </section>

    <section id="ballot-comparison" ref={resultRef} className={styles.comparison} aria-labelledby={`${ballotId}-results`}>
      <p className={styles.step}>02 · Compare the results</p>
      <div className={styles.sectionHeading}>
        <h2 id={`${ballotId}-results`}>What becomes visible when a ballot says more?</h2>
        <p>Your two answers join 99 synthetic voters. Explore their different preferences and the yes/no answers they produce, then combine those same 100 ballots into a tax rate. These are illustrative outcomes, not the actual 2022 election results.</p>
      </div>
      {error && <div className={styles.error} role="alert"><p>{error}</p><button type="button" disabled={busy} onClick={() => lastRequest && void compare(lastRequest)}>Retry submitted ballot</button></div>}
      {submission ? <ElectorateResults key={JSON.stringify(submission.request)} data={submission.data} ballot={submission.request.ballot} /> : <div className={styles.emptyState} role="status">{busy ? "Comparing your submitted ballot with the prepared electorate…" : "Submit your two answers above to reveal the comparison."}</div>}
    </section>
  </div>;
}
