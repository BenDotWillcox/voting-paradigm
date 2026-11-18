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
}

interface StoredVote {
  vote: Vote;
  reasoning: string;
  votedAt: string;
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
async function publishOnce(path: string, record: StoredForecast | StoredVote): Promise<void> {
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

async function projectEntry(dir: string, forecast: StoredForecast): Promise<JournalEntry> {
  const { id, measure, lockedAt } = forecast;
  const ballot = await readRecord<StoredVote>(join(dir, id + ".vote.json"));
  if (!ballot) return { id, measure, lockedAt, status: "locked" };
  const { vote, reasoning, votedAt } = ballot;
  return { id, measure, lockedAt, status: "revealed", vote, reasoning, votedAt, prediction: forecast.prediction };
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
    entries.push(await projectEntry(dir, forecast));
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

async function freezeForecast(
  dir: string, id: string, measure: JournalMeasure, predict: Predict
): Promise<JournalEntry> {
  const path = join(dir, id + forecastSuffix);
  let forecast = await readRecord<StoredForecast>(path);
  if (!forecast) {
    const history = (await entriesIn(dir))
      .filter((entry): entry is RevealedEntry => entry.status === "revealed")
      .sort((a, b) => a.votedAt.localeCompare(b.votedAt) || a.id.localeCompare(b.id));
    const eligibleHistoryIds = history.map((entry) => entry.id);
    const { choice, probabilityYes, model, explanation, historyCount } = await predict(measure, history);
    if (!Number.isFinite(probabilityYes) || probabilityYes < 0 || probabilityYes > 1 ||
        !["yes", "no"].includes(choice) || !Number.isInteger(historyCount) ||
        historyCount < 0 || historyCount > eligibleHistoryIds.length ||
        typeof model !== "string" || !model.trim() || typeof explanation !== "string") {
      throw new JournalStoreError(502, "The forecaster returned an invalid prediction.");
    }
    const prediction = { choice, probabilityYes, model, explanation, historyCount };
    await mkdir(dir, { recursive: true, mode: 0o700 });
    await publishOnce(path, { id, measure, lockedAt: new Date().toISOString(), prediction, eligibleHistoryIds });
    // A separate process may have published first. Its snapshot is authoritative.
    forecast = await readRecord<StoredForecast>(path);
    if (!forecast) throw new Error("Could not read the locked forecast.");
  }
  requireSameMeasure(measure, forecast.measure);
  return projectEntry(dir, forecast);
}

export async function lockEntry(inputId: string, input: JournalMeasure, predict: Predict): Promise<JournalEntry> {
  const id = entryId(inputId);
  const dir = journalDirectory();
  const key = join(dir, id);
  // Persist only the ballot fields. The forecast and the voter's answer have
  // separate write paths and may never be supplied as measure metadata.
  const { title, sourceUrl, text, yesMeaning, noMeaning, familiar } = input;
  const measure = { title, sourceUrl, text, yesMeaning, noMeaning, familiar };
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

export async function recordVote(inputId: string, vote: Vote, inputReasoning: string): Promise<JournalEntry> {
  const id = entryId(inputId);
  if (vote !== "yes" && vote !== "no") {
    throw new JournalStoreError(400, "A yes or no answer is required to reveal a forecast.");
  }
  const reasoning = typeof inputReasoning === "string" ? inputReasoning.trim() : "";
  if (!reasoning || reasoning.length > 10000) {
    throw new JournalStoreError(400, "Reasoning must be between 1 and 10,000 characters.");
  }
  const dir = journalDirectory();
  const forecast = await readRecord<StoredForecast>(join(dir, id + forecastSuffix));
  if (!forecast) throw new JournalStoreError(404, "No locked forecast exists for this entry.");
  const path = join(dir, id + ".vote.json");
  await publishOnce(path, { vote, reasoning, votedAt: new Date().toISOString() });
  const entry = await projectEntry(dir, forecast);
  if (entry.status !== "revealed") throw new Error("Could not read the recorded vote.");
  if (entry.vote !== vote || entry.reasoning !== reasoning) {
    throw new JournalStoreError(409, "This entry already has a different recorded answer.");
  }
  return entry;
}
