"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ScalarBallot } from "./scalar-ballot";
import { IncomeTaxBallot } from "./income-tax-ballot";
import { ElectorateResults } from "./electorate-results";
import { scalarComparisonResponseSchema } from "@/lib/validations/expressive-comparison";
import { RequestTimeoutError, withRequestDeadline } from "@/lib/request-deadline";
import { TAX_MEASURE } from "@/lib/expressive-tax-measure";
import type { BinaryVote, ScalarComparisonRequest, ScalarComparisonResponse, ScalarScenario } from "@/types/expressive-comparison";
import type { ScalarBallotState } from "@/types/expressive-scalar";
import styles from "./scalar-comparison.module.css";

const rateText = (value: number) => `${value.toFixed(2)}%`;
const COMPARISON_TIMEOUT_MS = 15_000;
const UNAVAILABLE_MESSAGE = "The comparison is unavailable. Your answers are still here; please try again.";
class ComparisonResponseError extends Error {}
type Submission = { request: ScalarComparisonRequest; data: ScalarComparisonResponse };
type RequestKind = "ballot" | "scenario";

export function ScalarComparison() {
  const [vote, setVote] = useState<BinaryVote | null>(null);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [lastRequest, setLastRequest] = useState<ScalarComparisonRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestKind, setRequestKind] = useState<RequestKind>("ballot");
  const controller = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const ballotId = useId();

  useEffect(() => () => {
    controller.current?.abort();
    controller.current = null;
  }, []);

  async function compare(request: ScalarComparisonRequest, kind: RequestKind = "ballot") {
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    setLastRequest(request);
    setRequestKind(kind);
    setBusy(true);
    setError(null);
    try {
      // Bound the browser's entire wait, including body parsing. Production
      // routes directly to Python, so the Next proxy's deadline does not apply.
      const data = await withRequestDeadline(async (signal) => {
        const response = await fetch("/api/expressive/scalar/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
          signal,
        });
        let body: unknown;
        try {
          body = await response.json();
        } catch {
          throw new ComparisonResponseError(response.ok
            ? "The comparison could not be read. Your answers are still here; please try again."
            : UNAVAILABLE_MESSAGE);
        }
        if (!response.ok) {
          const message = typeof body === "object" && body !== null && "message" in body && typeof body.message === "string"
            ? body.message : UNAVAILABLE_MESSAGE;
          throw new ComparisonResponseError(message);
        }
        const parsed = scalarComparisonResponseSchema.safeParse(body);
        if (!parsed.success) throw new ComparisonResponseError("The comparison could not be read. Your answers are still here; please try again.");
        if (parsed.data.scenario !== (request.scenario ?? "prepared")) throw new ComparisonResponseError("The requested electorate could not be loaded. Your answers are still here; please try again.");
        return parsed.data;
      }, { timeoutMs: COMPARISON_TIMEOUT_MS, signal: active.signal });
      if (controller.current !== active || active.signal.aborted) return;
      setSubmission({ request, data });
      if (kind === "ballot") resultRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    } catch (caught) {
      if (controller.current !== active || active.signal.aborted) return;
      setError(caught instanceof RequestTimeoutError
        ? "The comparison took too long. Your answers are still here; please try again."
        : caught instanceof ComparisonResponseError ? caught.message : UNAVAILABLE_MESSAGE);
    } finally {
      // A deadline must release the submit button; an older request must not
      // clear the busy state of the submission that replaced it.
      if (controller.current === active && !active.signal.aborted) {
        controller.current = null;
        setBusy(false);
      }
    }
  }

  function submitBallot(ballot: ScalarBallotState) {
    if (vote) void compare({ ballot, binary_vote: vote, ...(submission ? { scenario: submission.data.scenario } : {}) });
  }

  function changeScenario(scenario: ScalarScenario) {
    if (!submission || (busy && requestKind === "ballot")) return;
    if (!busy && !error && scenario === submission.data.scenario) return;
    // Use the submitted pair, including its explicit Yes/No answer. Draft
    // edits in the ballot form are independent until the visitor submits them.
    void compare({ ...submission.request, scenario }, "scenario");
  }

  const voteChanged = submission && vote !== submission.request.binary_vote;

  return <div className={styles.walkthrough}>
    {/* Part one: the ballot as it exists. Answer-sheet monochrome. */}
    <div className={styles.scantronZone}>
      <div className={styles.inner}>
        <section aria-labelledby={`${ballotId}-heading`}>
          <p className={styles.step}><span>01</span>The 2022 ballot</p>
          <div className={styles.sectionHeading}>
            <h2 id={`${ballotId}-heading`}>One policy question. How much can your answer say?</h2>
            <p>In 2022, Colorado voters were asked whether to reduce the statutory income tax rate from {rateText(TAX_MEASURE.statusQuo)} to {rateText(TAX_MEASURE.proposal)}. Answer that ballot question first, exactly as it was printed.</p>
          </div>
          <IncomeTaxBallot vote={vote} onVoteChange={setVote} />
        </section>
      </div>
    </div>

    {/* Part two: the ballot as it could be. Colour arrives with information. */}
    <div className={styles.richZone}>
      <div className={styles.spectrum} aria-hidden="true" />
      <div className={styles.inner}>
        <section aria-labelledby={`${ballotId}-richer`}>
          <p className={styles.step}><span>02</span>A richer ballot</p>
          <div className={styles.sectionHeading}>
            <h2 id={`${ballotId}-richer`}>Same question. Room to say how much.</h2>
          </div>
          <ScalarBallot onSubmitBallot={submitBallot} canSubmit={vote !== null} isSubmitting={busy} submittedBallot={submission?.request.ballot}
            context={<p>The 2022 ballot was binary. This experimental curve starts at the then-current statutory rate of {rateText(TAX_MEASURE.statusQuo)}. Shape it to show your ideal rate, what you would accept, and how quickly your support falls away.</p>}
            submissionHint={!vote ? "Choose Yes or No above, then shape your curve and compare." : voteChanged ? "Yes/no answer edited. The comparison still uses your submitted answers." : undefined} />
        </section>

        <section ref={resultRef} className={styles.comparison} aria-labelledby={`${ballotId}-results`}>
          <p className={styles.step}><span>03</span>Compare the results</p>
          <div className={styles.sectionHeading}>
            <h2 id={`${ballotId}-results`}>What becomes visible when a ballot says more?</h2>
            <p>Your two answers join 99 synthetic voters. Explore their different preferences and the yes/no answers they produce, then combine those same 100 ballots into a tax rate. These are illustrative outcomes, not the actual 2022 election results.</p>
          </div>
          {error && requestKind === "ballot" && <div className={styles.error} role="alert"><p>{error}</p><button type="button" disabled={busy} onClick={() => lastRequest && void compare(lastRequest)}>Retry submitted ballot</button></div>}
          {submission && requestKind === "ballot" && (busy || error) && <p role="status">{busy ? "Comparing your submitted answers. The results below still show your previous submission." : "The results below still show your previous submission."}</p>}
          {submission ? <ElectorateResults
            key={JSON.stringify({ ballot: submission.request.ballot, binary_vote: submission.request.binary_vote })}
            data={submission.data} ballot={submission.request.ballot}
            onScenarioChange={changeScenario}
            scenarioPending={busy && requestKind === "scenario" ? lastRequest?.scenario ?? "prepared" : null}
            scenarioError={requestKind === "scenario" ? error : null}
            scenarioDisabled={busy && requestKind === "ballot"}
            onRetryScenario={() => lastRequest && void compare(lastRequest, "scenario")}
          /> : <div className={styles.emptyState} role="status">{busy ? "Comparing your submitted ballot with the prepared electorate…" : "Submit your two answers above to reveal the comparison."}</div>}
        </section>
      </div>
    </div>
  </div>;
}
