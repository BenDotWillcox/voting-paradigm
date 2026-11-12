// Exercise the actual hook/component request paths with controlled transport
// failures. Numerical correctness remains covered by the Python API tests.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInThisContext } from "node:vm";
import ts from "typescript";

function load(path, dependencies = {}, environment = {}) {
  const { outputText } = ts.transpileModule(readFileSync(new URL(`../../${path}`, import.meta.url), "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  });
  const exports = {};
  runInThisContext(`(function(exports, require, setTimeout, clearTimeout, fetch, window) { ${outputText}\n })`, { filename: path })(
    exports,
    (name) => { assert.ok(name in dependencies, `Unexpected dependency: ${name}`); return dependencies[name]; },
    environment.clock?.setTimeout ?? setTimeout,
    environment.clock?.clearTimeout ?? clearTimeout,
    environment.fetch,
    environment.clock,
  );
  return exports;
}

function clock() {
  let now = 0, serial = 0;
  const timers = new Map();
  return {
    setTimeout(callback, delay) { const id = ++serial; timers.set(id, { at: now + delay, callback }); return id; },
    clearTimeout(id) { timers.delete(id); },
    advance(ms) {
      const until = now + ms;
      for (;;) {
        const next = [...timers].filter(([, timer]) => timer.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        const [id, timer] = next;
        now = timer.at; timers.delete(id); timer.callback();
      }
      now = until;
    },
  };
}

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const sameDeps = (a, b) => a && b && a.length === b.length && a.every((entry, i) => Object.is(entry, b[i]));

// A minimal commit/effect harness keeps the production async closures intact;
// it does not reproduce the request logic or call internal state setters.
function hookHarness() {
  const slots = [];
  let index = 0, pending = [], render, current, dirty = false, mounted = true, afterUnmount = 0;
  const react = {
    useState(initial) {
      const slot = index++;
      if (!slots[slot]) slots[slot] = { value: typeof initial === "function" ? initial() : initial };
      return [slots[slot].value, (next) => {
        if (!mounted) { afterUnmount++; return; }
        const value = typeof next === "function" ? next(slots[slot].value) : next;
        if (!Object.is(value, slots[slot].value)) { slots[slot].value = value; dirty = true; }
      }];
    },
    useRef(initial) { const slot = index++; return slots[slot] ??= { current: initial }; },
    useMemo(factory, deps) {
      const slot = index++;
      if (!sameDeps(slots[slot]?.deps, deps)) slots[slot] = { value: factory(), deps };
      return slots[slot].value;
    },
    useCallback(callback, deps) { return react.useMemo(() => callback, deps); },
    useEffect(effect, deps) {
      const slot = index++;
      if (!sameDeps(slots[slot]?.deps, deps)) {
        const previous = slots[slot];
        slots[slot] = { deps, cleanup: previous?.cleanup };
        pending.push(() => { previous?.cleanup?.(); slots[slot].cleanup = effect(); });
      }
    },
  };
  function commit() {
    for (let rounds = 0; rounds < 20; rounds++) {
      dirty = false; index = 0; pending = [];
      current = render();
      const effects = pending; pending = [];
      effects.forEach((effect) => effect());
      if (!dirty) return;
    }
    throw new Error("Render did not settle");
  }
  return {
    react,
    mount(callback) { render = callback; commit(); },
    get current() { return current; },
    get afterUnmount() { return afterUnmount; },
    async flush() { for (let i = 0; i < 20; i++) { await Promise.resolve(); if (dirty && mounted) commit(); } },
    unmount() { mounted = false; for (const slot of slots) slot?.cleanup?.(); },
  };
}

const profileModule = load("lib/methods/profile.ts", { "./candidates": load("lib/methods/candidates.ts") });
const preset = JSON.parse(readFileSync(new URL("../../public/data/methods/presets.json", import.meta.url), "utf8")).presets[0].resolution;
const edited = (extra = 1) => ({ ...preset.profile, rows: preset.profile.rows.map((row, i) => ({ ...row, count: row.count + (i === 0 ? extra : 0) })) });
const resolved = (profile) => ({ ...preset, profile, total_voters: profileModule.totalVoters(profile) });
const success = (data) => ({ isSuccess: true, message: "Counted", data });

async function electorate(action) {
  const timer = clock(), harness = hookHarness(), requests = [];
  const deadline = load("lib/request-deadline.ts", {}, { clock: timer });
  const client = load("lib/methods-client.ts", {}, { fetch: async (url, options) => {
    assert.equal(url, "/api/methods/profile");
    assert.ok(options.signal instanceof AbortSignal);
    requests.push({ url, ...options });
    const result = await action(JSON.parse(options.body), options.signal);
    return { ok: true, json: async () => result };
  } });
  const { useElectorate } = load("components/methods/instrument/use-electorate.ts", {
    react: harness.react,
    "@/lib/methods-client": client,
    "@/lib/methods/profile": profileModule,
    "@/lib/request-deadline": deadline,
  }, { clock: timer, fetch: async () => ({ ok: true, json: async () => ({ resolutions: {} }) }) });
  harness.mount(() => useElectorate({ presets: [{ profile: preset.profile, resolution: preset }], initialProfile: preset.profile, initialResolution: null }));
  await harness.flush();
  return { timer, harness, requests };
}

test("rejected fetch leaves counting, preserves edits, and retries the same electorate", async () => {
  const calls = [];
  const { timer, harness } = await electorate(async (request) => {
    calls.push(request);
    if (calls.length === 1) throw new Error("An unexpected response was received from the server.");
    return success(resolved(request.profile));
  });
  const profile = edited();
  harness.current.load(profile); await harness.flush(); timer.advance(250); await harness.flush();
  assert.equal(harness.current.status.kind, "offline");
  assert.equal(harness.current.profile, profile);
  assert.equal(harness.current.resolution, preset);
  assert.equal(harness.current.showing, false);
  harness.current.retry(); await harness.flush(); timer.advance(250); await harness.flush();
  assert.equal(harness.current.status.kind, "ready");
  assert.equal(harness.current.showing, true);
  assert.deepEqual(calls.map((call) => call.profile), [profile, profile]);
  harness.unmount();
});

test("a never-settling fetch is aborted and cannot block a successful retry or replace its result", async () => {
  const old = deferred();
  let count = 0;
  const { timer, harness, requests } = await electorate((request) => ++count === 1 ? old.promise : Promise.resolve(success(resolved(request.profile))));
  const profile = edited();
  harness.current.load(profile); await harness.flush(); timer.advance(250); await harness.flush();
  timer.advance(14_999); await harness.flush();
  assert.equal(harness.current.status.kind, "counting");
  timer.advance(1); await harness.flush();
  assert.equal(requests[0].signal.aborted, true);
  assert.equal(harness.current.status.kind, "offline");
  assert.match(harness.current.status.message, /too long/);
  harness.current.retry(); await harness.flush(); timer.advance(250); await harness.flush();
  assert.equal(count, 2, "retry sends a new fetch while the previous transport never settles");
  assert.equal(harness.current.status.kind, "ready");
  const retry = harness.current.resolution;
  old.resolve(success(preset)); await harness.flush();
  assert.equal(harness.current.resolution, retry);
  assert.equal(harness.current.status.kind, "ready");
  harness.unmount();
});

test("new edits, cached examples and unmount supersede outstanding action completions", async () => {
  const pending = [];
  const { timer, harness } = await electorate(() => { const request = deferred(); pending.push(request); return request.promise; });
  harness.current.load(edited()); await harness.flush(); timer.advance(250); await harness.flush();
  const newer = edited(2);
  harness.current.load(newer); await harness.flush(); timer.advance(250); await harness.flush();
  pending[1].resolve(success(resolved(newer))); await harness.flush();
  pending[0].resolve(success(resolved(edited()))); await harness.flush();
  assert.equal(harness.current.resolution.profile, newer);
  harness.current.load(edited(3)); await harness.flush(); timer.advance(250); await harness.flush();
  harness.current.load(preset.profile, preset); await harness.flush();
  assert.equal(harness.current.status.kind, "ready");
  assert.equal(harness.current.resolution, preset);
  pending[2].reject(new Error("Late transport failure")); await harness.flush();
  assert.equal(harness.current.status.kind, "ready");
  harness.current.load(edited(4)); await harness.flush(); timer.advance(250); await harness.flush();
  harness.unmount(); pending[3].resolve(success(resolved(edited(4)))); await harness.flush();
  assert.equal(harness.afterUnmount, 0);
});

test("reloading the same profile object cannot strand an aborted count", async () => {
  const pending = [];
  const { timer, harness } = await electorate(() => { const request = deferred(); pending.push(request); return request.promise; });
  const profile = edited();
  harness.current.load(profile); await harness.flush(); timer.advance(250); await harness.flush();
  harness.current.load(profile); await harness.flush(); timer.advance(250); await harness.flush();
  assert.equal(pending.length, 2);
  pending[1].resolve(success(resolved(profile))); await harness.flush();
  assert.equal(harness.current.status.kind, "ready");
  harness.unmount();
});

const jsx = (type, props) => ({ type, props });
const jsxRuntime = { jsx, jsxs: jsx, Fragment: "fragment" };
function elements(node) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(elements);
  return [node, ...elements(node.props?.children)];
}
function textOf(node) {
  if (node == null || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map(textOf).join("");
  return typeof node === "object" ? textOf(node.props?.children) : String(node);
}
const button = (tree, label) => {
  const found = elements(tree).find((node) => node.type === "button" && textOf(node) === label);
  assert.ok(found, `Missing button: ${label}`); return found.props;
};
const map = (tree) => elements(tree).find((node) => node.type?.name === "MainMap").props;
const atlasData = JSON.parse(readFileSync(new URL("../../public/data/methods/atlas.json", import.meta.url), "utf8"));
const atlasModule = load("lib/methods/atlas.ts", { "./instrument": load("lib/methods/instrument.ts") });

async function atlas(actions = {}, fetcher = async () => ({ ok: true, json: async () => atlasData })) {
  const timer = clock(), harness = hookHarness(), points = [], requests = [];
  const deadline = load("lib/request-deadline.ts", {}, { clock: timer });
  const client = load("lib/methods-client.ts", {}, { fetch: async (url, options) => {
    const method = { "/api/methods/atlas": "resolveAtlasAction", "/api/methods/atlas/point": "resolveAtlasPointAction" }[url];
    assert.ok(method && actions[method], `Unexpected request: ${url}`);
    assert.ok(options.signal instanceof AbortSignal);
    requests.push({ url, ...options });
    const result = await actions[method](JSON.parse(options.body), options.signal);
    return { ok: true, json: async () => result };
  } });
  const { Atlas } = load("components/methods/instrument/atlas.tsx", {
    react: harness.react, "react/jsx-runtime": jsxRuntime,
    "lucide-react": { X: () => null },
    "@/lib/methods-client": client,
    "@/lib/methods/atlas": atlasModule,
    "@/lib/request-deadline": deadline,
    "@/lib/utils": { cn: (...values) => values.filter(Boolean).join(" ") },
    "./glyph": { CandidateGlyph: () => null, CandidateMark: () => null },
    "./map-canvas": { MapCanvas: () => null, disagreementShade: () => "" },
  }, { clock: timer, fetch: fetcher });
  harness.mount(() => Atlas({ onLoadPoint: (...args) => points.push(args) }));
  await harness.flush();
  return { timer, harness, points, requests };
}

test("atlas transport rejection preserves edited positions and offers a working layout retry", async () => {
  const calls = [];
  const { harness } = await atlas({ resolveAtlasAction: async (request) => {
    calls.push(request);
    if (calls.length === 1) throw new Error("Server Action transport failed");
    return success({ ...atlasData.layouts[0].atlas, candidates: request.candidates });
  } });
  const candidates = map(harness.current).atlas.candidates.map((candidate, i) => i ? candidate : { ...candidate, x: candidate.x + 0.01 });
  await map(harness.current).onCommit(candidates); await harness.flush();
  assert.match(textOf(harness.current), /Live mapping is unavailable/);
  assert.deepEqual(map(harness.current).positions, candidates);
  assert.equal(map(harness.current).stale, true);
  button(harness.current, "Retry layout").onClick(); await harness.flush();
  assert.deepEqual(calls[1], calls[0]);
  assert.deepEqual(map(harness.current).atlas.candidates, candidates);
  assert.equal(map(harness.current).stale, false);
  harness.unmount();
});

test("atlas mapping has its own bounded budget and a saved layout supersedes late completion", async () => {
  const old = deferred();
  const { timer, harness } = await atlas({ resolveAtlasAction: () => old.promise });
  const candidates = map(harness.current).atlas.candidates.map((candidate, i) => i ? candidate : { ...candidate, x: candidate.x + 0.02 });
  void map(harness.current).onCommit(candidates); await harness.flush();
  timer.advance(64_999); await harness.flush();
  assert.match(textOf(harness.current), /Counting 4,096/);
  timer.advance(1); await harness.flush();
  assert.match(textOf(harness.current), /Mapping took too long/);
  const layoutButtons = elements(harness.current).filter((node) => node.type === "button" && node.props["aria-label"]?.includes("candidates"));
  layoutButtons[1].props.onClick(); await harness.flush();
  const selected = map(harness.current).atlas;
  old.resolve(success({ ...atlasData.layouts[0].atlas, candidates })); await harness.flush();
  assert.equal(map(harness.current).atlas, selected);
  assert.equal(map(harness.current).stale, false);
  harness.unmount();
});

test("point rejection and timeout clear loading and retry the selected electorate", async () => {
  const calls = [];
  const { timer, harness, points } = await atlas({ resolveAtlasPointAction: (request) => {
    calls.push(request);
    if (calls.length === 1) return Promise.reject(new Error("Network failed"));
    if (calls.length === 2) return new Promise(() => {});
    return Promise.resolve(success(preset));
  } });
  await map(harness.current).onPick(12); await harness.flush();
  assert.match(textOf(harness.current), /could not be loaded/);
  button(harness.current, "Retry electorate").onClick(); await harness.flush();
  timer.advance(15_000); await harness.flush();
  assert.match(textOf(harness.current), /took too long/);
  button(harness.current, "Retry electorate").onClick(); await harness.flush();
  assert.equal(points.length, 1);
  assert.equal(points[0][1].cell, 12);
  assert.deepEqual(calls.map((request) => request.cell), [12, 12, 12]);
  assert.doesNotMatch(textOf(harness.current), /Loading that electorate/);
  harness.unmount();
});

test("only the newest point may navigate; layout changes and unmount cancel pending points", async () => {
  const pending = [];
  const { harness, points } = await atlas({ resolveAtlasPointAction: () => {
    const request = deferred(); pending.push(request); return request.promise;
  } });
  void map(harness.current).onPick(1); await harness.flush();
  void map(harness.current).onPick(2); await harness.flush();
  pending[1].resolve(success(preset)); await harness.flush();
  pending[0].resolve(success(preset)); await harness.flush();
  assert.deepEqual(points.map(([, point]) => point.cell), [2]);
  void map(harness.current).onPick(3); await harness.flush();
  const layoutButtons = elements(harness.current).filter((node) => node.type === "button" && node.props["aria-label"]?.includes("candidates"));
  layoutButtons[1].props.onClick(); await harness.flush();
  pending[2].resolve(success(preset)); await harness.flush();
  assert.equal(points.length, 1);
  void map(harness.current).onPick(4); await harness.flush();
  harness.unmount(); pending[3].resolve(success(preset)); await harness.flush();
  assert.equal(points.length, 1);
  assert.equal(harness.afterUnmount, 0);
});

test("moving a candidate invalidates pending point and map results before committing the drag", async () => {
  const point = deferred(), count = deferred();
  const { harness, points } = await atlas({
    resolveAtlasPointAction: () => point.promise,
    resolveAtlasAction: () => count.promise,
  });
  const original = map(harness.current).atlas;
  const candidates = original.candidates.map((candidate, i) => i ? candidate : { ...candidate, x: candidate.x + 0.03 });
  void map(harness.current).onPick(1); await harness.flush();
  map(harness.current).onMove(candidates); await harness.flush();
  point.resolve(success(preset)); await harness.flush();
  assert.equal(points.length, 0);
  void map(harness.current).onCommit(candidates); await harness.flush();
  const movedAgain = candidates.map((candidate, i) => i ? candidate : { ...candidate, x: candidate.x + 0.01 });
  map(harness.current).onMove(movedAgain); await harness.flush();
  count.resolve(success({ ...original, candidates })); await harness.flush();
  assert.equal(map(harness.current).atlas, original);
  assert.deepEqual(map(harness.current).positions, movedAgain);
  harness.unmount();
});

test("unavailable static atlas maps can be retried without a page reload", async () => {
  let calls = 0;
  const { harness } = await atlas({}, async () => ++calls === 1
    ? { ok: false }
    : { ok: true, json: async () => atlasData });
  assert.match(textOf(harness.current), /maps could not be loaded/);
  button(harness.current, "Retry atlas").onClick(); await harness.flush();
  assert.ok(map(harness.current).atlas);
  harness.unmount();
});

test("server profile/point deadlines cover headers and JSON; atlas gets a longer budget", async () => {
  for (const [name, timeoutMs, stallBody] of [
    ["resolveProfile", 10_000, false], ["resolveAtlasPoint", 10_000, true], ["resolveAtlas", 60_000, false],
  ]) {
    const timer = clock();
    const deadline = load("lib/request-deadline.ts", {}, { clock: timer });
    let transportSignal;
    const api = load("lib/methods-api.ts", { "@/lib/request-deadline": deadline }, {
      clock: timer,
      fetch: async (_url, options) => {
        transportSignal = options.signal;
        if (!stallBody) return new Promise(() => {});
        return { ok: true, json: () => new Promise(() => {}) };
      },
    });
    const result = api[name]({ profile: preset.profile });
    const rejected = assert.rejects(result, deadline.RequestTimeoutError);
    await Promise.resolve();
    timer.advance(timeoutMs - 1);
    assert.equal(transportSignal.aborted, false);
    timer.advance(1); await rejected;
    assert.equal(transportSignal.aborted, true);
  }
});

test("server API preserves successful responses and propagates HTTP failures", async () => {
  const timer = clock();
  const deadline = load("lib/request-deadline.ts", {}, { clock: timer });
  let attempt = 0;
  const api = load("lib/methods-api.ts", { "@/lib/request-deadline": deadline }, {
    clock: timer,
    fetch: async () => ++attempt === 1
      ? { ok: false, status: 503, statusText: "Unavailable" }
      : { ok: true, json: async () => preset },
  });
  await assert.rejects(api.resolveProfile({ profile: preset.profile }), /503/);
  assert.equal(await api.resolveProfile({ profile: preset.profile }), preset);
});

test("browser HTTP adapter rejects HTTP errors, non-JSON and malformed result envelopes", async () => {
  const malformed = [null, [], {}, { isSuccess: "yes", message: "ok" }, { isSuccess: false },
    { isSuccess: true, message: "ok" }, { isSuccess: true, message: "ok", data: null },
    { isSuccess: true, message: "ok", data: 1 }];
  const responses = [
    { ok: false, status: 503 },
    { ok: true, json: async () => { throw new SyntaxError("Not JSON"); } },
    ...malformed.map((result) => ({ ok: true, json: async () => result })),
  ];
  for (const response of responses) {
    const client = load("lib/methods-client.ts", {}, { fetch: async () => response });
    await assert.rejects(client.requestProfile({ profile: preset.profile }, new AbortController().signal));
  }
  for (const result of [success(preset), { isSuccess: false, message: "Check the electorate" }]) {
    const client = load("lib/methods-client.ts", {}, { fetch: async () => ({ ok: true, json: async () => result }) });
    assert.equal(await client.requestProfile({ profile: preset.profile }, new AbortController().signal), result);
  }
});

test("browser deadline aborts a stalled JSON body and a new request can finish independently", async () => {
  const timer = clock();
  const deadline = load("lib/request-deadline.ts", {}, { clock: timer });
  const requests = [];
  const client = load("lib/methods-client.ts", {}, { fetch: async (url, options) => {
    requests.push({ url, ...options });
    return requests.length === 1
      ? { ok: true, json: () => new Promise(() => {}) }
      : { ok: true, json: async () => success(preset) };
  } });
  const input = { profile: preset.profile };
  const stalled = deadline.withRequestDeadline((signal) => client.requestProfile(input, signal), { timeoutMs: 15_000 });
  const rejected = assert.rejects(stalled, deadline.RequestTimeoutError);
  await Promise.resolve(); await Promise.resolve();
  timer.advance(15_000); await rejected;
  assert.equal(requests[0].signal.aborted, true);
  const retried = await deadline.withRequestDeadline((signal) => client.requestProfile(input, signal), { timeoutMs: 15_000 });
  assert.equal(retried.data, preset);
  assert.equal(requests.length, 2);
  assert.equal(requests[1].method, "POST");
  assert.equal(requests[1].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(requests[1].body), input);
});
