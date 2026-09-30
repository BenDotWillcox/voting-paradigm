// Run with: node --test tests/spectrum-answer.test.mjs
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
const utils = loadTypeScript("lib/utils.ts");
const button = loadTypeScript("components/ui/button.tsx", { "@/lib/utils": utils });
const popover = loadTypeScript("components/ui/popover.tsx", { "@/lib/utils": utils });
const fineAdjustment = loadTypeScript("components/preferences/spectrum-fine-adjustment.tsx", {
  "@/lib/preferences/spectrum": spectrum,
});
const { SpectrumAnswer } = loadTypeScript("components/preferences/spectrum-answer.tsx", {
  "@/lib/validations/elicitation-schemas": schemas,
  "@/lib/preferences/spectrum": spectrum,
  "@/components/ui/button": button,
  "@/components/ui/popover": popover,
  "./spectrum-fine-adjustment": fineAdjustment,
  "./spectrum-answer.module.css": { default: new Proxy({}, { get: (_, name) => String(name) }) },
});
const question = JSON.parse(readFileSync(
  new URL("../preferences/data/spectrum_demo_v1.json", import.meta.url), "utf8",
)).questions[0];

function render(draft = spectrum.emptySpectrumDraft(), extraProps = {}) {
  return renderToStaticMarkup(createElement(SpectrumAnswer, {
    question, draft, onChange: () => {}, ...extraProps,
  }));
}

function findButton(markup, text) {
  const match = [...markup.matchAll(/<button([^>]*)>([\s\S]*?)<\/button>/g)]
    .find((entry) => entry[2].replace(/<[^>]*>/g, "") === text);
  assert.ok(match, `Expected a button labelled ${text}`);
  assert.match(match[1], /type="button"/, "Optional controls must not submit the answer form");
  return match[1];
}

function sliders(markup) {
  return [...markup.matchAll(/<div([^>]*role="slider"[^>]*)>/g)].map((entry) => ({
    label: /aria-label="([^"]*)"/.exec(entry[1])[1],
    disabled: /aria-disabled="true"/.test(entry[1]),
  }));
}

test("initial graph exposes range previews without recording any default answer", () => {
  const draft = spectrum.emptySpectrumDraft();
  const before = structuredClone(draft);
  let changes = 0;
  const markup = render(draft, { onChange: () => { changes += 1; } });
  const labels = sliders(markup).map((slider) => slider.label);
  assert.ok(labels.includes("Lowest acceptable value"));
  assert.ok(labels.includes("Highest acceptable value"));
  findButton(markup, "Use this range");
  findButton(markup, "Hide range");
  assert.match(markup, /Optional · not included yet/);
  assert.match(markup, /data-unanswered="true"/);
  assert.match(markup, /Move a bar or use this range to include it/);
  assert.match(markup, /aria-label="About acceptable outcomes"/);
  assert.equal(changes, 0);
  assert.deepEqual(draft, before);
});

test("uncertainty toggle remains present and waits for an explicit position", () => {
  const markup = render();
  assert.match(findButton(markup, "Answer uncertainty"), /disabled=""/);
  assert.equal(sliders(markup).find((slider) => slider.label.startsWith("Uncertainty width")).disabled, true);
  assert.match(markup, /Choose a position first/);
  assert.match(markup, /aria-label="About reported uncertainty"/);

  const positioned = render({ ...spectrum.emptySpectrumDraft(), position: 20 });
  assert.doesNotMatch(findButton(positioned, "Answer uncertainty"), /disabled=""/);
  assert.equal(sliders(positioned).find((slider) => slider.label.startsWith("Uncertainty width")).disabled, false);
});

test("included uncertainty and acceptance expose their unanswered actions", () => {
  const markup = render({
    position: 20, reported_uncertainty: { sd_fraction: 0.137 },
    acceptable_range: { lower: 19, upper: 22 },
  });
  findButton(markup, "Leave uncertainty unanswered");
  findButton(markup, "Leave range unanswered");
  findButton(markup, "Hide range");
  assert.doesNotMatch(markup, />Answer uncertainty<|>Use this range</);
  assert.match(markup, />8:00 pm<\/option>/);
  assert.match(markup, /id="[^"]*-uncertainty-value"[^>]*>13\.7% of scale<\/p>/);
  assert.match(markup, /id="[^"]*-range-value"[^>]*>7:00 pm – 10:00 pm<\/p>/);
  assert.doesNotMatch(markup, /data-unanswered="true"/);
  assert.match(findButton(markup, "Leave uncertainty unanswered"), /clearAnswer/);
  assert.match(findButton(markup, "Leave range unanswered"), /clearAnswer/);
});

test("live optional readouts distinguish a selected width from unanswered defaults", () => {
  const initial = render();
  assert.match(initial, /id="[^"]*-uncertainty-value"[^>]*>Not answered<\/p>/);
  assert.match(initial, /id="[^"]*-range-value"[^>]*>Not answered<\/p>/);
  const selected = render({
    position: 20, reported_uncertainty: { sd_fraction: 0.08 },
    acceptable_range: { lower: 20, upper: 20 },
  });
  assert.match(selected, /id="[^"]*-uncertainty-value"[^>]*>8% of scale<\/p>/);
  assert.match(selected, /id="[^"]*-range-value"[^>]*>8:00 pm – 8:00 pm<\/p>/);
  assert.match(selected, /Included when you record this position/);
});

test("graph keyboard order follows position, uncertainty, then acceptable bounds", () => {
  assert.deepEqual(sliders(render()).map((slider) => slider.label), [
    "Your position", "Uncertainty width, pull up to narrow",
    "Lowest acceptable value", "Highest acceptable value",
  ]);
});

test("disabled answer controls retain their labels while preventing edits", () => {
  const markup = render({
    position: 20, reported_uncertainty: { sd_fraction: 0.137 },
    acceptable_range: { lower: 19, upper: 22 },
  }, { disabled: true });
  for (const label of ["Leave uncertainty unanswered", "Leave range unanswered", "Hide range"]) {
    assert.match(findButton(markup, label), /disabled=""/);
  }
  assert.ok(sliders(markup).every((slider) => slider.disabled));
});
