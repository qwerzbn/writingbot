import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow larger file uploads (100MB) for Server Actions (if used)
  experimental: {
    serverActions: {
      bodySizeLimit: '100mb',
    },
  },
};

export default nextConfig;
