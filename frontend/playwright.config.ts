import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const ARTIFACT_ROOT = path.resolve(__dirname, "..", ".tmp", "tri-ocr-e2e");

export default defineConfig({
  testDir: path.join(__dirname, "e2e"),
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 90_000,
  expect: {
    timeout: 15_000,
  },
  outputDir: path.join(ARTIFACT_ROOT, "test-results"),
  reporter: [
    ["list"],
    [
      "html",
      {
        outputFolder: path.join(ARTIFACT_ROOT, "playwright-report"),
        open: "never",
      },
    ],
    [
      "json",
      {
        outputFile: path.join(ARTIFACT_ROOT, "playwright-results.json"),
      },
    ],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    channel: "chrome",
    headless: process.env.PW_HEADLESS === "1",
    viewport: { width: 1440, height: 900 },
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    screenshot: "on",
    video: "on",
    trace: "on",
  },
  projects: [
    {
      name: "google-chrome-e2e",
      use: {
        ...devices["Desktop Chrome"],
        channel: "chrome",
      },
    },
  ],
});
