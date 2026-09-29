import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingExcludes: {
    // Server code reads only small plan.json / state outline files; the
    // pipeline sources and browser-fetched geometry layers stay out of
    // serverless bundles.
    "/*": [
      "./data/**/*",
      "./public/data/districting/**/*",
      "./public/data/district-plans/**/*.topo.json",
      "./public/data/us-states.json",
    ],
  },
  async redirects() {
    // /districts used to hold both explorers behind ?tab=; apportionment is
    // now its own demo. Keep old shared links working (first match wins;
    // query strings pass through).
    return [
      {
        source: "/districts/:stateFips(\\d{2})",
        destination: "/apportionment/explore/:stateFips",
        permanent: false,
      },
      {
        source: "/districts",
        has: [{ type: "query", key: "tab", value: "districting" }],
        destination: "/districts/explore",
        permanent: false,
      },
      {
        source: "/districts",
        has: [{ type: "query", key: "tab" }],
        destination: "/apportionment/explore",
        permanent: false,
      },
      {
        source: "/districts",
        has: [{ type: "query", key: "cap" }],
        destination: "/apportionment/explore",
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
