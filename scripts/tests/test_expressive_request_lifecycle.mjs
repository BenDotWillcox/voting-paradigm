// Exercise ScalarComparison's real async lifecycle with inert child components.
// Python -> Zod payload parity is covered by test_expressive_comparison.mjs;
// this host isolates transport, deadlines, retry, and request ownership.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { createContext, runInContext } from "node:vm";
import ts from "typescript";

const root = new URL("../../", import.meta.url);
const ballot = { ideal: 5.2, lower_half_width: 2, upper_half_width: 2, approval_min: 3, approval_max: 7, probe: 4.55 };
const nextBallot = { ...ballot, ideal: 6 };

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function createHost() {
  const hooks = [], effects = [], requests = [], timers = new Map(), attention = [];
  let cursor = 0, nextTimer = 1, dirty = true, tree, mounted = true, lateUpdates = 0, commit = 0;
  const jsx = (type, props, key) => ({ type, props: props ?? {}, key });
  const react = {
    useState(initial) {
      const slot = cursor++;
      if (!(slot in hooks)) hooks[slot] = typeof initial === "function" ? initial() : initial;
      return [hooks[slot], (value) => {
        if (!mounted) { lateUpdates++; return; }
        hooks[slot] = typeof value === "function" ? value(hooks[slot]) : value;
        dirty = true;
      }];
    },
    useRef(initial) {
      const slot = cursor++;
      return hooks[slot] ??= { current: initial };
    },
    useId() { cursor++; return "test-ballot"; },
    useEffect(effect, dependencies) {
      const slot = cursor++;
      const previous = hooks[slot];
      if (!previous || dependencies.some((dependency, index) => !Object.is(dependency, previous.dependencies[index]))) {
        effects.push(() => {
          previous?.cleanup?.();
          hooks[slot] = { dependencies, cleanup: effect() };
        });
      }
    },
  };
  const context = createContext({
    AbortController, DOMException, Promise,
    setTimeout(callback, delay) { const id = nextTimer++; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch(url, options) {
      const pending = deferred();
      requests.push({ ...pending, url, options });
      return pending.promise;
    },
    window: { matchMedia: () => ({ matches: true }) },
  });
  function load(relativePath, dependencies) {
    const source = readFileSync(new URL(relativePath, root), "utf8");
    const { outputText } = ts.transpileModule(source, {
      compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    });
    const exports = {};
    const factory = runInContext(`(function(exports, require) { ${outputText}\n })`, context, { filename: fileURLToPath(new URL(relativePath, root)) });
    factory(exports, (name) => {
      assert.ok(name in dependencies, `Unexpected dependency: ${name}`);
      return dependencies[name];
    });
    return exports;
  }
  const deadline = load("lib/request-deadline.ts", {});
  const { ScalarComparison } = load("components/expressive/scalar-comparison.tsx", {
    react,
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "./scalar-ballot": { ScalarBallot: "ScalarBallot" },
    "./income-tax-ballot": { IncomeTaxBallot: "IncomeTaxBallot" },
    "./electorate-results": { ElectorateResults: "ElectorateResults" },
    "@/lib/request-deadline": deadline,
    "@/lib/expressive-tax-measure": { TAX_MEASURE: { statusQuo: 4.55, proposal: 4.4 } },
    "@/lib/validations/expressive-comparison": {
      scalarComparisonResponseSchema: { safeParse: (body) => body?.valid ? { success: true, data: body } : { success: false } },
    },
    "./scalar-comparison.module.css": { default: {} },
  });
  function nodes(node = tree) {
    if (node == null || typeof node === "boolean") return [];
    if (Array.isArray(node)) return node.flatMap((child) => nodes(child));
    if (typeof node !== "object") return [];
    return [node, ...nodes(node.props?.children ?? null)];
  }
  function text(node = tree) {
    if (node == null || typeof node === "boolean") return "";
    if (Array.isArray(node)) return node.map((child) => text(child)).join(" ");
    return typeof node === "object" ? text(node.props?.children ?? null) : String(node);
  }
  async function flush() {
    for (let i = 0; i < 20; i++) {
      await Promise.resolve();
      if (mounted && dirty) {
        cursor = 0; dirty = false; tree = ScalarComparison();
        commit++;
        // React attaches child refs during commit, before passive effects. A
        // fresh target identifies which result was on screen when navigation
        // happened, catching a scroll that runs against the previous result.
        const result = child("ElectorateResults");
        if (result?.voterBrowserRef) {
          const target = result.data.id;
          const committedAt = commit;
          result.voterBrowserRef.current = {
            focus(options) { attention.push({ action: "focus", target, committedAt, options: JSON.parse(JSON.stringify(options)) }); },
            scrollIntoView(options) { attention.push({ action: "scroll", target, committedAt, options: JSON.parse(JSON.stringify(options)) }); },
          };
        }
        for (const effect of effects.splice(0)) effect();
      }
    }
  }
  const find = (predicate) => nodes().find(predicate);
  const child = (type) => find((node) => node.type === type)?.props;
  return {
    requests, timers, flush, text, child, attention,
    get lateUpdates() { return lateUpdates; },
    get busy() { return child("ScalarBallot").isSubmitting; },
    get result() { return child("ElectorateResults"); },
    get resultKey() { return find((node) => node.type === "ElectorateResults")?.key; },
    get error() { const node = find((item) => item.props.role === "alert"); return node ? text(node) : null; },
    async choose(vote = "no") { child("IncomeTaxBallot").onVoteChange(vote); await flush(); },
    async submit(value = ballot) { child("ScalarBallot").onSubmitBallot(value); await flush(); },
    async scenario(value) { child("ElectorateResults").onScenarioChange(value); await flush(); },
    async retryScenario() { child("ElectorateResults").onRetryScenario(); await flush(); },
    async retry() {
      const button = find((node) => node.type === "button" && text(node) === "Retry submitted ballot");
      assert.ok(button && !button.props.disabled, "Retry must be available after a failure");
      button.props.onClick(); await flush();
    },
    async expire() {
      assert.equal(timers.size, 1, "Only the current submission should own a deadline");
      const [id, timer] = [...timers][0];
      assert.equal(timer.delay, 15_000);
      timers.delete(id); timer.callback(); await flush();
    },
    async succeed(index, id, scenario = JSON.parse(requests[index].options.body).scenario ?? "prepared") {
      requests[index].resolve({ ok: true, json: async () => ({ valid: true, id, scenario }) }); await flush();
    },
    async unmount() {
      mounted = false;
      const ref = child("ElectorateResults")?.voterBrowserRef;
      if (ref) ref.current = null;
      for (const hook of hooks) hook?.cleanup?.();
      await flush();
    },
  };
}

async function start() {
  const host = createHost();
  await host.flush(); await host.choose(); await host.submit();
  assert.equal(host.busy, true);
  assert.deepEqual(host.attention, [], "Starting a request must not move focus or scroll");
  return host;
}

function assertNavigation(events, target) {
  assert.deepEqual(events.map(({ action, target: result }) => ({ action, target: result })), [
    { action: "focus", target }, { action: "scroll", target },
  ]);
  assert.equal(events[0].committedAt, events[1].committedAt);
  assert.ok(events[0].committedAt > 0, "The destination must have been committed before focus and scroll");
  assert.deepEqual(events[0].options, { preventScroll: true });
  assert.deepEqual(events[1].options, { behavior: "instant", block: "start" });
}

test("accepted first and repeated ballot comparisons focus and scroll the newly committed voter browser", async () => {
  const host = await start();
  await host.succeed(0, "first-result");
  assertNavigation(host.attention, "first-result");
  for (const [index, id] of ["changed-ballot", "same-ballot-again"].entries()) {
    const previousEvents = host.attention.length;
    await host.submit(nextBallot);
    assert.equal(host.attention.length, previousEvents, "The retained previous result must not be scrolled during loading");
    await host.succeed(index + 1, id);
    assertNavigation(host.attention.slice(previousEvents), id);
  }
  await host.choose("yes");
  assert.equal(host.attention.length, 6, "Editing the draft vote must not revisit the results");
  await host.unmount();
});

test("a stalled fetch times out, preserves answers, and retries the submitted pair", async () => {
  const host = await start();
  await host.expire();
  assert.equal(host.busy, false);
  assert.match(host.error, /took too long.*answers are still here/);
  assert.equal(host.requests[0].options.signal.aborted, true);
  assert.equal(host.child("IncomeTaxBallot").vote, "no");
  await host.choose("yes");
  await host.retry();
  assert.deepEqual(JSON.parse(host.requests[1].options.body), { ballot, binary_vote: "no" }, "Retry uses the exact failed submission, not an edited yes/no answer");
  await host.succeed(1, "retried");
  assert.equal(host.busy, false);
  assert.equal(host.error, null);
  assert.equal(host.result.data.id, "retried");
  assert.equal(host.timers.size, 0);
  assertNavigation(host.attention, "retried");
});

test("the deadline also bounds a stalled response body", async () => {
  const host = await start();
  const body = deferred();
  host.requests[0].resolve({ ok: true, json: () => body.promise });
  await host.flush(); await host.expire();
  assert.equal(host.busy, false);
  assert.match(host.error, /took too long/);
  body.resolve({ valid: true, id: "late-body" }); await host.flush();
  assert.equal(host.result, undefined, "A response body arriving after timeout must not become the result");
  assert.deepEqual(host.attention, [], "Failure and an expired response must not move focus or scroll");
});

test("network rejection and non-JSON gateway failures become friendly retry states", async () => {
  const host = await start();
  host.requests[0].reject(new TypeError("Failed to fetch")); await host.flush();
  assert.equal(host.busy, false);
  assert.match(host.error, /comparison is unavailable.*answers are still here/);
  assert.doesNotMatch(host.error, /Failed to fetch/);
  await host.retry();
  host.requests[1].resolve({ ok: false, json: async () => { throw new SyntaxError("Unexpected token '<': gateway HTML"); } });
  await host.flush();
  assert.equal(host.busy, false);
  assert.match(host.error, /comparison is unavailable/);
  assert.doesNotMatch(host.error, /Unexpected token|gateway HTML/);
  await host.retry(); await host.succeed(2, "recovered");
  assert.equal(host.result.data.id, "recovered");
});

test("invalid success payloads release submission and remain retryable", async () => {
  const host = await start();
  host.requests[0].resolve({ ok: true, json: async () => ({ malformed: true }) }); await host.flush();
  assert.equal(host.busy, false);
  assert.match(host.error, /could not be read/);
  await host.retry(); await host.succeed(1, "valid");
  assert.equal(host.result.data.id, "valid");
});

test("superseded requests cannot overwrite results or clear the current busy state", async () => {
  const host = await start();
  await host.submit(nextBallot);
  assert.equal(host.requests[0].options.signal.aborted, true);
  await host.succeed(0, "obsolete");
  assert.equal(host.busy, true);
  assert.equal(host.result, undefined);
  assert.equal(host.error, null);
  assert.deepEqual(host.attention, [], "An obsolete response must not navigate before the current result arrives");
  await host.succeed(1, "newest");
  assert.equal(host.result.data.id, "newest");
  assert.equal(host.result.ballot.ideal, nextBallot.ideal);
  assert.equal(host.busy, false);
  assertNavigation(host.attention, "newest");
});

test("late completion after timeout cannot interfere with a retry", async () => {
  const host = await start();
  await host.expire(); await host.retry();
  await host.succeed(0, "expired");
  assert.equal(host.busy, true);
  assert.equal(host.result, undefined);
  assert.deepEqual(host.attention, []);
  await host.succeed(1, "retry-result");
  assert.equal(host.result.data.id, "retry-result");
});

test("failed subsequent submissions retain and identify the previous result", async () => {
  const host = await start(); await host.succeed(0, "previous");
  await host.submit(nextBallot);
  assert.equal(host.result.data.id, "previous");
  assert.match(host.text(), /results below still show your previous submission/);
  assertNavigation(host.attention, "previous");
  await host.expire();
  assert.equal(host.result.data.id, "previous");
  assert.equal(host.child("ScalarBallot").submittedBallot.ideal, ballot.ideal);
  assert.match(host.text(), /results below still show your previous submission/);
  assertNavigation(host.attention, "previous");
});

test("unmount aborts transport and late results cause no state updates", async () => {
  const host = await start();
  await host.unmount();
  assert.equal(host.requests[0].options.signal.aborted, true);
  assert.equal(host.timers.size, 0);
  await host.succeed(0, "after-unmount");
  assert.equal(host.lateUpdates, 0);
  assert.deepEqual(host.attention, []);
});

test("scenario switches preserve the submitted pair, draft vote, and results component identity", async () => {
  const host = await start(); await host.succeed(0, "original");
  const key = host.resultKey;
  await host.choose("yes");
  for (const [index, scenario] of ["broad-agreement", "polarized", "intense-minority", "prepared"].entries()) {
    await host.scenario(scenario);
    assert.deepEqual(JSON.parse(host.requests[index + 1].options.body), { ballot, binary_vote: "no", scenario });
    assert.equal(host.result.scenarioPending, scenario);
    await host.succeed(index + 1, scenario);
    assert.equal(host.resultKey, key, "Changing the electorate must not remount and close the combined results");
    assert.equal(host.result.data.scenario, scenario);
    assert.deepEqual(JSON.parse(JSON.stringify(host.result.ballot)), ballot);
    assert.equal(host.child("IncomeTaxBallot").vote, "yes", "Unsubmitted edits remain in the ballot form");
    assert.equal(host.result.scenarioPending, null);
    assertNavigation(host.attention, "original");
  }
  await host.scenario("prepared");
  assert.equal(host.requests.length, 5, "An unchanged active scenario does not refetch");
});

test("rapid scenario switches apply only the newest complete dataset", async () => {
  const host = await start(); await host.succeed(0, "original");
  await host.scenario("polarized"); await host.scenario("intense-minority");
  assert.equal(host.requests[1].options.signal.aborted, true);
  assert.equal(host.result.data.id, "original", "The previous electorate stays intact during loading");
  await host.succeed(2, "minority"); await host.succeed(1, "late-polarized");
  assert.equal(host.result.data.id, "minority");
  assert.equal(host.result.data.scenario, "intense-minority");
  assert.equal(host.result.scenarioPending, null);
  assertNavigation(host.attention, "original");
});

test("failed scenario switches preserve active results and retry the exact submitted scenario", async () => {
  const host = await start(); await host.succeed(0, "original");
  await host.scenario("polarized"); await host.expire();
  assert.equal(host.result.data.scenario, "prepared");
  assert.match(host.result.scenarioError, /took too long/);
  assert.equal(host.error, null, "Scenario errors are displayed beside the scenario controls");
  await host.choose("yes"); await host.retryScenario();
  assert.deepEqual(JSON.parse(host.requests[2].options.body), { ballot, binary_vote: "no", scenario: "polarized" });
  await host.succeed(2, "retried");
  assert.equal(host.result.data.scenario, "polarized");
  assert.equal(host.result.scenarioError, null);
  assertNavigation(host.attention, "original");
});

test("scenario responses cannot silently substitute another electorate", async () => {
  const host = await start(); await host.succeed(0, "original");
  await host.scenario("polarized"); await host.succeed(1, "wrong", "prepared");
  assert.match(host.result.scenarioError, /requested electorate could not be loaded/);
  assert.equal(host.result.data.id, "original");
  assert.equal(host.busy, false);
});

test("a new ballot keeps the active scenario and cannot be superseded by an old-ballot scenario switch", async () => {
  const host = await start(); await host.succeed(0, "original");
  await host.scenario("polarized"); await host.succeed(1, "polarized");
  await host.choose("yes"); await host.submit(nextBallot);
  assert.deepEqual(JSON.parse(host.requests[2].options.body), { ballot: nextBallot, binary_vote: "yes", scenario: "polarized" });
  assert.equal(host.result.scenarioDisabled, true);
  await host.scenario("intense-minority");
  assert.equal(host.requests.length, 3);
  await host.succeed(2, "updated-ballot");
  assert.equal(host.result.data.id, "updated-ballot");
  assert.equal(host.result.scenarioDisabled, false);
  assert.equal(host.result.ballot.ideal, 6);
});
