import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Port 7071 (set via `npm run dev -- -p 7071`)
  experimental: {
    // Tolerate heavyweight sample JSON in public/
  },
};

export default nextConfig;
