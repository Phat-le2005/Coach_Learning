import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";

import {
  isDedicatedQaDatabaseName,
  loadUntrackedQaEnv,
  validateQaHarnessEnv,
  type EnvMap,
  type QaHarnessConfig,
} from "./qa-harness-safety";

export const REPO_ROOT = path.resolve(__dirname, "..", "..");
export const ARTIFACT_DIR = path.join(REPO_ROOT, ".tmp", "tri-ocr-e2e");
export const SCREENSHOT_DIR = path.join(ARTIFACT_DIR, "screenshots");
export const TELEMETRY_DIR = path.join(ARTIFACT_DIR, "telemetry");
export const PYTHON_EXE = path.join(REPO_ROOT, "backend", ".venv", "Scripts", "python.exe");
export const DB_HELPER = path.join(__dirname, "qa_db_helper.py");
export const DEFAULT_UNTRACKED_ENV_FILE = path.join(ARTIFACT_DIR, ".qa-e2e.env");

export const QA_STUDENT_EMAIL = "qa.ocr.e2e.isolated@edums.edu.vn";

for (const dir of [ARTIFACT_DIR, SCREENSHOT_DIR, TELEMETRY_DIR]) {
  fs.mkdirSync(dir, { recursive: true });
}

export { isDedicatedQaDatabaseName, loadUntrackedQaEnv, validateQaHarnessEnv, type EnvMap, type QaHarnessConfig };

function buildDbHelperEnv(env: EnvMap = process.env): NodeJS.ProcessEnv {
  const cfg = validateQaHarnessEnv(env, DEFAULT_UNTRACKED_ENV_FILE);
  return {
    ...(env as NodeJS.ProcessEnv),
    APP_ENV: cfg.appEnv,
    QA_E2E_PASSWORD: cfg.password,
    QA_E2E_DATABASE_NAME: cfg.qaDatabaseName,
    DATABASE_NAME: cfg.backendDatabaseName,
  };
}

export interface CreatedAttemptFixture {
  attempt_id: string;
  question_id: string;
  practice_session_id: string;
  student_email: string;
  database_name?: string;
  initial_revision: number;
  status: string;
}

export interface DbStepRecord {
  id: string;
  step_index: number;
  step_type: string;
  status: string;
  is_deleted: boolean;
  content_latex: string | null;
  explanation_text: string | null;
  step_revision_number: number;
}

export interface DbOperationRecord {
  id: string;
  client_action_id: string;
  operation_type: string;
  request_hash: string;
  result_attempt_revision: number;
}

export interface DbAttemptInspection {
  exists: boolean;
  database_name?: string;
  attempt: {
    id: string;
    status: string;
    attempt_revision_number: number;
    question_id: string | null;
    practice_session_id: string | null;
  };
  active_step_count: number;
  active_steps: DbStepRecord[];
  all_steps: DbStepRecord[];
  operation_count: number;
  operations: DbOperationRecord[];
  ink_document: {
    id: string;
    revision: number;
    pages: Array<{
      page_index: number;
      stroke_count: number;
      point_count: number;
      sha256: string;
    }>;
  } | null;
}

export function createIsolatedAttempt(label: string): CreatedAttemptFixture {
  const helperEnv = buildDbHelperEnv(process.env);
  const out = execFileSync(PYTHON_EXE, [DB_HELPER, "create-attempt", "--label", label], {
    cwd: path.join(REPO_ROOT, "backend"),
    env: helperEnv,
    encoding: "utf-8",
  });
  return JSON.parse(out.trim()) as CreatedAttemptFixture;
}

export function inspectAttemptInDb(attemptId: string): DbAttemptInspection {
  const helperEnv = buildDbHelperEnv(process.env);
  const out = execFileSync(PYTHON_EXE, [DB_HELPER, "inspect-attempt", "--attempt-id", attemptId], {
    cwd: path.join(REPO_ROOT, "backend"),
    env: helperEnv,
    encoding: "utf-8",
  });
  return JSON.parse(out.trim()) as DbAttemptInspection;
}

export function bumpAttemptRevisionInDb(
  attemptId: string,
  latex = "D = \\mathbb{R}",
): {
  attempt_id: string;
  database_name?: string;
  new_revision: number;
  step_count: number;
} {
  const helperEnv = buildDbHelperEnv(process.env);
  const out = execFileSync(
    PYTHON_EXE,
    [DB_HELPER, "bump-revision", "--attempt-id", attemptId, "--latex", latex],
    {
      cwd: path.join(REPO_ROOT, "backend"),
      env: helperEnv,
      encoding: "utf-8",
    },
  );
  return JSON.parse(out.trim());
}

export interface NetworkLogEntry {
  timestamp: string;
  method: string;
  url: string;
  status?: number;
  requestBody?: unknown;
  responseBody?: unknown;
}

export interface TelemetryCollector {
  consoleErrors: string[];
  pageErrors: string[];
  networkLogs: NetworkLogEntry[];
  save(name: string): string;
}

function redactObject(obj: unknown): unknown {
  if (!obj || typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map(redactObject);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    if (/password|token|secret|authorization|cookie/i.test(k)) {
      out[k] = "[REDACTED]";
    } else {
      out[k] = redactObject(v);
    }
  }
  return out;
}

export function attachTelemetry(page: Page): TelemetryCollector {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const networkLogs: NetworkLogEntry[] = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });

  page.on("pageerror", (err) => {
    pageErrors.push(`${err.name}: ${err.message}`);
  });

  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/api/v2/math-solutions/") && !url.includes("/auth/")) return;
    const req = response.request();
    let reqBody: unknown = undefined;
    try {
      const rawReq = req.postData();
      if (rawReq) reqBody = redactObject(JSON.parse(rawReq));
    } catch {
      reqBody = "[non-json]";
    }
    let resBody: unknown = undefined;
    try {
      const ct = response.headers()["content-type"] ?? "";
      if (ct.includes("application/json")) {
        resBody = redactObject(await response.json());
      }
    } catch {
      resBody = "[unreadable]";
    }
    networkLogs.push({
      timestamp: new Date().toISOString(),
      method: req.method(),
      url: url.replace(/^https?:\/\/[^/]+/, ""),
      status: response.status(),
      requestBody: reqBody,
      responseBody: resBody,
    });
  });

  return {
    consoleErrors,
    pageErrors,
    networkLogs,
    save(name: string): string {
      const safeName = name.replace(/[^a-zA-Z0-9_-]/g, "_");
      const filePath = path.join(TELEMETRY_DIR, `${safeName}.json`);
      fs.writeFileSync(
        filePath,
        JSON.stringify(
          {
            test: name,
            recordedAt: new Date().toISOString(),
            consoleErrors,
            pageErrors,
            networkLogs,
          },
          null,
          2,
        ),
        "utf-8",
      );
      return filePath;
    },
  };
}

export async function loginAsIsolatedStudent(page: Page): Promise<void> {
  const { password } = validateQaHarnessEnv(process.env);
  await page.goto("/login");
  const emailInput = page.locator('input[type="email"], input[name="email"]').first();
  const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
  await emailInput.fill(QA_STUDENT_EMAIL);
  await passwordInput.fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 20_000 });
}

/**
 * Draw a continuous stroke on the MathCanvas using real pointer events.
 * Coordinates are normalized [0..1] relative to the canvas bounding box.
 */
export async function drawNormalizedStroke(
  page: Page,
  points: Array<{ x: number; y: number }>,
): Promise<void> {
  if (points.length === 0) return;
  const canvas = page.locator("canvas").first();
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("MathCanvas boundingBox is null");

  const toScreen = (pt: { x: number; y: number }) => ({
    x: box.x + pt.x * box.width,
    y: box.y + pt.y * box.height,
  });

  const first = toScreen(points[0]);
  await page.mouse.move(first.x, first.y);
  await page.mouse.down();
  for (let i = 1; i < points.length; i++) {
    const pt = toScreen(points[i]);
    await page.mouse.move(pt.x, pt.y, { steps: 3 });
  }
  await page.mouse.up();
}

/**
 * Draw `lineCount` distinct horizontal handwritten expression rows on the A4 canvas
 * so that `segmentPageInk_v2` segments them into `lineCount` separate regions.
 */
export async function drawDistinctMathLines(page: Page, lineCount: number): Promise<void> {
  const canvas = page.locator("canvas").first();
  await canvas.waitFor({ state: "visible" });

  for (let i = 0; i < lineCount; i++) {
    const baseY = 0.05 + i * 0.042;
    await drawNormalizedStroke(page, [
      { x: 0.18, y: baseY },
      { x: 0.22, y: baseY + 0.008 },
      { x: 0.27, y: baseY + 0.002 },
      { x: 0.32, y: baseY + 0.008 },
    ]);
    await drawNormalizedStroke(page, [
      { x: 0.35, y: baseY + 0.002 },
      { x: 0.41, y: baseY + 0.008 },
      { x: 0.47, y: baseY + 0.004 },
    ]);
  }
}
