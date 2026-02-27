import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Disable Next.js dev indicator (floating "N" button)
  devIndicators: false,
  // Allow larger file uploads (100MB) for Server Actions (if used)
  experimental: {
    serverActions: {
      bodySizeLimit: '100mb',
    },
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

