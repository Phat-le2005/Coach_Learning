#!/usr/bin/env node
/**
 * Real Next.js Browser E2E Test for MathCanvas OCR V2 Structural Shadow Panel.
 * (Implementation 04.6: Replaces previous mock HTML simulation with authentic Next.js E2E testing).
 *
 * Verifies on the REAL Next.js application:
 * 1. Mounting PageOcrReviewModal and PageOcrShadowQaPanel within MathWorkspace.
 * 2. Toggling "Xem đề xuất cấu trúc (QA)" button.
 * 3. Inspecting real algorithm provenance (strokes, regions, candidates).
 * 4. Candidate selection and preview rendering.
 * 5. Clean unmounting when closing panel.
 * 6. Review state immutability (0 steps approved/saved).
 * 7. Zero application API mutation requests.
 * 8. Zero uncaught browser errors.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const root = path.resolve(__dirname, "../..");
const { chromium } = require(path.join(root, "frontend", "node_modules", "playwright"));

const outputDir = path.join(root, ".tmp", "tri-ocr-qa-impl046");
const screenshotsDir = path.join(outputDir, "screenshots");
if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true });
}

const targetPort = process.env.NEXT_PORT || 3001;
const baseUrl = `http://localhost:${targetPort}`;


// Fail closed: use the existing QA database helper instead of demo credentials.
// QA secrets are loaded from a gitignored local env file, never committed.
function prepareQaAttempt() {
  const envPath = path.join(root, ".tmp", "tri-ocr-e2e", ".qa-e2e.env");
  if (fs.existsSync(envPath)) {
    for (const entry of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
      const i = entry.indexOf("=");
      if (i < 1 || entry.trimStart().startsWith("#")) continue;
      const key = entry.slice(0, i).trim();
      if (!process.env[key]) process.env[key] = entry.slice(i + 1).trim().replace(/^["\x27]|["\x27]$/g, "");
    }
  }
  if (process.env.APP_ENV !== "test" ||
      !process.env.QA_E2E_DATABASE_NAME ||
      process.env.DATABASE_NAME !== process.env.QA_E2E_DATABASE_NAME ||
      !/_qa(?:_|$)/i.test(process.env.QA_E2E_DATABASE_NAME) ||
      !process.env.QA_E2E_PASSWORD || process.env.QA_E2E_PASSWORD.length < 12) {
    throw new Error("QA_E2E_SAFETY_ERROR: isolated QA database and local QA password required");
  }
  const python = process.env.PYTHON_EXE ||
    path.join(root, "backend", ".venv", "Scripts", "python.exe");
  const helper = path.join(root, "frontend", "e2e", "qa_db_helper.py");
  const opts = { cwd: root, encoding: "utf8", env: process.env, stdio: ["ignore","pipe","pipe"] };
  // This helper verifies the actual connected PostgreSQL current_database().
  execFileSync(python, [helper, "verify-safety"], opts);
  const data = JSON.parse(execFileSync(python,
    [helper, "create-attempt", "--label", "shadow-qa-046"], opts).trim());
  if (!/^[a-f0-9-]{36}$/i.test(data.attempt_id || "")) {
    throw new Error("QA_E2E_SAFETY_ERROR: no isolated attempt created");
  }
  return {
    email: "qa.ocr.e2e.isolated@edums.edu.vn",
    password: process.env.QA_E2E_PASSWORD,
    attemptId: data.attempt_id,
  };
}
async function main() {
  console.log(`=== RUNNING REAL-APP BROWSER E2E TEST ON ${baseUrl} ===`);

  const qa = prepareQaAttempt();
  const browser = await chromium.launch({
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    headless: true,
  });

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const pageErrors = [];
  page.on("pageerror", (err) => {
    console.error("Browser Page Error:", err.message);
    pageErrors.push(err.message);
  });

  const mutationRequests = [];
  page.on("request", (req) => {
    const method = req.method().toUpperCase();
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      mutationRequests.push({ url: req.url(), method, timestamp: new Date().toISOString() });
    }
  });

  const testResults = {
    testName: "MathCanvas Real-App E2E Shadow QA",
    timestamp: new Date().toISOString(),
    baseUrl,
    chromeVersion: browser.version(),
    tests: [],
  };

  try {
    // 1. Log in to real Next.js application
    console.log(`1. Logging into Next.js app on ${baseUrl}/login ...`);
    await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
    await page.locator('input[type="email"], input[name="email"]').first().fill(qa.email);
    await page.locator('input[type="password"], input[name="password"]').first().fill(qa.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });
    console.log("   Authenticated successfully.");

    // 2. Open student attempt workspace
    console.log("2. Navigating to isolated QA attempt workspace ...");
    await page.goto(`${baseUrl}/student/attempts/${qa.attemptId}`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForTimeout(3000);

    const extractBtn = page.getByRole("button", { name: /Trích xuất trang/i });
    await extractBtn.waitFor({ state: "visible", timeout: 10000 });

    // The freshly provisioned isolated QA attempt starts empty. Draw two real
    // pointer strokes on the actual MathCanvas to enable extraction.
    // This synthetic browser input is NOT counted as real-handwriting evidence.
    const canvas = page.locator("canvas").first();
    await canvas.waitFor({ state: "visible", timeout: 15000 });
    const rect = await canvas.boundingBox();
    if (!rect) throw new Error("QA canvas bounding box unavailable");
    for (const relativeY of [0.18, 0.32]) {
      await page.mouse.move(rect.x + rect.width * 0.18, rect.y + rect.height * relativeY);
      await page.mouse.down();
      await page.mouse.move(rect.x + rect.width * 0.29,
        rect.y + rect.height * (relativeY + 0.01), { steps: 8 });
      await page.mouse.up();
    }

    // 3. Open Page OCR Review Modal
    console.log("3. Opening PageOcrReviewModal via 'Trích xuất trang' ...");
    await extractBtn.click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang/i });
    await modal.waitFor({ state: "visible", timeout: 15000 });
    const shadowQaStart = mutationRequests.length; // ink flush was part of opening modal

    await page.screenshot({ path: path.join(screenshotsDir, "real_app_01_modal_initial.png") });

    // 4. Verify QA Toggle Button in Development Mode
    const qaToggleBtn = modal.getByRole("button", { name: /Xem đề xuất cấu trúc \(QA\)/i });
    const isQaBtnVisible = await qaToggleBtn.isVisible();

    testResults.tests.push({
      name: "QA Toggle button 'Xem đề xuất cấu trúc (QA)' is visible in development mode",
      pass: isQaBtnVisible,
    });

    // 5. Click 'Xem đề xuất cấu trúc (QA)' to mount PageOcrShadowQaPanel
    console.log("4. Toggling Shadow QA panel open ...");
    await qaToggleBtn.click();

    const shadowPanel = modal.locator("#ocr-shadow-qa-panel");
    await shadowPanel.waitFor({ state: "visible", timeout: 8000 });

    const panelHeader = await shadowPanel.locator("h3").textContent();
    const panelText = await shadowPanel.textContent();

    await page.screenshot({ path: path.join(screenshotsDir, "real_app_02_shadow_panel_open.png") });

    testResults.tests.push({
      name: "PageOcrShadowQaPanel successfully mounted in DOM",
      pass: panelHeader.includes("Đối chiếu cấu trúc — chỉ QA"),
    });

    // 6. Check panel displays real algorithmic metrics
    const hasProvenance = panelText.includes("Nét bút:") && panelText.includes("Phân vùng ban đầu:");
    const hasDiagnostics = panelText.includes("Nét thiếu ở baseline:") && panelText.includes("Nét lặp ở baseline:");

    testResults.tests.push({
      name: "Shadow QA panel displays real algorithm provenance and diagnostic counts",
      pass: hasProvenance && hasDiagnostics,
    });

    // 7. Candidate selection and preview
    console.log("5. Testing candidate selection and preview ...");
    const candidateButtons = await shadowPanel.locator('div[role="group"] button').all();
    let candidateSelectionOk = false;
    if (candidateButtons.length > 0) {
      await candidateButtons[0].click();
      await page.waitForTimeout(500);

      const selectedSection = shadowPanel.locator('[data-testid="ocr-shadow-selected"]');
      const isVisible = await selectedSection.isVisible();
      const text = await selectedSection.textContent();

      await page.screenshot({ path: path.join(screenshotsDir, "real_app_03_candidate_selected.png") });

      candidateSelectionOk = isVisible && text.includes("Nhóm 1:");
    }

    testResults.tests.push({
      name: "Selecting structural candidate displays details and preview without crashing",
      pass: candidateSelectionOk,
    });

    // 8. Close panel
    console.log("6. Closing Shadow QA panel via 'Ẩn đối chiếu cấu trúc (QA)' ...");
    const hideBtn = modal.getByRole("button", { name: /Ẩn đối chiếu cấu trúc \(QA\)/i });
    await hideBtn.click();
    await shadowPanel.waitFor({ state: "detached", timeout: 5000 });

    await page.screenshot({ path: path.join(screenshotsDir, "real_app_04_shadow_panel_closed.png") });

    testResults.tests.push({
      name: "Toggling button unmounts Shadow QA panel cleanly from DOM",
      pass: (await modal.locator("#ocr-shadow-qa-panel").count()) === 0,
    });

    // 9. Reopen panel
    console.log("7. Reopening Shadow QA panel ...");
    await modal.getByRole("button", { name: /Xem đề xuất cấu trúc \(QA\)/i }).click();
    await modal.locator("#ocr-shadow-qa-panel").waitFor({ state: "visible", timeout: 5000 });

    testResults.tests.push({
      name: "Shadow QA panel can be reopened cleanly without state corruption",
      pass: (await modal.locator("#ocr-shadow-qa-panel").count()) === 1,
    });

    // 10. Verify review rows and steps immutability
    const reviewList = modal.locator('nav[aria-label="Các vùng nét viết trên trang"] button');
    const reviewRowsCount = await reviewList.count();
    const progressText = await modal.locator('div[role="status"]').textContent();

    testResults.tests.push({
      name: "Review rows and solution steps are unchanged by QA panel interactions",
      pass: reviewRowsCount > 0 && progressText.includes("0 bước đã duyệt"),
    });

    // 11. Verify zero application API mutations
    const shadowQaMutations = mutationRequests.slice(shadowQaStart).filter((m) => {
      const isApiMutation = m.url.includes("/api/") || m.url.includes("/math-solutions/") || m.url.includes("/steps");
      const isInkFlush = m.url.includes("/paper") || m.url.includes("/strokes");
      return isApiMutation && !isInkFlush;
    });

    testResults.tests.push({
      name: "Zero API mutation requests generated by Shadow QA interactions",
      pass: shadowQaMutations.length === 0,
      details: shadowQaMutations,
    });

    // 12. Uncaught errors check
    testResults.tests.push({
      name: "Zero uncaught browser errors during real-app execution",
      pass: pageErrors.length === 0,
    });

    // Close modal cleanly
    await modal.getByRole("button", { name: "Đóng" }).click();
    await modal.waitFor({ state: "hidden", timeout: 8000 });

    testResults.allPassed = testResults.tests.every((t) => t.pass);
  } finally {
    await browser.close();
  }

  // Save report
  const resultsPath = path.join(outputDir, "real_app_e2e_results.json");
  fs.writeFileSync(resultsPath, JSON.stringify(testResults, null, 2), "utf8");

  console.log("\n=== REAL-APP E2E QA TEST RESULTS ===");
  testResults.tests.forEach((t, idx) => {
    console.log(`  [Test ${idx + 1}] ${t.name}: ${t.pass ? "PASS" : "FAIL"}`);
  });
  console.log(`\nOVERALL STATUS: ${testResults.allPassed ? "ALL 8 TESTS PASSED (100%)" : "FAILED"}`);

  if (!testResults.allPassed) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("FATAL ERROR:", err);
  process.exit(1);
});
