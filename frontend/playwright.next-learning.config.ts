import { randomBytes } from "node:crypto";
import path from "node:path";
import { defineConfig } from "@playwright/test";

const secret = process.env.NEXT_LEARNING_E2E_SECRET ?? randomBytes(48).toString("hex");
process.env.NEXT_LEARNING_E2E_SECRET = secret;
const baseURL = "http://127.0.0.1:3112";
const output = path.resolve(__dirname, "../.tmp/next-learning-20261109/browser");
export default defineConfig({
  testDir:"./e2e", testMatch:"next-learning.spec.ts", workers:1, timeout:90_000,
  expect:{timeout:20_000}, outputDir:path.join(output,"results"),
  reporter:[["list"],["json",{outputFile:path.join(output,"report.json")}]],
  use:{baseURL,channel:process.platform === "win32" ? "msedge" : undefined,headless:true,
    viewport:{width:1440,height:1100},trace:"retain-on-failure",screenshot:"only-on-failure"},
  webServer:[
    {command:"node e2e/fixtures/next-learning-server.mjs",url:"http://127.0.0.1:8898/health",reuseExistingServer:false},
    {command:"node node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port 3112",
      url:`${baseURL}/login`,reuseExistingServer:false,timeout:120_000,
      env:{NEXT_DIST_DIR:".next-next-learning-qa",AUTH_SESSION_SECRET:secret,SESSION_COOKIE_SECURE:"false",API_BASE_URL:"http://127.0.0.1:8898"}},
  ],
});
