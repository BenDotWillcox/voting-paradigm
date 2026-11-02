import "server-only";

import { createHash } from "node:crypto";
import { open, readFile, realpath, stat, type FileHandle } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";

import type { BlockPlanManifest } from "@/types/block-districting";

interface AssetEntry {
  path: string;
  rawSha256: string;
  gzipSha256: string;
  rawBytes: number;
  gzipBytes: number;
  contentType: string;
  proof: string | null;
}

interface PlanProof {
  reportPath: string;
  reportSha256: string;
  manifestPath: string;
  manifestSha256: string;
}

interface ServerIndex {
  schemaVersion: 1;
  catalogPath: string;
  catalogSha256: string;
  manifestPath: string;
  manifestSha256: string;
  proofs: Record<string, PlanProof>;
  assets: Record<string, AssetEntry>;
}

interface Bundle {
  index: ServerIndex;
  manifest: BlockPlanManifest;
}

const INDEX_PATH = "data/districting-block-plans/server-index.json";
const PUBLISHED_MANIFEST_PATH = "data/districting-block-plans/manifest.json";
const PUBLISHED_CATALOG_PATH = "prompts/state-block-final-catalog.json";
const SHA256 = /^[a-f0-9]{64}$/;
const ASSET_NAME = /^[a-zA-Z0-9._-]+\.(geojson|json)$/;
const bundles = new Map<string, { signature: string; promise: Promise<Bundle> }>();
const publishedManifests = new Map<string, Promise<BlockPlanManifest>>();

function hash(data: Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

/** Every path comes from the generated allowlist, never from request segments. */
async function repositoryPath(root: string, path: string): Promise<string> {
  if (isAbsolute(path) || /[:\\%\0]/.test(path) || path.split("/").some((part) => !part || part === "." || part === "..")) {
    throw new Error("Invalid block-plan resource path");
  }
  const rootPath = await realpath(root);
  const result = await realpath(resolve(rootPath, path));
  const local = relative(rootPath, result);
  if (!local || local === ".." || local.startsWith(`..${sep}`) || isAbsolute(local)) {
    throw new Error("Block-plan resource escapes repository");
  }
  return result;
}

/** Only historical cache resources may use the configured read-only cache mount. */
async function resourcePath(root: string, path: string, cacheRoot: string): Promise<string> {
  return path.startsWith(".cache/")
    ? repositoryPath(cacheRoot, path.slice(".cache/".length))
    : repositoryPath(root, path);
}

async function pinnedFile(root: string, path: string, expected: string, cacheRoot = resolve(root, ".cache")): Promise<Buffer> {
  if (!SHA256.test(expected)) throw new Error("Invalid block-plan resource identity");
  const bytes = await readFile(await resourcePath(root, path, cacheRoot));
  if (hash(bytes) !== expected) throw new Error("Block-plan evidence changed; rebuild the validated bundle");
  return bytes;
}

async function readBundle(root: string): Promise<Bundle> {
  const index = JSON.parse(await readFile(await repositoryPath(root, INDEX_PATH), "utf8")) as ServerIndex;
  if (index.schemaVersion !== 1 || !index.assets || !index.proofs || index.manifestPath !== "data/districting-block-plans/manifest.json") {
    throw new Error("Unsupported block-plan bundle");
  }
  const [manifestBytes] = await Promise.all([
    pinnedFile(root, index.manifestPath, index.manifestSha256),
    pinnedFile(root, index.catalogPath, index.catalogSha256),
  ]);
  const manifest = JSON.parse(manifestBytes.toString("utf8")) as BlockPlanManifest;
  if (manifest.schemaVersion !== 1 || manifest.catalogSha256 !== index.catalogSha256) {
    throw new Error("Block-plan manifest/catalog identity mismatch");
  }
  return { index, manifest };
}

async function getBundle(root: string): Promise<Bundle> {
  const key = resolve(root);
  const info = await stat(resolve(key, INDEX_PATH));
  const signature = `${info.size}:${info.mtimeMs}:${info.ctimeMs}`;
  const cached = bundles.get(key);
  if (cached?.signature === signature) return cached.promise;
  const promise = readBundle(key);
  bundles.set(key, { signature, promise });
  try {
    return await promise;
  } catch (error) {
    bundles.delete(key);
    throw error;
  }
}

/**
 * Deployments publish assets to object storage and ship no server index. The
 * tracked manifest must still name the exact final catalog it was built from.
 */
async function readPublishedManifest(root: string): Promise<BlockPlanManifest> {
  const [manifestBytes, catalogBytes] = await Promise.all([
    readFile(await repositoryPath(root, PUBLISHED_MANIFEST_PATH)),
    readFile(await repositoryPath(root, PUBLISHED_CATALOG_PATH)),
  ]);
  const manifest = JSON.parse(manifestBytes.toString("utf8")) as BlockPlanManifest;
  if (manifest.schemaVersion !== 1 || manifest.catalogSha256 !== hash(catalogBytes)) {
    throw new Error("Block-plan manifest/catalog identity mismatch");
  }
  return manifest;
}

/** Server components receive only the small browser manifest, never filesystem paths. */
export async function loadBlockPlanManifest(root = process.cwd()): Promise<BlockPlanManifest | null> {
  try {
    return (await getBundle(root)).manifest;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  const key = resolve(root);
  let published = publishedManifests.get(key);
  if (!published) {
    published = readPublishedManifest(key);
    publishedManifests.set(key, published);
  }
  try {
    return await published;
  } catch (error) {
    publishedManifests.delete(key);
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

function encodingQuality(header: string | null, coding: "gzip" | "identity"): number {
  if (!header) return coding === "identity" ? 1 : 0;
  const values = new Map<string, number>();
  for (const item of header.toLowerCase().split(",")) {
    const [name, ...parameters] = item.trim().split(";");
    const quality = parameters.map((x) => x.trim()).find((x) => x.startsWith("q="));
    const parsed = quality === undefined ? 1 : Number(quality.slice(2));
    values.set(name.trim(), Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : 0);
  }
  if (values.has(coding)) return values.get(coding)!;
  if (coding === "identity") return values.get("*") === 0 ? 0 : 1;
  return values.get("*") ?? 0;
}

function notModified(request: Request, etag: string): boolean {
  const candidates = request.headers.get("if-none-match")?.split(",").map((x) => x.trim().replace(/^W\//, ""));
  return !!candidates?.some((x) => x === "*" || x === etag);
}

/** Own the descriptor explicitly through EOF, abort, error and consumer cancel. */
function fileBody(
  file: FileHandle,
  compressedBytes: number,
  signal: AbortSignal,
  closeFile: () => Promise<void>,
): ReadableStream<Uint8Array> {
  let position = 0;
  let stopped = false;
  let cancelled = false;
  let aborted = false;
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const detach = () => signal.removeEventListener("abort", abort);
  const abort = () => {
    if (stopped) return;
    stopped = true;
    aborted = true;
    detach();
    controller.error(signal.reason ?? new DOMException("Request aborted", "AbortError"));
    // close() waits for any in-flight positioned read, retaining the handle until closed.
    void closeFile().catch(() => undefined);
  };
  return new ReadableStream<Uint8Array>({
    start(nextController) {
      controller = nextController;
      signal.addEventListener("abort", abort, { once: true });
      // An abort that happened before listener registration must not orphan the handle.
      if (signal.aborted) abort();
    },
    async pull(nextController) {
      if (stopped) return;
      try {
        const buffer = Buffer.allocUnsafe(64 * 1024);
        const { bytesRead } = await file.read(buffer, 0, Math.min(buffer.length, compressedBytes - position), position);
        if (stopped) return;
        if (!bytesRead && position < compressedBytes) throw new Error("Compressed map ended during delivery");
        if (bytesRead) {
          position += bytesRead;
          nextController.enqueue(new Uint8Array(buffer.subarray(0, bytesRead)));
        }
        if (!bytesRead || position >= compressedBytes) {
          stopped = true;
          detach();
          await closeFile();
          if (!cancelled) nextController.close();
        }
      } catch (error) {
        if (cancelled || aborted) return;
        stopped = true;
        detach();
        await closeFile().catch(() => undefined);
        if (!cancelled) nextController.error(error);
      }
    },
    async cancel() {
      cancelled = true;
      stopped = true;
      detach();
      await closeFile();
    },
  });
}

/** Optional root is dependency injection for tests/local relocation, never a URL parameter. */
export async function serveBlockPlanAsset(
  request: Request,
  asset: string[],
  options: { root?: string; cacheRoot?: string } = {},
): Promise<Response> {
  if (asset.length !== 2 || !SHA256.test(asset[0]) || !ASSET_NAME.test(asset[1])) {
    return new Response("Unknown district-plan asset", { status: 404 });
  }
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method not allowed", { status: 405, headers: { Allow: "GET, HEAD" } });
  }
  const root = options.root ?? process.cwd();
  // Explicit test roots are self-contained unless a cache root is also injected.
  // This server-only setting is never supplied by a request or exposed to the browser.
  const cacheRoot = options.cacheRoot ?? (options.root
    ? resolve(root, ".cache")
    : process.env.BLOCK_PLAN_CACHE_ROOT ?? resolve(root, ".cache"));
  try {
    request.signal.throwIfAborted();
    const { index } = await getBundle(root);
    const key = asset.join("/");
    if (!Object.hasOwn(index.assets, key)) return new Response("Unknown district-plan asset", { status: 404 });
    const entry = index.assets[key];
    if (entry.rawSha256 !== asset[0] || !SHA256.test(entry.gzipSha256) || !Number.isSafeInteger(entry.rawBytes) || entry.rawBytes < 1 || !Number.isSafeInteger(entry.gzipBytes) || entry.gzipBytes < 1) {
      throw new Error("Invalid asset allowlist entry");
    }
    if (!entry.path.startsWith(".cache/") && !entry.path.startsWith("data/districting-block-plans/assets/")) {
      throw new Error("Asset is outside approved data directories");
    }
    if (!["application/json; charset=utf-8", "application/geo+json; charset=utf-8"].includes(entry.contentType)) {
      throw new Error("Unexpected asset media type");
    }
    if (entry.proof !== null) {
      if (!Object.hasOwn(index.proofs, entry.proof)) throw new Error("Asset lacks an accepted plan identity");
      const proof = index.proofs[entry.proof];
      await Promise.all([
        pinnedFile(root, proof.reportPath, proof.reportSha256, cacheRoot),
        pinnedFile(root, proof.manifestPath, proof.manifestSha256, cacheRoot),
      ]);
    }
    const gzipQuality = encodingQuality(request.headers.get("accept-encoding"), "gzip");
    const identityQuality = encodingQuality(request.headers.get("accept-encoding"), "identity");
    if (gzipQuality <= 0 && identityQuality <= 0) {
      return new Response("No acceptable content encoding", { status: 406, headers: { Vary: "Accept-Encoding" } });
    }
    const gzip = gzipQuality > 0 && gzipQuality >= identityQuality;
    const etag = `"${gzip ? entry.gzipSha256 : entry.rawSha256}-${gzip ? "gzip" : "identity"}"`;
    const headers = new Headers({
      "Content-Type": entry.contentType,
      "Content-Length": String(gzip ? entry.gzipBytes : entry.rawBytes),
      "Cache-Control": "public, max-age=31536000, immutable",
      "X-Content-Type-Options": "nosniff",
      Vary: "Accept-Encoding",
      ETag: etag,
    });
    if (gzip) headers.set("Content-Encoding", "gzip");
    request.signal.throwIfAborted();
    const file = await open(await resourcePath(root, entry.path, cacheRoot), "r");
    let closing: Promise<void> | undefined;
    const closeFile = () => (closing ??= file.close());
    try {
      request.signal.throwIfAborted();
      const info = await file.stat();
      if (info.size !== entry.gzipBytes) throw new Error("Compressed map size changed");
      // Verify before returning headers; use the same open descriptor for streaming.
      const digest = createHash("sha256");
      const buffer = Buffer.allocUnsafe(64 * 1024);
      let position = 0;
      while (position < entry.gzipBytes) {
        request.signal.throwIfAborted();
        const { bytesRead } = await file.read(buffer, 0, Math.min(buffer.length, entry.gzipBytes - position), position);
        if (!bytesRead) throw new Error("Compressed map ended during verification");
        digest.update(buffer.subarray(0, bytesRead));
        position += bytesRead;
      }
      request.signal.throwIfAborted();
      if (digest.digest("hex") !== entry.gzipSha256) throw new Error("Compressed map hash changed");
      if (notModified(request, etag)) {
        await closeFile();
        headers.delete("Content-Length");
        return new Response(null, { status: 304, headers });
      }
      if (request.method === "HEAD") {
        await closeFile();
        return new Response(null, { headers });
      }
      const source = fileBody(file, entry.gzipBytes, request.signal, closeFile);
      // Web Streams propagate downstream cancellation through decompression to fileBody.cancel.
      const body = gzip ? source : source.pipeThrough(new DecompressionStream("gzip"));
      return new Response(body, { headers });
    } catch (error) {
      await closeFile().catch(() => undefined);
      throw error;
    }
  } catch {
    // Fail closed on missing cache files, changed evidence, or stale generated indexes.
    return new Response("Validated district-plan data unavailable", { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
