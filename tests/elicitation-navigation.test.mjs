// Run with: node --test tests/elicitation-navigation.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { compileFunction } from "node:vm";
import { test } from "node:test";
import ts from "typescript";

const filename = fileURLToPath(new URL("../lib/preferences/elicitation-navigation.ts", import.meta.url));
const { outputText } = ts.transpileModule(readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  fileName: filename,
});
const exports = {};
compileFunction(outputText, ["exports"], { filename })(exports);
const { replaceReviewedResponse } = exports;

const answer = (id, position) => ({
  action: "answer", question_id: id, question_version: 1, position,
  reported_uncertainty: { sd_fraction: 0.12 }, acceptable_range: null,
});
const nonAnswer = (id, action) => ({ action, question_id: id, question_version: 1 });

test("revising an earlier answer preserves every later response and the original summary", () => {
  const recorded = [answer("one", 20), nonAnswer("two", "skip"), nonAnswer("three", "depends"), answer("four", 5)];
  const before = structuredClone(recorded);
  const replacement = answer("one", 21);
  const submitted = replaceReviewedResponse(recorded, 0, replacement);
  assert.deepEqual(recorded, before, "A draft update cannot mutate the currently recorded summary");
  assert.equal(submitted.length, 4);
  assert.equal(submitted[0], replacement);
  for (let index = 1; index < recorded.length; index += 1) {
    assert.equal(submitted[index], recorded[index]);
  }
});

test("an explicit answer can replace skip or depends without duplicating its question", () => {
  for (const action of ["skip", "depends"]) {
    const recorded = [answer("one", 20), nonAnswer("two", action), answer("three", 21)];
    const updated = replaceReviewedResponse(recorded, 1, answer("two", 60));
    assert.deepEqual(updated.map((event) => event.question_id), ["one", "two", "three"]);
    assert.equal(updated[1].action, "answer");
    assert.equal(recorded[1].action, action);
    assert.equal(updated[2], recorded[2]);
  }
});

test("an explicit non-answer replaces a numeric answer without retaining numeric fields", () => {
  for (const action of ["skip", "depends"]) {
    const updated = replaceReviewedResponse([answer("one", 20)], 0, nonAnswer("one", action));
    assert.deepEqual(updated, [nonAnswer("one", action)]);
    assert.equal(Object.hasOwn(updated[0], "position"), false);
  }
});

test("first and subsequent new responses append only at the next unreviewed question", () => {
  const first = answer("one", 20);
  assert.deepEqual(replaceReviewedResponse([], 0, first), [first]);
  const second = nonAnswer("two", "skip");
  assert.deepEqual(replaceReviewedResponse([first], 1, second), [first, second]);
  for (const index of [-1, 0.5, 2, NaN]) {
    assert.throws(() => replaceReviewedResponse([first], index, second), /reviewed prefix/);
  }
});

test("replacement cannot silently change the question or its version", () => {
  const recorded = [answer("one", 20)];
  assert.throws(() => replaceReviewedResponse(recorded, 0, answer("other", 20)), /same question/);
  assert.throws(() => replaceReviewedResponse(recorded, 0, { ...answer("one", 20), question_version: 2 }), /same question/);
});
