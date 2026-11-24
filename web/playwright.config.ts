import { defineConfig } from "@playwright/test";

const PORT = process.env.WORKS_E2E_PORT || "8791";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: process.env.WORKS_E2E_URL || `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  reporter: [["list"]],
});
