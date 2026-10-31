import { test, expect } from "@playwright/test";
import path from "node:path";
import {
  attachTelemetry,
  createIsolatedAttempt,
  drawDistinctMathLines,
  inspectAttemptInDb,
  loginAsIsolatedStudent,
  SCREENSHOT_DIR,
} from "./helpers";

test.describe("Phase 2B — Structured Human Review, Classifier, Approval Invalidation & Step Composition", () => {
  test("B1, B2 & B3: DETERMINED vs ABSTAIN classification, long inputs, special symbols, approval invalidation on edit, and sequence enforcement", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("b1-human-review");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    await drawDistinctMathLines(page, 3);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", { name: /· Dừng/i })).toBeHidden({
      timeout: 30_000,
    });

    const latexInput = modal.getByLabel("Sửa công thức của em");
    const stepKindSelect = modal.getByLabel("Loại bước giải");
    const explanationInput = modal.getByLabel(/Lời giải thích/i);
    const approveBtn = modal.getByRole("button", { name: /Duyệt bước này \(Approve\)/i });
    const batchSaveBtn = modal.getByRole("button", { name: /Lưu tất cả bước đã duyệt/i });

    // 1. Test ABSTAIN on ambiguous isolated expression "x = 2"
    await latexInput.fill("x = 2");
    await explanationInput.fill("");
    await expect(
      modal.getByText(/Bộ phân loại chưa đủ căn cứ xác định loại bước/i),
    ).toBeVisible();
    await expect(stepKindSelect).toHaveValue("");

    // Attempting to approve when StepKind is unresolved must fail with alert
    await approveBtn.click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Hãy chọn loại bước trước khi duyệt/i }),
    ).toBeVisible();

    // 2. Test very long input (> 4000 chars) -> ABSTAIN without regex hang
    const veryLongLatex = "x + ".repeat(1050) + "1 = 0";
    await latexInput.fill(veryLongLatex);
    await expect(stepKindSelect).toHaveValue("");

    // 3. Test DETERMINED classification: Derivative "y' = 3x^2 - 6x"
    await latexInput.fill("y' = 3x^2 - 6x");
    await expect(stepKindSelect).toHaveValue("DERIVATIVE_CALCULATION");
    await expect(
      modal.getByText(/Loại bước đang là gợi ý tự động/i),
    ).toBeVisible();

    // 4. Test virtual math keypad special symbols (π, √)
    await modal.getByRole("button", { name: "π" }).click();
    await expect(latexInput).toHaveValue(/π|\\pi/);
    await latexInput.fill("y' = 3x^2 - 6x");

    // 5. Approve Region 1 -> automatically advances selection to Region 2
    await approveBtn.click();
    await expect(batchSaveBtn).toContainText("Lưu tất cả bước đã duyệt (1)");

    // Switch back to Region 1 and verify "Hủy duyệt bước này" is shown
    const regionNav = modal.getByRole("navigation", { name: /Các vùng nét viết trên trang/i });
    await regionNav.locator("button").nth(0).click();
    await expect(modal.getByRole("button", { name: /Hủy duyệt bước này/i })).toBeVisible();

    // 6. Edit formula after approval -> MUST immediately invalidate approval!
    await latexInput.fill("y' = 3x^2 - 6x + 1");
    await expect(modal.getByRole("button", { name: /Duyệt bước này \(Approve\)/i })).toBeVisible();
    await expect(batchSaveBtn).toBeDisabled();
    await expect(batchSaveBtn).toContainText("Lưu tất cả bước đã duyệt (0)");

    // 7. Re-approve Region 1, then Edit explanation -> MUST also invalidate approval!
    await modal.getByRole("button", { name: /Duyệt bước này \(Approve\)/i }).click();
    await regionNav.locator("button").nth(0).click();
    await explanationInput.fill("Đạo hàm bậc nhất");
    await expect(batchSaveBtn).toBeDisabled();
    await expect(batchSaveBtn).toContainText("Lưu tất cả bước đã duyệt (0)");

    // 8. Sequence enforcement: Select Region 3 while Region 1 & 2 are unreviewed
    await regionNav.locator("button").nth(2).click();
    await expect(
      modal.getByText(/Duyệt các vùng phía trên trước để lưu đúng thứ tự bài giải/i),
    ).toBeVisible();
    await expect(modal.getByRole("button", { name: /Lưu ngay bước này/i })).toBeDisabled();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "B1_B3_structured_review_and_invalidation.png"),
      fullPage: true,
    });

    // Verify PostgreSQL still has 0 steps (human review is local until save)
    const dbState = inspectAttemptInDb(fixture.attempt_id);
    expect(dbState.active_step_count).toBe(0);

    telemetry.save("B1_B3_structured_review");
  });

  test("B4: Logical merge, split at cursor, reorder, skip, and invalid split guards", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("b4-merge-split-reorder");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    await drawDistinctMathLines(page, 3);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", { name: /· Dừng/i })).toBeHidden({
      timeout: 30_000,
    });

    const regionNav = modal.getByRole("navigation", { name: /Các vùng nét viết trên trang/i });
    const latexInput = modal.getByLabel("Sửa công thức của em");
    const explanationInput = modal.getByLabel(/Lời giải thích/i);
    const stepKindSelect = modal.getByLabel("Loại bước giải");

    // Set formulas on Regions 1, 2, 3
    await regionNav.locator("button").nth(0).click();
    await latexInput.fill("TXĐ: D = \\mathbb{R}");

    await regionNav.locator("button").nth(1).click();
    await latexInput.fill("y' = 3x^2 - 6x");

    await regionNav.locator("button").nth(2).click();
    await latexInput.fill("3x^2 - 6x = 0");

    // 1. Reorder: Move Region 2 ("y' = 3x^2 - 6x") down and back up
    await regionNav.locator("button").nth(1).click();
    await modal.getByRole("button", { name: "Đưa xuống" }).click();
    await expect(latexInput).toHaveValue("y' = 3x^2 - 6x");
    await modal.getByRole("button", { name: "Đưa lên" }).click();

    // 2. Logical Merge: Merge Region 1 and Region 2 -> count becomes 2, StepKind becomes unresolved
    await regionNav.locator("button").nth(0).click();
    await modal.getByRole("button", { name: "Gộp hai bước logic" }).click();
    await expect(regionNav.locator("button")).toHaveCount(2);
    await expect(latexInput).toHaveValue("TXĐ: D = \\mathbb{R}\ny' = 3x^2 - 6x");
    await expect(stepKindSelect).toHaveValue("");

    // 3. Invalid Split Guard A: Cannot split when explanation text is non-empty
    await explanationInput.fill("Có giải thích");
    await modal.getByRole("button", { name: "Tách thành hai bước tại con trỏ" }).click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Bước đang có lời giải thích/i }),
    ).toBeVisible();
    await explanationInput.fill("");

    // 4. Invalid Split Guard B: Cannot split when cursor is at position 0
    await latexInput.focus();
    await latexInput.evaluate((el: HTMLTextAreaElement) => el.setSelectionRange(0, 0));
    await modal.getByRole("button", { name: "Tách thành hai bước tại con trỏ" }).click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Hãy đặt con trỏ trong ô LaTeX tại ranh giới/i }),
    ).toBeVisible();

    // 5. Valid Logical Split at newline boundary -> restores 3 rows
    await latexInput.focus();
    await latexInput.evaluate((el: HTMLTextAreaElement) => {
      const idx = el.value.indexOf("\n");
      el.setSelectionRange(idx, idx);
    });
    await modal.getByRole("button", { name: "Tách thành hai bước tại con trỏ" }).click();
    await expect(regionNav.locator("button")).toHaveCount(3);

    // 6. Skip Region 2 ("Bỏ qua vùng")
    await regionNav.locator("button").nth(1).click();
    await modal.getByRole("button", { name: "Bỏ qua vùng" }).click();
    await expect(regionNav.locator("button").nth(1)).toContainText("Đã bỏ qua");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "B4_merge_split_reorder_skip.png"),
      fullPage: true,
    });

    telemetry.save("B4_merge_split_reorder_skip");
  });

  test("B5 [BUG-002 REGRESSION]: Clicking 'Gộp hai bước logic' on an APPROVED step must not crash the React application with unhandled OCR_DRAFT_ALREADY_APPROVED", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("b5-bug002-crash");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    await drawDistinctMathLines(page, 2);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", { name: /· Dừng/i })).toBeHidden({
      timeout: 30_000,
    });

    const regionNav = modal.getByRole("navigation", { name: /Các vùng nét viết trên trang/i });
    const latexInput = modal.getByLabel("Sửa công thức của em");

    // Fill Region 1 and Region 2, then approve Region 1
    await regionNav.locator("button").nth(0).click();
    await latexInput.fill("y' = 3x^2 - 6x");
    await modal.getByRole("button", { name: /Duyệt bước này \(Approve\)/i }).click();

    // Fill Region 2
    await regionNav.locator("button").nth(1).click();
    await latexInput.fill("3x^2 - 6x = 0");

    // Go back to approved Region 1 and click "Gộp hai bước logic"
    await regionNav.locator("button").nth(0).click();
    const mergeLogicalBtn = modal.getByRole("button", { name: "Gộp hai bước logic" });

    // If enabled, clicking it triggers unhandled OCR_DRAFT_ALREADY_APPROVED in PageOcrReviewModal.tsx:224
    if (await mergeLogicalBtn.isEnabled()) {
      await mergeLogicalBtn.click();
    }

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "B5_BUG002_crash_on_approved_logical_merge.png"),
      fullPage: true,
    });

    telemetry.save("B5_BUG002_crash_on_approved_merge");

    // Authoritative Oracle: Modal must remain open and page must NOT crash with OCR_DRAFT_ALREADY_APPROVED
    expect(telemetry.pageErrors).toEqual([]);
    await expect(modal).toBeVisible();
  });

  test("B6 [BUG-004 REGRESSION]: Geometric merge ('Gộp vùng nét') after initial OCR finishes must not leave the new row stuck in 'Chờ nhận diện' with logical buttons disabled", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("b6-bug004-geom-merge");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    await drawDistinctMathLines(page, 3);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", { name: /· Dừng/i })).toBeHidden({
      timeout: 30_000,
    });

    // Click geometric merge ("Gộp vùng nét") on Region 1
    await modal.getByRole("button", { name: "Gộp vùng nét" }).click();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "B6_BUG004_geometric_merge_stuck_pending.png"),
      fullPage: true,
    });

    telemetry.save("B6_BUG004_geometric_merge_pending");

    // Authoritative Oracle: After geometric merge when recognition is not running,
    // the row should be in manual/ready state so "Đưa xuống" (reorder) is enabled without requiring a dummy edit.
    const moveDownBtn = modal.getByRole("button", { name: "Đưa xuống" });
    await expect(moveDownBtn).toBeEnabled();
  });
});
