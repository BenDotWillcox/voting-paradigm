#!/usr/bin/env node
/**
 * Check that the TypeScript apportionment sequence (lib/apportionment-sequence.ts,
 * used by /apportionment/explore) produces the same seat counts as the Python
 * package that generates the essay's artifacts, at every rule-defined House
 * size in public/data/apportionment-story/anchors.json, that the rule-
 * defined House sizes in lib/districting-cap-scale.ts equal the Python ones,
 * and that the essay's sweep (lib/apportionment-sweep.ts) reproduces
 * house-sizes.json: the award order and, at every House size, the extremes,
 * their ratio and the median deviation.
 *
 * The project has no TS test runner, so this transpiles these source
 * files with the installed TypeScript compiler into a temp directory and
 * imports them. Exits non-zero on any mismatch. Run by apportionment's pytest
 * suite when Node is available.
 */

import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import ts from "typescript";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const MODULES = [
  "apportionment-sequence",
  "apportionment-sweep",
  "districting-cap-scale",
  "us-state-populations",
  "us-states",
];

const dir = await mkdtemp(join(tmpdir(), "apportionment-parity-"));
try {
  for (const name of MODULES) {
    const source = await readFile(join(ROOT, "lib", `${name}.ts`), "utf8");
    const { outputText } = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    });
    await writeFile(
      join(dir, `${name}.mjs`),
      outputText.replace(/from "@\/lib\/([\w-]+)"/g, 'from "./$1.mjs"')
    );
  }
  const { getSeatCountsAfter } = await import(
    pathToFileURL(join(dir, "apportionment-sequence.mjs")).href
  );
  const capScale = await import(pathToFileURL(join(dir, "districting-cap-scale.mjs")).href);
  const anchors = JSON.parse(
    await readFile(join(ROOT, "public/data/apportionment-story/anchors.json"), "utf8")
  );

  let failures = 0;
  for (const rule of anchors.rules) {
    const tsSeats = getSeatCountsAfter(rule.seats);
    const mismatched = Object.keys(rule.state_seats).filter(
      (fips) => tsSeats[fips] !== rule.state_seats[fips]
    );
    if (mismatched.length > 0) {
      failures += 1;
      console.error(`${rule.key} (${rule.seats}): mismatched states ${mismatched.join(", ")}`);
    } else {
      console.log(`${rule.key} (${rule.seats}): TypeScript and Python agree`);
    }
  }
  const tsAnchors = capScale.CAP_ANCHORS.map((anchor) => anchor.cap);
  const pyAnchors = anchors.rules.map((rule) => rule.seats);
  if (JSON.stringify(tsAnchors) !== JSON.stringify(pyAnchors)) {
    failures += 1;
    console.error(`anchor sizes differ: TypeScript ${tsAnchors} vs Python ${pyAnchors}`);
  } else {
    console.log(`anchor sizes agree: ${tsAnchors.join(", ")}`);
  }

  // The essay's sweep against house-sizes.json.
  const sweepModule = await import(pathToFileURL(join(dir, "apportionment-sweep.mjs")).href);
  const { US_2020_APPORTIONMENT_POPULATIONS: populations } = await import(
    pathToFileURL(join(dir, "us-state-populations.mjs")).href
  );
  const sizes = JSON.parse(
    await readFile(join(ROOT, "public/data/apportionment-story/house-sizes.json"), "utf8")
  );
  const fipsAt = sizes.states.map((state) => state.fips);
  const samePopulations = sizes.states.every((state) => populations[state.fips] === state.population);
  const order = sweepModule.awardOrder(populations, sizes.stop);
  const pyOrder = sizes.award_order.map((index) => fipsAt[index]);
  const sameOrder = order.length === pyOrder.length && order.every((fips, i) => fips === pyOrder[i]);
  const sweep = sweepModule.sizeSweep(populations, order, sizes.start, sizes.stop);
  const round = (value, digits) => Number(value.toFixed(digits));
  const badSizes = sweep.filter(
    (row, i) =>
      round(row.ratio, 5) !== sizes.ratio[i] ||
      round(row.typical, 6) !== sizes.median_abs_deviation[i] ||
      row.largest.fips !== fipsAt[sizes.largest[i]] ||
      row.smallest.fips !== fipsAt[sizes.smallest[i]]
  );
  if (!samePopulations || !sameOrder || badSizes.length > 0 || sweep.length !== sizes.ratio.length) {
    failures += 1;
    console.error(
      `sweep: populations ${samePopulations ? "agree" : "differ"}, award order ${sameOrder ? "agrees" : "differs"}, ` +
        `${badSizes.length} House sizes differ${badSizes.length ? ` (first ${badSizes[0].size})` : ""}`
    );
  } else {
    console.log(`sweep (${sizes.start}-${sizes.stop}): TypeScript and Python agree at every House size`);
  }
  process.exitCode = failures > 0 ? 1 : 0;
} finally {
  await rm(dir, { recursive: true, force: true });
}
