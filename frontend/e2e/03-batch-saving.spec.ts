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

test.describe("Phase 2C — Batch Persistence (1, 3, 5, 10 Steps), Double-Click Guard & PostgreSQL Oracles", () => {
  test("C1 [BUG-001 BLOCKER REGRESSION]: Clicking 'Lưu tất cả bước đã duyệt (3)' in PageOcrReviewModal must persist 3 approved steps to PostgreSQL instead of failing with 'Thiếu thông tin phiên làm bài'", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("c1-bug001-batch-ui");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    await drawDistinctMathLines(page, 3);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();

    const stopBtn = modal.getByRole("button", { name: /Dừng/i });
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
    }

    const regionNav = modal.getByRole("navigation", { name: /Các vùng nét viết trên trang/i });
    const latexInput = modal.getByLabel("Sửa công thức của em");
    const approveBtn = modal.getByRole("button", { name: /Duyệt bước này \(Approve\)/i });

    const stepsToApprove = ["TXĐ: D = \\mathbb{R}", "y' = 3x^2 - 6x", "3x^2 - 6x = 0"];
    for (let i = 0; i < 3; i++) {
      await regionNav.locator("button").nth(i).click();
      await latexInput.fill(stepsToApprove[i]);
      await approveBtn.click();
    }

    const batchSaveBtn = modal.getByRole("button", { name: /Lưu tất cả bước đã duyệt \(3\)/i });
    await expect(batchSaveBtn).toBeEnabled();
    await batchSaveBtn.click();

    await expect(modal.getByText(/Đã lưu thành công tất cả 3 bước/i)).toBeVisible({
      timeout: 15_000,
    });

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "C1_BUG001_batch_save_verified.png"),
      fullPage: true,
    });

    telemetry.save("C1_BUG001_batch_save_ui");

    // Authoritative PostgreSQL Oracle: 3 steps should be committed in PostgreSQL (revision 4)
    const dbState = inspectAttemptInDb(fixture.attempt_id);
    expect(dbState.active_step_count).toBe(3);
    expect(dbState.attempt.attempt_revision_number).toBe(4);
  });

  test("C2: Real UI step persistence (1, 3, 5 steps), rapid double-click idempotency, and PostgreSQL revision/order verification", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("c2-ui-5-steps");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    await drawDistinctMathLines(page, 5);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();

    const stopBtn = modal.getByRole("button", { name: /Dừng/i });
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
    }

    const regionNav = modal.getByRole("navigation", { name: /Các vùng nét viết trên trang/i });
    const latexInput = modal.getByLabel("Sửa công thức của em");
    const explanationInput = modal.getByLabel(/Lời giải thích/i);
    const saveSingleBtn = modal.getByRole("button", { name: /Lưu ngay bước này/i });

    const stepsData = [
      { latex: "TXĐ: D = \\mathbb{R}", expl: "Tập xác định", expectedKind: "ASSUMPTION" },
      { latex: "y' = 3x^2 - 6x", expl: "Tính đạo hàm", expectedKind: "DERIVATIVE_CALCULATION" },
      { latex: "3x^2 - 6x = 0", expl: "Tìm nghiệm đạo hàm", expectedKind: "ROOT_FINDING" },
      { latex: "x = 0 \\lor x = 2", expl: "Hai điểm cực trị", expectedKind: "ROOT_FINDING" },
      { latex: "y_{CĐ} = 2", expl: "Vậy hàm số đạt cực đại tại x=0", expectedKind: "CONCLUSION" },
    ];

    // Save Step 1 with rapid double-click to test double-submission protection
    await regionNav.locator("button").nth(0).click();
    await latexInput.fill(stepsData[0].latex);
    await explanationInput.fill(stepsData[0].expl);
    await saveSingleBtn.dblclick();
    await expect(regionNav.locator("button").nth(0)).toContainText("Đã lưu");

    // Verify 1 step in PostgreSQL (revision 2, zero duplicate mutation from dblclick)
    const dbAfter1 = inspectAttemptInDb(fixture.attempt_id);
    expect(dbAfter1.active_step_count).toBe(1);
    expect(dbAfter1.operation_count).toBe(1);
    expect(dbAfter1.attempt.attempt_revision_number).toBe(2);

    // Save Steps 2 and 3 -> verify 3 steps in PostgreSQL (revision 4)
    for (let i = 1; i < 3; i++) {
      await regionNav.locator("button").nth(i).click();
      await latexInput.fill(stepsData[i].latex);
      await explanationInput.fill(stepsData[i].expl);
      await saveSingleBtn.click();
      await expect(regionNav.locator("button").nth(i)).toContainText("Đã lưu");
    }
    const dbAfter3 = inspectAttemptInDb(fixture.attempt_id);
    expect(dbAfter3.active_step_count).toBe(3);
    expect(dbAfter3.operation_count).toBe(3);
    expect(dbAfter3.attempt.attempt_revision_number).toBe(4);

    // Save Steps 4 and 5 -> verify 5 steps in PostgreSQL (revision 6)
    for (let i = 3; i < 5; i++) {
      await regionNav.locator("button").nth(i).click();
      await latexInput.fill(stepsData[i].latex);
      await explanationInput.fill(stepsData[i].expl);
      await saveSingleBtn.click();
      await expect(regionNav.locator("button").nth(i)).toContainText("Đã lưu");
    }

    await modal.getByRole("button", { name: "Đóng" }).click();
    await expect(modal).toBeHidden();

    // Verify left ProblemPane shows all 5 confirmed steps in order and revision v6
    await expect(page.getByText("Các bước giải đã xác nhận (5 bước)")).toBeVisible();
    await expect(page.getByText("v6")).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "C2_five_steps_persisted_and_verified.png"),
      fullPage: true,
    });

    // Authoritative PostgreSQL Oracle for 5 steps
    const dbAfter5 = inspectAttemptInDb(fixture.attempt_id);
    expect(dbAfter5.active_step_count).toBe(5);
    expect(dbAfter5.operation_count).toBe(5);
    expect(dbAfter5.attempt.attempt_revision_number).toBe(6);
    expect(dbAfter5.attempt.status).toBe("IN_PROGRESS");
    for (let i = 0; i < 5; i++) {
      expect(dbAfter5.active_steps[i].step_index).toBe(i + 1);
      expect(dbAfter5.active_steps[i].content_latex).toBe(stepsData[i].latex);
      expect(dbAfter5.active_steps[i].explanation_text).toBe(stepsData[i].expl);
      expect(dbAfter5.active_steps[i].step_type).toBe(stepsData[i].expectedKind);
      expect(dbAfter5.operations[i].result_attempt_revision).toBe(i + 2);
    }

    telemetry.save("C2_ui_1_3_5_steps_persistence");
  });

  test("C3: Real Browser IndexedDB + Web Locks + Next.js BFF + PostgreSQL 10-step sequential batch persistence", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("c3-batch-10-steps");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();

    // Execute a 10-step sequential batch inside the real Chrome browser context against
    // the real Next.js BFF (/api/v2/math-solutions/attempts/...) + IndexedDB + Web Locks + PostgreSQL
    const batchResult = await page.evaluate(async (attemptId: string) => {
      const csrfRes = await fetch("/auth/csrf", { credentials: "same-origin" });
      const { csrf_token: csrfToken } = (await csrfRes.json()) as { csrf_token: string };

      const getAttempt = async () => {
        const r = await fetch(`/api/v2/math-solutions/attempts/${attemptId}`, {
          credentials: "same-origin",
          headers: { Accept: "application/json", "X-EduMS-BFF": "1" },
        });
        if (!r.ok) throw new Error(`GET failed: ${r.status}`);
        return r.json();
      };

      const addStep = async (body: Record<string, unknown>) => {
        const r = await fetch(`/api/v2/math-solutions/attempts/${attemptId}/steps`, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-EduMS-BFF": "1",
            "X-CSRF-Token": csrfToken,
          },
          body: JSON.stringify(body),
        });
        if (!r.ok) throw new Error(`POST failed: ${r.status}`);
        return r.json();
      };

      return navigator.locks.request(
        `edums-ocr-batch:${attemptId}`,
        { mode: "exclusive", ifAvailable: true },
        async (lock) => {
          if (!lock) return { status: "LOCKED" };
          const initial = await getAttempt();
          let rev: number = initial.current_revision ?? initial.attempt_revision_number ?? 1;
          const entries = Array.from({ length: 10 }, (_, idx) => ({
            draftId: crypto.randomUUID(),
            actionId: crypto.randomUUID(),
            content: {
              step_type: idx === 0 ? "ASSUMPTION" : idx === 9 ? "CONCLUSION" : "EXPLANATION",
              content_latex: `x_{${idx + 1}} = ${idx + 1}`,
              explanation_text: `Bước giải thứ ${idx + 1}`,
              artifact: null,
            },
            state: "QUEUED",
            frozen: null as Record<string, unknown> | null,
            beforeStepIds: null as string[] | null,
            serverStepId: null as string | null,
            serverRevision: null as number | null,
            error: null as string | null,
          }));

          const saveJournal = (state: string, nextRevision: number) =>
            new Promise<void>((resolve, reject) => {
              const req = indexedDB.open("edums_step_batch_journal_v1", 1);
              req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains("pending_batches")) {
                  db.createObjectStore("pending_batches", { keyPath: "attemptId" });
                }
              };
              req.onsuccess = () => {
                const db = req.result;
                const tx = db.transaction("pending_batches", "readwrite");
                tx.objectStore("pending_batches").put({
                  schemaVersion: 1,
                  batchId: "batch-10-e2e",
                  attemptId,
                  createdAt: Date.now(),
                  nextRevision,
                  state,
                  message: null,
                  entries,
                });
                tx.oncomplete = () => {
                  db.close();
                  resolve();
                };
                tx.onerror = () => {
                  db.close();
                  reject(tx.error);
                };
              };
              req.onerror = () => reject(req.error);
            });

          await saveJournal("PREPARED", rev);
          let beforeIds: string[] = (initial.steps ?? []).map((s: { id: string }) => s.id);

          for (const entry of entries) {
            entry.frozen = {
              expected_attempt_revision: rev,
              client_action_id: entry.actionId,
              ...entry.content,
            };
            entry.beforeStepIds = [...beforeIds];
            entry.state = "SENDING";
            await saveJournal("PREPARED", rev);

            const updated = await addStep(entry.frozen);
            rev = updated.current_revision ?? updated.attempt_revision_number;
            const added = (updated.steps as Array<{ id: string }>).find(
              (s) => !beforeIds.includes(s.id),
            );
            entry.serverStepId = added?.id ?? null;
            entry.serverRevision = rev;
            entry.state = "COMMITTED";
            beforeIds = (updated.steps as Array<{ id: string }>).map((s) => s.id);
            await saveJournal("PREPARED", rev);
          }

          await saveJournal("COMPLETE", rev);
          return { status: "COMPLETE", finalRevision: rev, committedCount: entries.length };
        },
      );
    }, fixture.attempt_id);

    expect(batchResult).toEqual({
      status: "COMPLETE",
      finalRevision: 11,
      committedCount: 10,
    });

    // Reload page to verify UI renders all 10 persisted steps from PostgreSQL and no pending recovery banner appears
    await page.reload();
    await expect(page.getByText("Các bước giải đã xác nhận (10 bước)")).toBeVisible();
    await expect(page.getByText("v11")).toBeVisible();
    await expect(page.getByText(/Phát hiện đợt lưu bước giải chưa hoàn tất/i)).toBeHidden();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "C3_ten_steps_batch_persisted_v11.png"),
      fullPage: true,
    });

    // Authoritative PostgreSQL Oracle for 10 steps
    const dbAfter10 = inspectAttemptInDb(fixture.attempt_id);
    expect(dbAfter10.active_step_count).toBe(10);
    expect(dbAfter10.operation_count).toBe(10);
    expect(dbAfter10.attempt.attempt_revision_number).toBe(11);
    for (let i = 0; i < 10; i++) {
      expect(dbAfter10.active_steps[i].step_index).toBe(i + 1);
      expect(dbAfter10.active_steps[i].content_latex).toBe(`x_{${i + 1}} = ${i + 1}`);
      expect(dbAfter10.operations[i].result_attempt_revision).toBe(i + 2);
    }

    telemetry.save("C3_batch_10_steps_postgres");
  });
});
