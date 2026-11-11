// Run: node --test scripts/tests/test_expressive_scalar_graph.mjs
// Uses the project's Python environment, or EXPRESSIVE_TEST_PYTHON when supplied.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const source = readFileSync(new URL("../../lib/expressive-scalar-graph.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
});
const helpers = {};
runInThisContext(`(function(exports) { ${outputText}\n })`)(helpers);
const { scalarPresentationPreview, scalarPresentationScore, taperAnchor, taperRailPoint, taperRailWidth, TAPER_RAIL_TOP_INSET, SCALAR_DOMAIN, scalarFocusRange, scalarGraphTicks } = helpers;
const baseline = {
  ideal: 4.55, lower_half_width: 2, upper_half_width: 2,
  approval_min: 0, approval_max: 100, probe: 4.55,
};

const parityBallots = [
  baseline,
  { ideal: 6.12345, lower_half_width: 2.331, upper_half_width: 1.378, approval_min: 1.1234, approval_max: 12.6321, probe: 7.3333333 },
  { ideal: 7.371, lower_half_width: 0.1, upper_half_width: 0.1, approval_min: 0, approval_max: 100, probe: 7.391 },
  { ideal: 7.371, lower_half_width: 0.0001, upper_half_width: 0.00007, approval_min: 7.3708, approval_max: 7.3712, probe: 7.37103 },
  { ideal: 6.2345, lower_half_width: 2, upper_half_width: 3, approval_min: 6.2345, approval_max: 6.2345, probe: 6.2345 },
  { ideal: 0, lower_half_width: 100, upper_half_width: 4, approval_min: 0, approval_max: 9, probe: 0 },
  { ideal: 100, lower_half_width: 4, upper_half_width: 100, approval_min: 3, approval_max: 100, probe: 100 },
  { ideal: 6, lower_half_width: 2, upper_half_width: 3, approval_min: 4.2, approval_max: 8.7, probe: 4.2 },
  { ideal: 1.1, lower_half_width: 100, upper_half_width: 100, approval_min: 0, approval_max: 100, probe: 99.9 },
  { ideal: 6, lower_half_width: Number.MIN_VALUE, upper_half_width: 1e-300, approval_min: 0, approval_max: 100, probe: 7 },
  { ideal: 8, lower_half_width: 0.1, upper_half_width: 0.1, approval_min: 0, approval_max: 100, probe: 12.1 },
  { ideal: 10.000000000001, lower_half_width: 3.14159, upper_half_width: 0.12345, approval_min: 0.00000001, approval_max: 99.99999999, probe: 10.123456789 },
];

test("presentation samples and continuous probes agree with the actual Python evaluator", () => {
  const cases = parityBallots.map((ballot) => ({
    ballot,
    values: scalarPresentationPreview(ballot).points.map(({ value }) => value),
    probes: [...new Set([
      0, 0.1, 1.1, 6.12345, 100, ballot.probe, ballot.ideal,
      ballot.approval_min, ballot.approval_max,
      ballot.approval_min - 1e-10, ballot.approval_min + 1e-10,
      ballot.approval_max - 1e-10, ballot.approval_max + 1e-10,
      ballot.ideal - ballot.lower_half_width, ballot.ideal + ballot.upper_half_width,
    ])].filter((value) => value >= 0 && value <= 100),
  }));
  const python = process.env.EXPRESSIVE_TEST_PYTHON || [
    join(root, "venv", "Scripts", "python.exe"), join(root, "venv", "bin", "python"),
  ].find(existsSync) || "python";
  const reference = spawnSync(python, ["-c", `
import json, sys
from dataclasses import asdict
from expressive.scalar import ScalarBallot, SCALAR_MODEL_VERSION, scalar_unclipped_score, evaluate_scalar
results = []
for case in json.load(sys.stdin):
    fields = {key: value for key, value in case["ballot"].items() if key != "probe"}
    ballot = ScalarBallot(**fields)
    results.append({
        "model": SCALAR_MODEL_VERSION,
        "scores": [scalar_unclipped_score(ballot, value) for value in case["values"]],
        "probes": [asdict(evaluate_scalar(ballot, value)) for value in case["probes"]],
    })
json.dump(results, sys.stdout, allow_nan=False)
`], { cwd: root, input: JSON.stringify(cases), encoding: "utf8", maxBuffer: 2 * 1024 * 1024 });
  assert.equal(reference.status, 0, reference.error?.message || reference.stderr);
  const expected = JSON.parse(reference.stdout);
  cases.forEach(({ ballot, probes }, caseIndex) => {
    const actual = scalarPresentationPreview(ballot);
    assert.equal(actual.model, expected[caseIndex].model);
    actual.points.forEach((point, pointIndex) => {
      const score = expected[caseIndex].scores[pointIndex];
      assert.ok(Math.abs(point.unclipped_score - score) <= 1e-12, `case ${caseIndex}, plot rate ${point.value}`);
    });
    probes.forEach((value, probeIndex) => {
      const probe = scalarPresentationScore(ballot, value);
      const referenceProbe = expected[caseIndex].probes[probeIndex];
      assert.equal(probe.value, referenceProbe.value);
      assert.equal(probe.approved, referenceProbe.approved, `case ${caseIndex}, approval at ${value}`);
      assert.ok(Math.abs(probe.score - referenceProbe.score) <= 1e-12, `case ${caseIndex}, probe ${value}`);
    });
  });
});

test("continuous landmarks survive sampling without rounding or duplicated coordinates", () => {
  for (const ballot of parityBallots) {
    const points = scalarPresentationPreview(ballot).points;
    const values = points.map(({ value }) => value);
    for (const landmark of [ballot.ideal, ballot.approval_min, ballot.approval_max, ballot.probe]) {
      assert.ok(values.includes(landmark));
    }
    for (const landmark of [ballot.ideal - ballot.lower_half_width, ballot.ideal + ballot.upper_half_width]) {
      if (landmark >= 0 && landmark <= 100) assert.ok(values.includes(landmark));
    }
    points.forEach(({ value, unclipped_score }, index) => {
      assert.ok(value >= 0 && value <= 100);
      assert.ok(Number.isFinite(unclipped_score) && unclipped_score >= 0 && unclipped_score <= 1);
      if (index > 0) assert.ok(value > points[index - 1].value);
    });
  }
});

test("narrow tapers retain ideal-relative detail while the peak moves between grid positions", () => {
  for (const ideal of [7.371, 7.3725]) {
    const ballot = { ...baseline, ideal, lower_half_width: 0.1, upper_half_width: 0.1 };
    const values = scalarPresentationPreview(ballot).points.map(({ value }) => value);
    for (let step = 1; step <= 32; step += 1) {
      assert.ok(values.includes(ideal - ballot.lower_half_width * step / 8));
      assert.ok(values.includes(ideal + ballot.upper_half_width * step / 8));
    }
  }
});

test("inclusive clipping never widens bounds or renormalizes surviving scores", () => {
  const ballot = { ...baseline, approval_min: 4.2, approval_max: 8.7 };
  const unrestricted = { ...ballot, approval_min: 0, approval_max: 100 };
  for (const value of [4.2, 4.2 + 1e-10, 6, 8.7 - 1e-10, 8.7]) {
    const probe = scalarPresentationScore(ballot, value);
    assert.equal(probe.approved, true);
    assert.equal(probe.score, scalarPresentationScore(unrestricted, value).score);
  }
  for (const value of [4.2 - 1e-10, 8.7 + 1e-10]) {
    assert.deepEqual(scalarPresentationScore(ballot, value), { value, score: 0, approved: false });
  }
});

test("a singleton approval interval retains the ideal and zeros arbitrarily close alternatives", () => {
  const ballot = { ...baseline, ideal: 6.2345, approval_min: 6.2345, approval_max: 6.2345, probe: 6.2345 };
  assert.deepEqual(scalarPresentationPreview(ballot).probe, { value: 6.2345, score: 1, approved: true });
  for (const value of [ballot.ideal - 1e-10, ballot.ideal + 1e-10]) {
    assert.deepEqual(scalarPresentationScore(ballot, value), { value, score: 0, approved: false });
  }
});

test("sampling is deterministic and never mutates ballot state", () => {
  const ballot = Object.freeze({ ...baseline });
  assert.deepEqual(scalarPresentationPreview(ballot), scalarPresentationPreview(ballot));
  scalarPresentationScore(ballot, 7.12345);
  assert.deepEqual(ballot, baseline);
});

test("invalid plot states and readout values fail explicitly", () => {
  for (const field of ["ideal", "approval_min", "approval_max", "probe"]) {
    for (const value of [NaN, Infinity, -1, 101]) {
      assert.throws(() => scalarPresentationPreview({ ...baseline, [field]: value }), RangeError);
    }
  }
  for (const field of ["lower_half_width", "upper_half_width"]) {
    for (const value of [NaN, Infinity, 0, -1, 101]) {
      assert.throws(() => scalarPresentationPreview({ ...baseline, [field]: value }), RangeError);
    }
  }
  assert.throws(() => scalarPresentationPreview({ ...baseline, approval_min: 7 }), RangeError);
  assert.throws(() => scalarPresentationPreview({ ...baseline, approval_max: 4 }), RangeError);
  for (const value of [NaN, Infinity, -1, 101]) {
    assert.throws(() => scalarPresentationScore(baseline, value), RangeError);
  }
});

test("in-domain taper anchors retain their true half-score locations", () => {
  assert.deepEqual(taperAnchor(6, 2, "lower"), { value: 4, displayValue: 4, offScale: false });
  assert.deepEqual(taperAnchor(6, 3, "upper"), { value: 9, displayValue: 9, offScale: false });
  assert.deepEqual(taperAnchor(6, 6, "lower"), { value: 0, displayValue: 0, offScale: false });
  assert.deepEqual(taperAnchor(6, 94, "upper"), { value: 100, displayValue: 100, offScale: false });
});

test("off-domain taper anchors clamp display position while preserving the full width", () => {
  assert.deepEqual(taperAnchor(1, 10, "lower"), { value: -9, displayValue: 0, offScale: true });
  assert.deepEqual(taperAnchor(99, 10, "upper"), { value: 109, displayValue: 100, offScale: true });
  assert.deepEqual(taperAnchor(0, 100, "lower"), { value: -100, displayValue: 0, offScale: true });
  assert.deepEqual(taperAnchor(100, 100, "upper"), { value: 200, displayValue: 100, offScale: true });
});

test("invalid taper parameters are rejected", () => {
  for (const ideal of [NaN, Infinity, -1, 101]) assert.throws(() => taperAnchor(ideal, 2, "lower"), RangeError);
  for (const width of [NaN, Infinity, 0, -1, 101]) assert.throws(() => taperAnchor(6, width, "lower"), RangeError);
  assert.throws(() => taperAnchor(6, 2, "invalid"), RangeError);
});

const desktopRail = { left: 64, right: 966, top: 76, bottom: 374 };
const mobileRail = { left: 52, right: 358, top: 82, bottom: 434 };
const close = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 1e-10, `${message}: ${actual} versus ${expected}`);

test("taper rail geometry round-trips both sides at interior, edge, and near-edge ideals", () => {
  for (const bounds of [desktopRail, mobileRail]) {
    for (const ideal of [0, 1e-9, 0.1, 6, 99.9, 100 - 1e-9, 100]) {
      for (const direction of ["lower", "upper"]) {
        const distance = direction === "lower" ? ideal : 100 - ideal;
        for (const width of [0, 0.1, 3.12345, 6, 99.9, 100, distance]) {
          const point = taperRailPoint(ideal, width, direction, bounds);
          close(taperRailWidth(ideal, direction, point, bounds), width, `${ideal}/${direction}/${width}`);
          assert.equal(point.offScale, width > distance);
          assert.ok(point.x >= bounds.left && point.x <= bounds.right);
          assert.ok(point.y >= bounds.top && point.y <= (bounds.top + bounds.bottom) / 2);
        }
      }
    }
  }
});

test("taper handles meet the edge continuously before moving upward", () => {
  const bounds = desktopRail;
  const middleY = (bounds.top + bounds.bottom) / 2;
  for (const direction of ["lower", "upper"]) {
    const ideal = 6;
    const distance = direction === "lower" ? ideal : 100 - ideal;
    const edge = direction === "lower" ? bounds.left : bounds.right;
    const before = taperRailPoint(ideal, distance - 1e-8, direction, bounds);
    const corner = taperRailPoint(ideal, distance, direction, bounds);
    const after = taperRailPoint(ideal, distance + 1e-8, direction, bounds);
    assert.deepEqual(corner, { x: edge, y: middleY, offScale: false });
    assert.ok(Math.hypot(before.x - corner.x, before.y - corner.y) < 1e-5);
    assert.ok(Math.hypot(after.x - corner.x, after.y - corner.y) < 1e-5);
    assert.equal(before.y, middleY);
    assert.equal(after.x, edge);
    assert.ok(after.y < middleY);
    close(taperRailWidth(ideal, direction, corner, bounds), distance, "corner inverse");
  }
});

test("diagonal pointer travel through the inner corner has no nearest-segment jump", () => {
  const bounds = desktopRail;
  const middleY = (bounds.top + bounds.bottom) / 2;
  for (const direction of ["lower", "upper"]) {
    const edge = direction === "lower" ? bounds.left : bounds.right;
    const inward = direction === "lower" ? 1 : -1;
    let previous;
    for (let index = -100; index <= 100; index += 1) {
      const point = { x: edge + inward * (10 + index * 0.01), y: middleY - (10 - index * 0.01) };
      const width = taperRailWidth(6, direction, point, bounds);
      if (previous !== undefined) assert.ok(Math.abs(width - previous) < 0.01);
      previous = width;
    }
  }
});

test("an ideal on the domain edge uses vertical travel without losing width resolution", () => {
  const bounds = desktopRail;
  for (const [ideal, direction, edge] of [[0, "lower", bounds.left], [100, "upper", bounds.right]]) {
    const points = [0, 0.1, 1, 7.5, 100].map((width) => taperRailPoint(ideal, width, direction, bounds));
    points.forEach((point, index) => {
      assert.equal(point.x, edge);
      if (index > 0) assert.ok(point.y < points[index - 1].y);
    });
    assert.equal(points.at(-1).y, bounds.top + TAPER_RAIL_TOP_INSET);
    assert.ok(points.at(-1).y - bounds.top > 19, "rail hit target stays below the ideal");
    close(taperRailWidth(ideal, direction, { x: edge, y: bounds.top + TAPER_RAIL_TOP_INSET }, bounds), 100, "top rail endpoint");
  }
});

test("maximum-width controls stay continuous when the ideal reaches the opposite edge", () => {
  for (const [ideal, nearIdeal, direction] of [[100, 100 - 1e-9, "lower"], [0, 1e-9, "upper"]]) {
    const endpoint = taperRailPoint(ideal, 100, direction, desktopRail);
    const approaching = taperRailPoint(nearIdeal, 100, direction, desktopRail);
    assert.ok(Math.hypot(endpoint.x - approaching.x, endpoint.y - approaching.y) < 1e-6);
    close(taperRailWidth(nearIdeal, direction, approaching, desktopRail), 100, "near endpoint inverse");
  }
});

test("rail pointer offsets preserve width and off-plot travel stays bounded", () => {
  const bounds = desktopRail;
  const start = taperRailPoint(6, 11.2345, "lower", bounds);
  const labelOffset = { x: 100, y: -80 };
  const pointer = { x: start.x + labelOffset.x, y: start.y + labelOffset.y };
  close(taperRailWidth(6, "lower", { x: pointer.x - labelOffset.x, y: pointer.y - labelOffset.y }, bounds), 11.2345, "label grab offset");
  assert.equal(taperRailWidth(6, "lower", { x: -1e6, y: -1e6 }, bounds), 100);
  assert.equal(taperRailWidth(6, "lower", { x: 1e6, y: 1e6 }, bounds), 0);
  assert.equal(taperRailWidth(6, "upper", { x: 1e6, y: -1e6 }, bounds), 100);
  assert.equal(taperRailWidth(6, "upper", { x: -1e6, y: 1e6 }, bounds), 0);
});

test("invalid rail geometry fails explicitly", () => {
  for (const ideal of [NaN, Infinity, -1, 101]) assert.throws(() => taperRailPoint(ideal, 2, "lower", desktopRail), RangeError);
  for (const width of [NaN, Infinity, -1, 101]) assert.throws(() => taperRailPoint(6, width, "lower", desktopRail), RangeError);
  for (const bounds of [{ ...desktopRail, right: 64 }, { ...desktopRail, bottom: 76 }, { ...desktopRail, bottom: 124 }, { ...desktopRail, top: NaN }]) {
    assert.throws(() => taperRailPoint(6, 2, "lower", bounds), RangeError);
    assert.throws(() => taperRailWidth(6, "lower", { x: 0, y: 0 }, bounds), RangeError);
  }
  assert.throws(() => taperRailPoint(6, 2, "invalid", desktopRail), RangeError);
  assert.throws(() => taperRailWidth(6, "lower", { x: NaN, y: 0 }, desktopRail), RangeError);
});

test("focus rounds five-point bounds outward to whole percentages and clips at the domain edges", () => {
  assert.deepEqual(SCALAR_DOMAIN, { minimum: 0, maximum: 100 });
  for (const [ideal, minimum, maximum] of [[0, 0, 5], [4.55, 0, 10], [4.816, 0, 10], [50, 45, 55], [50.816, 45, 56], [98, 93, 100], [98.816, 93, 100], [100, 95, 100]]) {
    const range = scalarFocusRange(ideal);
    assert.deepEqual(range, { minimum, maximum });
    for (const narrow of [false, true]) {
      const ticks = scalarGraphTicks(range, narrow);
      assert.equal(ticks[0], minimum);
      assert.equal(ticks.at(-1), maximum);
      assert.ok(ticks.every((value, index) => !index || value > ticks[index - 1]));
    }
  }
  for (const value of [-1, 101, NaN, Infinity]) assert.throws(() => scalarFocusRange(value), RangeError);
});

test("viewport sampling preserves exact scores and ballot state across zoom levels", () => {
  for (const ideal of [0, 4.55, 50, 98, 100]) {
    const ballot = Object.freeze({ ...baseline, ideal, probe: ideal, approval_min: 0, approval_max: 100 });
    for (const view of [SCALAR_DOMAIN, scalarFocusRange(ideal)]) {
      const plot = scalarPresentationPreview(ballot, view);
      assert.equal(plot.points[0].value, view.minimum);
      assert.equal(plot.points.at(-1).value, view.maximum);
      assert.ok(plot.points.length < 400, "rendering cost stays bounded at either zoom level");
      for (const point of plot.points) {
        close(point.unclipped_score, scalarPresentationScore(ballot, point.value).score, "zoom does not alter scores");
      }
      assert.ok(plot.points.some((point) => point.value === ideal && point.unclipped_score === 1));
    }
  }
});

test("zoomed taper rails preserve widths through both viewport edges", () => {
  for (const ideal of [0, 4.55, 50, 98, 100]) {
    const view = scalarFocusRange(ideal);
    for (const bounds of [desktopRail, mobileRail].map((box) => ({ ...box, ...view }))) {
      for (const direction of ["lower", "upper"]) {
        const distance = direction === "lower" ? ideal - view.minimum : view.maximum - ideal;
        for (const width of [0, 0.1, 2, 5, 40, 100, distance]) {
          const point = taperRailPoint(ideal, width, direction, bounds);
          close(taperRailWidth(ideal, direction, point, bounds), width, "zoom rail round trip");
          assert.ok(point.x >= bounds.left - 1e-10 && point.x <= bounds.right + 1e-10);
          assert.ok(point.y >= bounds.top + TAPER_RAIL_TOP_INSET && point.y <= (bounds.top + bounds.bottom) / 2);
        }
      }
    }
  }
});
