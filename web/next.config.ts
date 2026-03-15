import path from "path";
import type { NextConfig } from "next";

const workspaceRoot = path.resolve(__dirname);

const nextConfig: NextConfig = {
  // Disable Next.js dev indicator (floating "N" button)
  devIndicators: false,
  outputFileTracingRoot: workspaceRoot,
  turbopack: {
    root: workspaceRoot,
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
        destination: 'http://localhost:5001/api/:path*',
      },
    ];
  },
};

export default nextConfig;
