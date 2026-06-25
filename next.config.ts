import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingExcludes: {
    "/*": [
      "./public/data/districting/**/*",
      "./public/data/districting-topo/**/*",
    ],
  },
};

export default nextConfig;
