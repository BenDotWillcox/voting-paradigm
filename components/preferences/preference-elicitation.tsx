"use client";

import { useEffect, useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SpectrumAnswer } from "@/components/preferences/spectrum-answer";
import { replaceReviewedResponse } from "@/lib/preferences/elicitation-navigation";
import {
  emptySpectrumDraft, formatSpectrumValue, formatSpectrumUncertainty, type SpectrumDraft,
} from "@/lib/preferences/spectrum";
import {
  acceptableRangeSchema, elicitationEventSchema, elicitationRequestSchema,
  elicitationResponseSchema, reportedUncertaintySchema, SPECTRUM_BANK_VERSION,
  spectrumEventMatchesQuestion, type ElicitationEvent, type ElicitationResponse,
} from "@/lib/validations/elicitation-schemas";

const formSchema = z.object({
  drafts: z.array(z.object({
    position: z.number().finite().nullable(),
    reported_uncertainty: reportedUncertaintySchema.nullable(),
    acceptable_range: acceptableRangeSchema.nullable(),
  })),
});

function ResponseSummary({ session, onEdit, disabled }: {
  session: ElicitationResponse; onEdit: (index: number) => void; disabled: boolean;
}) {
  return (
    <ol className="divide-y border-y">
      {session.questions.map((question, index) => {
        const response = session.responses[index];
        return (
          <li key={question.id} className="py-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-medium">{question.title}</h3>
              {index <= session.n_reviewed && (
                <Button type="button" variant="link" disabled={disabled}
                  aria-label={`${response ? "Edit" : "Answer"} ${question.title}`}
                  onClick={() => onEdit(index)}>
                  {response ? "Edit" : "Answer"}
                </Button>
              )}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{question.prompt}</p>
            {!response ? <p className="mt-3 text-sm">Not answered.</p>
              : response.action !== "answer" ? (
                <p className="mt-3 text-sm">
                  {response.action === "skip" ? "Skipped." : "Depends / hard to place."} No numeric position recorded.
                </p>
              ) : (
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
                  <div><dt className="text-muted-foreground">Your position</dt>
                    <dd className="mt-1 font-medium">{formatSpectrumValue(response.position, question.scale)}</dd></div>
                  <div><dt className="text-muted-foreground">Reported uncertainty</dt>
                    <dd className="mt-1 font-medium">
                      {response.reported_uncertainty === null ? "Not provided" :
                        formatSpectrumUncertainty(response.reported_uncertainty)}
                    </dd></div>
                  <div><dt className="text-muted-foreground">Acceptable range</dt>
                    <dd className="mt-1 font-medium">
                      {response.acceptable_range === null ? "Not provided" :
                        formatSpectrumValue(response.acceptable_range.lower, question.scale) + " – " +
                        formatSpectrumValue(response.acceptable_range.upper, question.scale)}
                    </dd></div>
                </dl>
              )}
          </li>
        );
      })}
    </ol>
  );
}

export function PreferenceElicitation() {
  const [session, setSession] = useState<ElicitationResponse | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [showSummary, setShowSummary] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const questionHeadingRefs = useRef<Array<HTMLHeadingElement | null>>([]);
  const summaryHeadingRef = useRef<HTMLHeadingElement>(null);
  const form = useForm<{ drafts: SpectrumDraft[] }>({
    resolver: zodResolver(formSchema),
    defaultValues: { drafts: [] },
  });
  const drafts = form.watch("drafts");

  useEffect(() => () => activeRequest.current?.abort(), []);
  useEffect(() => {
    (showSummary ? summaryHeadingRef.current : questionHeadingRefs.current[questionIndex])?.focus();
  }, [session, questionIndex, showSummary]);

  async function review(responses: ElicitationEvent[], recordedIndex?: number) {
    if (activeRequest.current) return;
    const input = elicitationRequestSchema.safeParse({
      bank_version: SPECTRUM_BANK_VERSION, responses,
    });
    if (!input.success) {
      setError("This answer is incomplete. Check the controls before recording it.");
      return;
    }
    const controller = new AbortController();
    activeRequest.current = controller;
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/preferences/elicitation", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input.data), cache: "no-store", signal: controller.signal,
      });
      if (!response.ok) throw new Error("Session unavailable");
      const result = elicitationResponseSchema.parse(await response.json());
      if (JSON.stringify(result.responses) !== JSON.stringify(input.data.responses) ||
        (session && JSON.stringify(result.questions) !== JSON.stringify(session.questions))) {
        throw new Error("Session changed");
      }
      if (controller.signal.aborted) return;
      if (!session) {
        form.reset({ drafts: result.questions.map(() => emptySpectrumDraft()) });
      }
      setSession(result);
      setQuestionIndex(recordedIndex === undefined ? 0 : Math.min(recordedIndex + 1, result.target_questions - 1));
      setShowSummary(recordedIndex === result.target_questions - 1);
    } catch {
      if (!controller.signal.aborted) {
        setError("The session could not be updated. Your change was not recorded. Recorded responses and your current controls are unchanged; please try again.");
      }
    } finally {
      if (!controller.signal.aborted) {
        activeRequest.current = null;
        setPending(false);
      }
    }
  }

  function restart() {
    if (activeRequest.current) return;
    setSession(null);
    setQuestionIndex(0);
    setShowSummary(false);
    form.reset({ drafts: [] });
    setError(null);
  }

  function goToQuestion(index: number) {
    if (!session || activeRequest.current || index < 0 ||
      index > session.n_reviewed || index >= session.target_questions) return;
    setQuestionIndex(index);
    setShowSummary(false);
    setError(null);
  }

  function recordAnswer(index: number, value: SpectrumDraft) {
    const question = session?.questions[index];
    if (!session || !question || activeRequest.current || index !== questionIndex) return;
    const event = elicitationEventSchema.safeParse({
      action: "answer", question_id: question.id, question_version: question.version, ...value,
    });
    if (!event.success || !spectrumEventMatchesQuestion(event.data, question)) {
      setError("Choose a position on this question’s scale before recording it.");
      return;
    }
    void review(replaceReviewedResponse(session.responses, index, event.data), index);
  }

  function recordNonAnswer(index: number, action: "skip" | "depends") {
    const question = session?.questions[index];
    if (!session || !question || activeRequest.current || index !== questionIndex) return;
    void review(replaceReviewedResponse(session.responses, index, {
      action, question_id: question.id, question_version: question.version,
    }), index);
  }

  return (
    <section aria-label="Spectrum preference session" className="space-y-6">
      {!session ? (
        <div className="space-y-5 border-y py-6">
          <h2 className="text-xl font-semibold">Try four everyday civic choices</h2>
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Each hypothetical question changes one quantity. Choose a position,
            optionally describe your uncertainty, and add a range you could accept.
            You can skip, say it depends, or review your answers at any point.
          </p>
          <Button size="lg" disabled={pending} onClick={() => void review([])}>
            {pending ? "Opening questions…" : error ? "Try again" : "Explore the questions"}
          </Button>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {session.n_reviewed} of {session.target_questions} reviewed · {session.n_answered} answered
              {" · "}{session.n_skipped} skipped · {session.n_depends} depends
            </p>
            <div className="flex items-center gap-2">
              {!showSummary && (
                <div role="group" aria-label="Question navigation" className="flex items-center gap-1">
                  <Button type="button" variant="outline" size="icon" className="size-11"
                    aria-label="Previous question" title="Previous question"
                    disabled={pending || questionIndex === 0}
                    onClick={() => goToQuestion(questionIndex - 1)}>
                    <ArrowLeft aria-hidden="true" />
                  </Button>
                  <Button type="button" variant="outline" size="icon" className="size-11"
                    aria-label="Next question" title="Next question"
                    disabled={pending || !session.responses[questionIndex] ||
                      questionIndex === session.target_questions - 1}
                    onClick={() => goToQuestion(questionIndex + 1)}>
                    <ArrowRight aria-hidden="true" />
                  </Button>
                </div>
              )}
              <Button type="button" variant="ghost" className="min-h-11" disabled={pending}
                onClick={restart}>Start again</Button>
            </div>
          </div>
          <progress value={session.n_reviewed} max={session.target_questions}
            aria-label="Questions reviewed" className="h-2 w-full accent-primary" />

          {showSummary && (
            <div className="space-y-5">
              <div>
                <h2 ref={summaryHeadingRef} tabIndex={-1} className="text-2xl font-semibold focus:outline-none">
                  What you told us
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  These are your recorded answers, not inferred preferences or model estimates.
                  Unanswered questions and omitted details stay unknown.
                </p>
              </div>
              <ResponseSummary session={session} onEdit={goToQuestion} disabled={pending} />
              <p className="text-sm text-muted-foreground">
                Unrecorded edits are excluded from this summary. Your controls are still there when you return.
              </p>
              <Button disabled={pending} onClick={() => goToQuestion(questionIndex)}>
                Back to question {questionIndex + 1}
              </Button>
            </div>
          )}
          {/* Keep each graph mounted so omitted widths, preview bounds, and fine-input drafts survive navigation. */}
          {session.questions.map((question, index) => (
            <form key={question.id} hidden={showSummary || index !== questionIndex} className="space-y-6"
              onSubmit={form.handleSubmit(({ drafts: answers }) => recordAnswer(index, answers[index]))}>
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Question {index + 1} of {session.target_questions} · {question.title}
                </p>
                <h2 ref={(element) => { questionHeadingRefs.current[index] = element; }} tabIndex={-1}
                  className="text-xl font-semibold focus:outline-none">
                  {question.prompt}
                </h2>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{question.context}</p>
                {session.responses[index] && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    {session.responses[index].action === "skip" ? "Recorded as skipped." :
                      session.responses[index].action === "depends" ? "Recorded as depends / hard to place." :
                      "A position is already recorded."}
                    {" "}Moving between questions keeps that response until you record a change.
                  </p>
                )}
              </div>
              <Controller name={`drafts.${index}`} control={form.control} render={({ field }) => (
                <SpectrumAnswer question={question}
                  draft={field.value} onChange={field.onChange} disabled={pending} />
              )} />
              <div className="flex flex-wrap gap-3">
                <Button type="submit" size="lg" disabled={pending || drafts[index]?.position === null}>
                  {pending ? "Recording…" : session.responses[index] ? "Update recorded position" : "Record this position"}
                </Button>
                <Button type="button" variant="outline" disabled={pending}
                  onClick={() => recordNonAnswer(index, "depends")}>Depends / hard to place</Button>
                <Button type="button" variant="ghost" disabled={pending}
                  onClick={() => recordNonAnswer(index, "skip")}>Skip</Button>
              </div>
              <div className="border-t pt-4">
                <Button type="button" variant="link" className="px-0" disabled={pending}
                  onClick={() => setShowSummary(true)}>Review recorded answers</Button>
              </div>
            </form>
          ))}
        </>
      )}

      {error && <p role="alert" className="rounded-md border border-destructive p-4 text-sm">{error}</p>}
      <p role="status" className="sr-only">{pending ? "Updating the session." : ""}</p>
      <p className="border-t pt-4 text-xs leading-relaxed text-muted-foreground">
        No saved session: answers stay in this page’s memory and are sent to the
        app’s Python service for validation, without database or browser-storage
        persistence. Refreshing or starting again clears them. No LLM is called,
        and no preference model is updated.
      </p>
    </section>
  );
}
