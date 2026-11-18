import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtemp, readFile, readdir, rmdir, unlink, writeFile } from "node:fs/promises";
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
  assert.deepEqual((await readdir(dir)).sort(), [id + ".event.1.json", id + ".forecast.json"]);
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

test("correcting a pending packet relocks it privately and stale votes fail", async (t) => {
  await privateDirectory(t);
  const id = randomUUID();
  const corrected = { ...measure, title: "Correct bridge title" };
  const first = await store.lockEntry(id, measure, async () => prediction(0));
  const offline = async () => { throw new Error("Offline"); };
  await assert.rejects(store.correctEntry(id, 0, "locked", corrected, offline), /Offline/);
  assert.deepEqual(await store.listEntries(), [first]);
  const second = await store.correctEntry(id, 0, "locked", corrected, async (packet, history) => {
    assert.deepEqual(packet, corrected);
    assert.deepEqual(history, []);
    return prediction(0, "no");
  });
  assert.deepEqual(Object.keys(second).sort(), ["id", "lockedAt", "measure", "revision", "status"]);
  assert.equal(second.revision, 1);
  assert.deepEqual(await store.correctEntry(id, 0, "locked", corrected, offline), second);
  await assert.rejects(store.correctEntry(id, 0, "locked", measure, offline), { status: 409 });
  await assert.rejects(store.recordVote(id, "yes", "Approve"), { status: 409 });
  const revealed = await store.recordVote(id, "yes", "Approve", 1);
  assert.deepEqual(revealed.measure, corrected);
  assert.deepEqual(revealed.prediction, prediction(0, "no"));
  assert.equal(revealed.forecastMeasure, undefined);
});

test("revealed corrections preserve the forecast packet and supply versioned evidence for later entries", async (t) => {
  const dir = await privateDirectory(t);
  const id = randomUUID();
  const corrected = { ...measure, noMeaning: "Keep the repair budget unchanged" };
  const original = await store.lockEntry(id, measure, async () => prediction(0));
  // Existing journals used this immutable vote file before corrections were added.
  const legacy = { vote: "no", reasoning: "Keep the budget.", votedAt: new Date().toISOString() };
  const legacyPath = join(dir, id + ".vote.json");
  await writeFile(legacyPath, JSON.stringify(legacy));
  const neverPredict = () => assert.fail("A revealed correction reran inference");
  const amended = await store.correctEntry(id, 0, "revealed", corrected, neverPredict);
  assert.deepEqual(amended, {
    ...original, ...legacy, status: "revealed", revision: 1, measure: corrected,
    forecastMeasure: measure, prediction: prediction(0),
  });
  assert.equal(await readFile(legacyPath, "utf8"), JSON.stringify(legacy));
  assert.deepEqual(await store.correctEntry(id, 0, "revealed", corrected, neverPredict), amended);
  const changedAgain = { ...corrected, title: "Second correction" };
  const amendedAgain = await store.correctEntry(id, 1, "revealed", changedAgain, neverPredict);
  assert.deepEqual(amendedAgain.forecastMeasure, measure);
  const next = randomUUID();
  await store.lockEntry(next, measure, async (_, history) => {
    assert.deepEqual(history, [amendedAgain]);
    return prediction(1);
  });
  const frozen = JSON.parse(await readFile(join(dir, next + ".forecast.json"), "utf8"));
  assert.deepEqual(frozen.eligibleHistoryIds, [id]);
  assert.deepEqual(frozen.eligibleHistoryRevisions, { [id]: 2 });
});

test("a vote can beat a slow relock without allowing a post-vote reforecast", async (t) => {
  await privateDirectory(t);
  const id = randomUUID();
  await store.lockEntry(id, measure, async () => prediction(0));
  let began, resume;
  const started = new Promise((resolve) => { began = resolve; });
  const waiting = new Promise((resolve) => { resume = resolve; });
  const compete = await import("../lib/personal-journal-store.ts?edit-vote-race");
  const correcting = compete.correctEntry(id, 0, "locked", { ...measure, title: "Change" }, async () => {
    began();
    await waiting;
    return prediction(0, "no");
  });
  await started;
  const revealed = await store.recordVote(id, "yes", "Repair it.");
  resume();
  await assert.rejects(correcting, { status: 409 });
  assert.deepEqual(await store.listEntries(), [revealed]);
  assert.deepEqual(revealed.prediction, prediction(0));
});

const question = { trigger: "miss", kind: "weight", prompt: "Which condition determined your decision on these repairs?" };
const ask = async () => question;
const frozen = async (_, history) => prediction(history.length);

async function completed(title) {
  const id = randomUUID();
  await store.lockEntry(id, { ...measure, title }, frozen);
  await store.recordVote(id, "no", "I want an independent inspection first.");
  return id;
}

test("follow-up stays post-vote, freezes once, and one durable answer informs only future forecasts", async t => {
  const dir = await privateDirectory(t);
  const id = randomUUID();
  const locked = await store.lockEntry(id, measure, frozen);
  const never = () => assert.fail("Unexpected policy call");
  await assert.rejects(store.suggestFollowUp(id, 0, never), { status: 409 });
  await assert.rejects(store.respondToFollowUp(id, 0, question.prompt, "inspection"), { status: 409 });
  assert.deepEqual(await store.listEntries(), [locked]);
  const voted = await store.recordVote(id, "no", "I want an independent inspection first.");
  await assert.rejects(store.suggestFollowUp(id, 0, async () => ({ ...question, referenceId: id })), { status: 502 });
  const pending = await store.suggestFollowUp(id, 0, ask);
  assert.deepEqual(pending, { ...voted, followUp: { status: "pending", question } });
  assert.deepEqual(await store.suggestFollowUp(id, 0, never), pending);
  const early = randomUUID();
  await store.lockEntry(early, measure, async (_, history) => {
    assert.deepEqual(history, [voted]);
    return prediction(1);
  });
  const answer = "An independent inspection would change my mind.";
  await assert.rejects(store.respondToFollowUp(id, 0, question.prompt, " "), { status: 400 });
  await assert.rejects(store.respondToFollowUp(id, 0, "A stale prompt", answer), { status: 409 });
  const result = await store.respondToFollowUp(id, 0, question.prompt, answer);
  assert.deepEqual(result, { ...voted, followUp: { question, status: "answered", answer } });
  const independent = await import("../lib/personal-journal-store.ts?response-retry");
  assert.deepEqual(await independent.respondToFollowUp(id, 0, question.prompt, answer), result);
  await assert.rejects(store.respondToFollowUp(id, 0, question.prompt, null), { status: 409 });
  const late = randomUUID();
  await store.lockEntry(late, measure, async (_, history) => {
    assert.deepEqual(history, [result]);
    return prediction(1);
  });
  const forecastFile = async id => JSON.parse(await readFile(join(dir, id + ".forecast.json"), "utf8"));
  assert.equal((await forecastFile(early)).eligibleClarificationIds, undefined);
  assert.deepEqual((await forecastFile(late)).eligibleClarificationIds, [id]);
  assert.deepEqual((await forecastFile(id)).prediction, voted.prediction);
});

test("a retrospective question uses the target's frozen history, excluding later answers, edits and votes", async t => {
  await privateDirectory(t);
  const first = await completed("Early bridge measure");
  const second = await completed("Another early measure");
  await store.suggestFollowUp(second, 0, ask);
  await store.respondToFollowUp(second, 0, question.prompt, "Only after an inspection.");
  const target = await completed("Target");
  await completed("Later proposal");
  await store.suggestFollowUp(first, 0, ask);
  await store.respondToFollowUp(first, 0, question.prompt, "An answer given after the target.");
  await store.correctEntry(second, 0, "revealed", { ...measure, title: "Corrected afterwards" }, frozen);
  const picked = await store.suggestFollowUp(target, 0, async (voted, history) => {
    assert.equal(voted.id, target);
    assert.deepEqual(history.map(entry => entry.id), [first, second]);
    assert.equal(history[0].followUp, undefined);
    assert.equal(history[1].measure.title, "Another early measure");
    assert.equal(history[1].followUp.answer, "Only after an inspection.");
    return { ...question, referenceId: second };
  });
  assert.equal(picked.followUp.question.referenceId, second);
  const now = (await store.listEntries()).find(entry => entry.id === second);
  assert.equal(now.followUp, undefined);
  assert.equal(now.archivedFollowUp.answer, "Only after an inspection.");
  await store.lockEntry(randomUUID(), measure, async (_, history) => {
    const corrected = history.find(entry => entry.id === second);
    assert.equal(corrected.followUp, undefined);
    assert.equal(corrected.archivedFollowUp, undefined);
    return prediction(history.length);
  });
  assert.deepEqual(await store.suggestFollowUp(second, 1, () => assert.fail("Corrected forecast misattributed")), now);
  await assert.rejects(store.respondToFollowUp(second, 0, question.prompt, "Stale"), { status: 409 });
  const voted = (await store.listEntries()).find(entry => entry.id === target);
  await store.correctEntry(target, 0, "revealed", { ...measure, title: "Later edit to target" }, frozen);
  const replay = await store.readRegressionCase(target);
  assert.deepEqual(replay.request.measure, voted.measure);
  assert.deepEqual(replay.locked, voted.prediction);
  assert.equal(replay.vote, voted.vote);
  assert.deepEqual(Object.keys(replay.request).sort(), ["history", "id", "measure"]);
  assert.deepEqual(replay.request.history.map(row => row.id), [first, second]);
  assert.equal(replay.request.history[0].clarification, undefined);
  assert.equal(replay.request.history[1].measure.title, "Another early measure");
  assert.equal(replay.request.history[1].clarification.answer, "Only after an inspection.");
});

test("concurrent answers and skips can only resolve a question once, and no-question decisions persist", async t => {
  await privateDirectory(t);
  const id = await completed("An eligible measure");
  const independent = await import("../lib/personal-journal-store.ts?question-race");
  const two = await Promise.all([store, independent].map((api, i) =>
    api.suggestFollowUp(id, 0, async () => ({ ...question, prompt: question.prompt + i }))));
  assert.deepEqual(two[0], two[1]);
  const prompt = two[0].followUp.question.prompt;
  const attempts = await Promise.allSettled([
    store.respondToFollowUp(id, 0, prompt, null),
    independent.respondToFollowUp(id, 0, prompt, "Inspection"),
  ]);
  assert.equal(attempts.filter(r => r.status === "fulfilled").length, 1);
  assert.equal(attempts.filter(r => r.status === "rejected" && r.reason.status === 409).length, 1);
  const unneeded = await completed("No follow-up needed");
  const reviewed = await store.suggestFollowUp(unneeded, 0, async () => null);
  assert.equal(reviewed.followUp, undefined);
  assert.equal(reviewed.followUpReviewed, true);
  assert.deepEqual(await independent.suggestFollowUp(unneeded, 0, () => assert.fail("Policy reran")), reviewed);
  const skipped = await completed("Another choice");
  await store.suggestFollowUp(skipped, 0, ask);
  const value = await store.respondToFollowUp(skipped, 0, question.prompt, null);
  assert.equal(value.followUp.status, "skipped");
  assert.deepEqual(await independent.respondToFollowUp(skipped, 0, question.prompt, null), value);
});

function comparison(count, version = "reasoning-examples-v2") {
  return {
    reasoning: { ...prediction(count), model: version },
    baseline: { ...prediction(count, "no"), model: "outcome-wording-v1" },
    withoutReasoning: { ...prediction(count, "no"), model: version + "-without-reasoning" },
  };
}

test("five slots share frozen evidence across restarts, votes, late answers and corrections", async t => {
  await privateDirectory(t);
  const early = await completed("Early measure");
  const second = await completed("Second measure");
  await store.suggestFollowUp(early, 0, ask);
  await store.respondToFollowUp(early, 0, question.prompt, "Include an independent audit.");
  const old = (await store.listEntries()).find(entry => entry.id === early);
  const independent = await import("../lib/personal-journal-store.ts?comparison-reload");
  assert.equal(await store.getCheck(), null);
  const [check, same] = await Promise.all([store.startCheck(), independent.startCheck()]);
  assert.deepEqual(check, same);
  assert.deepEqual(await independent.getCheck(), check);
  assert.equal(check.modelVersion, "reasoning-examples-v2");
  assert.equal(check.evidenceCount, 2);
  assert.equal(check.clarificationCount, 1);
  assert.equal(new Set(check.slotIds).size, 5);

  const predict = async (_packet, history, version) => {
    assert.equal(version, check.modelVersion);
    assert.deepEqual(history.map(entry => entry.id).sort(), [early, second].sort());
    assert.deepEqual(history.find(entry => entry.id === early), old);
    assert.equal(history.find(entry => entry.id === second).followUp, undefined);
    return comparison(history.length);
  };
  const first = { ...measure, title: "Unseen A" };
  const locked = await store.lockEntry(check.slotIds[0], first, predict, check.id);
  assert.deepEqual(Object.keys(locked).sort(), ["checkId", "id", "lockedAt", "measure", "status"]);
  assert.deepEqual(await independent.lockEntry(locked.id, first, () => assert.fail("Unexpected re-lock"), check.id), locked);
  const revealed = await store.recordVote(locked.id, "yes", "Fund the repairs now.");
  assert.deepEqual(revealed.comparison, { baseline: comparison(2).baseline, withoutReasoning: comparison(2).withoutReasoning });
  assert.deepEqual(revealed.prediction, comparison(2).reasoning);
  assert.equal(revealed.checkId, check.id);
  await store.correctEntry(early, 0, "revealed", { ...old.measure, title: "Corrected after freeze" }, () => assert.fail());
  await store.suggestFollowUp(second, 0, ask);
  await store.respondToFollowUp(second, 0, question.prompt, "This answer came too late.");
  const later = await store.lockEntry(randomUUID(), { ...measure, title: "Familiar later measure", familiar: true }, frozen);
  await store.recordVote(later.id, "yes", "A later choice.");
  assert.deepEqual(await store.startCheck(), check);
  for (const [i, id] of check.slotIds.slice(1).entries()) {
    const packet = { ...measure, title: "Another unseen measure " + i };
    const next = await independent.lockEntry(id, packet, predict, check.id);
    assert.equal(next.status, "locked");
    assert.equal(next.comparison, undefined);
    const amended = await store.correctEntry(id, 0, "locked", { ...packet, text: "Corrected text" }, predict);
    assert.equal(amended.checkId, check.id);
    assert.equal(amended.comparison, undefined);
    await assert.rejects(store.recordVote(id, "yes", "Stale"), { status: 409 });
    const voted = await store.recordVote(id, "yes", "Supports repairs", 1);
    assert.deepEqual(voted.comparison, revealed.comparison);
    const post = await store.correctEntry(id, 1, "revealed", { ...packet, title: "Corrected title " + i },
      () => assert.fail("A post-vote correction reran inference"));
    assert.deepEqual(post.forecastMeasure, amended.measure);
    assert.deepEqual(post.comparison, voted.comparison);
  }
  assert.deepEqual((await store.listEntries()).find(entry => entry.id === locked.id), revealed);
  assert.equal((await store.listEntries()).filter(entry => entry.checkId === check.id).length, 5);
  const after = await store.lockEntry(randomUUID(), { ...measure, title: "After all five" }, frozen);
  assert.equal(after.checkId, undefined);
  assert.equal((await store.recordVote(after.id, "no", "Previous system works.")).comparison, undefined);
});

test("only unseen entries fill check slots and all three forecasts publish together", async t => {
  await privateDirectory(t);
  const prior = await completed("Previously seen measure");
  const oldPending = await store.lockEntry(randomUUID(), { ...measure, title: "Ordinary pending measure" }, frozen);
  const check = await store.startCheck();
  const [first, second] = check.slotIds;
  const predict = async () => comparison(1);
  const never = () => assert.fail("An ineligible request reached the model");
  await assert.rejects(store.lockEntry(prior, measure, never, check.id), { status: 409 });
  await assert.rejects(store.lockEntry(first, measure, never, randomUUID()), { status: 409 });
  await assert.rejects(store.lockEntry(first, measure, never), { status: 409 });
  await assert.rejects(store.lockEntry(randomUUID(), measure, never), { status: 409 });
  assert.deepEqual(await store.lockEntry(oldPending.id, oldPending.measure, never), oldPending);
  const edited = await store.correctEntry(oldPending.id, 0, "locked", { ...oldPending.measure, title: "Old pending" }, frozen);
  assert.equal(edited.checkId, undefined);
  await assert.rejects(store.lockEntry(second, measure, never, check.id), { status: 409 });
  await assert.rejects(store.lockEntry(first, { ...measure, familiar: true }, never, check.id), { status: 400 });
  await assert.rejects(store.lockEntry(first, { ...measure, title: " previously  SEEN measure" }, never, check.id), { status: 409 });
  await assert.rejects(store.lockEntry(first, measure, async () => prediction(1), check.id), { status: 502 });
  await assert.rejects(store.lockEntry(first, measure, async () => ({ ...comparison(1), baseline: undefined }), check.id), { status: 502 });
  await assert.rejects(store.lockEntry(first, measure, async () => ({ ...comparison(1), baseline: comparison(0).baseline }), check.id), { status: 502 });
  await assert.rejects(store.lockEntry(first, measure, async () => comparison(1, "reasoning-examples-v1"), check.id), { status: 502 });
  assert.deepEqual((await store.listEntries()).map(entry => entry.id).sort(), [oldPending.id, prior].sort());
  await store.lockEntry(first, measure, predict, check.id);
  await assert.rejects(store.lockEntry(second, measure, never, check.id), { status: 409 });
  await store.lockEntry(second, { ...measure, title: "Different measure on the same official guide" }, predict, check.id);
});

test("a check started before versioning completes its remaining slots with v1", async t => {
  const dir = await privateDirectory(t);
  const id = randomUUID();
  const first = randomUUID();
  const oldCheck = { id, startedAt: new Date().toISOString(), evidenceCount: 0,
    clarificationCount: 0, slotIds: [first, ...Array.from({ length: 4 }, () => randomUUID())] };
  await writeFile(join(dir, "five-measure-check.json"), JSON.stringify({
    check: oldCheck, evidence: { eligibleHistoryIds: [] },
  }));
  assert.deepEqual(await store.startCheck(), oldCheck);
  await store.lockEntry(first, measure, async (_packet, _history, version) => {
    assert.equal(version, "reasoning-examples-v1");
    return comparison(0, version);
  }, id);
  const result = await store.recordVote(first, "no", "Keep the existing arrangement.");
  assert.equal(result.prediction.model, "reasoning-examples-v1");
  assert.equal(result.comparison.withoutReasoning.model, "reasoning-examples-v1-without-reasoning");
});
