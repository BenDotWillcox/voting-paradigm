// Run with: node --test tests/elicitation-route.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { compileFunction } from "node:vm";
import { test } from "node:test";
import ts from "typescript";

// Load only the two source modules under test; no global hooks or build files.
function loadTypeScript(relativePath, imports = {}) {
  const filename = fileURLToPath(new URL(`../${relativePath}`, import.meta.url));
  const { outputText } = ts.transpileModule(readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  });
  const nativeRequire = createRequire(filename);
  const loaded = { exports: {} };
  compileFunction(outputText, ["exports", "require", "module"], { filename })(
    loaded.exports,
    (id) => Object.hasOwn(imports, id) ? imports[id] : nativeRequire(id),
    loaded,
  );
  return loaded.exports;
}

const schemas = loadTypeScript("lib/validations/elicitation-schemas.ts");
const { POST } = loadTypeScript("app/api/preferences/elicitation/route.ts", {
  "@/lib/validations/elicitation-schemas": schemas,
});
const bankVersion = "spectrum_demo_v1";

function question(index) {
  return {
    id: `spectrum_${index}`,
    version: 1,
    title: `Public demonstration ${index + 1}`,
    prompt: "Where would you place the setting?",
    context: "A public test of one numerical axis, not a model prediction.",
    scale: {
      min: 0, max: 10, step: 0.5, unit: "units", format: "number",
      anchors: [
        { value: 0, label: "0 units" },
        { value: 5, label: "5 units" },
        { value: 10, label: "10 units" },
      ],
    },
  };
}

function event(index, action = "answer") {
  const identity = { action, question_id: `spectrum_${index}`, question_version: 1 };
  return action === "answer"
    ? { ...identity, position: 6, reported_uncertainty: null, acceptable_range: null }
    : identity;
}

function result(responses = []) {
  return {
    bank_version: bankVersion,
    questions: Array.from({ length: 4 }, (_, index) => question(index)),
    responses,
    n_reviewed: responses.length,
    n_answered: responses.filter((value) => value.action === "answer").length,
    n_skipped: responses.filter((value) => value.action === "skip").length,
    n_depends: responses.filter((value) => value.action === "depends").length,
    target_questions: 4,
    is_complete: responses.length === 4,
  };
}

function request(body = { bank_version: bankVersion, responses: [] }) {
  return new Request("http://localhost:3000/api/preferences/elicitation", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "private-caller-token",
      Cookie: "private-caller-cookie",
    },
    body: JSON.stringify(body),
  });
}

function configureUpstream(t, primary, fallback) {
  for (const [name, value] of [
    ["PREFERENCES_API_URL", primary], ["NEBULA_API_URL", fallback],
  ]) {
    const previous = process.env[name];
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
    t.after(() => {
      if (previous === undefined) delete process.env[name];
      else process.env[name] = previous;
    });
  }
}

function assertNoStore(response) {
  assert.equal(response.headers.get("cache-control"), "no-store");
}

test("initial, partial, and complete summaries pass through without caching or forwarding credentials", async (t) => {
  const answered = { ...event(0), reported_uncertainty: { sd_fraction: 0.117 }, acceptable_range: { lower: 3, upper: 9 } };
  const histories = [[], [answered], [answered, event(1, "skip"), event(2, "depends"), event(3)]];
  for (const responses of histories) {
    await t.test(`${responses.length} reviewed`, async (t) => {
      configureUpstream(t, "http://configured-python:8000/", "http://unused-fallback:8000");
      const input = { bank_version: bankVersion, responses };
      const expected = result(responses);
      t.mock.method(AbortSignal, "timeout", (milliseconds) => {
        assert.equal(milliseconds, 15_000);
        return new AbortController().signal;
      });
      const mocked = t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.equal(url, "http://configured-python:8000/api/preferences/elicitation");
        assert.equal(options.method, "POST");
        assert.equal(options.cache, "no-store");
        assert.equal(options.redirect, "error");
        assert.deepEqual(options.headers, { "Content-Type": "application/json" });
        assert.deepEqual(JSON.parse(options.body), input);
        assert.ok(options.signal instanceof AbortSignal);
        assert.equal(options.signal.aborted, false);
        return Response.json(expected);
      });
      const response = await POST(request(input));
      assert.equal(response.status, 200);
      assertNoStore(response);
      assert.deepEqual(await response.json(), expected);
      assert.equal(mocked.mock.callCount(), 1);
    });
  }
});

test("unanswered optional controls become null without inventing a confidence or acceptable range", async (t) => {
  const inputEvent = { action: "answer", question_id: "spectrum_0", question_version: 1, position: 6 };
  const input = { bank_version: bankVersion, responses: [inputEvent] };
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.deepEqual(JSON.parse(options.body).responses, [event(0)]);
    return Response.json(result([inputEvent]));
  });
  const response = await POST(request(input));
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).responses, [event(0)]);
});

test("upstream URL uses only server configuration with a local default", async (t) => {
  for (const [fallback, expected] of [
    ["http://fallback-python:9000/", "http://fallback-python:9000/api/preferences/elicitation"],
    [undefined, "http://localhost:8000/api/preferences/elicitation"],
  ]) {
    await t.test(String(fallback), async (t) => {
      configureUpstream(t, undefined, fallback);
      const mocked = t.mock.method(globalThis, "fetch", async (url) => {
        assert.equal(url, expected);
        return Response.json(result());
      });
      assert.equal((await POST(request())).status, 200);
      assert.equal(mocked.mock.callCount(), 1);
    });
  }
});

test("invalid requests and legacy pairwise payloads fail before an upstream call", async (t) => {
  const mocked = t.mock.method(globalThis, "fetch", async () => {
    assert.fail("Invalid client data must not reach Python");
  });
  const valid = { bank_version: bankVersion, responses: [] };
  const withEvent = (value) => ({ ...valid, responses: [value] });
  const invalid = [
    null,
    { model: "gaussian_linear", responses: [] },
    { ...valid, bank_version: "spectrum_demo_v2" },
    { ...valid, model: "bradley_terry" },
    { ...valid, posterior: { mu: [123] } },
    { ...valid, api_url: "https://caller-controlled.invalid" },
    withEvent({ ...event(0), position: "6" }),
    withEvent({ ...event(0), position: null }),
    withEvent({ action: "answer", question_id: "spectrum_0", question_version: 1 }),
    withEvent({ ...event(0), value: 6 }),
    withEvent({ ...event(0), question_version: 2 }),
    withEvent({ ...event(0), reported_uncertainty: "very_confident" }),
    withEvent({ ...event(0), reported_uncertainty: "narrow" }),
    withEvent({ ...event(0), reported_uncertainty: 0.15 }),
    withEvent({ ...event(0), reported_uncertainty: {} }),
    withEvent({ ...event(0), reported_uncertainty: { sd_fraction: "0.15" } }),
    withEvent({ ...event(0), reported_uncertainty: { sd_fraction: 0.079 } }),
    withEvent({ ...event(0), reported_uncertainty: { sd_fraction: 0.281 } }),
    withEvent({ ...event(0), reported_uncertainty: { sd_fraction: 0.15, confidence: 0.9 } }),
    withEvent({ ...event(0), acceptable_range: { lower: 9, upper: 3 } }),
    withEvent({ ...event(0), acceptable_range: { lower: 3, upper: 9, confidence: 1 } }),
    withEvent({ ...event(0, "skip"), position: 0 }),
    withEvent({ ...event(0, "skip"), reported_uncertainty: null }),
    withEvent({ ...event(0, "depends"), acceptable_range: null }),
    withEvent({ ...event(0, "depends"), explanation: "PRIVATE-UNSUPPORTED-TEXT" }),
    withEvent({ ...event(0), action: "invented_action" }),
    { ...valid, responses: Array.from({ length: 5 }, (_, index) => event(index, "skip")) },
  ];
  for (const body of invalid) {
    const response = await POST(request(body));
    assert.equal(response.status, 400);
    assertNoStore(response);
    assert.equal(JSON.stringify(await response.json()).includes("PRIVATE"), false);
  }
  const malformed = await POST(new Request("http://localhost/api/preferences/elicitation", {
    method: "POST", body: "{private-malformed-input",
  }));
  assert.equal(malformed.status, 400);
  assertNoStore(malformed);
  assert.equal(mocked.mock.callCount(), 0);
});

test("skip and depends remain distinct from an answer at the numerical midpoint", () => {
  const responses = [{ ...event(0), position: 5 }, event(1, "skip"), event(2, "depends")];
  const parsed = schemas.elicitationResponseSchema.parse(result(responses));
  assert.equal(parsed.n_answered, 1);
  assert.equal(parsed.n_skipped, 1);
  assert.equal(parsed.n_depends, 1);
  assert.deepEqual(parsed.responses, responses);
  for (const value of parsed.responses.slice(1)) {
    assert.equal(Object.hasOwn(value, "position"), false);
    assert.equal(Object.hasOwn(value, "reported_uncertainty"), false);
    assert.equal(Object.hasOwn(value, "acceptable_range"), false);
  }
});

test("position, reported uncertainty, and acceptable range are independent self-reports", () => {
  for (const reported_uncertainty of [null, { sd_fraction: 0.08 }, { sd_fraction: 0.17325 }, { sd_fraction: 0.28 }]) {
    for (const acceptable_range of [null, { lower: 3, upper: 9 }, { lower: 0, upper: 0 }]) {
      const response = { ...event(0), reported_uncertainty, acceptable_range };
      const parsed = schemas.elicitationResponseSchema.parse(result([response]));
      assert.deepEqual(parsed.responses[0], response);
    }
  }
  // Acceptance is not a plausibility bound: the position need not be inside it.
  assert.equal(schemas.spectrumEventMatchesQuestion(
    { ...event(0), position: 10, acceptable_range: { lower: 0, upper: 4 } }, question(0),
  ), true);
});

test("reported uncertainty keeps continuous width and rejects nonfinite or out-of-range values", () => {
  assert.equal(schemas.SPECTRUM_SD_MIN, 0.08);
  assert.equal(schemas.SPECTRUM_SD_MAX, 0.28);
  for (const sd_fraction of [0.08, 0.080000001, 0.117, 0.17325, 0.279999999, 0.28]) {
    const value = { sd_fraction };
    assert.deepEqual(schemas.reportedUncertaintySchema.parse(value), value);
  }
  for (const sd_fraction of [0, 0.079999999, 0.280000001, -1, NaN, Infinity, -Infinity, "0.15", null]) {
    assert.equal(schemas.reportedUncertaintySchema.safeParse({ sd_fraction }).success, false);
    const response = { ...event(0), reported_uncertainty: { sd_fraction } };
    assert.equal(schemas.elicitationResponseSchema.safeParse(result([response])).success, false);
  }
  for (const value of ["broad", "moderate", "narrow", {}, { sd_fraction: 0.15, extra: true }]) {
    assert.equal(schemas.reportedUncertaintySchema.safeParse(value).success, false);
  }
});

test("response validation enforces scale units, ordered anchors, and usable step geometry", () => {
  const valid = question(0);
  assert.equal(schemas.spectrumQuestionSchema.safeParse(valid).success, true);
  const malformed = [
    ["empty unit", (scale) => { scale.unit = ""; }],
    ["unsupported format", (scale) => { scale.format = "percent"; }],
    ["zero span", (scale) => { scale.max = scale.min; }],
    ["negative span", (scale) => { scale.min = 11; }],
    ["zero step", (scale) => { scale.step = 0; }],
    ["negative step", (scale) => { scale.step = -1; }],
    ["nonfinite step", (scale) => { scale.step = Infinity; }],
    ["nonfinite bound", (scale) => { scale.max = NaN; }],
    ["fractional interval count", (scale) => { scale.step = 3; }],
    ["empty anchors", (scale) => { scale.anchors = []; }],
    ["missing minimum anchor", (scale) => { scale.anchors[0].value = 1; }],
    ["missing maximum anchor", (scale) => { scale.anchors[2].value = 9; }],
    ["off-grid anchor", (scale) => { scale.anchors[1].value = 5.25; }],
    ["duplicate anchor", (scale) => { scale.anchors[1].value = 0; }],
    ["unordered anchor", (scale) => { scale.anchors.splice(1, 0, { value: 8, label: "8 units" }); }],
    ["unknown scale field", (scale) => { scale.model_confidence = 0.9; }],
  ];
  for (const [name, mutate] of malformed) {
    const value = structuredClone(valid);
    mutate(value.scale);
    assert.equal(schemas.spectrumQuestionSchema.safeParse(value).success, false, name);
  }
  const clock = question(0);
  clock.scale = {
    min: 8, max: 12, step: 0.5, unit: "hour", format: "clock_hour",
    anchors: [{ value: 8, label: "8:00 AM" }, { value: 12, label: "Noon" }],
  };
  assert.equal(schemas.spectrumQuestionSchema.safeParse(clock).success, true);
});

test("answers and acceptance endpoints must be finite on-scale steps, including endpoints", () => {
  for (const position of [0, 0.5, 5.5, 10]) {
    assert.equal(schemas.elicitationResponseSchema.safeParse(result([{ ...event(0), position }])).success, true);
  }
  const invalid = [
    { ...event(0), position: -0.5 },
    { ...event(0), position: 10.5 },
    { ...event(0), position: 5.25 },
    { ...event(0), position: NaN },
    { ...event(0), position: Infinity },
    { ...event(0), acceptable_range: { lower: -0.5, upper: 9 } },
    { ...event(0), acceptable_range: { lower: 3, upper: 10.5 } },
    { ...event(0), acceptable_range: { lower: 3.25, upper: 9 } },
    { ...event(0), acceptable_range: { lower: 3, upper: 9.25 } },
    { ...event(0), acceptable_range: { lower: 9, upper: 3 } },
    { ...event(0), acceptable_range: { lower: 3, upper: Infinity } },
  ];
  for (const response of invalid) {
    assert.equal(schemas.elicitationResponseSchema.safeParse(result([response])).success, false);
  }
  const decimal = { min: 0, max: 1, step: 0.1 };
  assert.equal(schemas.isScaleValue(0.3, decimal), true);
  assert.equal(schemas.isScaleValue(0.1 + 0.2, decimal), false);
  assert.equal(schemas.isScaleValue(0.35, decimal), false);
  assert.equal(schemas.isScaleValue(-0.3, { min: -1, max: 1, step: 0.1 }), true);
  assert.equal(schemas.isScaleValue(0.9, { min: 0.3, max: 1.2, step: 0.3 }), true);
  assert.equal(schemas.isScaleValue(1e-7, { min: 0, max: 1e-6, step: 1e-7 }), true);
});

test("session validation requires versioned question prefixes and exact counters", () => {
  const completed = result([event(0), event(1, "skip"), event(2, "depends"), event(3)]);
  assert.equal(schemas.elicitationResponseSchema.safeParse(completed).success, true);
  const malformed = [
    ["bank version", (value) => { value.bank_version = "spectrum_demo_v2"; }],
    ["question version", (value) => { value.questions[0].version = 2; }],
    ["answer version", (value) => { value.responses[0].question_version = 2; }],
    ["duplicate question", (value) => { value.questions[1].id = value.questions[0].id; }],
    ["missing question", (value) => { value.questions.pop(); }],
    ["wrong reviewed count", (value) => { value.n_reviewed = 3; }],
    ["wrong answer count", (value) => { value.n_answered = 3; }],
    ["wrong skip count", (value) => { value.n_skipped = 0; }],
    ["wrong depends count", (value) => { value.n_depends = 0; }],
    ["wrong target", (value) => { value.target_questions = 25; }],
    ["wrong completion flag", (value) => { value.is_complete = false; }],
    ["wrong question order", (value) => { value.responses.reverse(); }],
    ["repeated response", (value) => { value.responses[1] = value.responses[0]; }],
    ["unknown response field", (value) => { value.model = "gaussian_linear"; }],
    ["invented estimate", (value) => { value.values = [{ mean: 6, std: 1 }]; }],
  ];
  for (const [name, mutate] of malformed) {
    const value = structuredClone(completed);
    mutate(value);
    assert.equal(schemas.elicitationResponseSchema.safeParse(value).success, false, name);
  }
  const skippedPrefix = result([event(1, "skip")]);
  assert.equal(schemas.elicitationResponseSchema.safeParse(skippedPrefix).success, false);
  const prematureCompletion = { ...result([event(0)]), is_complete: true };
  assert.equal(schemas.elicitationResponseSchema.safeParse(prematureCompletion).success, false);
  const tooManyResponses = result(Array.from({ length: 5 }, (_, index) => event(index)));
  assert.equal(schemas.elicitationResponseSchema.safeParse(tooManyResponses).success, false);
});

test("the public spectrum bank passes the web contract without a second authored copy", () => {
  const bank = JSON.parse(readFileSync(
    new URL("../preferences/data/spectrum_demo_v1.json", import.meta.url), "utf8",
  ));
  assert.equal(bank.bank_version, bankVersion);
  const responses = bank.questions.map((value) => ({
    action: "answer",
    question_id: value.id,
    question_version: value.version,
    position: value.scale.anchors[1].value,
    reported_uncertainty: null,
    acceptable_range: { lower: value.scale.min, upper: value.scale.max },
  }));
  const expected = { ...result(responses), questions: bank.questions };
  assert.deepEqual(schemas.elicitationResponseSchema.parse(expected), expected);
});

test("the bridge rejects internally valid results that change any submitted answer", async (t) => {
  const submitted = { ...event(0), reported_uncertainty: { sd_fraction: 0.117 }, acceptable_range: { lower: 3, upper: 9 } };
  const input = { bank_version: bankVersion, responses: [submitted] };
  const cases = [
    ["position", [{ ...submitted, position: 7 }]],
    ["reported uncertainty", [{ ...submitted, reported_uncertainty: { sd_fraction: 0.118 } }]],
    ["acceptable range", [{ ...submitted, acceptable_range: { lower: 4, upper: 9 } }]],
    ["removed optional information", [event(0)]],
    ["answer converted to skip", [event(0, "skip")]],
    ["answer converted to depends", [event(0, "depends")]],
    ["dropped response", []],
    ["added response", [submitted, event(1)]],
  ];
  for (const [name, responses] of cases) {
    await t.test(name, async (t) => {
      const output = result(responses);
      assert.equal(schemas.elicitationResponseSchema.safeParse(output).success, true);
      t.mock.method(globalThis, "fetch", async () => Response.json(output));
      const response = await POST(request(input));
      assert.equal(response.status, 502);
      assertNoStore(response);
      assert.deepEqual(await response.json(), { error: "The session service returned an incompatible result." });
    });
  }
});

test("upstream HTTP failures expose generic errors without provider content", async (t) => {
  for (const [status, expected] of [[400, 400], [422, 400], [401, 502], [500, 502]]) {
    await t.test(`HTTP ${status}`, async (t) => {
      t.mock.method(globalThis, "fetch", async () => new Response("PRIVATE-UPSTREAM-BODY", { status }));
      const response = await POST(request());
      assert.equal(response.status, expected);
      assertNoStore(response);
      const body = await response.json();
      assert.deepEqual(Object.keys(body), ["error"]);
      assert.ok(body.error.length > 0);
      assert.equal(JSON.stringify(body).includes("PRIVATE"), false);
    });
  }
});

test("malformed response shapes are rejected without echoing their content", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ private_payload: "PRIVATE-RESULT" }));
  const response = await POST(request());
  assert.equal(response.status, 502);
  assertNoStore(response);
  const body = await response.json();
  assert.deepEqual(Object.keys(body), ["error"]);
  assert.equal(JSON.stringify(body).includes("PRIVATE"), false);
});

test("unreachable, timed-out, and malformed-JSON upstreams fail without leaking details", async (t) => {
  for (const kind of ["unreachable", "timeout", "malformed_json"]) {
    await t.test(kind, async (t) => {
      t.mock.method(globalThis, "fetch", async () => {
        if (kind === "malformed_json") return new Response("PRIVATE-NOT-JSON");
        if (kind === "timeout") throw new DOMException("PRIVATE-TIMEOUT", "TimeoutError");
        throw new Error("PRIVATE-UPSTREAM-URL-AND-RESPONSES");
      });
      const response = await POST(request());
      assert.equal(response.status, 503);
      assertNoStore(response);
      const body = await response.json();
      assert.deepEqual(Object.keys(body), ["error"]);
      const serialized = JSON.stringify(body);
      assert.equal(serialized.includes("PRIVATE"), false);
      assert.equal(serialized.includes("private-caller"), false);
    });
  }
});
