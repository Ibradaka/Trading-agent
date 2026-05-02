/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8899";
    return [
      { source: "/health", destination: `${backend}/health` },
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
    ];
  },
};

export default nextConfig;
