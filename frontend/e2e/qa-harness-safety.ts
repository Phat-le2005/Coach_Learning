import fs from "node:fs";
import path from "node:path";

const FORBIDDEN_DATABASE_NAMES = new Set([
  "edums",
  "postgres",
  "template0",
  "template1",
  "production",
  "prod",
  "main",
  "default",
  "dev",
  "development",
  "staging",
]);

export function getDefaultUntrackedEnvFile(repoRoot: string): string {
  return path.join(repoRoot, ".tmp", "tri-ocr-e2e", ".qa-e2e.env");
}

export type EnvMap = Record<string, string | undefined>;

export function loadUntrackedQaEnv(
  env: EnvMap = process.env,
  envFilePath?: string,
): void {
  if (env.QA_E2E_IGNORE_ENV_FILE === "1") return;
  const resolvedPath =
    envFilePath ??
    (env.QA_E2E_ENV_FILE?.trim() ||
      path.resolve(process.cwd(), "..", ".tmp", "tri-ocr-e2e", ".qa-e2e.env"));
  if (!fs.existsSync(resolvedPath)) return;
  const lines = fs
    .readFileSync(resolvedPath, "utf-8")
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const eqIdx = line.indexOf("=");
    const key = line.slice(0, eqIdx).trim();
    const val = line
      .slice(eqIdx + 1)
      .trim()
      .replace(/^["']|["']$/g, "");
    if (key && env[key] === undefined) {
      env[key] = val;
    }
  }
}

export function isDedicatedQaDatabaseName(dbName: string): boolean {
  const normalized = dbName.trim().toLowerCase();
  if (!normalized || !/^[a-z0-9_]+$/.test(normalized)) return false;
  if (FORBIDDEN_DATABASE_NAMES.has(normalized)) return false;
  const tokens = new Set(normalized.split("_"));
  return tokens.has("qa") || normalized.endsWith("_qa") || normalized.includes("_qa_");
}

export interface QaHarnessConfig {
  password: string;
  qaDatabaseName: string;
  backendDatabaseName: string;
  appEnv: string;
}

export function validateQaHarnessEnv(
  env: EnvMap = process.env,
  envFilePath?: string,
): QaHarnessConfig {
  loadUntrackedQaEnv(env, envFilePath);

  const appEnv = (env.APP_ENV ?? "test").trim().toLowerCase();
  if (appEnv === "production") {
    throw new Error(
      "QA_E2E_SAFETY_ERROR: APP_ENV=production is strictly forbidden for QA E2E execution.",
    );
  }

  const password = (env.QA_E2E_PASSWORD ?? "").trim();
  if (!password) {
    throw new Error(
      "QA_E2E_CONFIG_ERROR: QA_E2E_PASSWORD is required and must not be empty. " +
        "Set QA_E2E_PASSWORD in the environment or in the local untracked .tmp/tri-ocr-e2e/.qa-e2e.env file.",
    );
  }
  if (password.length < 12) {
    throw new Error(
      "QA_E2E_CONFIG_ERROR: QA_E2E_PASSWORD must contain at least 12 characters.",
    );
  }

  const qaDatabaseName = (env.QA_E2E_DATABASE_NAME ?? "").trim();
  if (!qaDatabaseName) {
    throw new Error(
      "QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME is required and must explicitly name the dedicated QA database.",
    );
  }
  if (!isDedicatedQaDatabaseName(qaDatabaseName)) {
    throw new Error(
      `QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME='${qaDatabaseName}' is not a dedicated QA database. ` +
        "Ordinary development or shared databases (such as 'edums') are forbidden.",
    );
  }

  const backendDatabaseName = (env.DATABASE_NAME ?? qaDatabaseName).trim();
  if (!isDedicatedQaDatabaseName(backendDatabaseName)) {
    throw new Error(
      `QA_E2E_SAFETY_ERROR: Backend DATABASE_NAME='${backendDatabaseName}' is not a dedicated QA database.`,
    );
  }
  if (backendDatabaseName !== qaDatabaseName) {
    throw new Error(
      `QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME ('${qaDatabaseName}') does not match DATABASE_NAME ('${backendDatabaseName}').`,
    );
  }

  return {
    password,
    qaDatabaseName,
    backendDatabaseName,
    appEnv,
  };
}
