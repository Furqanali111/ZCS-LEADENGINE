import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // STATIC_EXPORT=1 builds plain files into out/ for the desktop bundle (FastAPI serves them).
  ...(process.env.STATIC_EXPORT ? { output: "export" as const, trailingSlash: true } : {}),
  cacheComponents: !process.env.STATIC_EXPORT, // PPR cannot run in export mode
  partialPrefetching: !process.env.STATIC_EXPORT,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
