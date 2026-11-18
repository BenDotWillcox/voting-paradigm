"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight, BookOpen, LockKeyhole, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { JournalEntry } from "@/lib/personal-journal-types";

type Measure = JournalEntry["measure"];
type Revealed = Extract<JournalEntry, { status: "revealed" }>;
type Vote = Revealed["vote"];
type VoteInput = { id: string; vote: Vote; reasoning: string };
const endpoint = "/api/preferences/journal";
const labelVote = (vote: Vote) => vote === "yes" ? "Yes" : "No";
const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const timestamp = (value: string) => <time dateTime={value}>{dateTime.format(new Date(value))}</time>;

async function requestJournal<T>(method: "GET" | "POST" | "PUT", body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(endpoint, {
    method,
    cache: "no-store",
    signal,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.error === "string" ? data.error : "The local journal is unavailable. Please try again.");
  }
  return response.json() as Promise<T>;
}

function MeasureForm({ busy, onLock }: { busy: boolean; onLock: (measure: Measure) => void }) {
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
    onLock(measure);
  }

  return (
    <form onSubmit={submit} onInput={(event) => {
      const field = event.target;
      if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) field.setCustomValidity("");
    }}>
      <fieldset disabled={busy} className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="measure-title">Measure title</Label>
          <Input id="measure-title" name="title" required maxLength={300} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="measure-source">Source URL</Label>
          <Input id="measure-source" type="url" name="sourceUrl" required maxLength={2048} pattern="https?://.+" title="Enter an http:// or https:// URL." placeholder="https://" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="measure-text">Ballot text</Label>
          <p id="text-help" className="text-sm text-muted-foreground">Paste the wording you will use to decide. Keep your own opinion for the voting step.</p>
          <Textarea id="measure-text" name="text" aria-describedby="text-help" required maxLength={30000} className="min-h-32" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="measure-yes">What a yes vote means</Label>
            <Textarea id="measure-yes" name="yesMeaning" required maxLength={3000} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="measure-no">What a no vote means</Label>
            <Textarea id="measure-no" name="noMeaning" required maxLength={3000} />
          </div>
        </div>
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Had you seen this measure before this entry?</legend>
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
            <label className="flex min-h-8 items-center gap-2"><input required type="radio" name="familiar" value="no" /> New to me</label>
            <label className="flex min-h-8 items-center gap-2"><input required type="radio" name="familiar" value="yes" /> Familiar to me</label>
          </div>
        </fieldset>
        <Button type="submit" size="lg"><LockKeyhole aria-hidden="true" />{busy ? "Locking prediction…" : "Lock prediction"}</Button>
      </fieldset>
    </form>
  );
}

function BallotPacket({ entry }: { entry: JournalEntry }) {
  const { measure } = entry;
  return (
    <div className="space-y-4 rounded-lg border bg-muted/25 p-4 sm:p-5">
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
    if (vote === "yes" || vote === "no") onVote({ id: entry.id, vote, reasoning });
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
        <Button type="submit" size="lg">{busy ? "Recording vote…" : "Record vote and reveal prediction"}</Button>
      </fieldset>
    </form>
  );
}

function Comparison({ entry }: { entry: Revealed }) {
  const { prediction } = entry;
  const probability = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 }).format(prediction.probabilityYes);
  return (
    <div className="space-y-5">
      <section aria-label="Vote comparison" className="rounded-lg border border-foreground/20 p-4 sm:p-5">
        <h3 className="font-semibold">{entry.vote === prediction.choice ? "The prediction matched your vote" : "You and the model chose differently"}</h3>
        <dl className="mt-4 grid grid-cols-2 gap-4 border-y py-4">
          <div><dt className="text-sm text-muted-foreground">Your vote</dt><dd className="text-3xl font-serif">{labelVote(entry.vote)}</dd></div>
          <div><dt className="text-sm text-muted-foreground">Locked prediction</dt><dd className="text-3xl font-serif">{labelVote(prediction.choice)}</dd></div>
        </dl>
        <p className="mt-3 text-sm"><strong>{probability}</strong> estimated chance you would vote yes.</p>
        <p className="mt-1 break-words text-xs text-muted-foreground">{prediction.model} · {prediction.historyCount} prior {prediction.historyCount === 1 ? "entry" : "entries"} used</p>
      </section>
      <section><h3 className="font-semibold">Your reasoning</h3><p className="mt-2 whitespace-pre-wrap break-words">{entry.reasoning}</p></section>
      <section><h3 className="font-semibold">The model’s explanation</h3><p className="mt-2 whitespace-pre-wrap break-words">{prediction.explanation}</p></section>
      <p className="text-xs text-muted-foreground">Prediction locked {timestamp(entry.lockedAt)}. Vote recorded {timestamp(entry.votedAt)}.</p>
      <details><summary className="cursor-pointer py-1 text-sm font-medium">Review the measure</summary><div className="mt-2"><BallotPacket entry={entry} /></div></details>
    </div>
  );
}

export function PersonalBallotJournal() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [error, setError] = useState("");
  const [draftVersion, setDraftVersion] = useState(0);
  const draftId = useRef<string | null>(null);
  const hasRequest = useRef(false);
  const focusDetail = useRef(false);
  const detail = useRef<HTMLHeadingElement>(null);
  const ordered = [...entries].sort((a, b) => b.lockedAt.localeCompare(a.lockedAt) || b.id.localeCompare(a.id));
  const selected = entries.find((entry) => entry.id === selectedId);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setLoadError(false);
    try {
      const response = await requestJournal<{ entries: JournalEntry[] }>("GET", undefined, signal);
      if (signal?.aborted) return;
      setEntries(response.entries);
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
      detail.current?.focus();
      focusDetail.current = false;
    }
  }, [selectedId, selected?.status]);

  function navigate(id: string | null) {
    if (id === selectedId) {
      detail.current?.focus();
      return;
    }
    focusDetail.current = true;
    setSelectedId(id);
    setError("");
  }

  async function save(method: "POST" | "PUT", body: { id: string; measure: Measure } | VoteInput) {
    if (hasRequest.current) return;
    hasRequest.current = true;
    setBusy(true);
    setError("");
    try {
      const { entry } = await requestJournal<{ entry: JournalEntry }>(method, body);
      setEntries((previous) => [...previous.filter((row) => row.id !== entry.id), entry]);
      focusDetail.current = true;
      setSelectedId(entry.id);
      if (method === "POST") {
        draftId.current = null;
        setDraftVersion((previous) => previous + 1);
      }
    } catch (cause) {
      setError(cause instanceof Error && !(cause instanceof TypeError)
        ? cause.message
        : "Could not reach the journal. Your inputs are still here. Check the local server and try again.");
    } finally {
      hasRequest.current = false;
      setBusy(false);
    }
  }

  if (loading) return <p role="status" className="border-t py-6 text-muted-foreground">Opening your journal…</p>;
  if (loadError) return (
    <div className="space-y-3 border-t py-6"><p role="alert">Could not open the local journal. Check that the journal server is running.</p>
      <Button variant="outline" onClick={() => void load()}>Try again</Button>
    </div>
  );

  return (
    <div className="grid items-start gap-6 border-t pt-6 lg:grid-cols-[minmax(14rem,0.7fr)_minmax(0,1.8fr)]">
      <aside aria-labelledby="entries-heading" className="min-w-0 rounded-lg border bg-muted/20 p-4">
        <div className="mb-3 flex items-center gap-2">
          <BookOpen aria-hidden="true" className="size-4 text-muted-foreground" />
          <h2 id="entries-heading" className="font-semibold">Your entries <span className="ml-1 text-sm font-normal text-muted-foreground">({entries.length})</span></h2>
        </div>
        <Button variant="outline" disabled={busy} className="w-full justify-start bg-background" onClick={() => navigate(null)}><Plus aria-hidden="true" />New measure</Button>
        {entries.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">Lock your first prediction to create an entry.</p>
        ) : (
          <ul className="mt-3 divide-y">
            {ordered.map((entry) => (
              <li key={entry.id}>
                <button type="button" disabled={busy} aria-current={selectedId === entry.id ? "true" : undefined}
                  onClick={() => navigate(entry.id)}
                  className="block w-full rounded-sm px-2 py-3 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring aria-current:bg-muted">
                  <span className="block break-words text-sm font-medium">{entry.measure.title}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">{entry.status === "locked" ? "Awaiting your vote" : "Vote recorded"} · {timestamp(entry.lockedAt)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <section aria-labelledby="journal-detail" aria-busy={busy} className="min-w-0 space-y-5 rounded-lg border bg-card p-5 sm:p-7">
        <div>
          {selected && <p className="mb-2 text-sm font-medium text-muted-foreground">{selected.status === "locked" ? "Prediction locked · Awaiting your vote" : "Completed entry"}</p>}
          <h2 id="journal-detail" ref={detail} tabIndex={-1} className="break-words font-serif text-3xl tracking-tight">
            {selected ? selected.measure.title : "Add a measure"}
          </h2>
          {selected?.status === "locked" && <p className="mt-2 text-sm text-muted-foreground">Locked {timestamp(selected.lockedAt)}. Record your decision to reveal the prediction.</p>}
          {!selected && <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            The model uses the measure and your earlier completed entries. With no voting history, the default baseline starts at equal odds and breaks the tie.
            A configured local language model can make the prediction instead.
          </p>}
        </div>
        {error && <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{error}</p>}
        <div hidden={!!selected}>
          <MeasureForm key={draftVersion} busy={busy} onLock={(measure) => {
            draftId.current ??= crypto.randomUUID();
            void save("POST", { id: draftId.current, measure });
          }} />
        </div>
        {selected?.status === "locked" && <>
          <BallotPacket entry={selected} />
          <VoteForm key={selected.id} entry={selected} busy={busy} onVote={(input) => void save("PUT", input)} />
        </>}
        {selected?.status === "revealed" && <Comparison entry={selected} />}
      </section>
    </div>
  );
}
