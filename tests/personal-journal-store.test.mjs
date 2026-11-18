import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtemp, readFile, readdir, rmdir, unlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import * as store from "../lib/personal-journal-store.ts";

const measure = {
  title: "Bridge maintenance",
  sourceUrl: "https://example.org/measure",
  text: "Authorize a fixed repair fund.",
  yesMeaning: "Approve the repairs",
  noMeaning: "Keep the current budget",
  familiar: false,
};

function prediction(historyCount, choice = "yes") {
  return { choice, probabilityYes: choice === "yes" ? 0.7 : 0.3,
    model: "test", explanation: "Private forecast rationale", historyCount };
}

async function privateDirectory(t) {
  const dir = await mkdtemp(join(tmpdir(), "personal-journal-test-"));
  const previous = process.env.PERSONAL_JOURNAL_DIR;
  process.env.PERSONAL_JOURNAL_DIR = dir;
  t.after(async () => {
    if (previous === undefined) delete process.env.PERSONAL_JOURNAL_DIR;
    else process.env.PERSONAL_JOURNAL_DIR = previous;
    for (const name of await readdir(dir)) await unlink(join(dir, name));
    await rmdir(dir);
  });
  return dir;
}

test("forecast stays hidden through retry and reload, then the first vote reveals it", async (t) => {
  const dir = await privateDirectory(t);
  const id = randomUUID();
  const neverPredict = () => assert.fail("A retry reran inference");
  const before = await store.lockEntry(id, measure, async (_, history) => prediction(history.length));
  assert.deepEqual(Object.keys(before).sort(), ["id", "lockedAt", "measure", "status"]);
  assert.equal(before.status, "locked");
  await assert.rejects(store.recordVote(id, "invalid", "Test"), { status: 400 });
  for (const invalid of ["", " \t\n ", "a".repeat(10001)]) {
    await assert.rejects(store.recordVote(id, "yes", invalid), { status: 400 });
  }
  assert.deepEqual(await store.listEntries(), [before]);
  const reloaded = await import("../lib/personal-journal-store.ts?reload");
  assert.deepEqual(await reloaded.listEntries(), [before]);
  assert.deepEqual(await reloaded.lockEntry(id, measure, neverPredict), before);
  await assert.rejects(reloaded.lockEntry(id, { ...measure, text: "A new proposal" }, neverPredict), { status: 409 });
  const revealed = await reloaded.recordVote(id, "no", "  I prefer staged repairs.  ");
  assert.equal(revealed.status, "revealed");
  assert.deepEqual(revealed.prediction, prediction(0));
  assert.deepEqual(await store.recordVote(id, "no", "I prefer staged repairs."), revealed);
  await assert.rejects(store.recordVote(id, "no", "Changed my explanation"), { status: 409 });
  assert.deepEqual(await store.listEntries(), [revealed]);
  const persisted = execFileSync(process.execPath, [
    "--experimental-strip-types", "--disable-warning=ExperimentalWarning",
    "--input-type=module", "--eval",
    'import { listEntries } from "./lib/personal-journal-store.ts"; console.log(JSON.stringify(await listEntries()));',
  ], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  assert.deepEqual(JSON.parse(persisted), [revealed]);
  assert.deepEqual((await readdir(dir)).sort(), [id + ".forecast.json", id + ".vote.json"]);
});

test("frozen eligible history excludes unanswered measures even when the model uses fewer entries", async (t) => {
  const dir = await privateDirectory(t);
  const answered = randomUUID(), open = randomUUID(), next = randomUUID();
  const predict = async (_, history) => prediction(history.length);
  await store.lockEntry(answered, measure, predict);
  await store.lockEntry(open, { ...measure, title: "Pending" }, predict);
  const firstVote = await store.recordVote(answered, "no", "Repair next year.");
  await store.lockEntry(next, { ...measure, title: "New" }, async (target, history) => {
    assert.equal(target.title, "New");
    assert.deepEqual(history, [firstVote]);
    return prediction(0);
  });
  await store.recordVote(open, "yes", "Proceed now.");
  const stored = JSON.parse(await readFile(join(dir, next + ".forecast.json"), "utf8"));
  assert.deepEqual(stored.eligibleHistoryIds, [answered]);
  assert.equal(stored.prediction.historyCount, 0);
});

test("concurrent retries use one inference in-process and canonical immutable files across instances", async (t) => {
  await privateDirectory(t);
  const id = randomUUID();
  let calls = 0;
  let release;
  const wait = new Promise((resolve) => { release = resolve; });
  const predict = async () => { calls++; await wait; return prediction(0); };
  const first = store.lockEntry(id, measure, predict);
  const same = store.lockEntry(id, measure, predict);
  await assert.rejects(store.lockEntry(id, { ...measure, title: "Different" }, predict), { status: 409 });
  release();
  assert.deepEqual(await first, await same);
  assert.equal(calls, 1);

  const independent = await import("../lib/personal-journal-store.ts?independent");
  const race = randomUUID();
  const competing = [store, independent].map((instance, i) =>
    instance.lockEntry(race, measure, async () => prediction(0, i ? "no" : "yes")));
  const [one, two] = await Promise.all(competing);
  assert.deepEqual(one, two);
  const votes = await Promise.allSettled([
    store.recordVote(race, "yes", "Approved"),
    independent.recordVote(race, "no", "Opposed"),
  ]);
  assert.equal(votes.filter((v) => v.status === "fulfilled").length, 1);
  assert.equal(votes.filter((v) => v.status === "rejected" && v.reason.status === 409).length, 1);
  const winner = votes.find((v) => v.status === "fulfilled").value;
  assert.deepEqual((await store.listEntries()).find((v) => v.id === race), winner);
});

test("failed inference creates no partial entry and voting requires an existing forecast", async (t) => {
  await privateDirectory(t);
  const id = randomUUID();
  await assert.rejects(store.recordVote(id, "yes", "Test"), { status: 404 });
  await assert.rejects(store.lockEntry(id, measure, async () => { throw new Error("Offline"); }), /Offline/);
  await assert.rejects(store.lockEntry(id, measure, async () => ({ ...prediction(0), probabilityYes: NaN })), { status: 502 });
  assert.deepEqual(await store.listEntries(), []);
  assert.equal((await store.lockEntry(id, measure, async () => prediction(0))).status, "locked");
  await assert.rejects(store.recordVote("../public/index", "no", "Test"), { status: 400 });
});
