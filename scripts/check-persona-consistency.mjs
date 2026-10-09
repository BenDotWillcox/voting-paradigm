#!/usr/bin/env node
/**
 * Check that the essay's fictional people (lib/apportionment/persona.ts)
 * never contradict themselves. Samples many (seed, state) pairs and checks
 * every person's pieces against rules written here, independently of the
 * generator's own eligibility predicates:
 *
 * - pairs of statements that can never describe the same life;
 * - statements that only fit some kinds of role;
 * - every statement in the generator is reachable;
 * - the named pieces are short enough to label the intro's figure;
 * - the same (seed, state) always gives the same person.
 *
 * The project has no TS test runner, so this transpiles the module with the
 * installed TypeScript compiler into a temp directory and imports it. Exits
 * non-zero on any failure. Run by apportionment's pytest suite when Node is
 * available.
 */

import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import ts from "typescript";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SAMPLES = 300_000;
/** Named pieces label the figure on one or two short lines. */
const MAX_LABEL = 42;

// --- Independent rules ------------------------------------------------------

const HOUSING = [
  "Renting an apartment",
  "Paying down a mortgage",
  "Owns their home outright",
  "Living with their parents",
  "Living in a college dorm",
];
const OWNER_ONLY = [
  "Worries about property taxes",
  "Belongs to a neighborhood association",
  "Builds furniture in the garage",
];
const HAS_KIDS = [
  "Raising a toddler",
  "Raising two young kids",
  "Raising two kids",
  "Raising three kids",
  "Raising a teenager",
  "Raising two teenagers",
  "Raising a child alone",
  "Raising two kids alone",
  "Raising three kids alone",
  "Wants affordable childcare",
  "Hopes their kids go to college",
  "Wants their kids to afford a home nearby",
  "Drives the kids to soccer practice",
  "On the PTA",
  "Kids grown and moved away",
  "Grandparent of five",
  "Knits for the grandkids",
];
const RELIGIOUS_OTHER_THAN_CHRISTIAN = [
  "Not religious",
  "Spiritual but not religious",
  "Raised Catholic, rarely goes now",
  "Active in their synagogue",
  "Active in their mosque",
  "Active in their temple",
  "Meditates with a Buddhist group",
];
const COMMUTES = ["Driving an hour to work", "Takes the bus to work", "Wants a shorter commute"];

/** [a, b]: a and b never describe the same person. */
const INCOMPATIBLE = [
  ...pairsWithin(HOUSING),
  ...cross(["Renting with two roommates"], HOUSING.filter((h) => h !== "Renting an apartment")),
  ...cross(["Hopes to buy a first home"], ["Paying down a mortgage", "Owns their home outright", ...OWNER_ONLY]),
  ...cross(["Worries about rising rent"], [...HOUSING.filter((h) => h !== "Renting an apartment"), ...OWNER_ONLY]),
  ...cross(["Grows tomatoes on the balcony"], [...HOUSING.filter((h) => h !== "Renting an apartment"), ...OWNER_ONLY]),
  ...cross(["Living in a college dorm"], [
    "Keeps a vegetable garden",
    "Walks the dog every morning",
    "Has a cat named Biscuit",
    "Restores old cars",
    "Cooks a big dinner every Sunday",
    ...OWNER_ONLY,
  ]),
  ...cross(["Expecting their first child", "Newly married"], HAS_KIDS),
  ...cross(["Renting with two roommates", "Living with their parents", "Living in a college dorm"], [
    ...HAS_KIDS,
    "Newly married",
    "Expecting their first child",
  ]),
  ...cross(["Wants affordable childcare"], [
    "Kids grown and moved away",
    "Grandparent of five",
    "Raising a teenager",
    "Raising two teenagers",
    "Knits for the grandkids",
  ]),
  ...cross(["Living paycheck to paycheck"], ["Saving for retirement", "Owns their home outright"]),
  ...cross(["Works from home"], COMMUTES),
  ["Driving an hour to work", "Takes the bus to work"],
  ...cross(["Working night shifts"], ["Taking night classes", "Bowls on Thursday nights"]),
  ...cross(["Running a small business"], [
    "Hopes to start a business",
    "Union member",
    "Worries about job security",
    "Working two jobs",
  ]),
  ["Moved here two years ago", "Has lived in the same town all their life"],
  ...cross(["Has lived in the same town all their life"], [
    "Has moved bases four times",
    "Served in the Army",
    "Member of the American Legion",
  ]),
  ...cross(["Sings in the church choir"], RELIGIOUS_OTHER_THAN_CHRISTIAN),
  ...cross(["Votes in every local election"], ["Hasn't voted in years", "Has never voted"]),
  ["Raising two grandchildren", "Kids grown and moved away"],
  ["Caring for a spouse with dementia", "Newly married"],
];

const STUDENT_ONLY = ["Living in a college dorm", "Taking out loans for school"];
const RETIRED_ONLY = [
  "Recently retired",
  "Living on a fixed income",
  "Worries about outliving their savings",
  "Worries about Social Security",
  "Knits for the grandkids",
  "Grandparent of five",
  "Raising two grandchildren",
  "Caring for a spouse with dementia",
  "Kids grown and moved away",
];
const EMPLOYED_ONLY = [
  "Working night shifts",
  "Working two jobs",
  "Union member",
  "Driving an hour to work",
  "Takes the bus to work",
  "Works from home",
  "Worries about job security",
  "Saving for retirement",
  "Hopes to retire someday",
  "Hopes to start a business",
  "Taking night classes",
  "Running a small business",
];
const NO_KIDS_ROLES = ["student", "athlete", "barista"];

/** Statements that only fit some roles: [text, (role) => allowed]. */
const ROLE_RULES = [
  ...STUDENT_ONLY.map((text) => [text, (role) => role.status === "student"]),
  ...RETIRED_ONLY.map((text) => [text, (role) => role.status === "retired"]),
  ...EMPLOYED_ONLY.map((text) => [text, (role) => role.status === "employed"]),
  ...HAS_KIDS.map((text) => [text, (role) => !NO_KIDS_ROLES.includes(role.id)]),
  ["Has moved bases four times", (role) => role.id === "military"],
  ["Volunteer firefighter", (role) => role.id !== "firefighter"],
  ["Served in the Army", (role) => role.id !== "military"],
  ["Driving an hour to work", (role) => role.id !== "trucker" && role.id !== "bus"],
  ["Expecting their first child", (role) => role.status === "employed"],
];

function pairsWithin(list) {
  return list.flatMap((a, i) => list.slice(i + 1).map((b) => [a, b]));
}

function cross(left, right) {
  return left.flatMap((a) => right.filter((b) => b !== a).map((b) => [a, b]));
}

// --- Run ----------------------------------------------------------------------

const dir = await mkdtemp(join(tmpdir(), "persona-consistency-"));
try {
  const source = await readFile(join(ROOT, "lib", "apportionment", "persona.ts"), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  await writeFile(join(dir, "persona.mjs"), outputText);
  const persona = await import(pathToFileURL(join(dir, "persona.mjs")).href);

  const allStatements = [
    ...persona.FAMILY,
    ...persona.CIRCUMSTANCE,
    ...persona.FAITH_TIES,
    ...persona.COMMUNITY_TIES,
    ...persona.CONCERN,
    ...persona.EVERYDAY,
  ].map((s) => s.text);
  const known = new Set(allStatements);
  const ruleTexts = [...INCOMPATIBLE.flat(), ...ROLE_RULES.map(([text]) => text)];
  const unknownRuleTexts = [...new Set(ruleTexts.filter((text) => !known.has(text)))];

  const failures = new Map();
  const fail = (key, example) => {
    if (!failures.has(key)) failures.set(key, { count: 0, example });
    failures.get(key).count += 1;
  };
  const seen = new Map(allStatements.map((text) => [text, 0]));
  const states = [["39", 15], ["56", 1], ["06", 52], ["50", 1], ["13", 14]];

  for (let i = 0; i < SAMPLES; i++) {
    const [fips, seats] = states[i % states.length];
    const p = persona.generatePersona(i * 2654435761 >>> 0, fips, seats);
    const texts = [...p.readable, ...p.more].map((piece) => piece.text);
    const example = `${p.role.noun}: ${texts.join(" | ")}`;
    for (const text of texts) {
      if (!known.has(text)) fail(`unknown statement "${text}"`, example);
      seen.set(text, (seen.get(text) ?? 0) + 1);
    }
    if (new Set(texts).size !== texts.length) fail("repeated statement", example);
    for (const [a, b] of INCOMPATIBLE) {
      if (texts.includes(a) && texts.includes(b)) fail(`"${a}" with "${b}"`, example);
    }
    for (const [text, allowed] of ROLE_RULES) {
      if (texts.includes(text) && !allowed(p.role)) fail(`"${text}" for a ${p.role.noun}`, example);
    }
    for (const piece of p.readable) {
      if (piece.text.length > MAX_LABEL) fail(`label too long: "${piece.text}"`, example);
    }
    if (p.district !== null && (p.district < 1 || p.district > seats)) fail("district out of range", example);
  }

  const again = persona.generatePersona(12345, "39", 15);
  const first = persona.generatePersona(12345, "39", 15);
  if (JSON.stringify({ ...again, role: again.role.id, facts: null }) !== JSON.stringify({ ...first, role: first.role.id, facts: null })) {
    fail("not deterministic", "seed 12345, Ohio");
  }

  const unreachable = [...seen].filter(([, count]) => count === 0).map(([text]) => text);
  console.log(`Sampled ${SAMPLES.toLocaleString()} people over ${allStatements.length} statements.`);
  const rare = [...seen].sort((a, b) => a[1] - b[1]).slice(0, 5);
  console.log(`Rarest: ${rare.map(([text, count]) => `${text} (${count})`).join("; ")}`);

  let problems = 0;
  for (const text of unknownRuleTexts) {
    problems += 1;
    console.error(`rule names a statement the generator does not have: "${text}"`);
  }
  for (const text of unreachable) {
    problems += 1;
    console.error(`never generated: "${text}"`);
  }
  for (const [key, { count, example }] of failures) {
    problems += 1;
    console.error(`${key}: ${count} time(s), e.g. ${example}`);
  }
  if (problems === 0) console.log("No contradictions found.");
  process.exitCode = problems > 0 ? 1 : 0;
} finally {
  await rm(dir, { recursive: true, force: true });
}
