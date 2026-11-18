import { randomUUID } from "node:crypto";
import { link, mkdir, open, readFile, readdir, unlink } from "node:fs/promises";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { isDeepStrictEqual } from "node:util";
import type { JournalCheck, JournalEntry, JournalFollowUp, JournalForecastSet, JournalMeasure, JournalModelVersion, JournalPrediction, JournalQuestion } from "./personal-journal-types";

type RevealedEntry = Extract<JournalEntry, { status: "revealed" }>;
type Vote = RevealedEntry["vote"];
type Predict = (measure: JournalMeasure, history: RevealedEntry[], modelVersion?: JournalModelVersion) => Promise<JournalPrediction | JournalForecastSet>;
type ChooseQuestion = (entry: RevealedEntry, history: RevealedEntry[]) => Promise<JournalQuestion | null>;

interface EvidenceSnapshot {
  eligibleHistoryIds: string[];
  eligibleHistoryRevisions?: Record<string, number>;
  /** One immutable clarification can be answered per measure revision. */
  eligibleClarificationIds?: string[];
}

interface StoredForecast extends EvidenceSnapshot {
  id: string;
  measure: JournalMeasure;
  lockedAt: string;
  prediction: JournalPrediction;
  checkId?: string;
  comparison?: RevealedEntry["comparison"];
}

interface StoredCheck {
  check: JournalCheck;
  evidence: EvidenceSnapshot;
}

interface StoredVote {
  vote: Vote;
  reasoning: string;
  votedAt: string;
}

type EntryEvent =
  | { kind: "vote"; ballot: StoredVote }
  | { kind: "relock"; forecast: StoredForecast }
  | { kind: "correct"; measure: JournalMeasure; correctedAt: string }
  | { kind: "question"; question: JournalQuestion | null; askedAt: string }
  | { kind: "response"; answer: string | null; respondedAt: string };

interface EntryState {
  eventCount: number;
  revision: number;
  forecast: StoredForecast;
  ballot: StoredVote | null;
  correctedAfterVote?: JournalMeasure;
  archivedFollowUp?: RevealedEntry["archivedFollowUp"];
  followUp?: JournalFollowUp | null;
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
const checkFile = "five-measure-check.json";
const inFlight = new Map<string, { measure: JournalMeasure; checkId?: string; result: Promise<JournalEntry> }>();

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
async function publishOnce(path: string, record: StoredForecast | StoredCheck | EntryEvent): Promise<void> {
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

async function readState(dir: string, forecast: StoredForecast, throughRevision?: number): Promise<EntryState> {
  // Pre-correction journals saved the first vote in a separate immutable file.
  const id = forecast.id;
  const ballot = await readRecord<StoredVote>(join(dir, id + ".vote.json"));
  const state: EntryState = { eventCount: 0, revision: 0, forecast, ballot };
  for (;;) {
    const event = await readRecord<EntryEvent>(eventPath(dir, id, state.eventCount + 1));
    if (!event) return state;
    if ((event.kind === "correct" || event.kind === "relock") && state.revision === throughRevision) return state;
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
        // The participant confirmed that their vote and original reasoning
        // still apply. A clarification about earlier wording has no such confirmation.
        if (state.followUp?.status === "answered") state.archivedFollowUp = state.followUp;
        delete state.followUp;
        break;
      case "question":
        if (!state.ballot || state.followUp !== undefined) throw new Error("Unexpected journal question.");
        state.followUp = event.question ? { question: event.question, status: "pending" } : null;
        break;
      case "response":
        if (state.followUp?.status !== "pending") throw new Error("Unexpected journal follow-up response.");
        state.followUp = event.answer === null
          ? { question: state.followUp.question, status: "skipped" }
          : { question: state.followUp.question, status: "answered", answer: event.answer };
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
    ...(forecast.checkId ? { checkId: forecast.checkId } : {}),
    ...(revision ? { revision } : {}),
  };
  if (!ballot) return { ...base, status: "locked" };
  const { vote, reasoning, votedAt } = ballot;
  return {
    ...base, status: "revealed", vote, reasoning, votedAt, prediction: forecast.prediction,
    ...(forecast.comparison ? { comparison: forecast.comparison } : {}),
    ...(correctedAfterVote ? { forecastMeasure: forecast.measure } : {}),
    ...(state.archivedFollowUp ? { archivedFollowUp: state.archivedFollowUp } : {}),
    ...(state.followUp ? { followUp: state.followUp } : {}),
    ...(state.followUp === null ? { followUpReviewed: true } : {}),
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

function completedEvidence(entries: JournalEntry[]) {
  return entries
    .filter((entry): entry is RevealedEntry => entry.status === "revealed")
    .sort((a, b) => a.votedAt.localeCompare(b.votedAt) || a.id.localeCompare(b.id))
    .map(entry => modelEvidence(entry, true));
}

function snapshot(history: RevealedEntry[]): EvidenceSnapshot {
  const eligibleHistoryIds = history.map((entry) => entry.id);
  const eligibleClarificationIds = history.filter(entry => entry.followUp?.status === "answered").map(entry => entry.id);
  const eligibleHistoryRevisions: Record<string, number> = {};
  for (const entry of history) {
    if (entry.revision) eligibleHistoryRevisions[entry.id] = entry.revision;
  }
  return {
    eligibleHistoryIds,
    ...(Object.keys(eligibleHistoryRevisions).length ? { eligibleHistoryRevisions } : {}),
    ...(eligibleClarificationIds.length ? { eligibleClarificationIds } : {}),
  };
}

export async function getCheck(): Promise<JournalCheck | null> {
  return (await readRecord<StoredCheck>(join(journalDirectory(), checkFile)))?.check ?? null;
}

export async function startCheck(): Promise<JournalCheck> {
  const dir = journalDirectory();
  const path = join(dir, checkFile);
  const existing = await readRecord<StoredCheck>(path);
  if (existing) return existing.check;
  const evidence = snapshot(completedEvidence(await entriesIn(dir)));
  const check: JournalCheck = {
    id: randomUUID(), startedAt: new Date().toISOString(), slotIds: Array.from({ length: 5 }, () => randomUUID()),
    modelVersion: "reasoning-examples-v2",
    evidenceCount: evidence.eligibleHistoryIds.length, clarificationCount: evidence.eligibleClarificationIds?.length ?? 0,
  };
  await mkdir(dir, { recursive: true, mode: 0o700 });
  await publishOnce(path, { check, evidence });
  const winner = await readRecord<StoredCheck>(path);
  if (!winner) throw new Error("Could not read the frozen comparison.");
  return winner.check;
}

async function checkForSlot(dir: string, id: string, checkId?: string, newUnseen = false): Promise<StoredCheck | null> {
  const record = await readRecord<StoredCheck>(join(dir, checkFile));
  if (record?.check.slotIds.includes(id)) {
    if (checkId === record.check.id) return record;
    throw new JournalStoreError(409, "This slot is reserved for the five-measure check. Reload the journal.");
  }
  if (checkId) throw new JournalStoreError(409, "Select an available slot in the five-measure check.");
  if (record && newUnseen) {
    const names = new Set(await readdir(dir));
    if (record.check.slotIds.some(slot => !names.has(slot + forecastSuffix))) {
      throw new JournalStoreError(409, "The five-measure check is active. Reload the journal to use its next slot.");
    }
  }
  return null;
}

function sameBallot(a: JournalMeasure, b: JournalMeasure): boolean {
  const normalize = (field: string) => field.trim().replace(/\s+/g, " ").toLowerCase();
  return normalize(a.title) === normalize(b.title) && normalize(a.text) === normalize(b.text);
}

function checkedPrediction(prediction: JournalPrediction, evidenceCount: number): JournalPrediction {
  if (!prediction) throw new JournalStoreError(502, "The forecaster omitted a prediction.");
  const { choice, probabilityYes, model, explanation, historyCount } = prediction;
  if (!Number.isFinite(probabilityYes) || probabilityYes < 0 || probabilityYes > 1 ||
      !["yes", "no"].includes(choice) || !Number.isInteger(historyCount) ||
      historyCount < 0 || historyCount > evidenceCount ||
      typeof model !== "string" || !model.trim() || typeof explanation !== "string") {
    throw new JournalStoreError(502, "The forecaster returned an invalid prediction.");
  }
  return { choice, probabilityYes, model, explanation, historyCount };
}

async function makeForecast(
  dir: string, id: string, measure: JournalMeasure, predict: Predict, check: StoredCheck | null
): Promise<StoredForecast> {
  const entries = await entriesIn(dir);
  if (check) {
    if (measure.familiar) throw new JournalStoreError(400, "Choose a measure that is new to you for this check.");
    const other = entries.filter(entry => entry.id !== id);
    if (other.some(entry => sameBallot(measure, entry.measure) ||
      (entry.status === "revealed" && entry.forecastMeasure && sameBallot(measure, entry.forecastMeasure)))) {
      throw new JournalStoreError(409, "This measure already appears in the journal. Choose a new measure.");
    }
    if (!entries.some(entry => entry.id === id)) {
      const occupied = new Set(other.map(entry => entry.id));
      if (check.check.slotIds.find(slot => !occupied.has(slot)) !== id) {
        throw new JournalStoreError(409, "The next comparison slot changed. Reload the journal.");
      }
    }
  }
  const history = check ? await readEvidence(dir, check.evidence) : completedEvidence(entries.filter(entry => entry.id !== id));
  const evidence = check?.evidence ?? snapshot(history);
  const modelVersion = check ? (check.check.modelVersion ?? "reasoning-examples-v1") : undefined;
  const result = await predict(measure, history, modelVersion);
  const base = { id, measure, lockedAt: new Date().toISOString(), ...evidence };
  if (!check && !("reasoning" in result)) {
    return { ...base, prediction: checkedPrediction(result, history.length) };
  }
  if (!check || !("reasoning" in result)) throw new JournalStoreError(502, "The forecaster returned an incomplete comparison.");
  const prediction = checkedPrediction(result.reasoning, history.length);
  const baseline = checkedPrediction(result.baseline, history.length);
  const withoutReasoning = checkedPrediction(result.withoutReasoning, history.length);
  if (prediction.model !== modelVersion || baseline.model !== "outcome-wording-v1" ||
      withoutReasoning.model !== modelVersion + "-without-reasoning") {
    throw new JournalStoreError(502, "The forecasts did not match the model versions frozen for this check.");
  }
  if ([prediction, baseline, withoutReasoning].some(arm => arm.historyCount !== history.length)) {
    throw new JournalStoreError(502, "All three forecasts must use the same frozen decisions.");
  }
  return { ...base, checkId: check.check.id, prediction, comparison: { baseline, withoutReasoning } };
}

async function freezeForecast(
  dir: string, id: string, measure: JournalMeasure, predict: Predict, checkId?: string
): Promise<JournalEntry> {
  const path = join(dir, id + forecastSuffix);
  let forecast = await readRecord<StoredForecast>(path);
  const check = await checkForSlot(dir, id, checkId, !forecast && !measure.familiar);
  if (!forecast) {
    const proposal = await makeForecast(dir, id, measure, predict, check);
    await mkdir(dir, { recursive: true, mode: 0o700 });
    await publishOnce(path, proposal);
    // A separate process may have published first. Its snapshot is authoritative.
    forecast = await readRecord<StoredForecast>(path);
    if (!forecast) throw new Error("Could not read the locked forecast.");
  }
  if (forecast.checkId !== checkId) throw new JournalStoreError(409, "This entry belongs to a different forecast request.");
  requireSameMeasure(measure, forecast.measure);
  return projectEntry(await readState(dir, forecast));
}

function ballotFields(input: JournalMeasure): JournalMeasure {
  // Persist only the ballot fields. The forecast and the voter's answer have
  // separate write paths and may never be supplied as measure metadata.
  const { title, sourceUrl, text, yesMeaning, noMeaning, familiar } = input;
  return { title, sourceUrl, text, yesMeaning, noMeaning, familiar };
}

export async function lockEntry(inputId: string, input: JournalMeasure, predict: Predict, checkId?: string): Promise<JournalEntry> {
  const id = entryId(inputId);
  const dir = journalDirectory();
  const key = join(dir, id);
  const measure = ballotFields(input);
  const pending = inFlight.get(key);
  if (pending) {
    if (pending.checkId !== checkId) throw stale();
    requireSameMeasure(measure, pending.measure);
    return pending.result;
  }
  const result = freezeForecast(dir, id, measure, predict, checkId);
  inFlight.set(key, { measure, checkId, result });
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

function modelEvidence(entry: RevealedEntry, includeClarification: boolean): RevealedEntry {
  const evidence = { ...entry };
  delete evidence.archivedFollowUp;
  delete evidence.followUpReviewed;
  if (!includeClarification || evidence.followUp?.status !== "answered") delete evidence.followUp;
  return evidence;
}

async function readEvidence(dir: string, snapshot: EvidenceSnapshot): Promise<RevealedEntry[]> {
  const history: RevealedEntry[] = [];
  const clarified = new Set(snapshot.eligibleClarificationIds);
  for (const id of snapshot.eligibleHistoryIds) {
    const revision = snapshot.eligibleHistoryRevisions?.[id] ?? 0;
    const state = await readState(dir, await originalForecast(dir, id), revision);
    const entry = projectEntry(state);
    if (entry.status !== "revealed" || state.revision !== revision ||
        (clarified.has(id) && entry.followUp?.status !== "answered")) {
      throw new JournalStoreError(500, "The journal could not reconstruct the frozen evidence.");
    }
    history.push(modelEvidence(entry, clarified.has(id)));
  }
  return history;
}

function requireRevealed(state: EntryState, expectedRevision: number): RevealedEntry {
  const entry = projectEntry(state);
  if (state.revision !== expectedRevision) throw stale();
  if (entry.status !== "revealed") throw new JournalStoreError(409, "Record your vote before opening a follow-up.");
  return entry;
}

export async function suggestFollowUp(inputId: string, expectedRevision: number, choose: ChooseQuestion): Promise<JournalEntry> {
  const id = entryId(inputId);
  const dir = journalDirectory();
  const original = await originalForecast(dir, id);
  const state = await readState(dir, original);
  const entry = requireRevealed(state, expectedRevision);
  if (entry.forecastMeasure || state.followUp !== undefined) return entry;
  const history = (await readEvidence(dir, state.forecast)).filter(prior => prior.id !== id && prior.votedAt < entry.votedAt);
  const question = await choose(entry, history);
  if (question !== null && (
    !question || typeof question.prompt !== "string" || !question.prompt.trim() || question.prompt.length > 2000 ||
    !["miss", "uncertain"].includes(question.trigger) ||
    (question.kind !== undefined && !["contrast", "counterfactual", "weight"].includes(question.kind)) ||
    (question.referenceId !== undefined && !history.some(prior => prior.id === question.referenceId))
  )) throw new JournalStoreError(502, "The model returned an invalid follow-up question.");
  await publishOnce(eventPath(dir, id, state.eventCount + 1), {
    kind: "question", question, askedAt: new Date().toISOString(),
  });
  return requireRevealed(await readState(dir, original), expectedRevision);
}

export async function respondToFollowUp(
  inputId: string, expectedRevision: number, expectedPrompt: string, input: string | null
): Promise<JournalEntry> {
  const id = entryId(inputId);
  const answer = typeof input === "string" ? input.trim() : input;
  if (answer !== null && (typeof answer !== "string" || !answer || answer.length > 10000)) {
    throw new JournalStoreError(400, "Enter a follow-up answer of up to 10,000 characters, or skip the question.");
  }
  const dir = journalDirectory();
  const original = await originalForecast(dir, id);
  const state = await readState(dir, original);
  let entry = requireRevealed(state, expectedRevision);
  if (!entry.followUp || entry.followUp.question.prompt !== expectedPrompt) throw stale();
  if (entry.followUp.status === "pending") {
    await publishOnce(eventPath(dir, id, state.eventCount + 1), {
      kind: "response", answer, respondedAt: new Date().toISOString(),
    });
    entry = requireRevealed(await readState(dir, original), expectedRevision);
  }
  const saved = entry.followUp;
  if (saved?.status === "answered" && saved.answer === answer) return entry;
  if (saved?.status === "skipped" && answer === null) return entry;
  throw new JournalStoreError(409, "This question already has a different response.");
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
    ? { kind: "relock", forecast: await makeForecast(dir, id, measure, predict, await checkForSlot(dir, id, current.checkId)) }
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

export function pastDecision(entry: RevealedEntry) {
  const { id, measure, vote, reasoning, followUp } = entry;
  return {
    id, measure, vote, reasoning,
    ...(followUp?.status === "answered" && {
      clarification: { question: followUp.question.prompt, kind: followUp.question.kind, answer: followUp.answer },
    }),
  };
}

/** Recover the exact forecast packet for a completed local regression case. */
export async function readRegressionCase(inputId: string) {
  const id = entryId(inputId);
  const dir = journalDirectory();
  const state = await readState(dir, await originalForecast(dir, id));
  if (!state.ballot) throw new JournalStoreError(409, "Regression cases need a recorded vote.");
  const { forecast } = state;
  const history = await readEvidence(dir, forecast);
  if (new Set(history.map(prior => prior.id)).size !== history.length ||
      history.some(prior => prior.id === id || prior.votedAt > forecast.lockedAt)) {
    throw new JournalStoreError(500, "Invalid evidence in the locked regression case.");
  }
  return {
    request: { id, measure: forecast.measure, history: history.map(pastDecision) },
    locked: forecast.prediction, vote: state.ballot.vote,
  };
}
