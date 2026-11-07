import { networkInterfaces } from 'node:os';

// Exact local interface addresses; never a wildcard of the entire private network.
const lanHosts = process.env.COACH_LAN_MODE === '1' ? Object.entries(networkInterfaces())
  .filter(([name]) => !/^(?:lo|veth|br-|virbr|docker|tun|tap|wg)|loopback|vethernet|wsl|docker|virtual|vmware|vbox|tailscale|tunnel|vpn/i.test(name))
  .flatMap(([, addresses]) => (addresses ?? []).filter(a => a.family === 'IPv4' && !a.internal
    && /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(a.address)).map(a => a.address)) : [];

/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: [...new Set(['127.0.0.1', ...lanHosts, ...(process.env.NEXT_PUBLIC_APP_URL?.trim()
    ? [new URL(process.env.NEXT_PUBLIC_APP_URL.trim()).hostname] : [])])],
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    const backendUrl = process.env.API_BASE_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/v2/:path*",
        destination: `${backendUrl}/api/v2/:path*`,
        // Browser Math Workspace requests carry this header so the secure BFF handles them.
        missing: [{ type: "header", key: "x-edums-bff" }],
      },
    ];
  },
};

export default nextConfig;
