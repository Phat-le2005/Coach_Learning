import path from "node:path";
import { test, expect } from "@playwright/test";
import {
  SCREENSHOT_DIR,
  attachTelemetry,
  bumpAttemptRevisionInDb,
  createIsolatedAttempt,
  inspectAttemptInDb,
  loginAsIsolatedStudent,
  drawDistinctMathLines,
} from "./helpers";

test.describe("Phase 2D — Recovery, F5 Reload & Idempotent Replay (Real Chrome + PostgreSQL)", () => {
  test("D1 [BUG-001 BLOCKER REGRESSION]: F5 reload surfaces pending batch recovery banner, blocks new OCR extraction, and 'Lưu tiếp (Resume)' must resume pending batch", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("D1_f5_recovery_banner_resume");

    // Pre-commit Step 1 in PostgreSQL so the journal's COMMITTED entry matches authoritative server state
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");
    const dbBefore = inspectAttemptInDb(fixture.attempt_id);
    expect(dbBefore.active_step_count).toBe(1);
    const step1Id = dbBefore.active_steps[0].id;

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    const canvas = page.locator("canvas").first();
    await expect(canvas).toBeVisible({ timeout: 20_000 });

    // Seed a valid PAUSED BatchJournal in IndexedDB (1 COMMITTED, 1 UNKNOWN, 1 QUEUED)
    await page.evaluate(
      async ({ attemptId, committedStepId }) => {
        const journal = {
          schemaVersion: 1,
          batchId: "batch-d1-recovery-test",
          attemptId,
          createdAt: Date.now(),
          nextRevision: 2,
          state: "PAUSED",
          message: "BATCH_SEND_UNKNOWN",
          entries: [
            {
              draftId: "draft-d1-1",
              actionId: "11111111-1111-4111-8111-111111111101",
              content: {
                step_type: "ASSUMPTION",
                content_latex: "D = \\mathbb{R}",
                explanation_text: "External concurrent step",
                artifact: null,
              },
              state: "COMMITTED",
              frozen: {
                expected_attempt_revision: 1,
                client_action_id: "11111111-1111-4111-8111-111111111101",
                step_type: "ASSUMPTION",
                content_latex: "D = \\mathbb{R}",
                explanation_text: "External concurrent step",
                artifact: null,
              },
              beforeStepIds: [],
              serverStepId: committedStepId,
              serverRevision: 2,
              error: null,
              errorCode: null,
              httpStatus: null,
            },
            {
              draftId: "draft-d1-2",
              actionId: "11111111-1111-4111-8111-111111111102",
              content: {
                step_type: "DERIVATIVE_CALCULATION",
                content_latex: "y' = 3x^2 - 6x",
                explanation_text: null,
                artifact: null,
              },
              state: "UNKNOWN",
              frozen: {
                expected_attempt_revision: 2,
                client_action_id: "11111111-1111-4111-8111-111111111102",
                step_type: "DERIVATIVE_CALCULATION",
                content_latex: "y' = 3x^2 - 6x",
                explanation_text: null,
                artifact: null,
              },
              beforeStepIds: [committedStepId],
              serverStepId: null,
              serverRevision: null,
              error: "Network timeout",
              errorCode: "UNKNOWN",
              httpStatus: null,
            },
            {
              draftId: "draft-d1-3",
              actionId: "11111111-1111-4111-8111-111111111103",
              content: {
                step_type: "CONCLUSION",
                content_latex: "y' = 0 \\iff x = 0 \\lor x = 2",
                explanation_text: null,
                artifact: null,
              },
              state: "QUEUED",
              frozen: null,
              beforeStepIds: null,
              serverStepId: null,
              serverRevision: null,
              error: null,
              errorCode: null,
              httpStatus: null,
            },
          ],
        };

        await new Promise<void>((resolve, reject) => {
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
            tx.objectStore("pending_batches").put(journal);
            tx.oncomplete = () => {
              db.close();
              resolve();
            };
            tx.onerror = () => reject(tx.error);
          };
          req.onerror = () => reject(req.error);
        });
      },
      { attemptId: fixture.attempt_id, committedStepId: step1Id },
    );

    // Simulate F5 browser refresh
    await page.reload();
    await expect(canvas).toBeVisible({ timeout: 20_000 });

    // Oracle 1: Recovery banner must appear with 1/3 committed steps
    const recoveryBanner = page.getByRole("alert").filter({
      hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/,
    });
    await expect(recoveryBanner).toBeVisible({ timeout: 10_000 });
    await expect(recoveryBanner).toContainText("1/3 bước đã được xác nhận trên máy chủ");

    // Oracle 2: Attempt to extract page while pendingBatch is active must be blocked
    await drawDistinctMathLines(page, 1);
    const extractBtn = page.getByRole("button", { name: /Trích xuất trang/i });
    await extractBtn.click();
    await expect(
      page.getByText(/Đợt lưu trước chưa hoàn tất/i),
    ).toBeVisible();

    // Oracle 3: Click 'Lưu tiếp (Resume)' in the recovery banner
    const resumeBtn = recoveryBanner.getByRole("button", { name: /Lưu tiếp \(Resume\)/i });
    await expect(resumeBtn).toBeVisible();
    await resumeBtn.click();

    await expect(recoveryBanner).toBeHidden({ timeout: 15_000 });
    await expect(page.getByText("Các bước giải đã xác nhận (3 bước)")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("v4")).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "D1_bug001_f5_recovery_resume_verified.png"),
      fullPage: true,
    });
    telemetry.save("D1_f5_recovery_banner_resume");

    // Authoritative DB check: should have resumed and committed steps 2 and 3 (total 3 steps)
    const dbAfter = inspectAttemptInDb(fixture.attempt_id);
    expect(
      dbAfter.active_step_count,
      "BUG-001 BLOCKER: Clicking 'Lưu tiếp (Resume)' in the F5 recovery banner must resume and commit steps 2 & 3",
    ).toBe(3);
    expect(dbAfter.attempt.attempt_revision_number).toBe(4);
  });

  test("D2 [BUG-001 & BUG-003 REGRESSION]: 'Hủy đợt lưu' button in recovery banner for HTTP 422 rejected batch must abandon batch and reconcile committed steps into React attempt state", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("D2_f5_recovery_abandon_rejected");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    const canvas = page.locator("canvas").first();
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    // Initially React attempt state has 0 steps (v1)
    await expect(page.getByText("v1")).toBeVisible();

    // Commit Step 1 externally in PostgreSQL (so server is at v2 with 1 step, while React state is still v1 with 0 steps)
    bumpAttemptRevisionInDb(fixture.attempt_id, "y' = 3x^2 - 6x");
    const dbBefore = inspectAttemptInDb(fixture.attempt_id);
    const step1Id = dbBefore.active_steps[0].id;

    // Seed a PAUSED BatchJournal with 1 COMMITTED step and 1 REJECTED (HTTP 422) step
    await page.evaluate(
      async ({ attemptId, committedStepId }) => {
        const journal = {
          schemaVersion: 1,
          batchId: "batch-d2-abandon-test",
          attemptId,
          createdAt: Date.now(),
          nextRevision: 2,
          state: "PAUSED",
          message: "BATCH_SEND_INVALID_DRAFT",
          entries: [
            {
              draftId: "draft-d2-1",
              actionId: "22222222-2222-4222-8222-222222222201",
              content: {
                step_type: "ASSUMPTION",
                content_latex: "y' = 3x^2 - 6x",
                explanation_text: "External concurrent step",
                artifact: null,
              },
              state: "COMMITTED",
              frozen: {
                expected_attempt_revision: 1,
                client_action_id: "22222222-2222-4222-8222-222222222201",
                step_type: "ASSUMPTION",
                content_latex: "y' = 3x^2 - 6x",
                explanation_text: "External concurrent step",
                artifact: null,
              },
              beforeStepIds: [],
              serverStepId: committedStepId,
              serverRevision: 2,
              error: null,
              errorCode: null,
              httpStatus: null,
            },
            {
              draftId: "draft-d2-2",
              actionId: "22222222-2222-4222-8222-222222222202",
              content: {
                step_type: "DERIVATIVE_CALCULATION",
                content_latex: "\\invalid_step_422",
                explanation_text: null,
                artifact: null,
              },
              state: "REJECTED",
              frozen: {
                expected_attempt_revision: 2,
                client_action_id: "22222222-2222-4222-8222-222222222202",
                step_type: "DERIVATIVE_CALCULATION",
                content_latex: "\\invalid_step_422",
                explanation_text: null,
                artifact: null,
              },
              beforeStepIds: [committedStepId],
              serverStepId: null,
              serverRevision: null,
              error: "HTTP 422 Unprocessable Entity",
              errorCode: "INVALID_DRAFT",
              httpStatus: 422,
            },
          ],
        };

        await new Promise<void>((resolve, reject) => {
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
            tx.objectStore("pending_batches").put(journal);
            tx.oncomplete = () => {
              db.close();
              resolve();
            };
            tx.onerror = () => reject(tx.error);
          };
          req.onerror = () => reject(req.error);
        });
      },
      { attemptId: fixture.attempt_id, committedStepId: step1Id },
    );

    // Trigger checkPendingBatch without full SSR reload by opening and closing the OCR modal,
    // or intercepting initial SSR so React attempt state remains at v1 until abandon reconciles it
    await drawDistinctMathLines(page, 1);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();
    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Đóng" }).click();
    await expect(modal).toBeHidden();

    const recoveryBanner = page.getByRole("alert").filter({
      hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/,
    });
    await expect(recoveryBanner).toBeVisible({ timeout: 10_000 });
    await expect(recoveryBanner).toContainText("1/2 bước đã được xác nhận trên máy chủ");

    const abandonBtn = recoveryBanner.getByRole("button", { name: /Hủy đợt lưu/i });
    await expect(abandonBtn).toBeVisible();

    let confirmDialogShown = false;
    page.on("dialog", async (dialog) => {
      confirmDialogShown = true;
      await dialog.accept();
    });

    await abandonBtn.click();
    await page.waitForTimeout(800);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "D2_bug001_f5_recovery_abandon_blocked.png"),
      fullPage: true,
    });
    telemetry.save("D2_f5_recovery_abandon_rejected");

    // Oracle 1 (BUG-001): Confirmation dialog must be shown and batch abandoned
    expect(
      confirmDialogShown,
      "BUG-001 BLOCKER: handleAbandonPendingBatch in MathWorkspace.tsx line 324 returned early on `if (!attemptId || !accessToken || !apiClient)` before even showing window.confirm!",
    ).toBe(true);
    await expect(recoveryBanner).toBeHidden({ timeout: 5_000 });

    // Oracle 2 (BUG-003): After abandoning the rejected step 2, MathWorkspace must fetch the authoritative SolutionAttempt
    // and update React state so Step 1 ("y' = 3x^2 - 6x") and revision "v2" are visible in ProblemPane without a manual F5 reload!
    await expect(page.getByText("Các bước giải đã xác nhận (1 bước)")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("v2")).toBeVisible();

    // Oracle 3: PostgreSQL still preserves Step 1 intact at revision 2
    const dbAfter = inspectAttemptInDb(fixture.attempt_id);
    expect(dbAfter.active_step_count).toBe(1);
    expect(dbAfter.attempt.attempt_revision_number).toBe(2);
  });

  test("D4 [BUG-005 REGRESSION]: Modal close button is disabled while batch mutation is SENDING, enabled when PAUSED, does not claim committed steps will be lost, and surfaces recovery banner on close", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("D4_bug005_modal_close_behavior");

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
    const approveBtn = modal.getByRole("button", { name: /Duyệt bước này \(Approve\)/i });

    await regionNav.locator("button").nth(0).click();
    await latexInput.fill("TXĐ: D = \\mathbb{R}");
    await approveBtn.click();

    await regionNav.locator("button").nth(1).click();
    await latexInput.fill("y' = 3x^2 - 6x");
    await approveBtn.click();

    // Intercept POST /steps: delay 1st request by 800ms so we can assert Close button is disabled during SENDING,
    // let 1st request succeed in real PostgreSQL, and fail 2nd request with HTTP 500 so batch enters PAUSED state!
    let postCall = 0;
    await page.route(`**/api/v2/math-solutions/attempts/${fixture.attempt_id}/steps`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      postCall++;
      if (postCall === 1) {
        await new Promise((r) => setTimeout(r, 800));
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "INTERNAL_SERVER_ERROR", message: "Simulated 500 on step 2" },
        }),
      });
    });

    const closeBtn = modal.getByRole("button", { name: "Đóng" });
    const batchSaveBtn = modal.getByRole("button", { name: /Lưu tất cả bước đã duyệt \(2\)/i });
    await batchSaveBtn.click();

    // Oracle 1 (BUG-005 & BUG-001): While batchSaving (SENDING) is actively running, the Close ("Đóng") button MUST be disabled!
    await expect(
      closeBtn,
      "BUG-005 & BUG-001: Close ('Đóng') button must be disabled while batchSaving is actively running (PageOcrReviewModal.tsx line 514 only had disabled={saving} instead of disabled={saving || batchSaving})",
    ).toBeDisabled({ timeout: 3_000 });

    // Wait for batch to transition to PAUSED after Step 2 fails with 500
    await expect(
      modal.getByRole("alert").filter({ hasText: /Đợt lưu đang tạm dừng/i }),
    ).toBeVisible({ timeout: 10_000 });

    // Oracle 2 (BUG-005): Once PAUSED (not actively SENDING), Close button is enabled so student can follow "hoặc đóng modal để phục hồi an toàn"
    await expect(closeBtn).toBeEnabled();

    // Oracle 3 (BUG-005): Clicking Close when pausedJournal is active must NOT claim that committed/paused batch steps will be lost!
    const dialogMessages: string[] = [];
    page.on("dialog", async (dialog) => {
      dialogMessages.push(dialog.message());
      await dialog.accept();
    });

    await closeBtn.click();
    await expect(modal).toBeHidden();
    expect(
      dialogMessages.some((msg) => msg.includes("Các bước chưa lưu sẽ mất phần chỉnh sửa")),
      "BUG-005: Closing a paused batch modal should not falsely warn that paused/committed batch steps will be lost",
    ).toBe(false);

    // Oracle 4 (BUG-005): Recovery banner is immediately accessible in MathWorkspace after closing the modal
    const recoveryBanner = page.getByRole("alert").filter({
      hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/,
    });
    await expect(recoveryBanner).toBeVisible({ timeout: 5_000 });
    await expect(recoveryBanner).toContainText("1/2 bước đã được xác nhận trên máy chủ");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "D4_bug005_modal_close_paused_recovery.png"),
      fullPage: true,
    });
    telemetry.save("D4_bug005_modal_close_behavior");
  });

  test("D3: Lost HTTP response after server commit + F5 browser reload recovers idempotently via frozen client_action_id without duplicate steps in PostgreSQL", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("D3_lost_response_f5_idempotent_replay");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    const canvas = page.locator("canvas").first();
    await expect(canvas).toBeVisible({ timeout: 20_000 });

    // Intercept the 2nd POST to /steps: let it reach the real backend and commit in PostgreSQL,
    // then abort the response back to the browser to simulate a lost response / network drop mid-commit!
    let stepPostCount = 0;
    await page.route(`**/api/v2/math-solutions/attempts/${fixture.attempt_id}/steps`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      stepPostCount++;
      if (stepPostCount === 2) {
        // Fetch from the real BFF/FastAPI server so Step 2 REALLY commits in PostgreSQL
        await route.fetch();
        // Now drop the response to the browser!
        await route.abort("failed");
        return;
      }
      await route.continue();
    });

    // Execute initial 3-step batch in real Chrome (IndexedDB + Web Locks + Next.js BFF + PostgreSQL)
    const firstRun = await page.evaluate(async (attemptId) => {
      const csrfRes = await fetch("/auth/csrf", { credentials: "same-origin" });
      const { csrf_token: csrfToken } = (await csrfRes.json()) as { csrf_token: string };

      const saveJournal = (journal: Record<string, unknown>) =>
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
            tx.objectStore("pending_batches").put(journal);
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

      const entries = [
        {
          draftId: "d3-1",
          actionId: "33333333-3333-4333-8333-333333333301",
          content: {
            step_type: "ASSUMPTION",
            content_latex: "D = \\mathbb{R}",
            explanation_text: "Tập xác định",
            artifact: null,
          },
          state: "QUEUED",
          frozen: null as Record<string, unknown> | null,
          beforeStepIds: null as string[] | null,
          serverStepId: null as string | null,
          serverRevision: null as number | null,
          error: null as string | null,
          errorCode: null as string | null,
          httpStatus: null as number | null,
        },
        {
          draftId: "d3-2",
          actionId: "33333333-3333-4333-8333-333333333302",
          content: {
            step_type: "DERIVATIVE_CALCULATION",
            content_latex: "y' = 3x^2 - 6x",
            explanation_text: "Đạo hàm",
            artifact: null,
          },
          state: "QUEUED",
          frozen: null as Record<string, unknown> | null,
          beforeStepIds: null as string[] | null,
          serverStepId: null as string | null,
          serverRevision: null as number | null,
          error: null as string | null,
          errorCode: null as string | null,
          httpStatus: null as number | null,
        },
        {
          draftId: "d3-3",
          actionId: "33333333-3333-4333-8333-333333333303",
          content: {
            step_type: "CONCLUSION",
            content_latex: "y' = 0 \\iff x = 0 \\lor x = 2",
            explanation_text: "Nghiệm đạo hàm",
            artifact: null,
          },
          state: "QUEUED",
          frozen: null as Record<string, unknown> | null,
          beforeStepIds: null as string[] | null,
          serverStepId: null as string | null,
          serverRevision: null as number | null,
          error: null as string | null,
          errorCode: null as string | null,
          httpStatus: null as number | null,
        },
      ];

      let rev = 1;
      let beforeIds: string[] = [];

      for (const entry of entries) {
        entry.frozen = {
          expected_attempt_revision: rev,
          client_action_id: entry.actionId,
          ...entry.content,
        };
        entry.beforeStepIds = [...beforeIds];
        entry.state = "SENDING";
        await saveJournal({
          schemaVersion: 1,
          batchId: "batch-d3-lost-response",
          attemptId,
          createdAt: Date.now(),
          nextRevision: rev,
          state: "PREPARED",
          message: null,
          entries,
        });

        try {
          const r = await fetch(`/api/v2/math-solutions/attempts/${attemptId}/steps`, {
            method: "POST",
            credentials: "same-origin",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
              "X-EduMS-BFF": "1",
              "X-CSRF-Token": csrfToken,
            },
            body: JSON.stringify(entry.frozen),
          });
          if (!r.ok) throw new Error(`HTTP_${r.status}`);
          const updated = await r.json();
          rev = updated.current_revision ?? updated.attempt_revision_number;
          const added = (updated.steps as Array<{ id: string }>).find((s) => !beforeIds.includes(s.id));
          entry.serverStepId = added?.id ?? null;
          entry.serverRevision = rev;
          entry.state = "COMMITTED";
          beforeIds = (updated.steps as Array<{ id: string }>).map((s) => s.id);
        } catch (err) {
          entry.state = "UNKNOWN";
          entry.error = String(err);
          entry.errorCode = "UNKNOWN";
          const pausedJournal = {
            schemaVersion: 1,
            batchId: "batch-d3-lost-response",
            attemptId,
            createdAt: Date.now(),
            nextRevision: rev,
            state: "PAUSED",
            message: "BATCH_SEND_UNKNOWN",
            entries,
          };
          await saveJournal(pausedJournal);
          return { status: "PAUSED", journal: pausedJournal };
        }
      }
      return { status: "COMPLETE" };
    }, fixture.attempt_id);

    // Oracle 1: First run paused on Step 2 because the HTTP response was lost
    expect(firstRun.status).toBe("PAUSED");
    expect(firstRun.journal?.entries[0].state).toBe("COMMITTED");
    expect(firstRun.journal?.entries[1].state).toBe("UNKNOWN");
    expect(firstRun.journal?.entries[1].frozen?.client_action_id).toBe("33333333-3333-4333-8333-333333333302");
    expect(firstRun.journal?.entries[1].frozen?.expected_attempt_revision).toBe(2);
    expect(firstRun.journal?.entries[2].state).toBe("QUEUED");

    // Oracle 2: PostgreSQL ALREADY committed Step 2 (2 active steps, revision 3) even though browser lost the response!
    const dbMid = inspectAttemptInDb(fixture.attempt_id);
    expect(dbMid.active_step_count).toBe(2);
    expect(dbMid.attempt.attempt_revision_number).toBe(3);
    expect(dbMid.operation_count).toBe(2);

    // Unroute fault injection and perform a real F5 browser reload
    await page.unroute(`**/api/v2/math-solutions/attempts/${fixture.attempt_id}/steps`);
    await page.reload();
    await expect(canvas).toBeVisible({ timeout: 20_000 });

    // Verify F5 recovery banner appears in UI reading from IndexedDB
    const d3Banner = page.getByRole("alert").filter({
      hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/,
    });
    await expect(d3Banner).toBeVisible({ timeout: 10_000 });
    await expect(d3Banner).toContainText("1/3 bước đã được xác nhận trên máy chủ");

    // Now replay the frozen journal in the reloaded browser context
    const resumedRun = await page.evaluate(async (attemptId) => {
      const csrfRes = await fetch("/auth/csrf", { credentials: "same-origin" });
      const { csrf_token: csrfToken } = (await csrfRes.json()) as { csrf_token: string };

      const journal = await new Promise<any>((resolve, reject) => {
        const req = indexedDB.open("edums_step_batch_journal_v1", 1);
        req.onsuccess = () => {
          const db = req.result;
          const tx = db.transaction("pending_batches", "readonly");
          const getReq = tx.objectStore("pending_batches").get(attemptId);
          getReq.onsuccess = () => {
            db.close();
            resolve(getReq.result);
          };
          getReq.onerror = () => reject(getReq.error);
        };
        req.onerror = () => reject(req.error);
      });

      const saveJournal = (j: Record<string, unknown>) =>
        new Promise<void>((resolve, reject) => {
          const req = indexedDB.open("edums_step_batch_journal_v1", 1);
          req.onsuccess = () => {
            const db = req.result;
            const tx = db.transaction("pending_batches", "readwrite");
            tx.objectStore("pending_batches").put(j);
            tx.oncomplete = () => {
              db.close();
              resolve();
            };
            tx.onerror = () => reject(tx.error);
          };
          req.onerror = () => reject(req.error);
        });

      let rev: number = journal.nextRevision;
      let beforeIds: string[] = [journal.entries[0].serverStepId];

      for (const entry of journal.entries) {
        if (entry.state === "COMMITTED") continue;
        if (!entry.frozen) {
          entry.frozen = {
            expected_attempt_revision: rev,
            client_action_id: entry.actionId,
            ...entry.content,
          };
          entry.beforeStepIds = [...beforeIds];
          entry.state = "SENDING";
          await saveJournal(journal);
        }
        // Replay exact frozen request (including frozen client_action_id and expected_attempt_revision)
        const r = await fetch(`/api/v2/math-solutions/attempts/${attemptId}/steps`, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-EduMS-BFF": "1",
            "X-CSRF-Token": csrfToken,
          },
          body: JSON.stringify(entry.frozen),
        });
        if (!r.ok) throw new Error(`Replay POST failed: ${r.status}`);
        const updated = await r.json();
        rev = updated.current_revision ?? updated.attempt_revision_number;
        const added = (updated.steps as Array<{ id: string }>).find(
          (s) => !(entry.beforeStepIds as string[]).includes(s.id),
        );
        entry.serverStepId = added?.id ?? null;
        entry.serverRevision = rev;
        entry.state = "COMMITTED";
        entry.error = null;
        entry.errorCode = null;
        journal.nextRevision = rev;
        beforeIds = (updated.steps as Array<{ id: string }>).map((s) => s.id);
        await saveJournal(journal);
      }

      journal.state = "COMPLETE";
      journal.message = null;
      await saveJournal(journal);
      return { status: "COMPLETE", finalRevision: rev };
    }, fixture.attempt_id);

    expect(resumedRun).toEqual({ status: "COMPLETE", finalRevision: 4 });

    // Reload and verify recovery banner is cleared and all 3 steps render in ProblemPane
    await page.reload();
    await expect(page.getByText("Các bước giải đã xác nhận (3 bước)")).toBeVisible();
    await expect(page.getByText("v4")).toBeVisible();
    await expect(page.getByText(/Phát hiện đợt lưu bước giải chưa hoàn tất/i)).toBeHidden();

    // Oracle 3: Verify PostgreSQL has exactly 3 steps (Step 2 was deduplicated via client_action_id + request_hash, Step 3 was added at revision 4)
    const dbFinal = inspectAttemptInDb(fixture.attempt_id);
    expect(dbFinal.active_step_count).toBe(3);
    expect(dbFinal.attempt.attempt_revision_number).toBe(4);
    expect(dbFinal.operation_count).toBe(3);
    expect(dbFinal.active_steps.map((s) => s.content_latex)).toEqual([
      "D = \\mathbb{R}",
      "y' = 3x^2 - 6x",
      "y' = 0 \\iff x = 0 \\lor x = 2",
    ]);
    expect(dbFinal.operations.map((op) => op.client_action_id)).toEqual([
      "33333333-3333-4333-8333-333333333301",
      "33333333-3333-4333-8333-333333333302",
      "33333333-3333-4333-8333-333333333303",
    ]);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "D3_lost_response_f5_idempotent_replay_verified.png"),
      fullPage: true,
    });
    telemetry.save("D3_lost_response_f5_idempotent_replay");
  });
});
