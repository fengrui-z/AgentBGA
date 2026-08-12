import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The Python CLI serves this export directly, so no Node process is needed at runtime.
  output: "export",
};

export default nextConfig;
