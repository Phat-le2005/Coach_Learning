import { randomBytes } from "node:crypto";
import path from "node:path";
import { defineConfig } from "@playwright/test";

const secret = process.env.GEMINI_REVIEW_E2E_SECRET ?? randomBytes(48).toString("hex");
process.env.GEMINI_REVIEW_E2E_SECRET = secret;
const baseURL = "http://127.0.0.1:3108";
const output = path.resolve(__dirname, "../.tmp/gemini-ocr-review-20261108/browser");

export default defineConfig({
  testDir: "./e2e", testMatch: "gemini-ocr-review.spec.ts", workers: 1, timeout: 90_000,
  expect: { timeout: 20_000 }, outputDir: path.join(output, "results"),
  reporter: [["list"], ["json", { outputFile: path.join(output, "report.json") }]],
  use: { baseURL, channel: process.platform === "win32" ? "msedge" : undefined,
    headless: true, viewport: { width: 1440, height: 1000 }, trace: "off", video: "off",
    screenshot: "only-on-failure" },
  webServer: [
    { command: "node e2e/fixtures/gemini-review-server.mjs", url: "http://127.0.0.1:8897/health",
      reuseExistingServer: false },
    { command: "node node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port 3108",
      url: `${baseURL}/login`, reuseExistingServer: false, timeout: 120_000,
      env: { NEXT_DIST_DIR: ".next-gemini-review-qa", AUTH_SESSION_SECRET: secret,
        SESSION_COOKIE_SECURE: "false", API_BASE_URL: "http://127.0.0.1:8897" } },
  ],
});
