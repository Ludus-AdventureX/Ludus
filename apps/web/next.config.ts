import type { NextConfig } from "next";

// Prototype deploy (compose.prototype.yaml): the web container proxies /api/*
// to FastAPI so browsers see a single origin. Both variables are unset in
// local development, which keeps dev behaviour unchanged.
const apiProxyTarget = process.env.API_PROXY_TARGET ?? process.env.API_PROXY_ORIGIN;

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT_STANDALONE === "true" ? "standalone" : undefined,
  // The browser only ever talks to same-origin /api. When the FastAPI backend
  // runs on another origin, set API_PROXY_TARGET (compose deploy) or
  // API_PROXY_ORIGIN (local dev) and Next.js proxies /api/* to it. Both are
  // server-side only and unset by default, keeping dev behaviour unchanged.
  // The exact /api/health rewrite must precede the generic /api/:path* rule:
  // FastAPI serves /health outside the /api prefix.
  async rewrites() {
    if (!apiProxyTarget) return [];
    const target = apiProxyTarget.replace(/\/$/, "");
    return [
      { source: "/api/health", destination: `${target}/health` },
      { source: "/api/:path*", destination: `${target}/api/:path*` },
    ];
  },
};

export default nextConfig;
