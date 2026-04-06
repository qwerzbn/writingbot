import path from "path";
import { fileURLToPath } from "url";
import type { NextConfig } from "next";

const configDir = path.dirname(fileURLToPath(import.meta.url));
const apiBase = (process.env.WRITINGBOT_API_URL || "http://127.0.0.1:5001").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  // Disable Next.js dev indicator (floating "N" button)
  devIndicators: false,
  distDir: process.env.NEXT_DIST_DIR || '.next',
  outputFileTracingRoot: configDir,
  turbopack: {
    root: configDir,
  },
  // Allow larger file uploads (100MB) for Server Actions (if used)
  experimental: {
    serverActions: {
      bodySizeLimit: '100mb',
    },
    // Required to prevent Next.js from truncating large API proxy requests
    proxyClientMaxBodySize: 104857600, // 100MB in bytes
    // Increase proxy timeout to 30 minutes (1,800,000 ms) for long-running operations
    proxyTimeout: 1_800_000,
  },
  // Proxy /api requests to FastAPI backend
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
