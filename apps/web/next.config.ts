import type { NextConfig } from "next";

// Guest Simulation Alpha deploy (compose.prototype.yaml): the web container
// proxies /api/* to FastAPI so browsers see a single HTTPS origin. Both
// variables are unset in local development, which keeps dev behaviour
// unchanged.
const apiProxyTarget = process.env.API_PROXY_TARGET;

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT_STANDALONE === "true" ? "standalone" : undefined,
  async rewrites() {
    if (!apiProxyTarget) {
      return [];
    }
    return [
      {
        // FastAPI exposes /health without the /api prefix; map the
        // same-origin healthcheck path explicitly before the generic rule.
        source: "/api/health",
        destination: `${apiProxyTarget}/health`,
      },
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
