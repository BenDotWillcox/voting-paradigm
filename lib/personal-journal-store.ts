import { randomUUID } from "node:crypto";
import { link, mkdir, open, readFile, readdir, unlink } from "node:fs/promises";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { isDeepStrictEqual } from "node:util";
import type { JournalEntry, JournalMeasure, JournalPrediction } from "./personal-journal-types";

type RevealedEntry = Extract<JournalEntry, { status: "revealed" }>;
type Vote = RevealedEntry["vote"];
type Predict = (measure: JournalMeasure, history: RevealedEntry[]) => Promise<JournalPrediction>;

interface StoredForecast {
  id: string;
  measure: JournalMeasure;
  lockedAt: string;
  prediction: JournalPrediction;
  eligibleHistoryIds: string[];
  eligibleHistoryRevisions?: Record<string, number>;
}

interface StoredVote {
  vote: Vote;
  reasoning: string;
  votedAt: string;
}

type EntryEvent =
  | { kind: "vote"; ballot: StoredVote }
  | { kind: "relock"; forecast: StoredForecast }
  | { kind: "correct"; measure: JournalMeasure; correctedAt: string };

interface EntryState {
  eventCount: number;
  revision: number;
  forecast: StoredForecast;
  ballot: StoredVote | null;
  correctedAfterVote?: JournalMeasure;
}

export class JournalStoreError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "JournalStoreError";
    this.status = status;
  }
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const forecastSuffix = ".forecast.json";
const inFlight = new Map<string, { measure: JournalMeasure; result: Promise<JournalEntry> }>();

function journalDirectory(): string {
  const dir = resolve(process.env.PERSONAL_JOURNAL_DIR || "eval/private_runs/personal-journal");
  for (const served of ["public", ".next/static"]) {
    const path = relative(resolve(served), dir);
    if (path !== ".." && !path.startsWith(".." + sep) && !isAbsolute(path)) {
      throw new JournalStoreError(500, "The journal needs a private storage directory.");
    }
  }
  return dir;
}

function entryId(input: string): string {
  if (!uuid.test(input)) throw new JournalStoreError(400, "Invalid journal entry ID.");
  return input.toLowerCase();
}

function hasCode(error: unknown, code: string): boolean {
  return error instanceof Error && "code" in error && error.code === code;
}

async function readRecord<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch (error) {
    if (hasCode(error, "ENOENT")) return null;
    throw error;
  }
}

// The published name only ever points to a complete, synced file. Hard links
// never replace an existing entry, including a winner in another process.
async function publishOnce(path: string, record: StoredForecast | EntryEvent): Promise<void> {
  const temp = path + "." + randomUUID() + ".tmp";
  const file = await open(temp, "wx", 0o600);
  try {
    try {
      await file.writeFile(JSON.stringify(record) + "\n", "utf8");
      await file.sync();
    } finally {
      await file.close();
    }
    try {
      await link(temp, path);
    } catch (error) {
      if (!hasCode(error, "EEXIST")) throw error;
    }
  } finally {
    await unlink(temp);
  }
}

function eventPath(dir: string, id: string, sequence: number): string {
  return join(dir, id + ".event." + sequence + ".json");
}

async function readState(dir: string, forecast: StoredForecast): Promise<EntryState> {
  // Pre-correction journals saved the first vote in a separate immutable file.
  const id = forecast.id;
  const ballot = await readRecord<StoredVote>(join(dir, id + ".vote.json"));
  const state: EntryState = { eventCount: 0, revision: 0, forecast, ballot };
  for (;;) {
    const event = await readRecord<EntryEvent>(eventPath(dir, id, state.eventCount + 1));
    if (!event) return state;
    state.eventCount++;
    switch (event.kind) {
      case "vote":
        if (state.ballot) throw new Error("Unexpected repeated journal vote.");
        state.ballot = event.ballot;
        break;
      case "relock":
        if (state.ballot) throw new Error("Cannot relock a revealed journal vote.");
        state.forecast = event.forecast;
        state.revision++;
        break;
      case "correct":
        if (!state.ballot) throw new Error("A pending correction requires a forecast.");
        state.correctedAfterVote = event.measure;
        state.revision++;
        break;
      default:
        throw new Error("Unknown journal event.");
    }
  }
}

function projectEntry(state: EntryState): JournalEntry {
  const { forecast, ballot, revision, correctedAfterVote } = state;
  const base = {
    id: forecast.id, measure: correctedAfterVote ?? forecast.measure, lockedAt: forecast.lockedAt,
    ...(revision ? { revision } : {}),
  };
  if (!ballot) return { ...base, status: "locked" };
  const { vote, reasoning, votedAt } = ballot;
  return {
    ...base, status: "revealed", vote, reasoning, votedAt, prediction: forecast.prediction,
    ...(correctedAfterVote ? { forecastMeasure: forecast.measure } : {}),
  };
}

async function entriesIn(dir: string): Promise<JournalEntry[]> {
  let names: string[];
  try {
    names = await readdir(dir);
  } catch (error) {
    if (hasCode(error, "ENOENT")) return [];
    throw error;
  }
  const entries: JournalEntry[] = [];
  for (const name of names) {
    if (!name.endsWith(forecastSuffix)) continue;
    const id = name.slice(0, -forecastSuffix.length);
    if (!uuid.test(id)) continue;
    const forecast = await readRecord<StoredForecast>(join(dir, name));
    if (!forecast || forecast.id !== id) throw new Error("Could not read a journal forecast.");
    entries.push(projectEntry(await readState(dir, forecast)));
  }
  return entries.sort((a, b) => b.lockedAt.localeCompare(a.lockedAt) || a.id.localeCompare(b.id));
}

export function listEntries(): Promise<JournalEntry[]> {
  return entriesIn(journalDirectory());
}

function requireSameMeasure(requested: JournalMeasure, stored: JournalMeasure): void {
  if (!isDeepStrictEqual(requested, stored)) {
    throw new JournalStoreError(409, "This entry ID already belongs to a different measure.");
  }
}

async function makeForecast(
  dir: string, id: string, measure: JournalMeasure, predict: Predict
): Promise<StoredForecast> {
  const history = (await entriesIn(dir))
    .filter((entry): entry is RevealedEntry => entry.status === "revealed" && entry.id !== id)
    .sort((a, b) => a.votedAt.localeCompare(b.votedAt) || a.id.localeCompare(b.id));
  const eligibleHistoryIds = history.map((entry) => entry.id);
  const eligibleHistoryRevisions: Record<string, number> = {};
  for (const entry of history) {
    if (entry.revision) eligibleHistoryRevisions[entry.id] = entry.revision;
  }
  const { choice, probabilityYes, model, explanation, historyCount } = await predict(measure, history);
  if (!Number.isFinite(probabilityYes) || probabilityYes < 0 || probabilityYes > 1 ||
      !["yes", "no"].includes(choice) || !Number.isInteger(historyCount) ||
      historyCount < 0 || historyCount > eligibleHistoryIds.length ||
      typeof model !== "string" || !model.trim() || typeof explanation !== "string") {
    throw new JournalStoreError(502, "The forecaster returned an invalid prediction.");
  }
  return {
    id, measure, lockedAt: new Date().toISOString(),
    prediction: { choice, probabilityYes, model, explanation, historyCount }, eligibleHistoryIds,
    ...(Object.keys(eligibleHistoryRevisions).length ? { eligibleHistoryRevisions } : {}),
  };
}

async function freezeForecast(
  dir: string, id: string, measure: JournalMeasure, predict: Predict
): Promise<JournalEntry> {
  const path = join(dir, id + forecastSuffix);
  let forecast = await readRecord<StoredForecast>(path);
  if (!forecast) {
    const proposal = await makeForecast(dir, id, measure, predict);
    await mkdir(dir, { recursive: true, mode: 0o700 });
    await publishOnce(path, proposal);
    // A separate process may have published first. Its snapshot is authoritative.
    forecast = await readRecord<StoredForecast>(path);
    if (!forecast) throw new Error("Could not read the locked forecast.");
  }
  requireSameMeasure(measure, forecast.measure);
  return projectEntry(await readState(dir, forecast));
}

function ballotFields(input: JournalMeasure): JournalMeasure {
  // Persist only the ballot fields. The forecast and the voter's answer have
  // separate write paths and may never be supplied as measure metadata.
  const { title, sourceUrl, text, yesMeaning, noMeaning, familiar } = input;
  return { title, sourceUrl, text, yesMeaning, noMeaning, familiar };
}

export async function lockEntry(inputId: string, input: JournalMeasure, predict: Predict): Promise<JournalEntry> {
  const id = entryId(inputId);
  const dir = journalDirectory();
  const key = join(dir, id);
  const measure = ballotFields(input);
  const pending = inFlight.get(key);
  if (pending) {
    requireSameMeasure(measure, pending.measure);
    return pending.result;
  }
  const result = freezeForecast(dir, id, measure, predict);
  inFlight.set(key, { measure, result });
  try {
    return await result;
  } finally {
    inFlight.delete(key);
  }
}

function stale(): JournalStoreError {
  return new JournalStoreError(409, "This entry changed. Reopen it before saving.");
}

async function originalForecast(dir: string, id: string): Promise<StoredForecast> {
  const forecast = await readRecord<StoredForecast>(join(dir, id + forecastSuffix));
  if (!forecast) throw new JournalStoreError(404, "No locked forecast exists for this entry.");
  return forecast;
}

export async function correctEntry(
  inputId: string, expectedRevision: number, expectedStatus: JournalEntry["status"],
  input: JournalMeasure, predict: Predict
): Promise<JournalEntry> {
  const id = entryId(inputId);
  const dir = journalDirectory();
  const measure = ballotFields(input);
  const original = await originalForecast(dir, id);
  const state = await readState(dir, original);
  const current = projectEntry(state);
  if (current.status !== expectedStatus) throw stale();
  const matches = isDeepStrictEqual(current.measure, measure);
  if (matches && (state.revision === expectedRevision || state.revision === expectedRevision + 1)) return current;
  if (state.revision !== expectedRevision) throw stale();

  const event: EntryEvent = current.status === "locked"
    ? { kind: "relock", forecast: await makeForecast(dir, id, measure, predict) }
    : { kind: "correct", measure, correctedAt: new Date().toISOString() };
  // Both corrections and votes claim the same next slot. This prevents a stale
  // correction from racing a reveal, even in separate server processes.
  await publishOnce(eventPath(dir, id, state.eventCount + 1), event);
  const canonical = projectEntry(await readState(dir, original));
  if (canonical.status !== expectedStatus || canonical.revision !== expectedRevision + 1 ||
      !isDeepStrictEqual(canonical.measure, measure)) throw stale();
  return canonical;
}

export async function recordVote(
  inputId: string, vote: Vote, inputReasoning: string, expectedRevision = 0
): Promise<JournalEntry> {
  const id = entryId(inputId);
  if (vote !== "yes" && vote !== "no") {
    throw new JournalStoreError(400, "A yes or no answer is required to reveal a forecast.");
  }
  const reasoning = typeof inputReasoning === "string" ? inputReasoning.trim() : "";
  if (!reasoning || reasoning.length > 10000) {
    throw new JournalStoreError(400, "Reasoning must be between 1 and 10,000 characters.");
  }
  const dir = journalDirectory();
  const original = await originalForecast(dir, id);
  let state = await readState(dir, original);
  if (state.revision !== expectedRevision) throw stale();
  if (!state.ballot) {
    await publishOnce(eventPath(dir, id, state.eventCount + 1), {
      kind: "vote", ballot: { vote, reasoning, votedAt: new Date().toISOString() },
    });
    state = await readState(dir, original);
  }
  const entry = projectEntry(state);
  if (entry.status !== "revealed" || state.revision !== expectedRevision) throw stale();
  if (entry.vote !== vote || entry.reasoning !== reasoning) {
    throw new JournalStoreError(409, "This entry already has a different recorded answer.");
  }
  return entry;
}
