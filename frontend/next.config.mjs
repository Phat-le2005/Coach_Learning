/** @type {import('next').NextConfig} */
const nextConfig = {
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
