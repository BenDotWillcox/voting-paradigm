// Run with: node --test tests/spectrum-controls.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { compileFunction } from "node:vm";
import { test } from "node:test";
import ts from "typescript";

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
const {
  emptySpectrumDraft,
  formatSpectrumValue,
  formatSpectrumUncertainty,
  initialSpectrumPosition,
  sampleSpectrumCurve,
  spectrumAxisTicks,
  spectrumDraftCurve,
  spectrumValueAtFraction,
  uncertaintyFromVerticalDrag,
  updateSpectrumHandle,
  DEFAULT_UNCERTAINTY_SD,
  SPECTRUM_DENSITY_MAX,
} = loadTypeScript("lib/preferences/spectrum.ts", {
  "@/lib/validations/elicitation-schemas": schemas,
});

const scale = { min: 0, max: 100, step: 10, unit: "%", format: "number", anchors: [] };

function integral(points) {
  return points.slice(1).reduce((sum, current, index) => {
    const previous = points[index];
    return sum + (current.position - previous.position) * (current.density + previous.density) / 2;
  }, 0);
}

test("new drafts do not imply a midpoint, uncertainty, or acceptable range", () => {
  assert.deepEqual(emptySpectrumDraft(), {
    position: null, reported_uncertainty: null, acceptable_range: null,
  });
  assert.notEqual(emptySpectrumDraft(), emptySpectrumDraft());
  assert.deepEqual(spectrumDraftCurve(emptySpectrumDraft(), scale), []);
  assert.deepEqual(spectrumDraftCurve({ ...emptySpectrumDraft(), position: 50 }, scale), []);
  assert.deepEqual(spectrumDraftCurve({ ...emptySpectrumDraft(), reported_uncertainty: { sd_fraction: 0.08 } }, scale), []);
});

test("displayed initial positions lie on each demonstration's step grid", () => {
  for (const [min, max, step, expected] of [
    [17, 22, 1, 20], [0, 100, 10, 50], [7, 56, 1, 32], [1, 12, 1, 7],
  ]) {
    const value = initialSpectrumPosition({ ...scale, min, max, step });
    assert.equal(value, expected);
    assert.equal((value - min) % step, 0);
    assert.ok(value >= min && value <= max);
  }
});

test("curve area is one, density is finite, and the mode stays at the chosen position", () => {
  for (const position of [0, 0.01, 0.2, 0.371, 0.5, 0.99, 1]) {
    for (const sd_fraction of [0.08, 0.103, 0.15, 0.217, 0.28]) {
      const points = sampleSpectrumCurve(position, { sd_fraction });
      assert.equal(points[0].position, 0);
      assert.equal(points.at(-1).position, 1);
      assert.ok(Math.abs(integral(points) - 1) < 1e-12);
      assert.ok(points.every((point) => Number.isFinite(point.density) && point.density >= 0));
      assert.ok(points.every((point) => point.density < SPECTRUM_DENSITY_MAX));
      assert.equal(points.reduce((peak, point) => point.density > peak.density ? point : peak).position, position);
    }
  }
});

test("increasing reported certainty narrows the curve and raises its peak on a fixed density axis", () => {
  for (const position of [0, 0.5, 1]) {
    const peaks = [];
    const spreads = [];
    for (const sd_fraction of [0.28, 0.217, 0.15, 0.103, 0.08]) {
      const points = sampleSpectrumCurve(position, { sd_fraction });
      peaks.push(Math.max(...points.map((point) => point.density)));
      spreads.push(integral(points.map((point) => ({
        ...point, density: point.density * (point.position - position) ** 2,
      }))));
    }
    assert.ok(peaks.slice(1).every((value, index) => peaks[index] < value));
    assert.ok(spreads.slice(1).every((value, index) => spreads[index] > value));
  }
});

test("acceptable ranges neither truncate nor change position and uncertainty visualization", () => {
  const draft = { position: 60, reported_uncertainty: { sd_fraction: 0.117 }, acceptable_range: null };
  const original = structuredClone(draft);
  const expected = spectrumDraftCurve(draft, scale);
  for (const acceptable_range of [
    null, { lower: 30, upper: 90 }, { lower: 0, upper: 100 },
    { lower: 60, upper: 60 }, { lower: 0, upper: 20 },
  ]) {
    assert.deepEqual(spectrumDraftCurve({ ...draft, acceptable_range }, scale), expected);
  }
  assert.deepEqual(draft, original);
});

test("axis formatting preserves clock hours and physical units", () => {
  assert.equal(formatSpectrumValue(50, scale), "50%");
  assert.equal(formatSpectrumValue(17, { ...scale, format: "clock_hour" }), "5:00 pm");
  assert.equal(formatSpectrumValue(22, { ...scale, format: "clock_hour" }), "10:00 pm");
  assert.equal(formatSpectrumValue(35, { ...scale, unit: "days" }), "35 days");
  assert.equal(formatSpectrumValue(1, { ...scale, unit: "weeks" }), "1 week");
});

test("axis ticks follow every authored scale's numeric grid, not its semantic anchors", () => {
  const bank = JSON.parse(readFileSync(new URL("../preferences/data/spectrum_demo_v1.json", import.meta.url), "utf8"));
  for (const question of bank.questions) {
    const axis = question.scale;
    const ticks = spectrumAxisTicks(axis, 1000);
    const intervalCount = Math.round((axis.max - axis.min) / axis.step);
    assert.equal(ticks.length, intervalCount + 1);
    assert.equal(ticks[0].value, axis.min);
    assert.equal(ticks.at(-1).value, axis.max);
    assert.notEqual(ticks[0].label, null);
    assert.notEqual(ticks.at(-1).label, null);
    for (const [index, tick] of ticks.entries()) {
      assert.equal(tick.value, axis.min + index * axis.step);
      assert.equal(tick.fraction, (tick.value - axis.min) / (axis.max - axis.min));
    }
    assert.deepEqual(spectrumAxisTicks({ ...axis, anchors: [] }, 1000), ticks);
  }
  const hours = spectrumAxisTicks(bank.questions[0].scale, 1000);
  assert.deepEqual(hours.map((tick) => tick.label), ["5 pm", "6 pm", "7 pm", "8 pm", "9 pm", "10 pm"]);
  assert.equal(hours.find((tick) => tick.value === 20).fraction, 0.6);
  assert.deepEqual(spectrumAxisTicks(scale, 500).map((tick) => tick.label),
    ["0", "10", "20", "30", "40", "50", "60", "70", "80", "90", "100"]);
});

test("narrow axes thin labels with endpoint clearance without redistributing ticks", () => {
  const desktop = spectrumAxisTicks(scale, 500);
  const narrow = spectrumAxisTicks(scale, 240);
  assert.deepEqual(narrow.map(({ value, fraction }) => ({ value, fraction })),
    desktop.map(({ value, fraction }) => ({ value, fraction })));
  assert.deepEqual(narrow.filter((tick) => tick.label !== null).map((tick) => tick.value),
    [0, 20, 40, 60, 80, 100]);
  const uneven = spectrumAxisTicks({ ...scale, min: 1, max: 12, step: 1, unit: "weeks" }, 240);
  const labeled = uneven.filter((tick) => tick.label !== null);
  assert.deepEqual(labeled.map((tick) => tick.value), [1, 4, 7, 12]);
  assert.ok(labeled.slice(1).every((tick, index) =>
    (tick.fraction - labeled[index].fraction) * 240 >= 44));
  assert.equal(uneven.find((tick) => tick.value === 4).fraction, 3 / 11);
  for (const width of [0, 20]) {
    assert.deepEqual(spectrumAxisTicks(scale, width).filter((tick) => tick.label !== null)
      .map((tick) => tick.value), [0, 100]);
  }
});

test("public comment labels may be sparse while every day remains selectable", () => {
  const bank = JSON.parse(readFileSync(new URL("../preferences/data/spectrum_demo_v1.json", import.meta.url), "utf8"));
  const question = bank.questions.find((item) => item.id === "public_comment_days");
  const axis = question.scale;
  assert.equal(axis.step, 1);
  const expectedValues = Array.from({ length: 50 }, (_, index) => index + 7);
  for (const width of [240, 1000]) {
    const ticks = spectrumAxisTicks(axis, width);
    assert.deepEqual(ticks.map((tick) => tick.value), expectedValues);
    assert.ok(ticks.some((tick) => tick.label === null));
    for (const value of expectedValues) {
      assert.equal(spectrumValueAtFraction((value - axis.min) / (axis.max - axis.min), axis), value);
      assert.ok(schemas.isScaleValue(value, axis));
    }
    for (const position of [8, 29]) {
      assert.ok(schemas.spectrumEventMatchesQuestion({
        action: "answer", question_id: question.id, question_version: question.version,
        position, reported_uncertainty: null, acceptable_range: { lower: 8, upper: 29 },
      }, question));
    }
  }
  assert.equal(schemas.isScaleValue(8.5, axis), false);
});

test("axis ticks preserve decimal steps and reject invalid layout widths", () => {
  const decimalScale = { ...scale, min: -0.3, max: 0.7, step: 0.1 };
  const ticks = spectrumAxisTicks(decimalScale, 1000);
  assert.deepEqual(ticks.map((tick) => tick.value), [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]);
  assert.ok(ticks.every((tick) => schemas.isScaleValue(tick.value, decimalScale)));
  assert.equal(ticks[3].label, "0");
  for (const width of [-1, NaN, Infinity]) {
    assert.throws(() => spectrumAxisTicks(scale, width), RangeError);
  }
});

test("curve sampling rejects positions outside the normalized question axis", () => {
  for (const position of [-0.1, 1.1, NaN, Infinity]) {
    assert.throws(() => sampleSpectrumCurve(position, { sd_fraction: 0.15 }), RangeError);
  }
});

test("width is continuous numeric data with display-only percentage formatting", () => {
  assert.equal(DEFAULT_UNCERTAINTY_SD, 0.15);
  assert.equal(formatSpectrumUncertainty({ sd_fraction: 0.15 }), "15% of scale");
  assert.equal(formatSpectrumUncertainty({ sd_fraction: 0.137 }), "13.7% of scale");
  for (const sd_fraction of [0.001, 0.079, 0.281, NaN, Infinity]) {
    assert.throws(() => sampleSpectrumCurve(0.5, { sd_fraction }), RangeError);
  }
});

test("horizontal drags clamp and snap to exact integer and decimal API grids", () => {
  const grids = [
    { ...scale, min: 17, max: 22, step: 1 },
    { ...scale, min: 7, max: 56, step: 1 },
    { ...scale, min: 0, max: 1, step: 0.1 },
    { ...scale, min: -0.3, max: 0.7, step: 0.1 },
    { ...scale, min: 0.01, max: 0.11, step: 0.02 },
    { ...scale, min: 1e-7, max: 11e-7, step: 1e-7 },
  ];
  for (const grid of grids) {
    for (const fraction of [-1, 0, 0.01, 0.15, 0.3, 0.51, 0.87, 1, 2]) {
      const value = spectrumValueAtFraction(fraction, grid);
      assert.ok(schemas.isScaleValue(value, grid), `${value} must be on the ${grid.step} grid`);
    }
    assert.equal(spectrumValueAtFraction(-1, grid), grid.min);
    assert.equal(spectrumValueAtFraction(2, grid), grid.max);
  }
  assert.equal(spectrumValueAtFraction(0.3, grids[2]), 0.3);
  assert.throws(() => spectrumValueAtFraction(NaN, scale), RangeError);
});

test("vertical drag tracks the visible peak at center and endpoints with bounded rounding error", () => {
  const graphHeight = 200;
  const peak = (position, sd_fraction) => Math.max(
    ...sampleSpectrumCurve(position, { sd_fraction }).map((point) => point.density),
  );
  for (const position of [0, 0.37, 0.5, 1]) {
    for (const deltaY of [-20, -5, 5, 20]) {
      const start = 0.15;
      const width = uncertaintyFromVerticalDrag(start, deltaY, graphHeight, position);
      assert.ok(deltaY < 0 ? width < start : width > start);
      const actualDeltaY = (peak(position, start) - peak(position, width))
        / SPECTRUM_DENSITY_MAX * graphHeight;
      assert.ok(Math.abs(actualDeltaY - deltaY) < 1, `Peak travel ${actualDeltaY} must track pointer ${deltaY}`);
    }
    assert.equal(uncertaintyFromVerticalDrag(0.1234, 0, graphHeight, position), 0.1234);
    assert.equal(uncertaintyFromVerticalDrag(0.15, -10000, graphHeight, position), 0.08);
    assert.equal(uncertaintyFromVerticalDrag(0.15, 10000, graphHeight, position), 0.28);
  }
  assert.throws(() => uncertaintyFromVerticalDrag(0.15, 1, 0), RangeError);
  assert.throws(() => uncertaintyFromVerticalDrag(0.15, 1, 100, NaN), RangeError);
});

test("handle updates preserve unrelated signals and never invent optional acceptance bounds", () => {
  const empty = emptySpectrumDraft();
  assert.deepEqual(updateSpectrumHandle(empty, "position", 0), { ...empty, position: 0 });
  assert.deepEqual(updateSpectrumHandle(empty, "uncertainty", 0.1736), {
    ...empty, reported_uncertainty: { sd_fraction: 0.174 },
  });
  assert.deepEqual(updateSpectrumHandle(empty, "lower", 20), empty);
  assert.deepEqual(updateSpectrumHandle(empty, "upper", 80), empty);
  const draft = {
    position: 60, reported_uncertainty: { sd_fraction: 0.08 },
    acceptable_range: { lower: 30, upper: 90 },
  };
  const original = structuredClone(draft);
  assert.deepEqual(updateSpectrumHandle(draft, "position", 0), { ...draft, position: 0 });
  assert.deepEqual(updateSpectrumHandle(draft, "lower", 100), {
    ...draft, acceptable_range: { lower: 90, upper: 90 },
  });
  assert.deepEqual(updateSpectrumHandle(draft, "upper", 0), {
    ...draft, acceptable_range: { lower: 30, upper: 30 },
  });
  assert.deepEqual(updateSpectrumHandle(draft, "uncertainty", 0.2), {
    ...draft, reported_uncertainty: { sd_fraction: 0.2 },
  });
  assert.deepEqual(draft, original);
  assert.throws(() => updateSpectrumHandle(draft, "position", Infinity), RangeError);
});
