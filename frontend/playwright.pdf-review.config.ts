import { randomBytes } from "node:crypto";
import path from "node:path";
import { defineConfig } from "@playwright/test";

// Isolated UI contracts: no account credentials and no database access.
const secret = process.env.PDF_REVIEW_E2E_SECRET ?? randomBytes(48).toString("hex");
process.env.PDF_REVIEW_E2E_SECRET = secret;
const baseURL = "http://127.0.0.1:3106";
const output = path.resolve(__dirname, "..", ".tmp", "teacher-pdf-ui");

export default defineConfig({
  testDir: "./e2e", testMatch: "teacher-pdf-review.spec.ts", workers: 1, timeout: 90_000,
  expect: { timeout: 25_000 }, outputDir: path.join(output, "results"),
  reporter: [["list"], ["json", { outputFile: path.join(output, "report.json") }]],
  use: { baseURL, channel: process.platform === "win32" ? "msedge" : undefined, headless: true,
    launchOptions: { args: ["--enable-webgl", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
    viewport: { width: 1440, height: 1000 }, screenshot: "only-on-failure", trace: "off", video: "off" },
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3106",
    url: `${baseURL}/login`, reuseExistingServer: false, timeout: 120_000,
    env: { NEXT_DIST_DIR: ".next-teacher-pdf-qa", AUTH_SESSION_SECRET: secret, SESSION_COOKIE_SECURE: "false" },
  },
});
