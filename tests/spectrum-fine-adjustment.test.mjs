// Run with: node --test tests/spectrum-fine-adjustment.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { compileFunction } from "node:vm";
import { test } from "node:test";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

function loadTypeScript(relativePath, imports = {}) {
  const filename = fileURLToPath(new URL(`../${relativePath}`, import.meta.url));
  const { outputText } = ts.transpileModule(readFileSync(filename, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
    },
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
const spectrum = loadTypeScript("lib/preferences/spectrum.ts", {
  "@/lib/validations/elicitation-schemas": schemas,
});
const { SpectrumFineAdjustment } = loadTypeScript(
  "components/preferences/spectrum-fine-adjustment.tsx",
  { "@/lib/preferences/spectrum": spectrum },
);
const scale = {
  min: 17, max: 22, step: 1, unit: "hour", format: "clock_hour", anchors: [],
};

function render(overrides = {}) {
  return renderToStaticMarkup(createElement(SpectrumFineAdjustment, {
    label: "Position", value: null, min: 17, max: 22, step: 1,
    disabled: false, onChange: () => {}, scale, ...overrides,
  }));
}

function options(markup) {
  return [...markup.matchAll(/<option([^>]*)>([^<]*)<\/option>/g)].map((match) => ({
    value: /value="([^"]*)"/.exec(match[1])[1],
    label: match[2], selected: match[1].includes("selected="),
  }));
}

test("clock fine adjustment labels hours as times and leaves null explicitly unanswered", () => {
  let changes = 0;
  const markup = render({ onChange: () => { changes += 1; } });
  const entries = options(markup);
  assert.match(markup, /<label>Position<select/);
  assert.doesNotMatch(markup, /<input/);
  assert.deepEqual(entries.map(({ value, label }) => [value, label]), [
    ["", "Choose a time"], ["17", "5:00 pm"], ["18", "6:00 pm"],
    ["19", "7:00 pm"], ["20", "8:00 pm"], ["21", "9:00 pm"],
    ["22", "10:00 pm"],
  ]);
  assert.deepEqual(entries.filter((entry) => entry.selected).map((entry) => entry.value), [""]);
  assert.equal(changes, 0, "rendering the preview must not create an answer");
});

test("clock fine adjustment retains numeric selection and obeys narrowed bounds and step", () => {
  const markup = render({ value: 20, min: 18, max: 22, step: 2 });
  const entries = options(markup);
  assert.deepEqual(entries.map((entry) => entry.value), ["", "18", "20", "22"]);
  assert.deepEqual(entries.filter((entry) => entry.selected).map((entry) => entry.label), ["8:00 pm"]);
  const coincident = options(render({ value: 20, min: 20, max: 20 }));
  assert.deepEqual(coincident.map((entry) => entry.value), ["", "20"]);
});

test("clock formatting distinguishes noon and midnight and supports disabled controls", () => {
  const midnight = options(render({ value: 0, min: 0, max: 1 }));
  assert.equal(midnight.find((entry) => entry.selected).label, "12:00 am");
  const noon = render({ value: 12, min: 11, max: 13, disabled: true });
  assert.equal(options(noon).find((entry) => entry.selected).label, "12:00 pm");
  assert.match(noon, /<select[^>]* disabled=""/);
});

test("non-clock adjustments remain bounded numeric inputs with explicit empty values", () => {
  const empty = render({ scale: undefined, min: 8, max: 28, step: 0.1 });
  assert.match(empty, /type="number"/);
  assert.match(empty, /min="8" max="28" step="0.1" value=""/);
  assert.doesNotMatch(empty, /<select/);
  const populated = render({
    scale: { ...scale, format: "number" }, value: 13.7,
    min: 8, max: 28, step: 0.1, disabled: true,
  });
  assert.match(populated, /disabled=""/);
  assert.match(populated, /value="13.7"/);
});
