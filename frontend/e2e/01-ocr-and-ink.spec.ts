import { test, expect } from "@playwright/test";
import path from "node:path";
import {
  attachTelemetry,
  createIsolatedAttempt,
  drawDistinctMathLines,
  drawNormalizedStroke,
  inspectAttemptInDb,
  loginAsIsolatedStudent,
  SCREENSHOT_DIR,
  validateQaHarnessEnv,
} from "./helpers";

test.describe("Phase 2A — MathCanvas, Ink Persistence & Handwritten OCR", () => {
  test("A1 & A3: Empty strokes guard, tiny/large/fraction/multi-line strokes, ink persistence to PostgreSQL, and ink immutability across OCR", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);

    // 0. Verify QA Harness Safety Invariants against the exact Playwright environment:
    // (a) Missing QA_E2E_PASSWORD causes a clear failure
    expect(() =>
      validateQaHarnessEnv({
        QA_E2E_IGNORE_ENV_FILE: "1",
        APP_ENV: "test",
        QA_E2E_DATABASE_NAME: "edums_qa_e2e",
        DATABASE_NAME: "edums_qa_e2e",
      }),
    ).toThrow(/QA_E2E_CONFIG_ERROR: QA_E2E_PASSWORD is required/);

    // (b) Ordinary development database ('edums') or mismatched database name blocks provisioning
    expect(() =>
      validateQaHarnessEnv({
        QA_E2E_IGNORE_ENV_FILE: "1",
        APP_ENV: "test",
        QA_E2E_PASSWORD: "ValidQaSecretPassword!2026",
        QA_E2E_DATABASE_NAME: "edums",
        DATABASE_NAME: "edums",
      }),
    ).toThrow(/QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME='edums' is not a dedicated QA database/);

    expect(() =>
      validateQaHarnessEnv({
        QA_E2E_IGNORE_ENV_FILE: "1",
        APP_ENV: "test",
        QA_E2E_PASSWORD: "ValidQaSecretPassword!2026",
        QA_E2E_DATABASE_NAME: "edums_qa_e2e",
        DATABASE_NAME: "edums",
      }),
    ).toThrow(/QA_E2E_SAFETY_ERROR: Backend DATABASE_NAME='edums' is not a dedicated QA database/);

    // (c) Production configuration (APP_ENV=production) is rejected
    expect(() =>
      validateQaHarnessEnv({
        QA_E2E_IGNORE_ENV_FILE: "1",
        APP_ENV: "production",
        QA_E2E_PASSWORD: "ValidQaSecretPassword!2026",
        QA_E2E_DATABASE_NAME: "edums_qa_e2e",
        DATABASE_NAME: "edums_qa_e2e",
      }),
    ).toThrow(/QA_E2E_SAFETY_ERROR: APP_ENV=production is strictly forbidden/);

    // (d) Correct QA configuration allows fixture provisioning in dedicated QA database
    const activeCfg = validateQaHarnessEnv(process.env);
    expect(activeCfg.qaDatabaseName).toBe("edums_qa_e2e");
    const fixture = createIsolatedAttempt("a1-ocr-ink");
    expect(fixture.database_name).toBe("edums_qa_e2e");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    // 1. Verify workspace loaded & empty strokes disable "Trích xuất trang"
    const heading = page.getByRole("heading", { name: "Không gian giải bài Toán" });
    await expect(heading).toBeVisible();

    const extractBtn = page.getByRole("button", { name: /Trích xuất trang/i });
    await expect(extractBtn).toBeDisabled();

    // 2. Draw a tiny dot stroke, a fraction (numerator, bar, denominator), and a second line equation
    // Tiny stroke at top-left
    await drawNormalizedStroke(page, [{ x: 0.18, y: 0.08 }]);
    // Line 1: fraction-like structure (numerator, horizontal bar, denominator)
    await drawNormalizedStroke(page, [
      { x: 0.25, y: 0.12 },
      { x: 0.30, y: 0.14 },
      { x: 0.35, y: 0.12 },
    ]);
    await drawNormalizedStroke(page, [
      { x: 0.22, y: 0.16 },
      { x: 0.42, y: 0.16 },
    ]);
    await drawNormalizedStroke(page, [
      { x: 0.26, y: 0.18 },
      { x: 0.32, y: 0.21 },
      { x: 0.37, y: 0.18 },
    ]);
    // Line 2: large horizontal derivative/equation strokes
    await drawNormalizedStroke(page, [
      { x: 0.20, y: 0.32 },
      { x: 0.28, y: 0.35 },
      { x: 0.38, y: 0.32 },
      { x: 0.48, y: 0.35 },
    ]);
    // Line 3: system of equations / conclusion strokes
    await drawNormalizedStroke(page, [
      { x: 0.20, y: 0.46 },
      { x: 0.30, y: 0.49 },
      { x: 0.45, y: 0.47 },
    ]);

    await expect(extractBtn).toBeEnabled();

    // 3. Trigger "Trích xuất trang" which flushes dirty ink to PostgreSQL before opening modal
    await extractBtn.click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "A1_mathcanvas_ocr_modal_open.png"),
      fullPage: true,
    });

    // 4. Verify PostgreSQL oracle: Ink is saved (stroke_count === 6), and ZERO solution steps were auto-created!
    const dbStateAfterOcr = inspectAttemptInDb(fixture.attempt_id);
    expect(dbStateAfterOcr.exists).toBe(true);
    expect(dbStateAfterOcr.active_step_count).toBe(0);
    expect(dbStateAfterOcr.attempt.attempt_revision_number).toBe(1);
    expect(dbStateAfterOcr.ink_document).not.toBeNull();
    expect(dbStateAfterOcr.ink_document?.pages.length).toBe(1);
    expect(dbStateAfterOcr.ink_document?.pages[0].stroke_count).toBe(6);
    const initialInkSha = dbStateAfterOcr.ink_document?.pages[0].sha256;
    expect(initialInkSha).toBeTruthy();

    // 5. Wait for real ONNX OCR or manual fallback to settle, then close modal and confirm original ink is intact
    const stopBtn = modal.getByRole("button", { name: /Dừng/i });
    if (await stopBtn.isVisible()) {
      // Let real OCR attempt recognition briefly or stop if still loading
      await page.waitForTimeout(2500);
    }
    await modal.getByRole("button", { name: "Đóng" }).click();
    await expect(modal).toBeHidden();

    const dbStateAfterClose = inspectAttemptInDb(fixture.attempt_id);
    expect(dbStateAfterClose.active_step_count).toBe(0);
    expect(dbStateAfterClose.ink_document?.pages[0].stroke_count).toBe(6);
    expect(dbStateAfterClose.ink_document?.pages[0].sha256).toBe(initialInkSha);

    telemetry.save("A1_A3_ocr_and_ink_persistence");
  });

  test("A2: Unrecognizable handwriting / OCR uncertainty falls back safely to manual review without silent ground-truth mutation", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("a2-ocr-unrecognized");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    // Draw 3 distinct lines of ambiguous scribble strokes
    await drawDistinctMathLines(page, 3);

    const extractBtn = page.getByRole("button", { name: /Trích xuất trang/i });
    await expect(extractBtn).toBeEnabled();
    await extractBtn.click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();

    // Wait until recognition finishes (header processing button disappears)
    await expect(modal.getByRole("button", { name: /· Dừng/i })).toBeHidden({
      timeout: 30_000,
    });

    // Verify notice that OCR is only a suggestion
    await expect(modal.getByText(/OCR chỉ là gợi ý cho công thức viết tay/i)).toBeVisible();

    // Verify 3 segmented regions in navigation list
    const regionNav = modal.getByRole("navigation", { name: /Các vùng nét viết trên trang/i });
    const regionButtons = regionNav.locator("button");
    await expect(regionButtons).toHaveCount(3);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "A2_ocr_uncertainty_and_segmentation.png"),
      fullPage: true,
    });

    // Verify PostgreSQL oracle: 0 steps saved, attempt still DRAFT rev 1
    const dbState = inspectAttemptInDb(fixture.attempt_id);
    expect(dbState.active_step_count).toBe(0);
    expect(dbState.attempt.status).toBe("DRAFT");
    expect(dbState.attempt.attempt_revision_number).toBe(1);

    telemetry.save("A2_ocr_uncertainty");
  });
});
