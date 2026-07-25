import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The browser only ever talks to same-origin /api. When the FastAPI backend
  // runs on another origin (local dev), set API_PROXY_ORIGIN (server-side only,
  // e.g. http://127.0.0.1:8000) and Next.js proxies /api/* to it.
  async rewrites() {
    const apiProxyOrigin = process.env.API_PROXY_ORIGIN;
    if (!apiProxyOrigin) return [];
    return [{ source: "/api/:path*", destination: `${apiProxyOrigin.replace(/\/$/, "")}/api/:path*` }];
  },
};

export default nextConfig;
