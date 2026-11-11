import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { transpileConfig } from "next/dist/build/next-config-ts/transpile-config.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const expressivePaths = [
  "/api/expressive/scalar/compare",
  "/api/expressive/scalar/preview",
];

async function rewritesFor({ vercel, assetOrigin }) {
  const saved = {
    VERCEL: process.env.VERCEL,
    BLOCK_PLAN_ASSET_ORIGIN: process.env.BLOCK_PLAN_ASSET_ORIGIN,
  };
  try {
    for (const [key, value] of Object.entries({
      VERCEL: vercel,
      BLOCK_PLAN_ASSET_ORIGIN: assetOrigin,
    })) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    const { default: config } = await transpileConfig({
      cwd: root,
      nextConfigPath: `${root}next.config.ts`,
    });
    return await config.rewrites();
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test("Vercel routes the two scalar endpoints before their Next proxy handlers", async () => {
  const rewrites = await rewritesFor({ vercel: "1" });
  assert.deepEqual(rewrites.beforeFiles.map((rule) => rule.source).sort(), expressivePaths);
  for (const rule of rewrites.beforeFiles) assert.equal(rule.destination, "/api/main");
  assert.equal(rewrites.afterFiles.length + rewrites.fallback.length, 0);
});

test("local development keeps the Next-to-Python proxies", async () => {
  const rewrites = await rewritesFor({});
  assert.equal(rewrites.beforeFiles.length + rewrites.afterFiles.length + rewrites.fallback.length, 0);
});

test("R2 asset routing remains intact alongside both deployment modes", async () => {
  for (const vercel of [undefined, "1"]) {
    const rewrites = await rewritesFor({ vercel, assetOrigin: "https://assets.example.invalid/" });
    const assetRule = rewrites.beforeFiles.find((rule) => rule.source.startsWith("/api/district-plans/"));
    assert.deepEqual(assetRule, {
      source: "/api/district-plans/:sha([a-f0-9]{64})/:name",
      destination: "https://assets.example.invalid/:sha/:name",
    });
    assert.equal(rewrites.beforeFiles.length, vercel === "1" ? 3 : 1);
  }
});
