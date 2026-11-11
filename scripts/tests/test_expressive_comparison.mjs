// Checks the actual Python response against the browser/server Zod contract.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";
import ts from "typescript";
import * as zod from "zod";

const root = fileURLToPath(new URL("../../", import.meta.url));
function loadSchema(relativePath, dependencies) {
  const { outputText } = ts.transpileModule(readFileSync(join(root, relativePath), "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  });
  const exports = {};
  runInThisContext(`(function(exports, require) { ${outputText}\n })`)(exports, (name) => {
    assert.ok(name in dependencies, `Unexpected dependency: ${name}`);
    return dependencies[name];
  });
  return exports;
}
const scalar = loadSchema("lib/validations/expressive-scalar.ts", { zod });
const { scalarComparisonRequestSchema, scalarComparisonResponseSchema } = loadSchema(
  "lib/validations/expressive-comparison.ts",
  { zod, "@/lib/validations/expressive-scalar": scalar },
);
const baseline = {
  ballot: { ideal: 4.55, lower_half_width: 2, upper_half_width: 2, approval_min: 0, approval_max: 100, probe: 4.55 },
  binary_vote: "no",
};

test("comparison requires a separate explicit binary answer", () => {
  assert.ok(scalarComparisonRequestSchema.safeParse(baseline).success);
  for (const binary_vote of [undefined, true, "approve", "abstain"]) {
    assert.equal(scalarComparisonRequestSchema.safeParse({ ...baseline, binary_vote }).success, false);
  }
  assert.equal(scalarComparisonRequestSchema.safeParse({ ...baseline, ballot: { ...baseline.ballot, approval_min: 7 } }).success, false);
});

test("the richer ballot accepts the full theoretical range and rejects rates beyond it", () => {
  for (const ideal of [0, 50, 98, 100]) {
    assert.ok(scalarComparisonRequestSchema.safeParse({ ...baseline, ballot: { ...baseline.ballot, ideal, probe: ideal, lower_half_width: 100, upper_half_width: 100 } }).success);
  }
  for (const invalid of [-0.05, 100.05, Infinity, NaN]) {
    for (const key of ["ideal", "approval_min", "approval_max", "probe"]) {
      assert.equal(scalarComparisonRequestSchema.safeParse({ ...baseline, ballot: { ...baseline.ballot, [key]: invalid } }).success, false);
    }
  }
  assert.equal(scalarComparisonRequestSchema.safeParse({ ...baseline, ballot: { ...baseline.ballot, upper_half_width: 100.05 } }).success, false);
});

test("Python comparison payloads satisfy the frontend contract and its reconciliation guards", () => {
  const python = process.env.EXPRESSIVE_TEST_PYTHON || [
    join(root, "venv", "Scripts", "python.exe"), join(root, "venv", "bin", "python"),
  ].find(existsSync) || "python";
  const requests = [
    baseline,
    { ...baseline, binary_vote: "yes" },
    { ...baseline, ballot: { ...baseline.ballot, ideal: 6.123, approval_min: 6.123, approval_max: 6.123 } },
    { ...baseline, ballot: { ...baseline.ballot, ideal: 100, probe: 100, lower_half_width: 100, upper_half_width: 100 } },
    { ...baseline, ballot: { ...baseline.ballot, ideal: 0, probe: 0 } },
    baseline,
  ];
  const reference = spawnSync(python, ["-c", `
import asyncio, json, sys
import httpx
from api.main import app
async def run():
    results = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for body in json.load(sys.stdin):
            response = await client.post("/api/expressive/scalar/compare", json=body)
            response.raise_for_status()
            results.append(response.json())
    json.dump(results, sys.stdout, allow_nan=False)
asyncio.run(run())
`], { cwd: root, input: JSON.stringify(requests), encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  assert.equal(reference.status, 0, reference.error?.message || reference.stderr);
  const results = JSON.parse(reference.stdout);
  results.forEach((result) => assert.doesNotThrow(() => scalarComparisonResponseSchema.parse(result)));
  for (const [index, result] of results.entries()) {
    assert.equal(result.model, "scalar-comparison-v4");
    assert.equal(result.status_quo, 4.55);
    assert.equal(result.proposal, 4.4);
    assert.equal(result.electorate.voters.length, 100);
    assert.equal(new Set(result.electorate.voters.map((voter) => voter.id)).size, 100);
    const user = result.electorate.voters.find((voter) => voter.id === "you");
    const submittedBallot = Object.fromEntries(Object.entries(requests[index].ballot).filter(([key]) => key !== "probe"));
    assert.deepEqual(user.ballot, submittedBallot);
    assert.equal(user.binary_vote, requests[index].binary_vote);
    assert.equal(result.points.length, 2001);
    assert.equal(result.points[0].rate, 0);
    assert.equal(result.points.at(-1).rate, 100);
    assert.equal(result.points[91].mean_score, result.pair.status_quo_mean);
    assert.equal(result.points[88].mean_score, result.pair.proposal_mean);
    assert.deepEqual(
      result.electorate.voters.filter((voter) => voter.id !== "you"),
      results[0].electorate.voters.filter((voter) => voter.id !== "you"),
      "Editing the submitted ballot must preserve the 99 fictional voters",
    );
  }
  assert.deepEqual(results[0], results.at(-1), "The same request must reproduce the whole electorate and result");
  assert.equal(results[1].user_binary_vote, "yes");
  assert.equal(results[1].user_curve_vote, "no", "An explicit answer can disagree with the richer ballot");
  assert.equal(results[3].points.at(-1).user_score, 1, "A 100% ideal must be scored at the domain boundary");
  assert.equal(results[4].points[0].user_score, 1, "A 0% ideal must be scored at the domain boundary");
  assert.equal(results[2].user_curve_vote, "abstain", "Both offered rates can fall outside an approval interval");
  const prepared = results[0].electorate.voters.filter((voter) => voter.id !== "you");
  assert.equal(new Set(prepared.map((voter) => JSON.stringify(voter.ballot))).size, 99, "Prepared voters have individual curves");

  const corruptions = [
    ["irregular candidate grid", (result) => { result.points[4].rate = 0.45; }],
    ["tally count", (result) => { result.binary.yes += 1; }],
    ["unoffered binary outcome", (result) => { result.binary.outcome_rate = 5; }],
    ["incorrect binary passage", (result) => { result.binary.passed = !result.binary.passed; }],
    ["direct preference count", (result) => { result.points[50].prefer_this += 1; }],
    ["duplicate voter", (result) => { result.electorate.voters[1].id = result.electorate.voters[0].id; }],
    ["missing submitted voter", (result) => { result.electorate.voters.find((voter) => voter.id === "you").id = "someone-else"; }],
    ["synthetic explicit answer", (result) => {
      const voter = result.electorate.voters.find((entry) => entry.id !== "you");
      voter.binary_vote = voter.curve_vote === "yes" ? "no" : "yes";
    }],
    ["curve answer contradicts scores", (result) => {
      const voter = result.electorate.voters[0];
      voter.curve_vote = voter.curve_vote === "yes" ? "no" : "yes";
    }],
    ["submitted answer lost", (result) => { result.user_binary_vote = "yes"; }],
    ["pair scores no longer reconcile", (result) => { result.electorate.voters[0].proposal_score = 0.123456789; }],
    ["incorrect pair mean", (result) => { result.pair.proposal_mean = 0.123456789; }],
    ["incorrect pair winner", (result) => { result.pair.winner_rates = [4.4, 4.55]; }],
    ["off-grid richer winner", (result) => { result.winner_rates = [6.123]; }],
    ["duplicate richer winner", (result) => { result.winner_rates.push(result.winner_rates[0]); }],
    ["incorrect maximum", (result) => { result.max_mean_score = 0; }],
    ["submitted pair score lost", (result) => { result.points[91].user_score = 0; }],
    ["incorrect approval count", (result) => {
      const point = result.points[50];
      point.approval_count = point.approval_count === 100 ? 99 : point.approval_count + 1;
    }],
    ["comparing a rate with itself", (result) => {
      Object.assign(result.points[Math.round(result.binary.outcome_rate * 20)], { prefer_this: 1, prefer_binary: 0, indifferent: 99 });
    }],
    ["short electorate", (result) => { result.electorate.voters.pop(); }],
    ["empty candidate grid", (result) => { result.points = []; }],
  ];
  corruptions.forEach(([name, corrupt]) => {
    const changed = structuredClone(results[0]);
    corrupt(changed);
    assert.equal(scalarComparisonResponseSchema.safeParse(changed).success, false, name);
  });

  const clipped = structuredClone(results[2]);
  clipped.points[0].user_approved = true;
  assert.equal(scalarComparisonResponseSchema.safeParse(clipped).success, false, "Approval flags must match the displayed user interval");

  // Exercise preservation of multiple maxima without duplicating the Python rule.
  const tied = structuredClone(results[0]);
  const extraWinner = tied.points.find((point) => point.rate !== 4.4 && point.rate !== 4.55 && !tied.winner_rates.includes(point.rate));
  extraWinner.mean_score = tied.max_mean_score;
  tied.winner_rates.push(extraWinner.rate);
  assert.ok(scalarComparisonResponseSchema.safeParse(tied).success, "All declared grid maximizers can be retained");
  tied.winner_rates.pop();
  assert.equal(scalarComparisonResponseSchema.safeParse(tied).success, false, "A co-maximizer must not be silently dropped");
});
