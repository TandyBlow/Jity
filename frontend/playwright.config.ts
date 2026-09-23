import { defineConfig } from "@playwright/test";

const PORT = 3100;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // Screenshot capture must be reproducible and must not saturate the machine:
  // one worker, one browser, no parallel contexts.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    // Uses the Edge already installed on this machine; no browser download.
    channel: "msedge",
    headless: true,
    trace: "off",
    video: "off",
  },
  webServer: {
    // A production build is captured on purpose: `next dev` injects a dev
    // indicator and compiles routes on demand, both of which add noise.
    command: `npm run build && npm run start -- --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 240_000,
    env: { ENABLE_DEV_LOG: "true" },
  },
});
