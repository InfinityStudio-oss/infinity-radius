import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@infinity-radius/ui", "@infinity-radius/types"],
};

export default nextConfig;
