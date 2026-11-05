import { randomBytes } from "node:crypto";
import path from "node:path";
import { defineConfig } from "@playwright/test";

// These UI tests use an isolated Next server and ephemeral signed test sessions.
// They never log in to or mutate the application's database.
const secret = process.env.CLASSROOM_E2E_SECRET ?? randomBytes(48).toString("hex");
process.env.CLASSROOM_E2E_SECRET = secret;
process.env.CLASSROOM_E2E = "1";
const baseURL = "http://127.0.0.1:3105";
const output = path.resolve(__dirname, "..", ".tmp", "teacher-classroom");
const production = process.env.CLASSROOM_E2E_PRODUCTION === "1";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "teacher-classroom.spec.ts",
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  outputDir: path.join(output, "results"),
  reporter: [["list"], ["json", { outputFile: path.join(output, "report.json") }]],
  use: {
    baseURL,
    channel: process.platform === "win32" ? "msedge" : undefined,
    headless: true,
    viewport: { width: 1440, height: 1000 },
    launchOptions: { args: ["--enable-webgl", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
    screenshot: "only-on-failure",
    trace: "off",
    video: "off",
  },
  webServer: {
    command: `node node_modules/next/dist/bin/next ${production ? "start" : "dev"} --hostname 127.0.0.1 --port 3105`,
    url: `${baseURL}/login`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { NEXT_DIST_DIR: production ? ".next" : ".next-teacher-classroom-qa", AUTH_SESSION_SECRET: secret, SESSION_COOKIE_SECURE: "false" },
  },
});
