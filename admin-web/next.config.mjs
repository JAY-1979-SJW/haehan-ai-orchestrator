/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  transpilePackages: ["@haehan/design-system"],
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
  async rewrites() {
    // FASTAPI_BASE_URL 규약: /api/v1 까지 포함한 전체 베이스 (backend-auth.ts 와 동일).
    const fastapiBase = process.env.FASTAPI_BASE_URL;
    if (!fastapiBase) return [];
    return [
      {
        source: "/api/v1/:path*",
        destination: `${fastapiBase}/:path*`,
      },
    ];
  },
};

export default nextConfig;
