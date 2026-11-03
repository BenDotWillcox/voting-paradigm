// Run the complete display-data adapter with the same cache mount as Next.js.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import dotenv from "dotenv";

dotenv.config({ path: ".env.local" });
const localPython = process.platform === "win32" ? "venv/Scripts/python.exe" : "venv/bin/python";
const python = process.env.BLOCK_PLAN_PYTHON || (existsSync(localPython) ? localPython : "python");
const cacheRoot = resolve(process.env.BLOCK_PLAN_CACHE_ROOT || ".cache");
const sourceRoot = resolve(process.env.BLOCK_COMPARISON_SOURCES_ROOT || resolve(cacheRoot, "block-comparison-sources-v1"));
// Pin/download display references before replacing the existing app indexes.
// None of these commands invokes a district solver or edits historical runs.
for (const args of [
  ["scripts/fetch_block_comparison_sources.py", "--output-dir", sourceRoot],
  ["scripts/build_block_plan_bundle.py", "--cache-root", cacheRoot, "--with-state-outlines"],
  ["scripts/build_block_comparison_layers.py", "--cache-root", cacheRoot, "--source-dir", sourceRoot],
  ["scripts/build_michigan_land_display.py", "--source-root", resolve("."), "--cache-root", cacheRoot],
  ["scripts/build_michigan_explorer.py", "--cache-root", cacheRoot],
  ["scripts/build_michigan_spatial_blocks.py", "--cache-root", cacheRoot],
  ["scripts/build_state_explorer_cities.py", "--cache-root", cacheRoot],
  ["scripts/build_state_explorer_geometry.py", "--cache-root", cacheRoot],
  ["scripts/build_state_explorer_blocks.py", "--cache-root", cacheRoot, "--workers", "1"],
  ["scripts/publish_state_explorer.py", "--cache-root", cacheRoot, "--publish"],
]) {
  const result = spawnSync(python, ["-X", "utf8", ...args], { stdio: "inherit", env: process.env });
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) process.exit(result.status ?? 1);
}
