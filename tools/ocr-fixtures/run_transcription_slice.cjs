#!/usr/bin/env node
"use strict";
// Real Next.js + isolated PostgreSQL + unmocked browser CoMER. No production accounts.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { spawn, execFileSync } = require("node:child_process");
const { createHash, randomUUID } = require("node:crypto");
const net = require("node:net");
const root = path.resolve(__dirname, "../..");
const out = path.join(root, ".tmp/tri-ocr-core-impl053");
const build = path.join(root, "frontend/.test-build-run/src/features/math-workspace/utils");
const IR = require(path.join(build, "structured-transcription-ir.js"));
const { segmentPageInk_v2 } = require(path.join(build, "page-ocr.js"));
const { chromium, expect } = require(path.join(root, "frontend/node_modules/@playwright/test"));
const { validateQaHarnessEnv } = require(path.join(root, "frontend/.test-build-run/e2e/qa-harness-safety.js"));
const base = "http://localhost:3003";
const backend = "http://127.0.0.1:8003";
const sha = (data) => createHash("sha256").update(data).digest("hex");
const write = (name, value) => fs.writeFileSync(path.join(out, name), JSON.stringify(value, null, 2));
const children = [];
let browser;
const report = { timestamp: new Date().toISOString(), realMultiLineStatus: "REAL_MULTI_LINE_NOT_VERIFIED", checks: [], scenarios: [] };
function check(name, condition, details) {
  report.checks.push({ name, pass: Boolean(condition), ...(details === undefined ? {} : { details }) });
  assert.ok(condition, name);
}
function helper(python, env, ...args) {
  return JSON.parse(execFileSync(python, [path.join(root, "frontend/e2e/qa_db_helper.py"), ...args], {
    cwd: path.join(root, "backend"), env, encoding: "utf8", timeout: 90000, stdio: ["ignore", "pipe", "pipe"],
  }).trim());
}
function start(exe, args, cwd, env, name) {
  const fd = fs.openSync(path.join(out, `${name}.log`), "w");
  const proc = spawn(exe, args, { cwd, env, windowsHide: true, stdio: ["ignore", fd, fd] });
  children.push(proc); fs.closeSync(fd);
  return proc;
}
async function ready(url, proc) {
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    if (proc.exitCode !== null) throw new Error(`QA_SERVER_EXIT: ${url}`);
    try { if ((await fetch(url, { signal: AbortSignal.timeout(4000) })).ok) return; } catch { /* retry startup */ }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`QA_SERVER_NOT_READY: ${url}`);
}
async function requireFreePort(port) {
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", () => reject(new Error(`QA_PORT_IN_USE: ${port}; refusing to use an existing service`)));
    server.listen(port, () => server.close(resolve));
  });
}
async function api(page, method, suffix, body) {
  return page.evaluate(async ({ method, suffix, body }) => {
    const csrf = await (await fetch("/auth/csrf")).json();
    const response = await fetch(suffix, { method, headers: { "content-type": "application/json", "x-edums-bff": "1",
      "x-csrf-token": csrf.csrf_token }, ...(body ? { body: JSON.stringify(body) } : {}) });
    if (!response.ok) throw new Error(`QA_API_${response.status}: ${suffix}`);
    return response.json();
  }, { method, suffix, body });
}
async function downloadIr(page, panel, file) {
  const pending = page.waitForEvent("download");
  await panel.getByRole("button", { name: "Tải bản chép IR về máy" }).click();
  const download = await pending;
  await download.saveAs(path.join(out, file));
  const ir = JSON.parse(fs.readFileSync(path.join(out, file), "utf8"));
  IR.validateSolutionTranscriptionIR(ir);
  return ir;
}
async function recognize(panel) {
  const button = panel.getByTestId("btn-recognize-unit-comer");
  const t0 = performance.now();
  await button.click();
  await expect(button).toBeEnabled({ timeout: 90000 });
  const raw = await panel.getByTestId("raw-recognition").innerText();
  check("real CoMER produces raw LaTeX", raw !== "UNRESOLVED" && raw.trim().length > 0, { raw });
  return { raw, durationMs: Math.round(performance.now() - t0), timingScope: "UI action with model warmed by legacy OCR, not cold-load benchmark",
    evidence: "MODEL_OUTPUT", engine: "CoMER v0_1 int8 ONNX WASM beamWidth=3" };
}

// Polyline glyphs replayed by Playwright mouse events into the actual MathCanvas.
// These are SYNTHETIC_INK, not handwriting or an OCR accuracy benchmark.
function calculusPaths() {
  const glyphs = {
    f: [[[0.8,0],[0.3,0.1],[0.2,1]], [[0,0.4],[0.7,0.4]]],
    x: [[[0,0.15],[0.8,1]], [[0.8,0.15],[0,1]]],
    "(": [[[0.8,0],[0.2,0.3],[0.1,0.65],[0.8,1]]],
    ")": [[[0,0],[0.6,0.3],[0.7,0.65],[0,1]]],
    "=": [[[0,0.35],[0.8,0.35]], [[0,0.65],[0.8,0.65]]],
    "'": [[[0.3,0],[0.1,0.25]]],
    "2": [[[0,0.2],[0.4,0],[0.8,0.2],[0.6,0.5],[0,1],[0.85,1]]],
    "0": [[[0.4,0],[0,0.2],[0,0.8],[0.4,1],[0.8,0.8],[0.8,0.2],[0.4,0]]],
  };
  const texts = ["f(x)=x2", "f'(x)=2x", "f'(x)=0", "x=0"];
  const paths = [];
  texts.forEach((text, row) => {
    [...text].forEach((char, i) => {
      const superscript = row === 0 && i === text.length - 1;
      for (const line of glyphs[char]) paths.push(line.map(([x,y]) => ({ x: 0.14 + i * 0.022 + x * 0.016,
        y: 0.08 + row * 0.09 + (superscript ? -0.009 : 0) + y * (superscript ? 0.012 : 0.022) })));
    });
  });
  return paths;
}
function systemPaths() {
  return [
    [{x:0.11,y:0.10},{x:0.095,y:0.14},{x:0.08,y:0.19},{x:0.095,y:0.24},{x:0.11,y:0.28}],
    [{x:0.13,y:0.12},{x:0.16,y:0.135},{x:0.18,y:0.14}],
    [{x:0.13,y:0.22},{x:0.16,y:0.235},{x:0.18,y:0.24}],
  ];
}
async function draw(page, paths) {
  const canvas = page.locator("canvas").first();
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox(); assert.ok(box);
  for (const points of paths) {
    const screen = (p) => ({ x: box.x + p.x * box.width, y: box.y + p.y * box.height });
    let p = screen(points[0]); await page.mouse.move(p.x, p.y); await page.mouse.down();
    for (const point of points.slice(1)) { p = screen(point); await page.mouse.move(p.x, p.y, { steps: 3 }); }
    await page.mouse.up();
  }
}

async function main() {
  fs.mkdirSync(path.join(out, "screenshots"), { recursive: true });
  const cfg = validateQaHarnessEnv(process.env, path.join(root, ".tmp/tri-ocr-e2e/.qa-e2e.env"));
  assert.equal(cfg.appEnv, "test");
  const env = { ...process.env, APP_ENV: "test", DATABASE_NAME: cfg.qaDatabaseName, QA_E2E_DATABASE_NAME: cfg.qaDatabaseName,
    PYTHONDONTWRITEBYTECODE: "1", API_BASE_URL: backend };
  const python = process.env.PYTHON_EXE || [path.join(root, "backend/.venv/Scripts/python.exe"),
    path.resolve(root, "../Coach_Learning/backend/.venv/Scripts/python.exe")].find(fs.existsSync);
  if (!python) throw new Error("BLOCKED_QA_PYTHON_MISSING");
  console.log("Checking dedicated QA database...");
  const safety = helper(python, env, "verify-safety"); assert.equal(safety.connected_database_name, cfg.qaDatabaseName);
  write("qa_safety.json", safety);
  await requireFreePort(8003); await requireFreePort(3003);
  const apiServer = start(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8003"], path.join(root, "backend"), env, "backend-qa");
  await ready(`${backend}/openapi.json`, apiServer);
  const next = start(process.execPath, [path.join(root, "frontend/node_modules/next/dist/bin/next"), "dev", "--hostname", "localhost", "--port", "3003"],
    path.join(root, "frontend"), { ...env, NEXT_DIST_DIR: ".next-build" }, "next-qa");
  await ready(`${base}/login`, next);
  browser = await chromium.launch({ channel: "chrome", headless: true });
  report.browser = browser.version();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1500 }, acceptDownloads: true });
  const page = await context.newPage();
  const errors = [], mutations = [];
  page.on("pageerror", (err) => errors.push(err.message));
  page.on("request", (req) => {
    if (/POST|PUT|PATCH|DELETE/.test(req.method()) && new URL(req.url()).pathname.startsWith("/api/")) mutations.push({ method: req.method(), path: new URL(req.url()).pathname });
  });
  await page.goto(`${base}/login`);
  await page.locator('input[type="email"]').fill("qa.ocr.e2e.isolated@edums.edu.vn");
  // Provisioning creates/updates ONLY the existing helper's QA-owned account.
  const realAttempt = helper(python, env, "create-attempt", "--label", "impl053-native");
  await page.locator('input[type="password"]').fill(cfg.password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  const nativePath = path.join(root, ".tmp/tri-ocr-native/integral_case_01.json");
  if (!fs.existsSync(nativePath)) throw new Error("BLOCKED_MISSING_REAL_INK_FIXTURE");
  const nativeBytes = fs.readFileSync(nativePath), native = JSON.parse(nativeBytes);
  const manifest = { baseCommit: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
    architecture: "Coach_Learning_MathCanvas_OCR_V2_Architecture_Implementation_Plan.pdf v1.0", realMultiLineStatus: report.realMultiLineStatus,
    nativeFixture: { path: ".tmp/tri-ocr-native/integral_case_01.json", sha256: sha(nativeBytes), sourceKind: native.sourceKind, evidence: "REAL_INK", strokeCount: native.strokes.length },
    models: Object.fromEntries(["encoder_int8.onnx", "decoder_int8.onnx", "vocab.json"].map((file) => [file, sha(fs.readFileSync(path.join(root, "frontend/public/ocr/comer/v0_1", file)))])),
    implementation: Object.fromEntries([
      "frontend/src/features/math-workspace/utils/structured-transcription-ir.ts",
      "frontend/src/features/math-workspace/components/PageOcrTranscriptionReviewPanel.tsx",
      "frontend/src/features/math-workspace/components/PageOcrReviewModal.tsx",
      "frontend/src/features/math-workspace/MathWorkspace.tsx", "tools/ocr-fixtures/run_transcription_slice.cjs",
    ].map((file) => [file, sha(fs.readFileSync(path.join(root, file)))])),
    scenarios: [] };
  write("source_manifest.json", manifest);
  const before = {}, after = {}, recognition = [], integrity = {}, projections = {};
  for (const scenario of ["native", "calculus", "system"]) {
    console.log(`Running real-app scenario: ${scenario}`);
    const attempt = scenario === "native" ? realAttempt : helper(python, env, "create-attempt", "--label", `impl053-${scenario}`);
    assert.equal(attempt.database_name, cfg.qaDatabaseName);
    const inkPath = `/api/v2/math-solutions/attempts/${attempt.attempt_id}/ink`;
    if (scenario === "native") {
      const doc = await api(page, "GET", inkPath);
      await api(page, "PUT", `${inkPath}/pages/0`, { expected_document_revision: doc.document_revision, client_action_id: randomUUID(), strokes: native.strokes.slice(0, -1) });
      // Exercise a nondefault document revision; source identity must not be a constant 1.
      const updated = await api(page, "GET", inkPath);
      await api(page, "PUT", `${inkPath}/pages/0`, { expected_document_revision: updated.document_revision, client_action_id: randomUUID(), strokes: native.strokes });
    }
    await page.goto(`${base}/student/attempts/${attempt.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible({ timeout: 30000 });
    await expect(page.locator("canvas").first()).toBeVisible();
    if (scenario !== "native") await draw(page, scenario === "calculus" ? calculusPaths() : systemPaths());
    const extract = page.getByRole("button", { name: /Trích xuất trang/i });
    await expect(extract).toBeEnabled(); await extract.click();
    const modal = page.getByRole("dialog", { name: /Trích xuất trang/i });
    await expect(modal).toBeVisible();
    const stop = modal.getByRole("button", { name: /Đang nhận diện.*Dừng/ });
    // Let the existing recognition queue finish; a stop-button click races its removal.
    await expect(stop).toBeHidden({ timeout: 90000 });
    await modal.getByTestId("btn-toggle-transcription-review").click();
    const panel = modal.getByTestId("ocr-transcription-review-panel"); await expect(panel).toBeVisible();
    const reviewStart = mutations.length;
    const savedSource = await api(page, "GET", `${inkPath}/pages/0`);
    const sourceStrokes = savedSource.strokes;
    before[scenario] = await downloadIr(page, panel, `${scenario}_before.json`);
    IR.validateSolutionTranscriptionIR(before[scenario], sourceStrokes);
    check(`${scenario}: IR carries the actual saved document revision`, before[scenario].sourceRevision === savedSource.document_revision);
    if (scenario === "native") check("native: a nondefault source revision was exercised", savedSource.document_revision > 1);
    await page.screenshot({ path: path.join(out, `screenshots/${scenario}-before.png`) });
    const sourceHash = sha(JSON.stringify(sourceStrokes));
    const scene = { name: scenario, evidence: scenario === "native" ? "REAL_INK" : "SYNTHETIC_INK", strokeCount: sourceStrokes.length,
      regions: segmentPageInk_v2(sourceStrokes).length, contentUnits: before[scenario].contentUnits.length,
      topLevelUnits: IR.getRootContentUnits(before[scenario].contentUnits).length,
      containers: before[scenario].contentUnits.filter((u) => u.role === "CONTAINER").length,
      modelUnits: 0, beforeApproval: before[scenario].reviewStatus };
    manifest.scenarios.push({ ...scene, sourceSha256: sourceHash });
    const containers = before[scenario].contentUnits.filter((u) => u.role === "CONTAINER");
    for (const u of containers) await panel.getByRole("button", { name: `Mở cấu trúc ${u.id}`, exact: true }).click();
    check(`${scenario}: every required review unit is reachable`, await panel.getByTestId("transcription-unit-nav").count() === before[scenario].contentUnits.length);
    if (containers.length) {
      await panel.getByTestId("transcription-unit-nav").first().scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(out, `screenshots/${scenario}-hierarchy.png`) });
    }
    if (scenario === "system") {
      check("system: structural engine found one container with two children", containers.length === 1 && containers[0].childIds.length === 2);
      await panel.locator(`[data-unit-id="${containers[0].id}"]`).click();
      check("system: no fake container textarea", await panel.locator("textarea").count() === 0);
      check("system: container has no CoMER action", await panel.getByTestId("btn-recognize-unit-comer").count() === 0);
      await panel.getByRole("button", { name: "Xác nhận cấu trúc này" }).click();
      await expect(panel.getByRole("alert")).toContainText("CHILDREN_UNAPPROVED");
    }
    let mathIndex = 0;
    for (const { unit } of IR.getOrderedReviewUnits(before[scenario].contentUnits).filter((r) => r.unit.role === "ATOMIC")) {
      await panel.locator(`[data-unit-id="${unit.id}"]`).click();
      if (scenario === "system") {
        // Geometry-only fixture: do not claim its diagonal lines are handwritten equations.
        await panel.getByLabel("Bản chép nội dung", { exact: true }).fill(`symbol-${mathIndex + 1}`);
      } else {
        const result = await recognize(panel); scene.modelUnits++;
        let correction;
        if (scenario === "native") {
          // Explicit simulation, not annotated ground truth: upper handwritten limit visually resembles 2.
          correction = result.raw.replace(/\^\s*\{\s*3\s*\}/, "^{2}");
        } else {
          correction = ["f(x)=x^2", "f'(x)=2x", "f'(x)=0", "x=0"][mathIndex];
        }
        assert.ok(correction, "unexpected synthetic segmentation must not receive invented extra content");
        recognition.push({ scenario, unitId: unit.id, sourceStrokeIds: unit.sourceStrokeIds, ...result,
          correction: { evidence: "MANUAL_CORRECTION", content: correction, simulatedHuman: true,
            groundTruthStatus: scenario === "native" ? "NOT_ANNOTATED; partial visual correction only, remaining text unverified" : "synthetic drawing intent, not handwriting ground truth" } });
        await panel.getByLabel("Bản chép nội dung", { exact: true }).fill(correction);
      }
      await panel.getByRole("button", { name: "Xác nhận bản chép này" }).click(); mathIndex++;
    }
    for (const u of containers.reverse()) {
      await panel.locator(`[data-unit-id="${u.id}"]`).click();
      await panel.getByRole("button", { name: "Xác nhận cấu trúc này" }).click();
    }
    await panel.getByRole("button", { name: "Xác nhận thứ tự đọc đang hiển thị" }).click();
    await expect(panel.getByTestId("transcription-status")).toContainText("APPROVED");
    after[scenario] = await downloadIr(page, panel, `${scenario}_after.json`);
    IR.validateSolutionTranscriptionIR(after[scenario], sourceStrokes);
    IR.requireApprovedTranscriptionIR(after[scenario], sourceStrokes);
    check(`${scenario}: approved IR validates against exact original source`, after[scenario].reviewStatus === "APPROVED");
    if (scenario === "system") {
      const child = before[scenario].contentUnits.find((u) => u.role === "ATOMIC");
      await panel.locator(`[data-unit-id="${child.id}"]`).click();
      await panel.getByLabel("Bản chép nội dung", { exact: true }).fill("edited symbol");
      const edited = await downloadIr(page, panel, "system_child_edited.json");
      check("UI: editing approved child invalidates parent", edited.reviewStatus === "NEEDS_REVIEW" && edited.contentUnits.find((u) => u.role === "CONTAINER").reviewStatus === "NEEDS_REVIEW");
      await panel.getByRole("button", { name: "Xác nhận bản chép này" }).click();
      await panel.locator(`[data-unit-id="${containers[0].id}"]`).click();
      await panel.getByRole("button", { name: "Xác nhận cấu trúc này" }).click();
      after[scenario] = await downloadIr(page, panel, "system_after.json");
    } else {
      const u = after[scenario].contentUnits.find((u) => u.role === "ATOMIC");
      await panel.locator(`[data-unit-id="${u.id}"]`).click();
      await recognize(panel);
      check(`${scenario}: real OCR rerun preserves manual correction`, await panel.getByLabel("Bản chép nội dung", { exact: true }).inputValue() === u.approvedContent);
      after[scenario] = await downloadIr(page, panel, `${scenario}_after.json`);
    }
    // TEXT/UNKNOWN review is manual and cannot trigger CoMER. Restore accepted math afterwards.
    if (scenario === "calculus") {
      check("calculus: four independent lines remain four roots", scene.topLevelUnits === 4 && scene.containers === 0);
      await panel.getByLabel("Loại nội dung", { exact: true }).selectOption("TEXT");
      check("TEXT has manual transcription and no CoMER button", await panel.getByTestId("btn-recognize-unit-comer").count() === 0);
      await panel.getByLabel("Bản chép nội dung", { exact: true }).fill("Suy ra");
      const textIr = await downloadIr(page, panel, "text_manual_review.json");
      check("TEXT edit invalidates approval", textIr.reviewStatus === "NEEDS_REVIEW");
      await panel.getByLabel("Loại nội dung", { exact: true }).selectOption("UNKNOWN");
      check("UNKNOWN is explicit and has no CoMER button", await panel.getByTestId("btn-recognize-unit-comer").count() === 0);
      const unknownIr = await downloadIr(page, panel, "unknown_projection_blocked.json");
      const partial = IR.projectTranscriptionToLegacySteps(unknownIr);
      check("three approved plus UNKNOWN never emits partial API steps", partial.steps.length === 0 && partial.submitPayload === null && !partial.readyToSubmit);
      await panel.getByLabel("Loại nội dung", { exact: true }).selectOption("MATH");
      await panel.getByLabel("Bản chép nội dung", { exact: true }).fill(after[scenario].contentUnits.find((u) => u.id === selectedAtomicId(after[scenario])).approvedContent);
      await panel.getByRole("button", { name: "Xác nhận bản chép này" }).click();
      after[scenario] = await downloadIr(page, panel, "calculus_after.json");
    }
    await panel.getByRole("button", { name: "Xem trước chuyển đổi bước chấm", exact: true }).click();
    await expect(panel.getByTestId("legacy-projection-preview")).toContainText("BLOCKED");
    await page.screenshot({ path: path.join(out, `screenshots/${scenario}-approved-projection.png`) });
    projections[scenario] = IR.projectTranscriptionToLegacySteps(after[scenario]);
    const finalSource = await api(page, "GET", `${inkPath}/pages/0`);
    const reviewMutations = mutations.slice(reviewStart);
    const db = helper(python, env, "inspect-attempt", "--attempt-id", attempt.attempt_id);
    check(`${scenario}: IR review makes zero application API mutations`, reviewMutations.length === 0, reviewMutations);
    check(`${scenario}: no grading steps or batch operations created`, db.active_step_count === 0 && db.operation_count === 0);
    check(`${scenario}: source ink unchanged`, sourceHash === sha(JSON.stringify(finalSource.strokes)));
    integrity[scenario] = { sourceSha256: sourceHash, finalSourceSha256: sha(JSON.stringify(finalSource.strokes)), sourceStrokeCount: sourceStrokes.length,
      serializedPhysicalStrokes: after[scenario].sourceSnapshot.strokes.length, rootCoveredStrokeCount: new Set(IR.getRootContentUnits(after[scenario].contentUnits).flatMap((u) => u.sourceStrokeIds)).size,
      reviewApiMutations: reviewMutations, databaseSteps: db.active_step_count, databaseOperations: db.operation_count, validated: true };
    scene.afterApproval = after[scenario].reviewStatus; scene.validation = "VALID"; scene.unrecognizedUnits = after[scenario].contentUnits.filter((u) => u.recognitionStatus === "UNRESOLVED").length;
    report.scenarios.push(scene);
    write("source_manifest.json", manifest); write("ir_before_review.json", before); write("ir_after_review.json", after);
    write("recognition_results.json", recognition); write("source_integrity.json", integrity); write("projection_preview.json", projections);
    await modal.getByRole("button", { name: "Đóng", exact: true }).click();
    await page.reload();
    check(`${scenario}: legacy reload still has zero submitted steps`, (await api(page, "GET", `/api/v2/math-solutions/attempts/${attempt.attempt_id}`)).steps.length === 0);
  }
  check("no uncaught browser errors", errors.length === 0, errors);
  if (process.argv.includes("--legacy-regression")) {
    console.log("Running existing legacy review and F5 recovery Playwright tests...");
    const fd = fs.openSync(path.join(out, "legacy-playwright.json"), "w");
    const code = await new Promise((resolve, reject) => {
      const proc = spawn(process.execPath, [path.join(root, "frontend/node_modules/@playwright/test/cli.js"), "test",
        "e2e/02-human-review.spec.ts", "e2e/04-recovery.spec.ts", "--grep", "B1, B2 & B3|D1 \\[", "--timeout", "180000", "--reporter=json"],
        { cwd: path.join(root, "frontend"), env: { ...env, PYTHON_EXE: python, E2E_BASE_URL: base, PW_HEADLESS: "1" },
          windowsHide: true, stdio: ["ignore", fd, fd] });
      children.push(proc); proc.on("error", reject); proc.on("exit", resolve);
    });
    fs.closeSync(fd);
    const legacy = JSON.parse(fs.readFileSync(path.join(out, "legacy-playwright.json"), "utf8"));
    report.legacyRegression = legacy.stats;
    check("existing legacy review and F5 batch recovery E2E", code === 0 && legacy.stats.expected === 2 && legacy.stats.unexpected === 0, legacy.stats);
  }
  report.allPassed = true;
}
function selectedAtomicId(ir) { return ir.contentUnits.find((u) => u.role === "ATOMIC").id; }
main().catch((err) => {
  report.allPassed = false;
  // Avoid dumping child process environments, stdout, credentials or cookies.
  report.failure = err.message; console.error(err.message); process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close();
  for (const child of children.reverse()) {
    if (process.platform === "win32" && child.pid) { try { execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" }); } catch {} }
    else child.kill();
  }
  write("browser_results.json", report);
  console.log(JSON.stringify({ allPassed: report.allPassed, checks: report.checks.length, scenarios: report.scenarios, failure: report.failure }, null, 2));
});
