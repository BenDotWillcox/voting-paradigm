import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInThisContext } from "node:vm";
import ts from "typescript";

const { outputText } = ts.transpileModule(
  readFileSync(new URL("../../lib/request-deadline.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } },
);
const exports = {};
runInThisContext(`(function(exports) { ${outputText}\n })`)(exports);
const { withRequestDeadline, RequestTimeoutError } = exports;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

test("a healthy response clears its deadline and cancellation listener", async () => {
  const parent = new AbortController();
  let transportSignal;
  const value = await withRequestDeadline(async (signal) => {
    transportSignal = signal;
    return { count: 101 };
  }, { timeoutMs: 10, signal: parent.signal });
  assert.deepEqual(value, { count: 101 });
  parent.abort();
  await wait(15);
  assert.equal(transportSignal.aborted, false);
});

test("network and synchronous startup failures propagate immediately", async () => {
  const failure = new TypeError("Network failed");
  await assert.rejects(withRequestDeadline(async () => { throw failure; }, { timeoutMs: 100 }), (e) => e === failure);
  await assert.rejects(withRequestDeadline(() => { throw failure; }, { timeoutMs: 100 }), (e) => e === failure);
});

test("stalled fetch expires even if its transport ignores abort", async () => {
  let transportSignal;
  await assert.rejects(withRequestDeadline((signal) => {
    transportSignal = signal;
    return new Promise(() => {});
  }, { timeoutMs: 5 }), RequestTimeoutError);
  assert.equal(transportSignal.aborted, true);
  assert.ok(transportSignal.reason instanceof RequestTimeoutError);
});

test("deadline covers the response body after headers arrive", async () => {
  const body = deferred();
  let headersRead = false;
  await assert.rejects(withRequestDeadline(async () => {
    const response = await Promise.resolve({ json: () => body.promise });
    headersRead = true;
    return response.json();
  }, { timeoutMs: 5 }), RequestTimeoutError);
  assert.equal(headersRead, true);
  body.resolve({ stale: true });
});

test("supersession aborts active transport and rejects separately from a timeout", async () => {
  const parent = new AbortController();
  let transportSignal;
  const request = withRequestDeadline((signal) => {
    transportSignal = signal;
    return new Promise(() => {});
  }, { timeoutMs: 100, signal: parent.signal });
  const check = assert.rejects(request, (e) => e.name === "AbortError" && !(e instanceof RequestTimeoutError));
  parent.abort();
  await check;
  assert.equal(transportSignal.aborted, true);
});

test("already cancelled work is never started", async () => {
  const parent = new AbortController();
  parent.abort();
  let started = false;
  await assert.rejects(withRequestDeadline(async () => { started = true; }, {
    timeoutMs: 5, signal: parent.signal,
  }), { name: "AbortError" });
  assert.equal(started, false);
});

test("a failed request can be retried; its late completion cannot replace the retry", async () => {
  const old = deferred();
  const first = withRequestDeadline(() => old.promise, { timeoutMs: 5 });
  await assert.rejects(first, RequestTimeoutError);
  const second = await withRequestDeadline(async () => ({ count: 102 }), { timeoutMs: 100 });
  old.resolve({ count: 101 });
  assert.deepEqual(second, { count: 102 });
  await assert.rejects(first, RequestTimeoutError);
});

test("late rejection after a timeout remains handled", async () => {
  const old = deferred();
  await assert.rejects(withRequestDeadline(() => old.promise, { timeoutMs: 5 }), RequestTimeoutError);
  old.reject(new Error("The upstream eventually failed"));
  await wait(0);
});
