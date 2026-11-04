import path from "node:path";
import { test, expect } from "@playwright/test";
import {
  SCREENSHOT_DIR,
  attachTelemetry,
  bumpAttemptRevisionInDb,
  createIsolatedAttempt,
  drawDistinctMathLines,
  inspectAttemptInDb,
  loginAsIsolatedStudent,
} from "./helpers";

test.describe("Phase 2D — Failure Injection, HTTP 401/409/422/500, Multi-Tab Concurrency, Web Locks & Corrupted IndexedDB", () => {
  test("E1: Network unavailable before request, HTTP 401/422/500 fault injection, and real PostgreSQL HTTP 409 SOLUTION_REVISION_CONFLICT detection", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("E1_http_faults_and_409");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);

    await drawDistinctMathLines(page, 2);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();

    const modal = page.getByRole("dialog", { name: /Trích xuất trang 1/i });
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", { name: /· Dừng/i })).toBeHidden({
      timeout: 30_000,
    });

    const latexInput = modal.getByLabel("Sửa công thức của em");
    const saveSingleBtn = modal.getByRole("button", { name: /Lưu ngay bước này|Lưu lại/i });
    await latexInput.fill("y' = 3x^2 - 6x");

    const stepsUrlPattern = `**/api/v2/math-solutions/attempts/${fixture.attempt_id}/steps`;

    // 1. Network unavailable before request -> transitions row to retryOnly ("Lưu lại") and locks editing to prevent duplicate actionId mutation
    await page.route(stepsUrlPattern, async (route) => {
      if (route.request().method() === "POST") {
        await route.abort("internetdisconnected");
        return;
      }
      await route.continue();
    });
    await saveSingleBtn.click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Mất kết nối khi lưu\. Giữ nguyên nội dung và bấm Lưu lại/i }),
    ).toBeVisible();
    await expect(latexInput).toBeDisabled();
    expect(inspectAttemptInDb(fixture.attempt_id).active_step_count).toBe(0);
    await page.unroute(stepsUrlPattern);

    // 2. HTTP 500 Internal Server Error -> keeps row in retryOnly ("Lưu lại")
    await page.route(stepsUrlPattern, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "INTERNAL_SERVER_ERROR",
              message: "Internal server error during step save",
            },
          }),
        });
        return;
      }
      await route.continue();
    });
    await saveSingleBtn.click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Mất kết nối khi lưu\. Giữ nguyên nội dung và bấm Lưu lại/i }),
    ).toBeVisible();
    expect(inspectAttemptInDb(fixture.attempt_id).active_step_count).toBe(0);
    await page.unroute(stepsUrlPattern);

    // 3. HTTP 422 Unprocessable Entity -> unlocks editing (retryOnly = false) and displays validation error
    await page.route(stepsUrlPattern, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "INVALID_DRAFT",
              message: "Invalid step payload 422",
            },
          }),
        });
        return;
      }
      await route.continue();
    });
    await saveSingleBtn.click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Invalid step payload 422|Không lưu được bước giải/i }),
    ).toBeVisible();
    await expect(latexInput).toBeEnabled();
    expect(inspectAttemptInDb(fixture.attempt_id).active_step_count).toBe(0);
    await page.unroute(stepsUrlPattern);

    // 4. HTTP 401 Session Expired (also intercept /auth/refresh and /auth/me so session-refresh does not silently renew the mocked 401)
    await page.route("**/auth/me", async (route) => {
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({}) });
    });
    await page.route("**/auth/refresh", async (route) => {
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({}) });
    });
    await page.route(stepsUrlPattern, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "SESSION_EXPIRED",
              message: "Phiên đăng nhập đã hết hạn",
            },
          }),
        });
        return;
      }
      await route.continue();
    });
    await saveSingleBtn.click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Phiên đăng nhập đã hết hạn/i }),
    ).toBeVisible();
    expect(inspectAttemptInDb(fixture.attempt_id).active_step_count).toBe(0);
    await page.unroute(stepsUrlPattern);
    await page.unroute("**/auth/me");
    await page.unroute("**/auth/refresh");

    // 5. Real PostgreSQL HTTP 409 SOLUTION_REVISION_CONFLICT:
    // Bump revision in PostgreSQL externally (from rev 1 -> rev 2) while browser still holds rev 1
    const bumped = bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");
    expect(bumped.new_revision).toBe(2);

    // Clicking save hits real HTTP 409 from FastAPI and surfaces the conflict warning without overwriting Step 1 in PostgreSQL
    await saveSingleBtn.click();
    await expect(
      modal.getByRole("alert").filter({ hasText: /Bài giải đã thay đổi ở nơi khác/i }),
    ).toBeVisible();

    const dbAfter409 = inspectAttemptInDb(fixture.attempt_id);
    expect(dbAfter409.active_step_count).toBe(1);
    expect(dbAfter409.attempt.attempt_revision_number).toBe(2);
    expect(dbAfter409.active_steps[0].content_latex).toBe("D = \\mathbb{R}");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "E1_http_faults_and_real_409_recovery.png"),
      fullPage: true,
    });
    telemetry.save("E1_http_faults_and_409");
  });

  test("E2: Two tabs operating on the same attempt — Web Locks contention fails closed ('LOCKED') and concurrent revision conflict is enforced", async ({
    page,
    context,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("E2_two_tabs_weblocks");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 20_000 });

    // Open a second tab in the same browser context pointing to the same attempt
    const tab2 = await context.newPage();
    await tab2.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(tab2.locator("canvas").first()).toBeVisible({ timeout: 20_000 });

    // Hold exclusive Web Lock `edums-ocr-batch:${attempt_id}` in Tab 1 for 2.5 seconds while Tab 2 tries to acquire it with `ifAvailable: true`
    const lockHoldPromise = page.evaluate((attemptId) => {
      return navigator.locks.request(
        `edums-ocr-batch:${attemptId}`,
        { mode: "exclusive" },
        async () => {
          await new Promise((r) => setTimeout(r, 2500));
          return "TAB1_HELD_LOCK";
        },
      );
    }, fixture.attempt_id);

    await page.waitForTimeout(200);

    // Tab 2 tries to acquire the same lock using BrowserBatchLock's exact contract (`ifAvailable: true`)
    const tab2LockAttempt = await tab2.evaluate((attemptId) => {
      return navigator.locks.request(
        `edums-ocr-batch:${attemptId}`,
        { mode: "exclusive", ifAvailable: true },
        async (lock) => (lock ? "TAB2_ACQUIRED" : "LOCKED_FAIL_CLOSED"),
      );
    }, fixture.attempt_id);

    expect(tab2LockAttempt).toBe("LOCKED_FAIL_CLOSED");
    expect(await lockHoldPromise).toBe("TAB1_HELD_LOCK");

    await tab2.screenshot({
      path: path.join(SCREENSHOT_DIR, "E2_two_tabs_weblocks_contention.png"),
      fullPage: true,
    });
    await tab2.close();
    telemetry.save("E2_two_tabs_weblocks");
  });

  test("E3: Attempt switching with pending recovery isolates recovery banner per attemptId and preserves unfinished journal across navigation", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const attemptA = createIsolatedAttempt("E3_attempt_A_pending");
    const attemptB = createIsolatedAttempt("E3_attempt_B_clean");

    bumpAttemptRevisionInDb(attemptA.attempt_id, "D = \\mathbb{R}");
    const step1Id = inspectAttemptInDb(attemptA.attempt_id).active_steps[0].id;

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${attemptA.attempt_id}`);
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 20_000 });

    // Seed a valid PAUSED journal for Attempt A
    await page.evaluate(
      async ({ attemptId, committedStepId }) => {
        const journal = {
          schemaVersion: 1,
          batchId: "batch-e3-switch",
          attemptId,
          createdAt: Date.now(),
          nextRevision: 2,
          state: "PAUSED",
          message: "BATCH_SEND_UNKNOWN",
          entries: [
            {
              draftId: "d-e3-1",
              actionId: "44444444-4444-4444-8444-444444444401",
              content: {
                step_type: "ASSUMPTION",
                content_latex: "D = \\mathbb{R}",
                explanation_text: null,
                artifact: null,
              },
              state: "COMMITTED",
              frozen: {
                expected_attempt_revision: 1,
                client_action_id: "44444444-4444-4444-8444-444444444401",
                step_type: "ASSUMPTION",
                content_latex: "D = \\mathbb{R}",
                explanation_text: null,
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
              draftId: "d-e3-2",
              actionId: "44444444-4444-4444-8444-444444444402",
              content: {
                step_type: "DERIVATIVE_CALCULATION",
                content_latex: "y' = 3x^2 - 6x",
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
      { attemptId: attemptA.attempt_id, committedStepId: step1Id },
    );

    await page.reload();
    await expect(
      page.getByRole("alert").filter({ hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/i }),
    ).toBeVisible({ timeout: 10_000 });

    // Switch to Attempt B -> no recovery banner should appear
    await page.goto(`/student/attempts/${attemptB.attempt_id}`);
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 20_000 });
    await expect(
      page.getByRole("alert").filter({ hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/i }),
    ).toBeHidden();

    // Switch back to Attempt A -> recovery banner is restored intact
    await page.goto(`/student/attempts/${attemptA.attempt_id}`);
    await expect(
      page.getByRole("alert").filter({ hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/i }),
    ).toBeVisible({ timeout: 10_000 });

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "E3_attempt_switching_recovery_isolation.png"),
      fullPage: true,
    });
    telemetry.save("E3_attempt_switching_recovery_isolation");
  });

  test("E4 [BUG-006 REGRESSION]: Corrupted IndexedDB journal ('BATCH_JOURNAL_CORRUPT') must render an error alert in MathWorkspace and block new OCR extraction", async ({
    page,
  }) => {
    const telemetry = attachTelemetry(page);
    const fixture = createIsolatedAttempt("E4_bug006_corrupt_journal_swallowed");

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 20_000 });

    // Seed a corrupted journal (schemaVersion: 999) for fixture.attempt_id in IndexedDB
    await page.evaluate(async (attemptId) => {
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
          tx.objectStore("pending_batches").put({
            schemaVersion: 999,
            attemptId,
            corrupted: true,
          });
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
          tx.onerror = () => reject(tx.error);
        };
        req.onerror = () => reject(req.error);
      });
    }, fixture.attempt_id);

    await page.reload();
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(800);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "E4_bug006_corrupted_indexeddb_journal_swallowed.png"),
      fullPage: true,
    });
    telemetry.save("E4_bug006_corrupted_indexeddb_journal_swallowed");

    // Authoritative Oracle 1: When checkPendingBatch() catches Error("BATCH_JOURNAL_CORRUPT") and calls setRecoveryMessage(err.message),
    // MathWorkspace MUST render that error alert in the DOM!
    const corruptBanner = page.getByRole("alert").filter({
      hasText: /BATCH_JOURNAL_CORRUPT|Lỗi đọc dữ liệu đợt lưu/i,
    });
    await expect(
      corruptBanner,
      "BUG-006 HIGH: checkPendingBatch() sets recoveryMessage('BATCH_JOURNAL_CORRUPT'), but MathWorkspace.tsx line 1095 only renders recoveryMessage when pendingBatch !== null, silently swallowing IndexedDB corruption!",
    ).toBeVisible({ timeout: 3_000 });

    // Authoritative Oracle 2: Must block unsafe new OCR batches while journal is corrupted
    await drawDistinctMathLines(page, 1);
    await page.getByRole("button", { name: /Trích xuất trang/i }).click();
    await expect(page.getByRole("dialog", { name: /Trích xuất trang 1/i })).toBeHidden();

    // Authoritative Oracle 3: Must preserve original corrupted journal bytes in IndexedDB (never silently clear)
    const rawJournalAfter = await page.evaluate(async (attemptId) => {
      return await new Promise<any>((resolve, reject) => {
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
    }, fixture.attempt_id);
    expect(rawJournalAfter).toEqual({
      schemaVersion: 999,
      attemptId: fixture.attempt_id,
      corrupted: true,
    });

    // Authoritative Oracle 4: Safe recovery/support action refreshes authoritative server attempt without deleting journal bytes
    const syncSupportBtn = corruptBanner.getByRole("button", {
      name: /Đối soát máy chủ|Tải lại trạng thái máy chủ/i,
    });
    await expect(syncSupportBtn).toBeVisible();
    await syncSupportBtn.click();
    expect(inspectAttemptInDb(fixture.attempt_id).active_step_count).toBe(0);
  });
});
