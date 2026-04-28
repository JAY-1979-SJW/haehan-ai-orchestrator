/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const fastapiBase = process.env.FASTAPI_BASE_URL;
    if (!fastapiBase) return [];
    return [
      {
        source: "/api/v1/:path*",
        destination: `${fastapiBase}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
