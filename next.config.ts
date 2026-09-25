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
