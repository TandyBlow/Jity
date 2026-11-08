import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const isPlaywright = process.env.JITY_PLAYWRIGHT === "1";

const nextConfig: NextConfig = {
  outputFileTracingRoot: frontendRoot,
  // The browser-test build must never clean or replace a live dev server's files.
  distDir: isPlaywright ? ".next-playwright" : ".next",
  typescript: {
    tsconfigPath: isPlaywright ? "tsconfig.playwright.json" : "tsconfig.json",
  },
};

export default nextConfig;
