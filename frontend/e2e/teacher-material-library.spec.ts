import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { signSession } from "../src/lib/auth/session-codec";
import { AUTH_COOKIES } from "../src/lib/auth/constants";
import type { TeacherMaterial } from "../src/features/teacher/api";
import type { PdfReviewSubmit, TeacherPdfImport } from "../src/features/teacher/pdf-api";

const classId = "00000000-0000-4000-8000-000000000101";
const jobId = "00000000-0000-4000-8000-000000000102";
const originalId = "00000000-0000-4000-8000-000000000103";
const replacementId = "00000000-0000-4000-8000-000000000104";
test.skip(!process.env.PDF_REVIEW_E2E_SECRET, "Use the isolated PDF review configuration.");

function material(id = originalId, title = "Tài liệu gốc"): TeacherMaterial {
  return { id, title, original_file_name: "exercise.reviewed.json", mime_type: "application/json",
    file_size_bytes: 512, status: "READY", subject_id: classId, created_at: "2026-11-09T00:00:00Z" };
}

function draft(status: TeacherPdfImport["status"] = "FAILED"): TeacherPdfImport {
  return { id: jobId, classroom_id: classId, subject_id: classId, title: "Bài tập nguyên hàm",
    original_file_name: "btap_nguyen_ham.pdf", source_kind: "PDF", source_mime_type: "application/pdf",
    status, created_at: "2026-11-09T00:00:00Z", material_id: null,
    error: status === "FAILED" ? "OCR chưa hoàn tất. Phần đã xử lý được giữ để thử lại." : null,
    progress: { processed_pages: 1, selected_pages: 2 }, review: null,
    questions: [{ question_id: "q1", number: 1, source_number: 1, content: "Tính $1+1$.",
      answer: "2", explanation: "Cộng hai số.", difficulty_level: "NHAN_BIET", pages: [1],
      warnings: [], suggested: true, source_assets: [], visual_assets: [] }] };
}

interface State {
  job: TeacherPdfImport | null;
  materials: TeacherMaterial[];
  retryCalls: number;
  discardCalls: number;
  rejectDiscard: boolean;
  submitted: PdfReviewSubmit | null;
  errors: string[];
}

async function fixture(page: Page, context: BrowserContext, baseURL: string, state: State) {
  if (baseURL !== "http://127.0.0.1:3106") throw Error("Requires isolated PDF UI server");
  const session = await signSession({ v: 1, userId: "library-qa", email: "teacher@example.test",
    fullName: "Giáo viên kiểm thử", role: "TEACHER", expiresAt: Date.now() + 600_000 }, process.env.PDF_REVIEW_E2E_SECRET!);
  await context.addCookies([{ name: AUTH_COOKIES.session, value: session, url: baseURL, httpOnly: true, sameSite: "Lax" }]);
  page.on("pageerror", error => state.errors.push(error.message));
  await page.route("**/auth/csrf", route => route.fulfill({ json: { csrf_token: "library-test-token" } }));
  // Every teacher request is intercepted. This fixture cannot dispatch a real OCR job.
  await page.route("**/api/teacher/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.slice("/api/teacher/".length);
    let body: unknown;
    if (path === "classes") body = [{ id: classId, name: "12A1", academic_year: "2026-2027", grade_level: 12 }];
    else if (path === "subjects") body = [{ id: classId, code: "MATH", name: "Toán", grade_level: 12 }];
    else if (path === "materials") body = state.materials;
    else if (path === "materials/pdf-imports") body = state.job ? [state.job] : [];
    else if (path === `materials/pdf-imports/${jobId}` && request.method() === "DELETE") {
      state.discardCalls++;
      if (state.rejectDiscard) {
        state.rejectDiscard = false;
        await route.fulfill({ status: 503, json: { error: { code: "TEST_FAILURE", message: "Chưa xóa được bản nháp. Hãy thử lại." } } });
      } else { state.job = null; await route.fulfill({ status: 204, body: "" }); }
      return;
    } else if (path === `materials/pdf-imports/${jobId}`) body = state.job;
    else if (path === `materials/pdf-imports/${jobId}/retry`) {
      state.retryCalls++;
      state.job = { ...draft("NEEDS_REVIEW") };
      body = state.job;
    } else if (path === `materials/pdf-imports/${jobId}/submit`) {
      state.submitted = request.postDataJSON();
      const next = material(replacementId, state.submitted!.title);
      state.materials = [next, ...state.materials.filter(m => state.submitted!.save_mode !== "REPLACE" || m.id !== originalId)];
      state.job = null;
      body = next;
    } else if (path.endsWith("/analytics")) body = { student_count: 0, subject_progress: [], chapter_progress: [],
      weak_problem_types: [], students_needing_attention: [], assignment_completion: { assignment_count: 0,
        submitted_count: 0, graded_count: 0, completion_rate: 0 }, evidence_summary: { scored_events: 0, needs_teacher_review_count: 0 } };
    else if (path.endsWith("/students") || path.endsWith("/assignments") || path.endsWith("/items")) body = [];
    else { await route.fulfill({ status: 404, json: { error: { code: "UNMOCKED", message: path } } }); return; }
    await route.fulfill({ json: body });
  });
}

function state(): State {
  return { job: draft(), materials: [], retryCalls: 0, discardCalls: 0,
    rejectDiscard: false, submitted: null, errors: [] };
}

async function openList(page: Page) {
  await page.goto("/teacher?tab=materials");
  await page.getByRole("button", { name: "Danh sách", exact: true }).click();
}

test("FAILED draft can be discarded after confirmation and a recoverable error", async ({ page, context, baseURL }, info) => {
  const s = state(); s.rejectDiscard = true;
  await fixture(page, context, baseURL!, s);
  await openList(page);
  await expect(page.getByText(/Cần thử lại · btap_nguyen_ham.pdf/)).toBeVisible();
  await page.getByRole("button", { name: "Xem tiến độ", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chưa hoàn tất OCR" })).toBeVisible();
  expect(s.retryCalls).toBe(0);
  await expect(page.getByRole("button", { name: "Xóa bản nháp", exact: true })).toBeVisible({ timeout: 8_000 });
  await page.getByRole("button", { name: "Xóa bản nháp", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Xóa bản nháp này?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Giữ lại, quay về" }).click();
  expect(s.discardCalls).toBe(0);
  await page.getByRole("button", { name: "Xóa bản nháp", exact: true }).click();
  await dialog.getByRole("button", { name: "Xóa bản nháp", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Chưa xóa được");
  expect(s.job?.status).toBe("FAILED");
  await page.screenshot({ path: info.outputPath("failed-draft-delete.png") });
  await dialog.getByRole("button", { name: "Xóa bản nháp", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chưa có tài liệu nào trong lớp học này" })).toBeVisible();
  expect(s.discardCalls).toBe(2);
  expect(s.errors).toEqual([]);
});

test("FAILED retry opens simulated review without an automatic OCR request", async ({ page, context, baseURL }) => {
  const s = state();
  await fixture(page, context, baseURL!, s);
  await openList(page);
  await page.getByRole("button", { name: "Xem tiến độ", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chưa hoàn tất OCR" })).toBeVisible();
  expect(s.retryCalls).toBe(0);
  await page.getByRole("button", { name: "Thử lại OCR", exact: true }).click();
  await expect(page.getByRole("checkbox")).toBeVisible();
  expect(s.retryCalls).toBe(1);
  expect(s.errors).toEqual([]);
});

test("revision replacement waits for confirmation and removes the original card", async ({ page, context, baseURL }) => {
  const s = state(); s.materials = [material()]; s.job = draft("NEEDS_REVIEW");
  s.job.revision_of = originalId; s.job.revision_title = "Tài liệu gốc";
  s.job.review = { title: s.job.title, decisions: [{ question_id: "q1", accepted: true, source_checked: true,
    content: "Đề đã sửa", answer: "2", explanation: "Đã đối chiếu", difficulty_level: "NHAN_BIET" }] };
  await fixture(page, context, baseURL!, s);
  await page.goto(`/teacher?tab=materials&pdfImport=${jobId}`);
  await page.getByRole("radio", { name: /Lưu đè tài liệu gốc/ }).check();
  await page.getByLabel("Tên tài liệu sau khi duyệt").fill("Bản cập nhật");
  await page.getByRole("button", { name: "Lưu đè tài liệu gốc", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Lưu đè tài liệu gốc?" });
  await expect(dialog).toBeVisible();
  expect(s.submitted).toBeNull();
  await dialog.getByRole("button", { name: "Xác nhận lưu đè" }).click();
  await page.getByRole("button", { name: "Danh sách", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Bản cập nhật", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tài liệu gốc", exact: true })).toHaveCount(0);
  expect(s.submitted!.save_mode).toBe("REPLACE");
  expect(s.errors).toEqual([]);
});

test("library pagination resets on search and stays inside the mobile viewport", async ({ page, context, baseURL }, info) => {
  const s = state(); s.job = null;
  s.materials = Array.from({ length: 13 }, (_, i) => material(
    `00000000-0000-4000-8000-${String(200 + i).padStart(12, "0")}`, `Học liệu ${String(i + 1).padStart(2, "0")}`));
  await fixture(page, context, baseURL!, s);
  await openList(page);
  const cards = page.locator("article");
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeLessThanOrEqual(8);
  await page.getByRole("button", { name: "Trang tài liệu sau" }).click();
  await page.getByRole("textbox", { name: "Tìm kiếm học liệu" }).fill("Học liệu 13");
  await expect(cards).toHaveCount(1);
  await expect(cards.getByRole("heading", { name: "Học liệu 13" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("textbox", { name: "Tìm kiếm học liệu" }).fill("");
  await expect(cards).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("library-mobile.png"), fullPage: true });
  expect(s.errors).toEqual([]);
});
