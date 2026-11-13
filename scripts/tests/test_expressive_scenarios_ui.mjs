// Render the actual result copy and controls against the Python API's scenarios.
// Internal exports are added only in this test's transpilation, not the app API.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";
import * as React from "react";
import * as jsxRuntime from "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const baseline = {
  ballot: { ideal: 4.55, lower_half_width: 2, upper_half_width: 2, approval_min: 0, approval_max: 100, probe: 4.55 },
  binary_vote: "no",
};
const scenarioNames = ["prepared", "broad-agreement", "polarized", "intense-minority"];
let fixtures;
let tied;
let pairTied;
let binaryIncludedTie;
let unchanged;
before(() => {
  const python = process.env.EXPRESSIVE_TEST_PYTHON || [join(root, "venv", "Scripts", "python.exe"), join(root, "venv", "bin", "python")].find(existsSync) || "python";
  const requests = scenarioNames.map((scenario) => ({ ...baseline, scenario }));
  const reference = spawnSync(python, ["-c", `
import asyncio, json, sys
from dataclasses import asdict
from unittest.mock import patch
import httpx
from api.main import app
from expressive.comparison import ComparisonElectorate, ComparisonVoter, aggregate_electorate, curve_vote
from expressive.scalar import ScalarBallot

async def authored_result(client, name, low, high, user, vote):
    # Copy-only boundary fixtures are deliberately separate from the varied
    # production presets. The real domain evaluator and API schema compute them.
    background = [low] * 49 + [high] * 50
    voters = tuple(ComparisonVoter(f"voter-{index}", f"Voter {index}", ballot, curve_vote(ballot))
                   for index, ballot in enumerate(background))
    electorate = ComparisonElectorate(f"ui-test-{name}", "UI boundary fixture", "Hand-authored UI test only.",
                                     0, (*voters, ComparisonVoter("you", "You", user, vote)))
    result = aggregate_electorate(electorate)
    body = {"ballot": {**asdict(user), "probe": user.ideal}, "binary_vote": vote, "scenario": "prepared"}
    with patch("api.services.expressive_comparison.compare_ballots", return_value=result):
        response = await client.post("/api/expressive/scalar/compare", json=body)
    response.raise_for_status()
    return response.json()

async def run():
    results = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for body in json.load(sys.stdin):
            response = await client.post("/api/expressive/scalar/compare", json=body)
            response.raise_for_status()
            results.append(response.json())
        full_tie = await authored_result(client, "full-tie", ScalarBallot(3, .6, .6, 2, 4.4),
                                        ScalarBallot(5.95, .6, .6, 4.55, 7), ScalarBallot(3, .1, .1, 3, 3), "yes")
        pair_tie = await authored_result(client, "pair-tie", ScalarBallot(4.4, .1, .1, 4.4, 4.4),
                                        ScalarBallot(4.55, .1, .1, 4.55, 4.55), ScalarBallot(4.4, .1, .1, 4.4, 4.4), "yes")
        binary_tie = await authored_result(client, "binary-included-tie", ScalarBallot(4.55, .1, .1, 4.55, 4.55),
                                          ScalarBallot(5.95, .1, .1, 5.95, 5.95), ScalarBallot(4.55, .1, .1, 4.55, 4.55), "no")
        unanimous = ScalarBallot(4.4, 1, 1, 3, 6)
        unchanged = await authored_result(client, "unchanged", unanimous, unanimous, unanimous, "yes")
    json.dump({"scenarios": results, "full_tie": full_tie, "pair_tie": pair_tie,
               "binary_tie": binary_tie, "unchanged": unchanged}, sys.stdout, allow_nan=False)
asyncio.run(run())
`], { cwd: root, input: JSON.stringify(requests), encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  assert.equal(reference.status, 0, reference.error?.message || reference.stderr);
  const results = JSON.parse(reference.stdout);
  fixtures = Object.fromEntries(scenarioNames.map((name, index) => [name, results.scenarios[index]]));
  tied = results.full_tie;
  pairTied = results.pair_tie;
  binaryIncludedTie = results.binary_tie;
  unchanged = results.unchanged;
});

const source = readFileSync(join(root, "components/expressive/electorate-results.tsx"), "utf8");
const { outputText } = ts.transpileModule(`${source}\nexport { ScenarioSelector, WhatToNotice, AggregateResults };`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
});
const exports = {};
const dependencies = {
  // Static copy tests have no layout. Before-paint effects are exercised by
  // test_expressive_layout.mjs instead of running DOM measurement during SSR.
  react: { ...React, useLayoutEffect: React.useEffect },
  "react/jsx-runtime": jsxRuntime,
  "next/link": { default: ({ children, ...props }) => React.createElement("a", props, children) },
  "lucide-react": Object.fromEntries(["ArrowDown", "ArrowRight", "ChevronLeft", "ChevronRight"].map((name) => [name, () => null])),
  "@/lib/expressive-scalar-graph": {
    SCALAR_DOMAIN: { minimum: 0, maximum: 100 },
    scalarFocusRange: () => ({ minimum: 0, maximum: 100 }),
    scalarPresentationPreview: () => ({ points: [] }),
    scalarTransitionTicks: () => [],
  },
  "@/lib/use-scalar-viewport": { useScalarViewport: (initial) => ({ view: initial, from: initial, target: initial, progress: 1, setView() {} }) },
  "./electorate-results.module.css": { default: new Proxy({}, { get: (_, name) => name }) },
};
runInThisContext(`(function(exports, require) { ${outputText}\n })`)(exports, (name) => {
  assert.ok(name in dependencies, `Unexpected UI dependency: ${name}`);
  return dependencies[name];
});
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
const plainText = (html) => html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
const notice = (data) => plainText(render(exports.WhatToNotice, { data }));
const controls = { onScenarioChange() {}, scenarioPending: null, scenarioError: null, onRetryScenario() {}, scenarioDisabled: false };
function button(html, label) {
  const found = [...html.matchAll(/<button\b[^>]*>[\s\S]*?<\/button>/g)].find(([markup]) => plainText(markup).includes(label));
  assert.ok(found, `Missing button: ${label}`);
  return found[0];
}
function winnerPoint(data) {
  assert.equal(data.winner_rates.length, 1, "The baseline scenario should have a single maximum");
  return data.points.find((point) => point.rate === data.winner_rates[0]);
}
function assertWinnerCopy(text, point) {
  assert.ok(text.includes(`Opening the full range selects ${point.rate.toFixed(2)}%.`), "The copy must name the returned winner");
  assert.ok(text.includes(`${point.approval_count} of 100 voters include the rate in their approval band`), "The copy must use the returned approval count");
  assert.ok(text.includes(`${point.prefer_this} prefer this rate`), "The copy must use the returned preference count");
  assert.ok(text.includes(`${point.prefer_binary} prefer the yes/no outcome`), "The copy must use the returned opposing preference count");
  assert.ok(text.includes(`${point.indifferent} score them equally`), "The copy must use the returned indifference count");
}

test("broad agreement reports shared approval without implying identical preferences", () => {
  const data = fixtures["broad-agreement"];
  const point = winnerPoint(data);
  assert.ok(point.approval_count >= 90, "The agreement scenario should retain broad approval");
  assert.ok(point.mean_score > 0.9, "The agreement scenario should retain high shared scores");
  assert.notEqual(point.rate, data.binary.outcome_rate);
  const text = notice(data);
  assertWinnerCopy(text, point);
  assert.doesNotMatch(text, /full range also selects that same yes\/no outcome|all 100 voters score the comparison equally/);
});

test("polarization reports preference and approval counts without claiming pairwise defeat", () => {
  const data = fixtures.polarized;
  const point = winnerPoint(data);
  assert.ok(point.approval_count <= 60, "One camp's winner should not be described as broadly approved");
  assert.ok(point.prefer_this > point.prefer_binary);
  assert.ok(point.indifferent > 0, "Disjoint approval ranges leave some voters indifferent between these rates");
  const text = notice(data);
  assertWinnerCopy(text, point);
  assert.doesNotMatch(text, /More voters prefer the yes\/no outcome|does not have support from a majority/);
});

test("the minority case distinguishes highest average from the more-preferred outcome", () => {
  const data = fixtures["intense-minority"];
  const point = winnerPoint(data);
  assert.ok(data.binary.no > data.binary.yes);
  assert.ok(point.prefer_binary > point.prefer_this, "The minority example should retain its average-versus-preference distinction");
  assert.notEqual(data.pair.winner_rates[0], data.binary.outcome_rate);
  const text = notice(data);
  assert.ok(text.includes(`two-option result from ${data.binary.outcome_rate.toFixed(2)}% to ${data.pair.winner_rates[0].toFixed(2)}%`));
  assertWinnerCopy(text, point);
  assert.match(text, /More voters prefer the yes\/no outcome to this rate/);
  assert.match(text, /intensity means steeper differences in declared scores/);
  assert.match(text, /does not guarantee a compromise everyone prefers/);
});

test("an unchanged outcome is reported honestly using a computed boundary fixture", () => {
  assert.deepEqual(unchanged.winner_rates, [unchanged.binary.outcome_rate]);
  assert.deepEqual(unchanged.pair.winner_rates, unchanged.winner_rates);
  const text = notice(unchanged);
  assert.match(text, /original two-option result unchanged at 4\.40%/);
  assert.match(text, /full range also selects that same yes\/no outcome/);
  assert.match(text, /100 of 100 voters include the rate in their approval band/);
  assert.match(text, /all 100 voters score the comparison equally/);
});

test("a tied full-range maximum names its representative instead of implying a unique winner", () => {
  assert.deepEqual(tied.winner_rates, [3, 5.95]);
  const text = notice(tied);
  assert.match(text, /2 rates tie for the highest average/);
  assert.match(text, /At the lowest tied rate, 3\.00%/);
  assert.match(text, /50 prefer this rate.*50 prefer the yes\/no outcome.*0 score them equally/);
  assert.doesNotMatch(text, /full range selects 3\.00%/);
  const all = plainText(render(exports.AggregateResults, { data: tied, ballot: baseline.ballot, voters: [] }));
  assert.match(all, /The count is tied; the status quo remains/);
});

test("pair ties and a tied representative equal to the binary outcome remain explicit", () => {
  assert.deepEqual(new Set(pairTied.pair.winner_rates), new Set([4.4, 4.55]));
  assert.match(notice(pairTied), /two original rates tie on average score/);
  assert.equal(binaryIncludedTie.winner_rates.length, 2);
  assert.equal(binaryIncludedTie.winner_rates[0], binaryIncludedTie.binary.outcome_rate);
  const text = notice(binaryIncludedTie);
  assert.match(text, /yes\/no outcome is among them/);
  assert.match(text, /all 100 voters score the comparison equally/);
  assert.doesNotMatch(text, /More voters prefer the yes\/no outcome/);
});

test("a pending scenario keeps the loaded selection and other choices available", () => {
  const html = render(exports.ScenarioSelector, { ...controls, scenario: "broad-agreement", scenarioPending: "polarized" });
  assert.match(button(html, "Broad agreement"), /aria-pressed="true"/);
  assert.match(button(html, "Polarized electorate"), /aria-pressed="false"/);
  assert.match(button(html, "Polarized electorate"), /Loading/);
  assert.match(button(html, "Original electorate"), /Try this/);
  assert.match(button(html, "Original electorate"), /aria-pressed="false"/);
  assert.doesNotMatch(html, /\sdisabled=""/);
  assert.match(plainText(html), /All results still show Broad agreement/);
  assert.match(plainText(html), /submitted curve and explicit yes\/no answer stay the same/);
});

test("a fresh ballot disables scenario changes while failures retain a local retry", () => {
  const loading = render(exports.ScenarioSelector, { ...controls, scenario: "prepared", scenarioDisabled: true });
  assert.match(loading, /<fieldset disabled=""/);
  assert.match(plainText(loading), /results still show your previous submission/);
  const failed = render(exports.ScenarioSelector, { ...controls, scenario: "prepared", scenarioError: "The comparison took too long." });
  assert.match(failed, /role="alert"/);
  assert.match(button(failed, "Retry scenario"), /<button/);
  assert.match(button(failed, "Original electorate"), /aria-pressed="true"/);
  assert.match(plainText(failed), /All results still show Original electorate/);
});

test("four matching scenario cards follow the voter browser with the original selected initially", () => {
  const html = render(exports.ElectorateResults, { ...controls, data: fixtures.prepared, ballot: baseline.ballot });
  const text = plainText(html);
  assert.match(text, /Combine these 100 ballots/);
  assert.match(text, /Try a different electorate/);
  assert.match(html, /<div tabindex="-1" class="browserHeading">/, "The voter-browser destination must accept programmatic focus without joining the tab order");
  const grid = html.match(/<div class="scenarioGrid">([\s\S]*?)<\/div>/)?.[1];
  assert.ok(grid, "All electorate choices must share the card grid");
  const cards = [...grid.matchAll(/<button\b[^>]*>[\s\S]*?<\/button>/g)].map(([markup]) => markup);
  assert.equal(cards.length, 4);
  const labels = ["Original electorate", "Broad agreement", "Polarized electorate", "Intense minority"];
  for (const [index, label] of labels.entries()) {
    assert.ok(plainText(cards[index]).includes(label), `${label} must occupy its expected position in the grid`);
    assert.match(cards[index], /class="scenarioCard"/);
    assert.match(cards[index], index === 0 ? /aria-pressed="true"/ : /aria-pressed="false"/);
  }
  const landmarks = ["Browse all 100", "100 voters. One yes/no question.", "Try a different electorate", "Combine these 100 ballots"];
  let previousIndex = -1;
  for (const landmark of landmarks) {
    const index = text.indexOf(landmark);
    assert.ok(index > previousIndex, `${landmark} must appear after the preceding section`);
    previousIndex = index;
  }
  assert.doesNotMatch(text, /A collective score for every available rate|Richer scores, same two options|What to notice|Things to consider|How do we prepare a fair question/);
});

test("ballot-design considerations follow the combined chart and precede its tradeoffs", () => {
  const html = render(exports.AggregateResults, { data: fixtures.prepared, ballot: baseline.ballot, voters: [] });
  const landmarks = ['class="aggregateChart"', 'class="preferenceComparison"', 'class="considerations"', 'class="tradeoffs"'];
  let previousIndex = -1;
  for (const landmark of landmarks) {
    const index = html.indexOf(landmark);
    assert.ok(index > previousIndex, `${landmark} must follow the preceding combined-results content`);
    previousIndex = index;
  }
  assert.match(plainText(html), /Things to consider.*How do we prepare a fair question/);
});
