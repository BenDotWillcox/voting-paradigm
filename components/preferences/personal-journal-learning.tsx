"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { JournalRequestError, requestJournal } from "./personal-journal-client";
import type { JournalEntry } from "@/lib/personal-journal-types";

type Revealed = Extract<JournalEntry, { status: "revealed" }>;
type Profile = { model: string; evidenceCount: number; facets: { label: string; evidenceIds: string[] }[] };
export type FollowUpResponse = { id: string; expectedRevision: number; expectedPrompt: string } &
  ({ action: "answer"; answer: string } | { action: "skip" });

// A confident miss gets priority over a tie-break. Correct but uncertain forecasts come next.
function priority(entry: Revealed) {
  if (entry.forecastMeasure || entry.followUpReviewed || (entry.followUp && entry.followUp.status !== "pending")) return 0;
  const probability = entry.prediction.probabilityYes;
  if (entry.vote !== entry.prediction.choice) return 1 + (entry.vote === "yes" ? 1 - probability : probability);
  return probability >= 0.4 && probability <= 0.6 ? 1 - Math.abs(0.5 - probability) : 0;
}

export function JournalLearning({ entries, disabled, onSelect, onFollowUp }: {
  entries: JournalEntry[]; disabled: boolean; onSelect: (id: string) => void; onFollowUp: (id: string) => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const completed = entries.filter((entry): entry is Revealed => entry.status === "revealed");
  const evidence = completed.map(entry => [entry.id, entry.revision ?? 0, entry.followUp?.status === "answered"].join("/")).sort().join("|");
  const next = completed.filter(entry => priority(entry) > 0).sort((a, b) =>
    priority(b) - priority(a) || b.votedAt.localeCompare(a.votedAt) || a.id.localeCompare(b.id))[0];
  useEffect(() => {
    if (!evidence) return;
    const controller = new AbortController();
    setFailed(false);
    setProfile(null);
    requestJournal<Profile>("GET", undefined, controller.signal, "/profile")
      .then(data => { if (!controller.signal.aborted) setProfile(data); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [evidence, retry]);

  if (!completed.length) return null;
  return (
    <div className="mb-6 grid items-start gap-3 sm:grid-cols-2">
      <details className="min-w-0 rounded-lg border bg-card p-4">
        <summary className="cursor-pointer font-semibold">
          Your preference profile <span className="ml-1 text-sm font-normal text-muted-foreground">({completed.length} {completed.length === 1 ? "decision" : "decisions"})</span>
        </summary>
        {failed
          ? <div role="alert" className="mt-3 space-y-2 text-sm"><p>The local profile could not be loaded.</p><Button variant="outline" size="sm" onClick={() => setRetry(count => count + 1)}>Retry profile</Button></div>
          : !profile ? <p role="status" className="mt-3 text-sm">Reading your decisions…</p>
          : <>
            <p className="mt-3 text-sm text-muted-foreground">These phrases come from your reasoning and saved follow-ups. Open a source to read what you said in context.</p>
            {profile.facets.length ? <ul className="mt-3 divide-y">
              {profile.facets.map(facet => <li key={facet.label} className="space-y-1 py-2">
                <div className="break-words text-sm font-medium">{facet.label}</div>
                {facet.evidenceIds.map(id => {
                  const source = completed.find(entry => entry.id === id);
                  return source && <button type="button" key={id} disabled={disabled} onClick={() => onSelect(id)}
                    className="block max-w-full break-words text-left text-xs text-muted-foreground underline underline-offset-2">{source.measure.title}</button>;
                })}
              </li>)}
            </ul> : <p className="mt-2 text-sm">There are no phrases to show yet.</p>}
          </>}
      </details>
      {next && <section aria-label="Next follow-up" className="min-w-0 rounded-lg border bg-muted/20 p-4">
        <h2 className="font-semibold">Next follow-up</h2>
        <p className="mt-1 break-words text-sm text-muted-foreground">{next.measure.title}</p>
        <Button size="sm" variant="outline" className="mt-3" disabled={disabled} onClick={() => onFollowUp(next.id)}>Open follow-up <ArrowRight aria-hidden="true" /></Button>
      </section>}
    </div>
  );
}

export function JournalFollowUp({ entry, busy, draft, onDraft, onSuggested, onRespond, onReload, reference, onSelect }: {
  entry: Revealed; busy: boolean; draft: string; onDraft: (text: string) => void;
  onSuggested: (entry: Revealed) => void; onRespond: (response: FollowUpResponse) => void; onReload: () => void;
  reference?: JournalEntry; onSelect: (id: string) => void;
}) {
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const followUp = entry.followUp;
  const shouldRequest = !followUp && priority(entry) > 0;
  const { id, revision = 0 } = entry;
  useEffect(() => {
    if (!shouldRequest) return;
    const controller = new AbortController();
    setError("");
    setConflict(false);
    requestJournal<{ entry: Revealed }>("POST", { action: "suggest", id, expectedRevision: revision }, controller.signal, "/follow-up")
      .then(({ entry: result }) => { if (!controller.signal.aborted) onSuggested(result); })
      .catch(cause => {
        if (controller.signal.aborted) return;
        setError(cause instanceof JournalRequestError ? cause.message : "The local follow-up could not be loaded.");
        setConflict(cause instanceof JournalRequestError && cause.status === 409);
      });
    return () => controller.abort();
  }, [id, revision, shouldRequest, retry, onSuggested]);

  if (!followUp && !shouldRequest) return null;
  if (!followUp) return <div className="border-t pt-4 text-sm">
    {error ? <div role="alert" className="space-y-2"><p>{error}</p>
      <Button size="sm" variant="outline" disabled={busy} onClick={conflict ? onReload : () => setRetry(count => count + 1)}>{conflict ? "Load saved entry" : "Retry follow-up"}</Button></div>
      : <p role="status">Choosing a follow-up…</p>}
  </div>;
  const { question, status } = followUp;
  const context = entry.prediction.probabilityYes === 0.5
    ? "The model gave both outcomes equal odds."
    : question.trigger === "miss" ? "The model predicted a different vote." : "The forecast was close to even.";
  const responseFields = { id, expectedRevision: revision, expectedPrompt: question.prompt };
  function answer(event: FormEvent) {
    event.preventDefault();
    if (draft.trim()) onRespond({ ...responseFields, action: "answer", answer: draft.trim() });
  }
  return <section aria-label="Follow-up question" className="space-y-3 rounded-lg border bg-muted/25 p-4 sm:p-5">
    <h3 className="font-semibold">Follow-up question</h3>
    <p className="text-sm text-muted-foreground">{context}</p>
    <p id="journal-question" className="break-words font-medium">{question.prompt}</p>
    {reference && <button type="button" disabled={busy} onClick={() => onSelect(reference.id)}
      className="block max-w-full break-words text-left text-sm text-muted-foreground underline underline-offset-2">Read the earlier entry · {reference.measure.title}</button>}
    {status === "pending" ? <form onSubmit={answer}>
      <fieldset disabled={busy} className="space-y-3">
        <Textarea aria-labelledby="journal-question" name="clarification" maxLength={10000} required value={draft}
          onChange={event => onDraft(event.target.value)} className="min-h-24" />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!draft.trim()}>Save answer</Button>
          <Button type="button" variant="outline" disabled={!!draft.trim()} title={draft.trim() ? "Clear your draft to skip the question" : undefined}
            onClick={() => onRespond({ ...responseFields, action: "skip" })}>Skip question</Button>
        </div>
      </fieldset>
    </form> : status === "answered" ? <div className="border-t pt-3">
      <h4 className="text-sm font-semibold">Your saved answer</h4>
      <p className="mt-1 whitespace-pre-wrap break-words text-sm">{followUp.answer}</p>
    </div> : <p className="text-sm text-muted-foreground">You skipped this question.</p>}
  </section>;
}
