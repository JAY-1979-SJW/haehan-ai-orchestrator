/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  distDir: "../dist/nextjs",
  transpilePackages: ["@haehan/design-system"],
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
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
