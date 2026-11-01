import path from "node:path";
import { test, expect, type Page } from "@playwright/test";
import {
  SCREENSHOT_DIR,
  createIsolatedAttempt,
  bumpAttemptRevisionInDb,
  inspectAttemptInDb,
  loginAsIsolatedStudent,
} from "./helpers";

async function writeJournal(page: Page, attemptId: string, journal: unknown): Promise<void> {
  await page.evaluate(async ({ attemptId, journal }) => {
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
        tx.objectStore("pending_batches").put({ ...(journal as Record<string, unknown>), attemptId });
        tx.oncomplete = () => {
          db.close();
          resolve();
        };
        tx.onabort = () => {
          db.close();
          reject(tx.error);
        };
      };
      req.onerror = () => reject(req.error);
    });
  }, { attemptId, journal });
}

function makeJournal(
  attemptId: string,
  state: "PAUSED" | "COMPLETE" | "ABANDONED",
  entryState: "QUEUED" | "COMMITTED" | "REJECTED",
) {
  const actionId = "51b151b1-51b1-451b-851b-51b151b151b1";
  const content = {
    step_type: "ROOT_FINDING",
    content_latex: "x=1",
    explanation_text: null,
    artifact: null,
  };
  return {
    schemaVersion: 1,
    batchId: `submit-gate-${state.toLowerCase()}`,
    attemptId,
    createdAt: Date.now(),
    nextRevision: 2,
    state,
    message: state === "PAUSED" ? "BATCH_SEND_UNKNOWN" : null,
    entries: [
      {
        draftId: "draft-submit-gate",
        actionId,
        content,
        state: entryState,
        frozen:
          entryState === "COMMITTED"
            ? {
                expected_attempt_revision: 1,
                client_action_id: actionId,
                ...content,
              }
            : null,
        beforeStepIds: entryState === "COMMITTED" ? [] : null,
        serverStepId: entryState === "COMMITTED" ? "step-1" : null,
        serverRevision: entryState === "COMMITTED" ? 2 : null,
        error: entryState === "REJECTED" ? "Revision conflict" : null,
        errorCode: entryState === "REJECTED" ? "REVISION_CONFLICT" : null,
        httpStatus: entryState === "REJECTED" ? 409 : null,
      },
    ],
  };
}

test.describe("PR #29 Full QA Acceptance Matrix — Real Chrome + edums_qa_e2e PostgreSQL", () => {
  test("Case 1: PAUSED batch blocks Submit (both runtime click guard before reload and disabled state after F5) without mutating PostgreSQL", async ({ page }) => {
    const fixture = createIsolatedAttempt("pr29_c1_paused_batch");
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");

    const beforeDb = inspectAttemptInDb(fixture.attempt_id);
    expect(beforeDb.attempt.status).toBe("IN_PROGRESS");
    expect(beforeDb.attempt.attempt_revision_number).toBe(2);
    expect(beforeDb.active_step_count).toBe(1);
    expect(beforeDb.operation_count).toBe(1);

    let submitPostCount = 0;
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes(`/attempts/${fixture.attempt_id}/submit`)) {
        submitPostCount += 1;
      }
    });

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();
    await page.waitForTimeout(500);

    const headerSubmitBtn = page.getByRole("button", { name: /^Nộp & Chấm bài$/i });
    await expect(headerSubmitBtn).toBeEnabled();

    // Runtime click guard check (stale React state vs PAUSED journal in IndexedDB)
    await writeJournal(page, fixture.attempt_id, makeJournal(fixture.attempt_id, "PAUSED", "QUEUED"));
    await headerSubmitBtn.click();
    await expect(
      page.getByRole("alert").filter({ hasText: /Có đợt lưu OCR chưa hoàn tất|Phát hiện đợt lưu bước giải chưa hoàn tất/ }).first(),
    ).toBeVisible();
    expect(submitPostCount).toBe(0);

    const midDb = inspectAttemptInDb(fixture.attempt_id);
    expect(midDb.attempt.status).toBe("IN_PROGRESS");
    expect(midDb.attempt.attempt_revision_number).toBe(2);
    expect(midDb.operation_count).toBe(1);

    // Post-F5 reload check
    await page.reload();
    await expect(page.getByRole("alert").filter({ hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/ })).toBeVisible();
    const submitButtons = page.getByRole("button", { name: /Nộp & Chấm bài/i });
    await expect(submitButtons.nth(0)).toBeDisabled();
    await expect(submitButtons.nth(1)).toBeDisabled();
    expect(submitPostCount).toBe(0);

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "PR29_C1_paused_batch_blocked.png"), fullPage: true });

    const afterDb = inspectAttemptInDb(fixture.attempt_id);
    expect(afterDb.attempt.status).toBe("IN_PROGRESS");
    expect(afterDb.attempt.attempt_revision_number).toBe(2);
    expect(afterDb.active_step_count).toBe(1);
    expect(afterDb.operation_count).toBe(1);
  });

  test("Case 2: Corrupted IndexedDB journal blocks Submit (both runtime click guard and post-F5 disabled state) without mutating PostgreSQL", async ({ page }) => {
    const fixture = createIsolatedAttempt("pr29_c2_corrupt_journal");
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");

    const beforeDb = inspectAttemptInDb(fixture.attempt_id);
    expect(beforeDb.attempt.status).toBe("IN_PROGRESS");
    expect(beforeDb.attempt.attempt_revision_number).toBe(2);
    expect(beforeDb.active_step_count).toBe(1);
    expect(beforeDb.operation_count).toBe(1);

    let submitPostCount = 0;
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes(`/attempts/${fixture.attempt_id}/submit`)) {
        submitPostCount += 1;
      }
    });

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();
    await page.waitForTimeout(500);

    const headerSubmitBtn = page.getByRole("button", { name: /^Nộp & Chấm bài$/i });
    await expect(headerSubmitBtn).toBeEnabled();

    // Runtime click guard check when IndexedDB journal gets corrupted before reload
    await writeJournal(page, fixture.attempt_id, { schemaVersion: 999, state: "PAUSED", entries: [] });
    await headerSubmitBtn.click();
    await expect(
      page.getByRole("alert").filter({ hasText: /Không thể xác minh nhật ký lưu OCR|Phát hiện dữ liệu lịch sử lưu hàng loạt bị hỏng/ }).first(),
    ).toBeVisible();
    expect(submitPostCount).toBe(0);

    // Post-F5 reload check
    await page.reload();
    await expect(page.getByText(/Lỗi đọc dữ liệu đợt lưu từ bộ nhớ trình duyệt/i)).toBeVisible();
    const submitButtons = page.getByRole("button", { name: /Nộp & Chấm bài/i });
    await expect(submitButtons.nth(0)).toBeDisabled();
    await expect(submitButtons.nth(1)).toBeDisabled();
    expect(submitPostCount).toBe(0);

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "PR29_C2_corrupt_journal_blocked.png"), fullPage: true });

    const afterDb = inspectAttemptInDb(fixture.attempt_id);
    expect(afterDb.attempt.status).toBe("IN_PROGRESS");
    expect(afterDb.attempt.attempt_revision_number).toBe(2);
    expect(afterDb.active_step_count).toBe(1);
    expect(afterDb.operation_count).toBe(1);
  });

  test("Case 3: No journal in IndexedDB allows normal Submit and transitions PostgreSQL attempt to SUBMITTED", async ({ page }) => {
    const fixture = createIsolatedAttempt("pr29_c3_no_journal_submit");
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");

    const beforeDb = inspectAttemptInDb(fixture.attempt_id);
    expect(beforeDb.attempt.status).toBe("IN_PROGRESS");
    expect(beforeDb.attempt.attempt_revision_number).toBe(2);
    expect(beforeDb.active_step_count).toBe(1);
    expect(beforeDb.operation_count).toBe(1);

    let submitStatus: number | null = null;
    page.on("response", (res) => {
      if (res.request().method() === "POST" && res.url().includes(`/attempts/${fixture.attempt_id}/submit`)) {
        submitStatus = res.status();
      }
    });

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();

    const headerSubmitBtn = page.getByRole("button", { name: /^Nộp & Chấm bài$/i });
    await expect(headerSubmitBtn).toBeEnabled();
    await headerSubmitBtn.click();

    await expect.poll(() => submitStatus).toBe(200);
    await expect.poll(() => inspectAttemptInDb(fixture.attempt_id).attempt.status).toBe("SUBMITTED");

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "PR29_C3_no_journal_submitted.png"), fullPage: true });

    const afterDb = inspectAttemptInDb(fixture.attempt_id);
    expect(afterDb.attempt.status).toBe("SUBMITTED");
    expect(afterDb.attempt.attempt_revision_number).toBe(3);
    expect(afterDb.active_step_count).toBe(1);
    expect(afterDb.operation_count).toBe(2);
    expect(afterDb.operations.filter((op) => op.operation_type === "SUBMIT")).toHaveLength(1);
  });

  test("Case 4A & 4B: COMPLETE and ABANDONED batch journals do not falsely block Submit", async ({ page }) => {
    await loginAsIsolatedStudent(page);

    // 4A: COMPLETE journal
    const fixtureComplete = createIsolatedAttempt("pr29_c4a_complete_journal");
    bumpAttemptRevisionInDb(fixtureComplete.attempt_id, "D = \\mathbb{R}");
    const beforeCompleteDb = inspectAttemptInDb(fixtureComplete.attempt_id);
    expect(beforeCompleteDb.attempt.status).toBe("IN_PROGRESS");
    expect(beforeCompleteDb.attempt.attempt_revision_number).toBe(2);

    await page.goto(`/student/attempts/${fixtureComplete.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();
    await page.waitForTimeout(300);
    await writeJournal(page, fixtureComplete.attempt_id, makeJournal(fixtureComplete.attempt_id, "COMPLETE", "COMMITTED"));
    await page.reload();

    await expect(page.getByRole("alert").filter({ hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/ })).toHaveCount(0);
    await expect(page.getByText(/Lỗi đọc dữ liệu đợt lưu từ bộ nhớ trình duyệt/i)).toHaveCount(0);
    const submitBtnA = page.getByRole("button", { name: /^Nộp & Chấm bài$/i });
    await expect(submitBtnA).toBeEnabled();
    await submitBtnA.click();

    await expect.poll(() => inspectAttemptInDb(fixtureComplete.attempt_id).attempt.status).toBe("SUBMITTED");
    const afterCompleteDb = inspectAttemptInDb(fixtureComplete.attempt_id);
    expect(afterCompleteDb.attempt.status).toBe("SUBMITTED");
    expect(afterCompleteDb.attempt.attempt_revision_number).toBe(3);
    expect(afterCompleteDb.operation_count).toBe(2);
    expect(afterCompleteDb.operations.filter((op) => op.operation_type === "SUBMIT")).toHaveLength(1);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "PR29_C4A_complete_journal_submitted.png"), fullPage: true });

    // 4B: ABANDONED journal
    const fixtureAbandoned = createIsolatedAttempt("pr29_c4b_abandoned_journal");
    bumpAttemptRevisionInDb(fixtureAbandoned.attempt_id, "D = \\mathbb{R}");
    const beforeAbandonedDb = inspectAttemptInDb(fixtureAbandoned.attempt_id);
    expect(beforeAbandonedDb.attempt.status).toBe("IN_PROGRESS");
    expect(beforeAbandonedDb.attempt.attempt_revision_number).toBe(2);

    await page.goto(`/student/attempts/${fixtureAbandoned.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();
    await page.waitForTimeout(300);
    await writeJournal(page, fixtureAbandoned.attempt_id, makeJournal(fixtureAbandoned.attempt_id, "ABANDONED", "REJECTED"));
    await page.reload();

    await expect(page.getByRole("alert").filter({ hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/ })).toHaveCount(0);
    await expect(page.getByText(/Lỗi đọc dữ liệu đợt lưu từ bộ nhớ trình duyệt/i)).toHaveCount(0);
    const submitBtnB = page.getByRole("button", { name: /^Nộp & Chấm bài$/i });
    await expect(submitBtnB).toBeEnabled();
    await submitBtnB.click();

    await expect.poll(() => inspectAttemptInDb(fixtureAbandoned.attempt_id).attempt.status).toBe("SUBMITTED");
    const afterAbandonedDb = inspectAttemptInDb(fixtureAbandoned.attempt_id);
    expect(afterAbandonedDb.attempt.status).toBe("SUBMITTED");
    expect(afterAbandonedDb.attempt.attempt_revision_number).toBe(3);
    expect(afterAbandonedDb.operation_count).toBe(2);
    expect(afterAbandonedDb.operations.filter((op) => op.operation_type === "SUBMIT")).toHaveLength(1);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "PR29_C4B_abandoned_journal_submitted.png"), fullPage: true });
  });

  test("Case 5: Two concurrent tabs — holding Web Lock in Tab 1 blocks Submit in Tab 2 with 0 HTTP POST requests, and subsequent retry after lock release + 409 refresh succeeds cleanly", async ({ page, context }) => {
    const fixture = createIsolatedAttempt("pr29_c5_two_tabs_weblock");
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");

    const beforeDb = inspectAttemptInDb(fixture.attempt_id);
    expect(beforeDb.attempt.status).toBe("IN_PROGRESS");
    expect(beforeDb.attempt.attempt_revision_number).toBe(2);
    expect(beforeDb.active_step_count).toBe(1);
    expect(beforeDb.operation_count).toBe(1);

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();

    const page2 = await context.newPage();
    const submitPayloads: Array<{ expected_attempt_revision: number; client_action_id: string }> = [];
    const countSubmit = (req: { method(): string; url(): string; postDataJSON(): unknown }) => {
      if (req.method() === "POST" && req.url().includes(`/attempts/${fixture.attempt_id}/submit`)) {
        submitPayloads.push(req.postDataJSON() as { expected_attempt_revision: number; client_action_id: string });
      }
    };
    page.on("request", countSubmit);
    page2.on("request", countSubmit);

    await page2.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page2.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();

    const tab2SubmitBtn = page2.getByRole("button", { name: /^Nộp & Chấm bài$/i });
    await expect(tab2SubmitBtn).toBeEnabled();

    // Acquire and hold the exclusive Web Lock in Tab 1
    await page.evaluate(async (attemptId) => {
      await new Promise<void>((resolveAcquired) => {
        (window as unknown as { __releaseTestBatchLock?: () => void }).__releaseTestBatchLock = undefined;
        void navigator.locks.request(`edums-ocr-batch:${attemptId}`, { mode: "exclusive" }, () => {
          return new Promise<void>((resolveRelease) => {
            (window as unknown as { __releaseTestBatchLock?: () => void }).__releaseTestBatchLock = resolveRelease;
            resolveAcquired();
          });
        });
      });
    }, fixture.attempt_id);

    // Click Submit in Tab 2 while Tab 1 holds the lock -> blocked before network call
    await tab2SubmitBtn.click();
    await expect(page2.getByRole("alert").filter({ hasText: /Một tab khác đang xử lý bước giải/ })).toBeVisible();
    expect(submitPayloads).toHaveLength(0);

    await page2.screenshot({ path: path.join(SCREENSHOT_DIR, "PR29_C5_two_tabs_weblock_blocked.png"), fullPage: true });

    const lockedDb = inspectAttemptInDb(fixture.attempt_id);
    expect(lockedDb.attempt.status).toBe("IN_PROGRESS");
    expect(lockedDb.attempt.attempt_revision_number).toBe(2);
    expect(lockedDb.active_step_count).toBe(1);
    expect(lockedDb.operation_count).toBe(1);

    // Simulate Tab 1 committing a second step while holding the lock (revision 2 -> 3), then releasing the lock
    bumpAttemptRevisionInDb(fixture.attempt_id, "y' = 3x^2 - 6x");
    await page.evaluate(() => {
      (window as unknown as { __releaseTestBatchLock?: () => void }).__releaseTestBatchLock?.();
    });

    // Click Submit in Tab 2 after lock release: first click sees 409 (Tab 2 still had revision 2 in React state),
    // refreshes attempt to revision 3 and clears submitActionRef; next click submits with revision 3 and new actionId.
    const conflictRespPromise = page2.waitForResponse(
      (res) => res.request().method() === "POST" && res.url().includes(`/attempts/${fixture.attempt_id}/submit`),
    );
    await tab2SubmitBtn.click();
    const conflictResp = await conflictRespPromise;
    expect(conflictResp.status()).toBe(409);
    await expect(page2.getByText("v3", { exact: true })).toBeVisible();

    const successRespPromise = page2.waitForResponse(
      (res) => res.request().method() === "POST" && res.url().includes(`/attempts/${fixture.attempt_id}/submit`),
    );
    await tab2SubmitBtn.click();
    const successResp = await successRespPromise;
    expect(successResp.status()).toBe(200);

    await expect.poll(() => submitPayloads.length).toBe(2);
    expect(submitPayloads[0].expected_attempt_revision).toBe(2);
    expect(submitPayloads[1].expected_attempt_revision).toBe(3);
    expect(submitPayloads[1].client_action_id).not.toBe(submitPayloads[0].client_action_id);

    const finalDb = inspectAttemptInDb(fixture.attempt_id);
    expect(finalDb.attempt.status).toBe("SUBMITTED");
    expect(finalDb.attempt.attempt_revision_number).toBe(4);
    expect(finalDb.active_step_count).toBe(2);
    expect(finalDb.operation_count).toBe(3);
    expect(finalDb.operations.filter((op) => op.operation_type === "SUBMIT")).toHaveLength(1);

    await page2.close();
  });

  test("Case 6: Ambiguous network timeout on Submit preserves client_action_id for idempotent retry without duplicate PostgreSQL operations", async ({ page }) => {
    const fixture = createIsolatedAttempt("pr29_c6_timeout_idempotent_retry");
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");

    const beforeDb = inspectAttemptInDb(fixture.attempt_id);
    expect(beforeDb.attempt.status).toBe("IN_PROGRESS");
    expect(beforeDb.attempt.attempt_revision_number).toBe(2);
    expect(beforeDb.operation_count).toBe(1);

    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", { name: "Không gian giải bài Toán" })).toBeVisible();

    const submitPayloads: Array<{ expected_attempt_revision: number; client_action_id: string }> = [];
    let attemptCount = 0;
    await page.route(`**/api/v2/math-solutions/attempts/${fixture.attempt_id}/submit`, async (route) => {
      const req = route.request();
      if (req.method() === "POST") {
        attemptCount += 1;
        submitPayloads.push(req.postDataJSON() as { expected_attempt_revision: number; client_action_id: string });
        if (attemptCount === 1) {
          await route.abort("timedout");
          return;
        }
      }
      await route.continue();
    });

    const submitBtn = page.getByRole("button", { name: /^Nộp & Chấm bài$/i });
    await expect(submitBtn).toBeEnabled();

    // First click aborts with network timeout (unknown commit outcome)
    await submitBtn.click();
    await expect(page.getByRole("alert").filter({ hasText: /Không thể kết nối tới EduMS API/ })).toBeVisible();
    expect(submitPayloads).toHaveLength(1);

    // Second click must reuse the exact same client_action_id and expected_attempt_revision
    const retryRespPromise = page.waitForResponse(
      (res) => res.request().method() === "POST" && res.url().includes(`/attempts/${fixture.attempt_id}/submit`),
    );
    await submitBtn.click();
    const retryResp = await retryRespPromise;
    expect(retryResp.status()).toBe(200);

    expect(submitPayloads).toHaveLength(2);
    expect(submitPayloads[0].expected_attempt_revision).toBe(2);
    expect(submitPayloads[1].expected_attempt_revision).toBe(2);
    expect(submitPayloads[1].client_action_id).toBe(submitPayloads[0].client_action_id);

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "PR29_C6_timeout_idempotent_retry.png"), fullPage: true });

    const afterDb = inspectAttemptInDb(fixture.attempt_id);
    expect(afterDb.attempt.status).toBe("SUBMITTED");
    expect(afterDb.attempt.attempt_revision_number).toBe(3);
    expect(afterDb.active_step_count).toBe(1);
    expect(afterDb.operation_count).toBe(2);
    const submitOps = afterDb.operations.filter((op) => op.operation_type === "SUBMIT");
    expect(submitOps).toHaveLength(1);
    expect(submitOps[0].client_action_id).toBe(submitPayloads[0].client_action_id);
  });
});
