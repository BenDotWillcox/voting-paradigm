// The regression runner reads only the case IDs it sends on stdin. Keep the
// original packet and historical cutoff identical to the journal's own reader.
import { readFileSync } from "node:fs";
import { readRegressionCase } from "../lib/personal-journal-store.ts";

const ids = JSON.parse(readFileSync(0, "utf8"));
const cases = [];
for (const id of ids) cases.push(await readRegressionCase(id));
process.stdout.write(JSON.stringify(cases));
