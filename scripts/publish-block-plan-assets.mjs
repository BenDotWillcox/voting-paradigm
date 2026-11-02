// Upload the verified block-plan assets to an S3-compatible bucket (Cloudflare
// R2) so deployments can serve them without the 15 GB local cache.
//
// Each object key is the route's own `<rawSha256>/<name>` path, so setting
// BLOCK_PLAN_ASSET_ORIGIN makes next.config.ts rewrite /api/district-plans/*
// straight to the bucket. Objects keep the gzip bytes the local route streams,
// with Content-Encoding: gzip, and are immutable because their keys are content
// hashes. Every file is checked against server-index.json, and every accepted
// plan's proof files against their pins, before anything is sent.
//
//   node scripts/publish-block-plan-assets.mjs --dry-run   # verify and count only
//   node scripts/publish-block-plan-assets.mjs             # upload what is missing
//
// Reads .env.local: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
// R2_BUCKET, and optionally BLOCK_PLAN_CACHE_ROOT (default ./.cache).
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import { AwsClient } from "aws4fetch";
import dotenv from "dotenv";

dotenv.config({ path: ".env.local" });

const INDEX_PATH = "data/districting-block-plans/server-index.json";
const SHA256 = /^[a-f0-9]{64}$/;
const ASSET_KEY = /^[a-f0-9]{64}\/[a-zA-Z0-9._-]+\.(geojson|json)$/;
const MEDIA_TYPES = new Set(["application/json; charset=utf-8", "application/geo+json; charset=utf-8"]);

const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
const concurrency = Number(process.env.BLOCK_PLAN_UPLOAD_CONCURRENCY ?? 32);
const root = process.cwd();
const cacheRoot = resolve(process.env.BLOCK_PLAN_CACHE_ROOT || ".cache");

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

/** Index paths are generated, but still never leave their approved root. */
function localPath(path) {
  if (path.split("/").some((part) => !part || part === "." || part === "..")) throw new Error(`Invalid index path ${path}`);
  const [base, rest] = path.startsWith(".cache/") ? [cacheRoot, path.slice(".cache/".length)] : [root, path];
  const result = resolve(base, rest);
  if (!result.startsWith(base + sep)) throw new Error(`Index path escapes its root: ${path}`);
  return result;
}

async function pinned(path, expected) {
  const bytes = await readFile(localPath(path));
  if (sha256(bytes) !== expected) throw new Error(`${path} no longer matches its pinned SHA-256`);
  return bytes;
}

async function pool(items, worker) {
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (next < items.length) await worker(items[next++]);
  }));
}

async function retry(label, attempt) {
  for (let tries = 1; ; tries++) {
    try {
      return await attempt();
    } catch (error) {
      if (tries >= 5) throw new Error(`${label}: ${error.message}`);
      await new Promise((done) => setTimeout(done, 500 * 2 ** tries));
    }
  }
}

function bucketClient() {
  const missing = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"].filter((name) => !process.env[name]);
  if (missing.length) throw new Error(`Set ${missing.join(", ")} in .env.local`);
  const client = new AwsClient({
    accessKeyId: process.env.R2_ACCESS_KEY_ID,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY,
    service: "s3",
    region: "auto",
  });
  const endpoint = `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${process.env.R2_BUCKET}`;
  return { client, endpoint };
}

/** Existing key → size, so reruns resume and a truncated object is replaced. */
async function listBucket({ client, endpoint }) {
  const sizes = new Map();
  let token = null;
  do {
    const query = new URLSearchParams({ "list-type": "2", "max-keys": "1000" });
    if (token) query.set("continuation-token", token);
    const body = await retry("list", async () => {
      const response = await client.fetch(`${endpoint}?${query}`);
      if (!response.ok) throw new Error(`HTTP ${response.status} ${await response.text()}`);
      return response.text();
    });
    for (const [, item] of body.matchAll(/<Contents>([\s\S]*?)<\/Contents>/g)) {
      const key = item.match(/<Key>([^<]*)<\/Key>/)?.[1];
      const size = item.match(/<Size>(\d+)<\/Size>/)?.[1];
      if (key && size) sizes.set(key, Number(size));
    }
    token = /<IsTruncated>true<\/IsTruncated>/.test(body)
      ? body.match(/<NextContinuationToken>([^<]*)<\/NextContinuationToken>/)?.[1]?.replaceAll("&amp;", "&") ?? null
      : null;
  } while (token);
  return sizes;
}

const started = Date.now();
const index = JSON.parse(await readFile(resolve(root, INDEX_PATH), "utf8"));
if (index.schemaVersion !== 1 || !index.assets || !index.proofs) throw new Error("Unsupported block-plan index");
await pinned(index.manifestPath, index.manifestSha256);
await pinned(index.catalogPath, index.catalogSha256);
const proofs = Object.entries(index.proofs);
await pool(proofs, async ([, proof]) => {
  await pinned(proof.reportPath, proof.reportSha256);
  await pinned(proof.manifestPath, proof.manifestSha256);
});
console.log(`Verified manifest, catalog and ${proofs.length} plan proofs.`);

const entries = Object.entries(index.assets);
for (const [key, entry] of entries) {
  if (!ASSET_KEY.test(key) || key.split("/")[0] !== entry.rawSha256 || !SHA256.test(entry.gzipSha256) || !MEDIA_TYPES.has(entry.contentType)) {
    throw new Error(`Invalid index entry ${key}`);
  }
  if (entry.proof !== null && !Object.hasOwn(index.proofs, entry.proof)) throw new Error(`${key} lacks an accepted plan identity`);
}

const bucket = dryRun ? null : bucketClient();
const existing = bucket ? await listBucket(bucket) : new Map();
const pending = entries.filter(([key, entry]) => existing.get(key) !== entry.gzipBytes);
const pendingBytes = pending.reduce((total, [, entry]) => total + entry.gzipBytes, 0);
console.log(`${entries.length} assets; ${entries.length - pending.length} already published; ${pending.length} to ${dryRun ? "verify" : "upload"} (${(pendingBytes / 2 ** 30).toFixed(2)} GiB).`);

let done = 0;
let sentBytes = 0;
await pool(pending, async ([key, entry]) => {
  const bytes = await readFile(localPath(entry.path));
  if (bytes.length !== entry.gzipBytes || sha256(bytes) !== entry.gzipSha256) throw new Error(`${entry.path} no longer matches the index`);
  if (bucket) {
    await retry(key, async () => {
      const response = await bucket.client.fetch(`${bucket.endpoint}/${key}`, {
        method: "PUT",
        body: bytes,
        headers: {
          "Content-Type": entry.contentType,
          "Content-Encoding": "gzip",
          "Cache-Control": "public, max-age=31536000, immutable",
        },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status} ${await response.text()}`);
    });
  }
  done += 1;
  sentBytes += bytes.length;
  if (done % 5000 === 0 || done === pending.length) {
    const minutes = (Date.now() - started) / 60000;
    console.log(`${done}/${pending.length} (${(sentBytes / 2 ** 30).toFixed(2)} GiB) after ${minutes.toFixed(1)} min`);
  }
});
console.log(dryRun ? "Dry run complete; nothing was uploaded." : "All block-plan assets are published.");
