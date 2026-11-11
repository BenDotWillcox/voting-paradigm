import type { NextConfig } from "next";
import nextPackage from "next/package.json";

interface AutomaticTracePlugin {
  constructor: { name: string };
  compilerType?: unknown;
  traceIgnores?: unknown;
}

const blockPlanAutomaticTraceIgnores = [
  "**/data/districting-block-plans/**",
  "**/.cache",
  "**/.cache/**",
];

// Deployments serve the content-addressed block-plan assets from object
// storage (uploaded by scripts/publish-block-plan-assets.mjs). Leave this unset
// locally and /api/district-plans streams the verified files from disk.
const blockPlanAssetOrigin = process.env.BLOCK_PLAN_ASSET_ORIGIN?.replace(/\/+$/, "");
if (blockPlanAssetOrigin !== undefined && !/^https:\/\/[^/?#]+$/.test(blockPlanAssetOrigin)) {
  throw new Error("BLOCK_PLAN_ASSET_ORIGIN must be an https origin such as https://pub-example.r2.dev");
}

const nextConfig: NextConfig = {
  webpack(config, { dev, isServer, nextRuntime }) {
    if (dev || !isServer || nextRuntime !== "nodejs") return config;
    // Next 15.2.8's early NFT plugin otherwise expands the loader's unknown
    // test/runtime root into **/*/.cache and **/*/data/.../server-index.json.
    // These search the whole repository before route includes/excludes run.
    // Guard this private, version-pinned plugin contract instead of changing
    // installed Next code or dropping explicitly packaged runtime assets.
    const tracers = (config.plugins ?? []).filter(
      (plugin: AutomaticTracePlugin | null | undefined) =>
        plugin?.constructor?.name === "TraceEntryPointsPlugin",
    ) as AutomaticTracePlugin[];
    if (nextPackage.version !== "15.2.8" || tracers.length !== 1 || tracers[0].compilerType !== "server") {
      throw new Error("Next automatic tracing contract changed; verify block-plan asset packaging before building");
    }
    const tracer = tracers[0];
    const ignores = tracer.traceIgnores;
    if (!Array.isArray(ignores) || !ignores.every((value) => typeof value === "string")) {
      throw new Error("Next traceIgnores contract changed; verify block-plan asset packaging before building");
    }
    tracer.traceIgnores = [...new Set([...ignores, ...blockPlanAutomaticTraceIgnores])];
    return config;
  },
  outputFileTracingExcludes: {
    // Installed Next uses this special key for shared ignores in its second
    // NFT pass. It matches neither API nor page routes, so their explicit
    // includes below remain intact. Cache resources retain their read-only
    // BLOCK_PLAN_CACHE_ROOT mount contract; they are not a standalone bundle.
    "next-server": blockPlanAutomaticTraceIgnores,
    // Server code reads only small plan.json / state outline files; the
    // pipeline sources and browser-fetched geometry layers stay out of
    // serverless bundles.
    "/*": [
      "./data/districting/**/*",
      "./.cache/**/*",
      "./public/data/districting/**/*",
      "./public/data/district-plans/**/*.topo.json",
      "./public/data/us-states.json",
    ],
  },
  outputFileTracingIncludes: {
    // The methods inspector reads excerpts from the actual Python package.
    "/methods": ["./voting/methods/*.py"],
    // Resumable build fragments and publication-history backups are audit data,
    // not runtime dependencies. Only publishable metadata/assets enter tracing.
    "/districts": ["./data/districting-block-plans/manifest.json", "./data/districting-block-plans/server-index.json", "./prompts/state-block-final-catalog.json"],
    "/api/district-plans/*": [
      "./data/districting-block-plans/manifest.json",
      "./data/districting-block-plans/server-index.json",
      // Next 15.2 spreads each glob's results into a function call. Partition
      // the content-hashed filenames so one 500k-file glob cannot exceed V8's
      // argument limit; every generated gzip asset remains included.
      ..."0123456789abcdef".split("").map((prefix) => `./data/districting-block-plans/assets/${prefix}*.gz`),
      "./prompts/state-block-final-catalog.json",
    ],
  },
  async rewrites() {
    const beforeFiles = [];
    if (process.env.VERCEL === "1") {
      // Vercel's file-based Python function receives the original request path.
      // Shadow only these Next proxies so the demo uses this deployment's
      // Python code, independently of the shared external API environment.
      beforeFiles.push(
        { source: "/api/expressive/scalar/compare", destination: "/api/main" },
        { source: "/api/expressive/scalar/preview", destination: "/api/main" },
      );
    }
    if (blockPlanAssetOrigin) {
      // Shadow the local route so manifest and nested-index asset URLs resolve
      // to the bucket without changing their public paths.
      beforeFiles.push({
        source: "/api/district-plans/:sha([a-f0-9]{64})/:name",
        destination: `${blockPlanAssetOrigin}/:sha/:name`,
      });
    }
    return { beforeFiles, afterFiles: [], fallback: [] };
  },
  async redirects() {
    // /districts used to hold both explorers behind ?tab=; apportionment is
    // now its own demo. The district explorer moved from /districts/explore
    // back to /districts and owns ?cap at its four block anchors. Keep old
    // shared links working (first match wins; query strings pass through, so
    // the /districts rules must not match the explorer's own URLs).
    return [
      {
        source: "/districts/:stateFips(\\d{2})",
        destination: "/apportionment/explore/:stateFips",
        permanent: false,
      },
      {
        source: "/districts/explore",
        destination: "/districts",
        permanent: false,
      },
      {
        source: "/districts",
        has: [{ type: "query", key: "tab", value: "(?!districting$).*" }],
        destination: "/apportionment/explore",
        permanent: false,
      },
      {
        source: "/districts",
        has: [{ type: "query", key: "cap", value: "(?!(?:435|574|692|1000)$).*" }],
        destination: "/apportionment/explore",
        permanent: false,
      },
      // The methods lab became the instrument on /methods
      {
        source: "/methods/lab",
        destination: "/methods",
        permanent: false,
      },
    ];
  },
  async headers() {
    return [
      {
        // Rebuilt only by `npm run build:map-display`; paths are not
        // content-hashed, so cache briefly and revalidate in the background.
        source: "/data/district-plans/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=3600, stale-while-revalidate=86400",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
