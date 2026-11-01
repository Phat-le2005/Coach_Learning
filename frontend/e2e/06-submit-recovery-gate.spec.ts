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
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onabort = () => { db.close(); reject(tx.error); };
      };
      req.onerror = () => reject(req.error);
    });
  }, { attemptId, journal });
}

function pausedJournal(attemptId: string) {
  return {
    schemaVersion: 1, batchId: "submit-gate-test", attemptId, createdAt: Date.now(),
    nextRevision: 2, state: "PAUSED", message: "BATCH_SEND_UNKNOWN",
    entries: [{
      draftId: "draft-submit-gate", actionId: "51b151b1-51b1-451b-851b-51b151b151b1",
      content: { step_type: "ROOT_FINDING", content_latex: "x=1", explanation_text: null, artifact: null },
      state: "QUEUED", frozen: null, beforeStepIds: null,
      serverStepId: null, serverRevision: null, error: null, errorCode: null, httpStatus: null,
    }],
  };
}

test.describe("Submission gate — actual MathWorkspace + PostgreSQL", () => {
  test("S1: F5 with PAUSED OCR batch disables Submit and preserves the unfinished attempt", async ({page}) => {
    const fixture = createIsolatedAttempt("s1_paused_ocr_batch_submit_gate");
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");
    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", {name: "Không gian giải bài Toán"})).toBeVisible();
    await writeJournal(page, fixture.attempt_id, pausedJournal(fixture.attempt_id));
    await page.reload();
    await expect(page.getByRole("alert").filter({hasText: /Phát hiện đợt lưu bước giải chưa hoàn tất/})).toBeVisible();
    const submitButtons = page.getByRole("button", {name: /Nộp & Chấm bài/i});
    await expect(submitButtons.first()).toBeDisabled();
    await page.screenshot({path: path.join(SCREENSHOT_DIR, "S1_submit_blocked_pending_ocr_batch.png"), fullPage: true});
    const db = inspectAttemptInDb(fixture.attempt_id);
    expect(db.active_step_count).toBe(1);
    expect(db.attempt.status).not.toBe("SUBMITTED");
    expect(db.attempt.attempt_revision_number).toBe(2);
  });

  test("S2: corrupted batch journal blocks Submit and does not mutate PostgreSQL", async ({page}) => {
    const fixture = createIsolatedAttempt("s2_corrupt_ocr_batch_submit_gate");
    bumpAttemptRevisionInDb(fixture.attempt_id, "D = \\mathbb{R}");
    await loginAsIsolatedStudent(page);
    await page.goto(`/student/attempts/${fixture.attempt_id}`);
    await expect(page.getByRole("heading", {name: "Không gian giải bài Toán"})).toBeVisible();
    await writeJournal(page, fixture.attempt_id, {schemaVersion: 999, state: "PAUSED", entries: []});
    await page.reload();
    await expect(page.getByText(/Lỗi đọc dữ liệu đợt lưu từ bộ nhớ trình duyệt/i)).toBeVisible();
    await expect(page.getByRole("button", {name: /Nộp & Chấm bài/i}).first()).toBeDisabled();
    await page.screenshot({path: path.join(SCREENSHOT_DIR, "S2_submit_blocked_corrupt_ocr_batch.png"), fullPage: true});
    const db = inspectAttemptInDb(fixture.attempt_id);
    expect(db.active_step_count).toBe(1);
    expect(db.attempt.status).not.toBe("SUBMITTED");
    expect(db.attempt.attempt_revision_number).toBe(2);
  });
});
