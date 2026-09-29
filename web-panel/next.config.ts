import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allows loading HMR frames across the local network
  allowedDevOrigins: ['192.168.1.22', 'localhost', '127.0.0.1', 'panel.gangasmx.com'],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8001/api/:path*",
      },
    ];
  },
};

export default nextConfig;
