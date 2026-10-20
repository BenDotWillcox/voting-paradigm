/**
 * Rule-defined House sizes from the 2020 apportionment populations, and the
 * range of sizes the demos cover: today's 435 seats to the largest House
 * Article I allows. The districting demo precomputes maps at 435; the
 * essay's named sizes (lib/apportionment/house-sizes.ts) are built from
 * these constants.
 */

import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";

// Rule-defined House sizes are computed from the 2020 apportionment
// populations, never typed in, and mirror apportionment/analysis.py (the
// parity script compares them). Every rule uses apportionment populations
// consistently; mixing in resident populations is how the commonly quoted
// "574" arises.
const POPULATIONS = Object.values(US_2020_APPORTIONMENT_POPULATIONS);
const TOTAL_POPULATION = POPULATIONS.reduce((sum, population) => sum + population, 0);
const SMALLEST_STATE = Math.min(...POPULATIONS);

/** Wyoming Rule: the House whose average district is closest to the smallest state. */
export const WYOMING_RULE_SEATS = Math.round(TOTAL_POPULATION / SMALLEST_STATE);
/** Taagepera's cube-root law. */
export const CUBE_ROOT_SEATS = Math.round(Math.cbrt(TOTAL_POPULATION));
/**
 * Article I §2: "The Number of Representatives shall not exceed one for every
 * thirty Thousand." The largest compliant House rounds down.
 */
export const ARTICLE_ONE_MAX_SEATS = Math.floor(TOTAL_POPULATION / 30_000);

/** Today's House size, kept by the 1929 act; the districting demo's maps are drawn for it. */
export const CAP_MIN = 435;
/** The largest House Article I §2 allows. */
export const CAP_MAX = ARTICLE_ONE_MAX_SEATS;
