"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight, BookOpen, LockKeyhole, Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { JournalRequestError, requestJournal } from "./personal-journal-client";
import { JournalFollowUp, JournalLearning, type FollowUpResponse } from "./personal-journal-learning";
import { FiveMeasureCheck, PairedPredictions, hasPairedForecasts } from "./personal-journal-check";
import type { JournalCheck, JournalEntry } from "@/lib/personal-journal-types";

type Measure = JournalEntry["measure"];
type Revealed = Extract<JournalEntry, { status: "revealed" }>;
type Vote = Revealed["vote"];
type VoteInput = { id: string; vote: Vote; reasoning: string; expectedRevision: number };
type LockInput = { id: string; measure: Measure; checkId?: string };
type JournalState = { entries: JournalEntry[]; check: JournalCheck | null };
type CorrectionInput = {
  id: string; measure: Measure; expectedRevision: number; expectedStatus: JournalEntry["status"]; confirmVote?: true;
};
const labelVote = (vote: Vote) => vote === "yes" ? "Yes" : "No";
const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const timestamp = (value: string) => <time dateTime={value}>{dateTime.format(new Date(value))}</time>;

function MeasureForm({ busy, entry, nextSlot, onSave, onCancel }: {
  busy: boolean; entry?: JournalEntry; nextSlot?: number; onSave: (measure: Measure, confirmed: boolean) => void; onCancel?: () => void;
}) {
  const id = entry ? "edit" : "measure";
  const current = entry?.measure;
  const [familiarity, setFamiliarity] = useState(current?.familiar);
  const paired = !!entry?.checkId || (!!nextSlot && familiarity === false);
  const lockLabel = paired ? "Lock comparison forecasts" : "Lock prediction";
  const submitLabel = entry?.status === "revealed" ? "Save correction" : entry ? (paired ? "Save and lock forecasts" : "Save and lock prediction") : lockLabel;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const read = (name: string) => String(fields.get(name) ?? "").trim();
    const measure = {
      title: read("title"), sourceUrl: read("sourceUrl"), text: read("text"),
      yesMeaning: read("yesMeaning"), noMeaning: read("noMeaning"), familiar: read("familiar") === "yes",
    };
    for (const name of ["title", "text", "yesMeaning", "noMeaning"] as const) {
      if (measure[name]) continue;
      const field = form.elements.namedItem(name) as HTMLInputElement | HTMLTextAreaElement;
      field.setCustomValidity("Enter text for this field.");
      field.reportValidity();
      return;
    }
    onSave(measure, fields.get("confirmVote") === "on");
  }

  return (
    <form onSubmit={submit} onInput={(event) => {
      const field = event.target;
      if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) field.setCustomValidity("");
    }}>
      <fieldset disabled={busy} className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor={id + "-title"}>Measure title</Label>
          <Input id={id + "-title"} defaultValue={current?.title} name="title" required maxLength={300} />
        </div>
        <div className="space-y-2">
          <Label htmlFor={id + "-source"}>Source URL</Label>
          <Input id={id + "-source"} defaultValue={current?.sourceUrl} type="url" name="sourceUrl" required maxLength={2048} pattern="https?://.+" title="Enter an http:// or https:// URL." placeholder="https://" />
        </div>
        <div className="space-y-2">
          <Label htmlFor={id + "-text"}>Ballot text</Label>
          <p id={id + "-help"} className="text-sm text-muted-foreground">Use the wording of the measure itself. Record your own opinion in the voting step.</p>
          <Textarea id={id + "-text"} defaultValue={current?.text} name="text" aria-describedby={id + "-help"} required maxLength={30000} className="min-h-32" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor={id + "-yes"}>What a yes vote means</Label>
            <Textarea id={id + "-yes"} defaultValue={current?.yesMeaning} name="yesMeaning" required maxLength={3000} />
          </div>
          <div className="space-y-2">
            <Label htmlFor={id + "-no"}>What a no vote means</Label>
            <Textarea id={id + "-no"} defaultValue={current?.noMeaning} name="noMeaning" required maxLength={3000} />
          </div>
        </div>
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Had you seen this measure before this entry?</legend>
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
            <label className="flex min-h-8 items-center gap-2"><input required type="radio" name="familiar" value="no" defaultChecked={current?.familiar === false} onChange={() => setFamiliarity(false)} /> New to me</label>
            <label className="flex min-h-8 items-center gap-2"><input required type="radio" name="familiar" value="yes" defaultChecked={current?.familiar === true} onChange={() => setFamiliarity(true)} /> Familiar to me</label>
          </div>
          {nextSlot && <p className="mt-2 text-sm text-muted-foreground">{familiarity === true
            ? "This familiar measure will be saved as a regular journal entry outside the check."
            : `A measure that is new to you will fill slot ${nextSlot} of 5 in the check.`}</p>}
        </fieldset>
        {entry?.status === "revealed" && (
          <div className="space-y-3 rounded-md border bg-muted/25 p-4">
            <p className="text-sm font-semibold">Your recorded vote was {labelVote(entry.vote)}.</p>
            <p className="whitespace-pre-wrap break-words text-sm">{entry.reasoning}</p>
            {entry.followUp?.status === "answered" && <p className="text-sm text-muted-foreground">
              Changing this measure will archive your follow-up answer with the original wording and remove that answer from future forecasts.
            </p>}
            <label className="flex items-start gap-2 text-sm font-medium">
              <input type="checkbox" name="confirmVote" required className="mt-1" />
              My recorded vote and reasoning still apply to the corrected measure.
            </label>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="lg">{entry?.status !== "revealed" && <LockKeyhole aria-hidden="true" />}{busy ? "Saving…" : submitLabel}</Button>
          {onCancel && <Button type="button" size="lg" variant="outline" onClick={onCancel}>Cancel</Button>}
        </div>
      </fieldset>
    </form>
  );
}

function BallotPacket({ measure, showTitle = false }: { measure: Measure; showTitle?: boolean }) {
  return (
    <div className="space-y-4 rounded-lg border bg-muted/25 p-4 sm:p-5">
      {showTitle && <h4 className="break-words font-semibold">{measure.title}</h4>}
      <p className="whitespace-pre-wrap break-words leading-relaxed">{measure.text}</p>
      <dl className="grid gap-3 border-t pt-3 text-sm sm:grid-cols-2">
        <div><dt className="font-semibold">A yes vote</dt><dd className="mt-1 whitespace-pre-wrap break-words">{measure.yesMeaning}</dd></div>
        <div><dt className="font-semibold">A no vote</dt><dd className="mt-1 whitespace-pre-wrap break-words">{measure.noMeaning}</dd></div>
      </dl>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <a href={measure.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline underline-offset-2">
          Open source <ArrowUpRight aria-hidden="true" className="size-3" />
        </a>
        <span>{measure.familiar ? "Familiar measure" : "New to you"}</span>
      </div>
    </div>
  );
}

function VoteForm({ entry, busy, onVote }: { entry: JournalEntry; busy: boolean; onVote: (input: VoteInput) => void }) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const vote = data.get("vote");
    const reasoning = String(data.get("reasoning") ?? "").trim();
    if (!reasoning) {
      const field = form.elements.namedItem("reasoning") as HTMLTextAreaElement;
      field.setCustomValidity("Enter your reason for this vote.");
      field.reportValidity();
      return;
    }
    if (vote === "yes" || vote === "no") onVote({ id: entry.id, expectedRevision: entry.revision ?? 0, vote, reasoning });
  }

  return (
    <form onSubmit={submit}>
      <fieldset disabled={busy} className="space-y-5">
        <fieldset>
          <legend className="mb-3 font-semibold">How would you vote?</legend>
          <div className="grid grid-cols-2 gap-3">
            {(["yes", "no"] as const).map((value) => (
              <label key={value} className="flex min-h-12 cursor-pointer items-center gap-3 rounded-md border px-4 font-medium has-checked:border-foreground has-checked:bg-muted">
                <input required type="radio" name="vote" value={value} /> {labelVote(value)}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="space-y-2">
          <Label htmlFor="vote-reason">Why did you choose this vote?</Label>
          <Textarea id="vote-reason" name="reasoning" required maxLength={10000} className="min-h-24" onInput={(event) => event.currentTarget.setCustomValidity("")} />
        </div>
        <Button type="submit" size="lg">{busy ? "Recording vote…" : entry.checkId ? "Record vote and reveal forecasts" : "Record vote and reveal prediction"}</Button>
      </fieldset>
    </form>
  );
}

function Comparison({ entry }: { entry: Revealed }) {
  const { prediction, forecastMeasure } = entry;
  const probability = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 }).format(prediction.probabilityYes);
  return (
    <div className="space-y-5">
      {hasPairedForecasts(entry) ? <PairedPredictions entry={entry} /> : <section aria-label="Vote comparison" className="rounded-lg border border-foreground/20 p-4 sm:p-5">
        <h3 className="font-semibold">{forecastMeasure ? "Prediction for the original wording" :
          entry.vote === prediction.choice ? "The prediction matched your vote" : "You and the model chose differently"}</h3>
        {forecastMeasure && <p className="mt-2 text-sm text-muted-foreground">You corrected the measure after revealing this prediction. Future forecasts can use the corrected entry.</p>}
        <dl className="mt-4 grid grid-cols-2 gap-4 border-y py-4">
          <div><dt className="text-sm text-muted-foreground">Your vote</dt><dd className="text-3xl font-serif">{labelVote(entry.vote)}</dd></div>
          <div><dt className="text-sm text-muted-foreground">Locked prediction</dt><dd className="text-3xl font-serif">{labelVote(prediction.choice)}</dd></div>
        </dl>
        <p className="mt-3 text-sm"><strong>{probability}</strong> estimated chance you would vote yes.</p>
        <p className="mt-1 break-words text-xs text-muted-foreground">{prediction.model} · {prediction.historyCount} prior {prediction.historyCount === 1 ? "entry" : "entries"} used</p>
      </section>}
      <section><h3 className="font-semibold">Your reasoning</h3><p className="mt-2 whitespace-pre-wrap break-words">{entry.reasoning}</p></section>
      {!entry.comparison && <section><h3 className="font-semibold">The model’s explanation</h3><p className="mt-2 whitespace-pre-wrap break-words">{prediction.explanation}</p></section>}
      <p className="text-xs text-muted-foreground">{entry.comparison ? "Forecasts" : "Prediction"} locked {timestamp(entry.lockedAt)}. Vote recorded {timestamp(entry.votedAt)}.</p>
      <details><summary className="cursor-pointer py-1 text-sm font-medium">{forecastMeasure ? "Review the corrected measure" : "Review the measure"}</summary>
        <div className="mt-2"><BallotPacket measure={entry.measure} showTitle={!!forecastMeasure} /></div>
      </details>
      {forecastMeasure && <details><summary className="cursor-pointer py-1 text-sm font-medium">Review the wording used for the prediction</summary>
        <div className="mt-2"><BallotPacket measure={forecastMeasure} showTitle /></div>
        {entry.archivedFollowUp?.status === "answered" && <section className="mt-3 space-y-2 rounded-lg border p-4 text-sm">
          <h4 className="font-semibold">Archived follow-up for this wording</h4>
          <p className="break-words">{entry.archivedFollowUp.question.prompt}</p>
          <p className="whitespace-pre-wrap break-words"><strong>Your answer</strong><br />{entry.archivedFollowUp.answer}</p>
          <p className="text-muted-foreground">This answer was retired from the preference profile when you corrected the measure.</p>
        </section>}
      </details>}
    </div>
  );
}

export function PersonalBallotJournal() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [check, setCheck] = useState<JournalCheck | null>(null);
  const [startError, setStartError] = useState("");
  const [pairedDraft, setPairedDraft] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [editing, setEditing] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");
  const [draftVersion, setDraftVersion] = useState(0);
  const [answerDrafts, setAnswerDrafts] = useState<Record<string, string>>({});
  const draftId = useRef<string | null>(null);
  const hasRequest = useRef(false);
  const focusDetail = useRef(false);
  const focusQuestion = useRef(false);
  const questionSection = useRef<HTMLDivElement>(null);
  const detail = useRef<HTMLHeadingElement>(null);
  const ordered = [...entries].sort((a, b) => b.lockedAt.localeCompare(a.lockedAt) || b.id.localeCompare(a.id));
  const selected = entries.find((entry) => entry.id === selectedId);
  const nextSlot = check?.slotIds.find(id => !entries.some(entry => entry.id === id));
  const answerKey = selected ? selected.id + "/" + (selected.revision ?? 0) : "";

  function updateAnswerDraft(key: string, value: string) {
    setAnswerDrafts(previous => {
      const drafts = { ...previous };
      if (value) drafts[key] = value;
      else delete drafts[key];
      return drafts;
    });
  }
  const hasUnsavedAnswer = Object.keys(answerDrafts).length > 0;
  useEffect(() => {
    if (!hasUnsavedAnswer) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasUnsavedAnswer]);

  const addSuggestion = useCallback((result: Revealed) => {
    setEntries(previous => previous.map(row =>
      row.id === result.id && row.status === "revealed" && (row.revision ?? 0) === (result.revision ?? 0) && !row.followUp
        ? result : row));
  }, []);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setLoadError(false);
    try {
      const response = await requestJournal<JournalState>("GET", undefined, signal);
      if (signal?.aborted) return;
      setEntries(response.entries);
      setCheck(response.check ?? null);
      const latestPending = response.entries.filter((entry) => entry.status === "locked")
        .sort((a, b) => b.lockedAt.localeCompare(a.lockedAt))[0];
      setSelectedId(latestPending?.id ?? null);
    } catch {
      if (!signal?.aborted) setLoadError(true);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (focusDetail.current) {
      (focusQuestion.current ? questionSection.current : detail.current)?.focus();
      focusQuestion.current = false;
      focusDetail.current = false;
    }
  }, [selectedId, selected?.status, editing]);

  function navigate(id: string | null, toQuestion = false) {
    if (id === selectedId) {
      (toQuestion ? questionSection.current : detail.current)?.focus();
      return;
    }
    focusQuestion.current = toQuestion;
    focusDetail.current = true;
    setSelectedId(id);
    setError("");
    setConflict(false);
    setSavedMessage("");
  }

  function toggleEditor(open: boolean) {
    focusDetail.current = true;
    setEditing(open);
    setError("");
    setConflict(false);
    setSavedMessage("");
  }

  async function startCheck() {
    if (hasRequest.current) return;
    hasRequest.current = true;
    setBusy(true);
    setStartError("");
    try {
      const result = await requestJournal<{ check: JournalCheck }>("POST", {}, undefined, "/check");
      setCheck(result.check);
    } catch (cause) {
      setStartError(cause instanceof JournalRequestError ? cause.message : "Could not start the check. Please try again.");
    } finally {
      hasRequest.current = false;
      setBusy(false);
    }
  }

  async function reloadSavedEntry() {
    if (hasRequest.current) return;
    hasRequest.current = true;
    setBusy(true);
    try {
      const response = await requestJournal<JournalState>("GET");
      setEntries(response.entries);
      setCheck(response.check ?? null);
      if (selectedId === null) {
        draftId.current = null;
        setError("");
        setConflict(false);
        setSavedMessage("Journal refreshed. Your measure draft is still here.");
      } else {
        updateAnswerDraft(answerKey, "");
        toggleEditor(false);
      }
    } catch {
      setError("The latest entry could not be loaded. Your inputs are still here.");
    } finally {
      hasRequest.current = false;
      setBusy(false);
    }
  }

  async function save(method: "POST" | "PUT" | "PATCH" | "FOLLOW_UP", body: LockInput | VoteInput | CorrectionInput | FollowUpResponse) {
    if (hasRequest.current) return;
    hasRequest.current = true;
    setBusy(true);
    setError("");
    setSavedMessage("");
    setConflict(false);
    try {
      const { entry } = method === "FOLLOW_UP"
        ? await requestJournal<{ entry: JournalEntry }>("POST", body, undefined, "/follow-up")
        : await requestJournal<{ entry: JournalEntry }>(method, body);
      setEntries((previous) => [...previous.filter((row) => row.id !== entry.id), entry]);
      focusDetail.current = true;
      setSelectedId(entry.id);
      if (method === "PATCH") {
        updateAnswerDraft(answerKey, "");
        setEditing(false);
        setSavedMessage(entry.status === "locked" ? "Correction saved. The prediction is locked." : "Correction saved.");
      }
      if (method === "FOLLOW_UP") {
        updateAnswerDraft(answerKey, "");
        setSavedMessage(entry.status === "revealed" && entry.followUp?.status === "answered"
          ? "Answer saved for future forecasts." : "Question skipped.");
      }
      if (method === "POST") {
        draftId.current = null;
        setPairedDraft(false);
        setDraftVersion((previous) => previous + 1);
      }
    } catch (cause) {
      setConflict(cause instanceof JournalRequestError && cause.status === 409);
      setError(cause instanceof Error && !(cause instanceof TypeError)
        ? cause.message
        : "Could not reach the journal. Your inputs are still here. Check the local server and try again.");
    } finally {
      hasRequest.current = false;
      setBusy(false);
    }
  }

  function lockMeasure(measure: Measure) {
    if (!measure.familiar && check && nextSlot) {
      setPairedDraft(true);
      void save("POST", { id: nextSlot, checkId: check.id, measure });
      return;
    }
    if (!measure.familiar && pairedDraft) {
      setError("All five slots have been used. Choose how to save this draft below.");
      return;
    }
    draftId.current ??= crypto.randomUUID();
    void save("POST", { id: draftId.current, measure });
  }

  if (loading) return <p role="status" className="border-t py-6 text-muted-foreground">Opening your journal…</p>;
  if (loadError) return (
    <div className="space-y-3 border-t py-6"><p role="alert">Could not open the local journal. Check that the journal server is running.</p>
      <Button variant="outline" onClick={() => void load()}>Try again</Button>
    </div>
  );

  return (
    <div className="border-t pt-6">
    {selected?.status !== "locked" && !editing && <JournalLearning entries={entries} disabled={busy}
      onSelect={id => navigate(id)} onFollowUp={id => navigate(id, true)} />}
    {selected?.status !== "locked" && !editing && <>
      <FiveMeasureCheck check={check} entries={entries} busy={busy} onStart={() => void startCheck()} />
      {startError && <p role="alert" className="mb-4 text-sm text-destructive">{startError}</p>}
    </>}
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(14rem,0.7fr)_minmax(0,1.8fr)]">
      <aside aria-labelledby="entries-heading" className="min-w-0 rounded-lg border bg-muted/20 p-4">
        <div className="mb-3 flex items-center gap-2">
          <BookOpen aria-hidden="true" className="size-4 text-muted-foreground" />
          <h2 id="entries-heading" className="font-semibold">Your entries <span className="ml-1 text-sm font-normal text-muted-foreground">({entries.length})</span></h2>
        </div>
        <Button variant="outline" disabled={busy || editing} className="w-full justify-start bg-background" onClick={() => navigate(null)}><Plus aria-hidden="true" />New measure</Button>
        {entries.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">Lock your first prediction to create an entry.</p>
        ) : (
          <ul className="mt-3 divide-y">
            {ordered.map((entry) => (
              <li key={entry.id}>
                <button type="button" disabled={busy || editing} aria-current={selectedId === entry.id ? "true" : undefined}
                  onClick={() => navigate(entry.id)}
                  className="block w-full rounded-sm px-2 py-3 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring aria-current:bg-muted">
                  <span className="block break-words text-sm font-medium">{entry.measure.title}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">{entry.checkId && "Five-measure check · "}{entry.status === "locked" ? "Awaiting your vote" : "Vote recorded"} · {timestamp(entry.lockedAt)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <section aria-labelledby="journal-detail" aria-busy={busy} className="min-w-0 space-y-5 rounded-lg border bg-card p-5 sm:p-7">
        <div>
          {selected && <p className="mb-2 text-sm font-medium text-muted-foreground">{selected.checkId && "Five-measure check · "}{selected.status === "locked" ? "Awaiting your vote" : "Completed entry"}</p>}
          <h2 id="journal-detail" ref={detail} tabIndex={-1} className="break-words font-serif text-3xl tracking-tight">
            {editing ? "Edit measure" : selected ? selected.measure.title : "Add a measure"}
          </h2>
          {editing && <p className="mt-2 text-sm text-muted-foreground">{selected?.status === "locked"
            ? "Saving a correction locks a prediction based on the updated measure. You can then record your vote."
            : "The prediction you saw belongs to the original wording. Correct this entry if the same vote and reasoning still apply."}</p>}
          {selected?.status === "locked" && !editing && <p className="mt-2 text-sm text-muted-foreground">Locked {timestamp(selected.lockedAt)}. Record your decision to reveal {selected.checkId ? "the comparison forecasts" : "the prediction"}.</p>}
          {!selected && <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            Future forecasts can draw on your earlier votes, written reasons, and follow-up answers. Your first forecast starts at equal odds.
          </p>}
        </div>
        {error && <div role="alert" className="space-y-3 rounded-md border border-destructive/40 p-3 text-sm">
          <p className="text-destructive">{error}</p>
          {conflict && <Button type="button" variant="outline" disabled={busy} onClick={() => void reloadSavedEntry()}>{selected ? "Discard draft and load saved entry" : "Refresh check and keep draft"}</Button>}
        </div>}
        {savedMessage && <p role="status" className="text-sm font-medium">{savedMessage}</p>}
        {selected && !editing && <Button type="button" variant="outline" disabled={busy || !!answerDrafts[answerKey]}
          title={answerDrafts[answerKey] ? "Save or clear your follow-up draft before editing the measure" : undefined} onClick={() => toggleEditor(true)}>
          <Pencil aria-hidden="true" /> Edit measure
        </Button>}
        <div hidden={!!selected}>
          {pairedDraft && !nextSlot && <div className="mb-4 space-y-2 rounded-md border p-3 text-sm">
            <p>The check is full. You can still save this measure outside it.</p>
            <Button variant="outline" disabled={busy} onClick={() => { setPairedDraft(false); setError(""); }}>Use regular journal for this draft</Button>
          </div>}
          <MeasureForm key={draftVersion} busy={busy} nextSlot={check && nextSlot ? check.slotIds.indexOf(nextSlot) + 1 : undefined} onSave={lockMeasure} />
        </div>
        {selected && editing && (
          <MeasureForm key={selected.id} entry={selected} busy={busy} onCancel={() => toggleEditor(false)} onSave={(measure, confirmed) =>
            void save("PATCH", {
              id: selected.id, measure, expectedRevision: selected.revision ?? 0, expectedStatus: selected.status,
              ...(confirmed ? { confirmVote: true } : {}),
            })} />
        )}
        {selected?.status === "locked" && <div hidden={editing} className="space-y-5">
          <BallotPacket measure={selected.measure} />
          <VoteForm key={selected.id + "-" + (selected.revision ?? 0)} entry={selected} busy={busy} onVote={(input) => void save("PUT", input)} />
        </div>}
        {selected?.status === "revealed" && !editing && <>
          <Comparison entry={selected} />
          <div ref={questionSection} tabIndex={-1}>
            <JournalFollowUp key={answerKey} entry={selected} busy={busy} draft={answerDrafts[answerKey] ?? ""}
              onDraft={text => updateAnswerDraft(answerKey, text)} onSuggested={addSuggestion}
              reference={entries.find(entry => entry.id === selected.followUp?.question.referenceId)} onSelect={id => navigate(id)}
              onRespond={response => void save("FOLLOW_UP", response)} onReload={() => void reloadSavedEntry()} />
          </div>
        </>}
      </section>
    </div>
    </div>
  );
}
