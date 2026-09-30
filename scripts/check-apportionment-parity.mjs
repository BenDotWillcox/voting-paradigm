#!/usr/bin/env node
/**
 * Check that the TypeScript apportionment sequence (lib/apportionment-sequence.ts,
 * used by /apportionment/explore) produces the same seat counts as the Python
 * package that generates the essay's artifacts, at every rule-defined House
 * size in public/data/apportionment-story/anchors.json, and that the rule-
 * defined House sizes in lib/districting-cap-scale.ts equal the Python ones.
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
  process.exitCode = failures > 0 ? 1 : 0;
} finally {
  await rm(dir, { recursive: true, force: true });
}
