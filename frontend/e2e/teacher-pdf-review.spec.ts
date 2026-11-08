import { expect, test } from "@playwright/test";
import { signSession } from "../src/lib/auth/session-codec";
import { AUTH_COOKIES } from "../src/lib/auth/constants";
import type { PdfReviewSubmit } from "../src/features/teacher/pdf-api";
import { MATH_SYMBOL_GROUPS } from "../src/features/teacher/math-symbols";

const classId = "00000000-0000-4000-8000-000000000001";
const jobId = "00000000-0000-4000-8000-000000000002";
const materialId = "00000000-0000-4000-8000-000000000003";
const revisionId = "00000000-0000-4000-8000-000000000004";
test.skip(!process.env.PDF_REVIEW_E2E_SECRET, "Use playwright.pdf-review.config.ts with an isolated server.");

for (const sourceKind of ["PDF", "IMAGE"] as const) {
test(`${sourceKind}: upload, review, revise and delete selected material`, async ({ page, context, baseURL }, testInfo) => {
  if (baseURL !== "http://127.0.0.1:3106") throw new Error("Requires isolated PDF UI server");
  const signed = await signSession({ v: 1, userId: "pdf-ui-qa", email: "teacher@example.test", fullName: "Giáo viên kiểm thử", role: "TEACHER", expiresAt: Date.now() + 600_000 }, process.env.PDF_REVIEW_E2E_SECRET!);
  await context.addCookies([{ name: AUTH_COOKIES.session, value: signed, url: baseURL, httpOnly: true, sameSite: "Lax" }]);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let submitted: PdfReviewSubmit | null = null;
  let saved: PdfReviewSubmit | null = null;
  let uploaded = false;
  let deleted = false;
  let rejectDeletion = true;
  const material = { id: materialId, title: "Đề ôn tập đã duyệt", original_file_name: "exercise.reviewed.json", mime_type: "application/json", file_size_bytes: 500, status: "READY", subject_id: classId, created_at: "2026-11-08T00:00:00Z", pdf_import_id: jobId };
  const draft = () => ({ id: jobId, classroom_id: classId, subject_id: classId, title: "Đề ôn tập", original_file_name: sourceKind === "IMAGE" ? "exercise.png" : "exercise.pdf", source_kind: sourceKind, source_mime_type: sourceKind === "IMAGE" ? "image/png" : "application/pdf", status: submitted ? "SUBMITTED" : "NEEDS_REVIEW", created_at: "2026-11-08T00:00:00Z", error: null, material_id: submitted ? materialId : null, progress: { processed_pages: 1, selected_pages: 1, failed_regions: 1 }, review: saved,
    questions: [1, 2].map((n) => ({ question_id: `q${n}`, number: n, source_number: n, content: `Câu ${n}. Tính $${n}+1$`, answer: String(n + 1), explanation: "Lời giải từ PDF", pages: [1], warnings: n === 2 ? ["INCOMPLETE"] : [], suggested: n === 1, source_assets: [], visual_assets: [] })) });
  await page.route("**/auth/csrf", (route) => route.fulfill({ json: { csrf_token: "isolated-ui-token" } }));
  await page.route("**/api/teacher/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.slice("/api/teacher/".length);
    let body: unknown;
    if (path === "classes") body = [{ id: classId, name: "12A · Kiểm thử", academic_year: "2026-2027", grade_level: 12 }];
    else if (path === "subjects") body = [{ id: classId, code: "MATH", name: "Toán", grade_level: 12 }];
    else if (path === "materials") body = submitted && !deleted ? [material] : [];
    else if (path === `materials/${materialId}` && request.method() === "DELETE") {
      if (rejectDeletion) { rejectDeletion = false; await route.fulfill({ status: 503, json: { error: { code: "DELETE_RETRY", message: "Chưa thể xóa tài liệu lúc này." } } }); }
      else { deleted = true; await route.fulfill({ status: 204, body: "" }); }
      return;
    }
    else if (path.endsWith("/students") || path.endsWith("/assignments")) body = [];
    else if (path.endsWith("/analytics")) body = { student_count: 0, subject_progress: [], chapter_progress: [], weak_problem_types: [], students_needing_attention: [], assignment_completion: { assignment_count: 0, submitted_count: 0, graded_count: 0, completion_rate: 0 }, evidence_summary: { scored_events: 0, needs_teacher_review_count: 0 } };
    else if (path === "materials/pdf-imports" && request.method() === "POST") { uploaded = true; body = draft(); }
    else if (path === "materials/pdf-imports") body = uploaded && !submitted ? [draft()] : [];
    else if (path === `materials/pdf-imports/${jobId}`) body = draft();
    else if (path.endsWith("/revise") || path === `materials/pdf-imports/${revisionId}`) body = { ...draft(), id: revisionId, status: "NEEDS_REVIEW", revision_of: materialId, material_id: null };
    else if (path.endsWith("/review")) { saved = request.postDataJSON(); body = draft(); }
    else if (path.endsWith("/submit")) { submitted = request.postDataJSON(); body = material; }
    else { await route.fulfill({ status: 404, json: { error: { code: "UNMOCKED", message: path } } }); return; }
    await route.fulfill({ json: body });
  });
  await page.goto("/teacher?tab=materials");
  await page.getByRole("button", { name: /Chế độ 2D/ }).click();
  await page.getByRole("button", { name: "Tải lên tài liệu mới", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(sourceKind === "IMAGE" ? {
    name: "exercise.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XfS8AAAAASUVORK5CYII=", "base64"),
  } : { name: "exercise.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 UI fixture") });
  await page.getByLabel("Tên tài liệu / Tiêu đề đề bài").fill("Đề ôn tập");
  await page.getByRole("button", { name: sourceKind === "IMAGE" ? "Tải ảnh & xử lý OCR" : "Tải PDF & xử lý OCR" }).click();
  await expect(page.getByRole("heading", { name: sourceKind === "IMAGE" ? "Duyệt bài tập từ ảnh" : "Duyệt bài tập từ PDF" })).toBeVisible();
  await expect(page.getByRole("link", { name: sourceKind === "IMAGE" ? "Mở ảnh gốc" : "Mở PDF gốc" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Lưu 0 câu vào kho" })).toBeDisabled();
  await expect(page.getByText("Cần kiểm tra nguồn", { exact: true })).toBeVisible();
  const first = page.locator("article").filter({ has: page.getByRole("heading", { name: /Câu 1/ }) });
  await first.getByRole("button", { name: "Chỉnh sửa câu hỏi", exact: true }).click();
  await first.getByLabel("Đề bài", { exact: true }).fill("Câu 1. Nội dung đã sửa $x^2$");
  await first.getByLabel("Đáp án", { exact: true }).fill("Đáp án đã sửa $2$");
  await first.getByLabel("Lời giải", { exact: true }).fill("Lời giải đã sửa $1+1=2$");
  const preview = first.getByLabel("Bản xem trước sau chỉnh sửa");
  await expect(preview.getByText(/Lời giải đã sửa/)).toBeVisible();
  await first.getByRole("checkbox").check();
  await expect(page.getByRole("button", { name: "Lưu 1 câu vào kho" })).toBeDisabled();
  await first.getByRole("radio", { name: "Vận dụng cao", exact: true }).check();
  await expect(page.getByRole("button", { name: "Lưu 1 câu vào kho" })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath("edit-desktop.png"), fullPage: true });
  await page.getByLabel("Tên tài liệu sau khi duyệt").fill(material.title);
  await page.getByRole("button", { name: "Lưu nháp", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã lưu bản nháp duyệt" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("checkbox").first()).toBeChecked();
  await expect(page.getByRole("checkbox").nth(1)).not.toBeChecked();
  await expect(page.getByRole("radio", { name: "Vận dụng cao", exact: true }).first()).toBeChecked();
  await page.getByLabel("Lọc theo mức độ").selectOption("unknown");
  await expect(page.locator("article")).toHaveCount(1);
  await expect(page.locator("article").getByRole("heading", { name: /Câu 2/ })).toBeVisible();
  await page.getByLabel("Lọc theo mức độ").selectOption("all");
  await page.screenshot({ path: testInfo.outputPath("review-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Lưu 1 câu vào kho" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("review-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Lưu 1 câu vào kho" }).click();
  const listMode = page.getByRole("button", { name: /Chế độ 2D/ });
  await listMode.click();
  await expect(page.getByRole("heading", { name: material.title, exact: true })).toBeVisible();
  expect(submitted!.decisions.filter((d) => d.accepted).map((d) => d.question_id)).toEqual(["q1"]);
  expect(submitted!.decisions[0].content).toContain("Nội dung đã sửa");
  expect(submitted!.decisions[0].answer).toContain("Đáp án đã sửa");
  expect(submitted!.decisions[0].explanation).toContain("Lời giải đã sửa");
  expect(submitted!.decisions[0].difficulty_level).toBe("VAN_DUNG_CAO");
  await expect(page.getByRole("link", { name: "Tải bản đã duyệt" })).toHaveAttribute("href", `/api/teacher/materials/${materialId}/document`);
  await page.getByRole("button", { name: "Xem nguồn / Chỉnh sửa" }).click();
  await page.getByRole("button", { name: "Chỉnh sửa & phân loại câu hỏi" }).click();
  await expect(page).toHaveURL(new RegExp(`pdfImport=${revisionId}`));
  await expect(page.getByRole("radio", { name: "Vận dụng cao", exact: true }).first()).toBeChecked();
  const revisedFirst = page.locator("article").first();
  await revisedFirst.getByRole("button", { name: "Chỉnh sửa câu hỏi", exact: true }).click();
  await revisedFirst.getByLabel("Đề bài", { exact: true }).fill("Câu 1. Bản chỉnh sửa thứ hai");
  await expect(revisedFirst.getByRole("checkbox")).not.toBeChecked();
  await expect(revisedFirst.getByLabel("Bản xem trước sau chỉnh sửa")).toContainText("Bản chỉnh sửa thứ hai");
  expect(submitted!.decisions[0].content).toContain("Nội dung đã sửa");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("edit-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Lưu nháp & quay lại" }).click();
  const deleteButton = page.getByRole("button", { name: `Xóa tài liệu ${material.title}`, exact: true });
  await deleteButton.click();
  let dialog = page.getByRole("dialog", { name: "Xóa tài liệu khỏi kho?" });
  await dialog.getByRole("button", { name: "Hủy", exact: true }).click();
  await expect(deleteButton).toBeFocused();
  await deleteButton.click();
  dialog = page.getByRole("dialog", { name: "Xóa tài liệu khỏi kho?" });
  await dialog.getByRole("button", { name: "Xóa khỏi kho", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Chưa thể xóa");
  await expect(page.locator("article").filter({ hasText: material.title })).toHaveCount(1);
  await dialog.getByRole("button", { name: "Xóa khỏi kho", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("heading", { name: material.title, exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Tải lên tài liệu mới", exact: true })).toBeFocused();
  await page.reload();
  await page.getByRole("button", { name: /Chế độ 2D/ }).click();
  await expect(page.getByRole("heading", { name: material.title, exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
});
}

test("visual math: edit OCR formulas, fill templates, insert at caret and persist", async ({ page, context, baseURL }, testInfo) => {
  if (baseURL !== "http://127.0.0.1:3106") throw new Error("Requires isolated PDF UI server");
  const signed = await signSession({ v: 1, userId: "math-ui-qa", email: "teacher@example.test", fullName: "Giáo viên kiểm thử", role: "TEACHER", expiresAt: Date.now() + 600_000 }, process.env.PDF_REVIEW_E2E_SECRET!);
  await context.addCookies([{ name: AUTH_COOKIES.session, value: signed, url: baseURL, httpOnly: true, sameSite: "Lax" }]);
  const errors: string[] = [];
  const externalRequests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => { if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) externalRequests.push(request.url()); });
  let saved: PdfReviewSubmit | null = null;
  const draft = () => ({ id: jobId, classroom_id: classId, subject_id: classId, title: "Sửa công thức", original_file_name: "exercise.png", source_kind: "IMAGE", source_mime_type: "image/png", created_at: "2026-11-08T00:00:00Z", status: "NEEDS_REVIEW", progress: { processed_pages: 1, selected_pages: 1, failed_regions: 0 }, review: saved,
    questions: [{ question_id: "q1", number: 1, source_number: 1, content: "Trước $x^2$ sau.\nDòng thứ hai.", answer: String.raw`$\frac{3}{10}$`, explanation: "Lời giải tiếng Việt", pages: [1], warnings: [], suggested: true, source_assets: [], visual_assets: [] }] });
  await page.route("**/auth/csrf", (route) => route.fulfill({ json: { csrf_token: "isolated-ui-token" } }));
  await page.route("**/api/teacher/**", async (route) => {
    const path = new URL(route.request().url()).pathname.slice("/api/teacher/".length);
    let body: unknown;
    if (path === "classes") body = [{ id: classId, name: "12A", academic_year: "2026-2027", grade_level: 12 }];
    else if (path === "subjects") body = [{ id: classId, code: "MATH", name: "Toán", grade_level: 12 }];
    else if (path === "materials/pdf-imports") body = [draft()];
    else if (path === `materials/pdf-imports/${jobId}`) body = draft();
    else if (path.endsWith("/review")) { saved = route.request().postDataJSON(); body = draft(); }
    else if (path.endsWith("/analytics")) body = { student_count: 0, subject_progress: [], chapter_progress: [], weak_problem_types: [], students_needing_attention: [], assignment_completion: { assignment_count: 0, submitted_count: 0, graded_count: 0, completion_rate: 0 }, evidence_summary: { scored_events: 0, needs_teacher_review_count: 0 } };
    else body = [];
    await route.fulfill({ json: body });
  });
  await page.goto(`/teacher?tab=materials&pdfImport=${jobId}`);
  await expect(page.getByRole("button", { name: "Chỉnh sửa câu hỏi", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Chỉnh sửa câu hỏi", exact: true }).click();
  const content = page.getByLabel("Đề bài", { exact: true });
  const answer = page.getByLabel("Đáp án", { exact: true });
  await expect(content.getByRole("button", { name: "Sửa công thức toán" })).toHaveCount(1);
  await page.getByRole("radio", { name: "Thông hiểu", exact: true }).check();
  await page.getByRole("checkbox").check();
  await content.getByRole("button", { name: "Sửa công thức toán" }).click();
  let dialog = page.getByRole("dialog", { name: "Chỉnh sửa công thức", exact: true });
  let field = dialog.getByTestId("teacher-mathfield");
  await expect(field).toBeVisible();
  await expect(dialog.getByLabel("Mã LaTeX của công thức")).not.toBeVisible();
  await field.press("ControlOrMeta+A");
  await dialog.getByRole("button", { name: "Nhập 9", exact: true }).click();
  await dialog.getByLabel("Tìm ký hiệu", { exact: true }).fill("/landa");
  await dialog.getByRole("button", { name: "lambda", exact: true }).click();
  await dialog.getByRole("button", { name: "Hoàn tác công thức", exact: true }).click();
  await dialog.getByRole("button", { name: "Làm lại công thức", exact: true }).click();
  await expect(field.locator('[part="virtual-keyboard-toggle"]')).not.toBeVisible();
  await expect(field.locator('[part="menu-toggle"]')).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("math-palette-desktop.png") });
  await dialog.getByRole("button", { name: "Cập nhật công thức", exact: true }).click();
  await expect(content.locator("[data-math-token]")).toHaveAttribute("data-latex", /9\\lambda/);
  await expect(content).toContainText("Dòng thứ hai.");
  await expect(page.getByRole("checkbox")).not.toBeChecked();

  // Cancellation leaves the accepted state and stored formula intact.
  await page.getByRole("checkbox").check();
  await content.getByRole("button", { name: "Sửa công thức toán" }).click();
  dialog = page.getByRole("dialog", { name: "Chỉnh sửa công thức", exact: true });
  await dialog.getByRole("button", { name: "Nhập 8", exact: true }).click();
  await dialog.getByRole("button", { name: "Hủy", exact: true }).click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await expect(content.locator("[data-math-token]")).toHaveAttribute("data-latex", /9\\lambda/);

  // Fill a visual fraction using only palette buttons, including the next-slot button.
  await answer.getByRole("button", { name: "Sửa công thức toán" }).click();
  dialog = page.getByRole("dialog", { name: "Chỉnh sửa công thức", exact: true });
  field = dialog.getByTestId("teacher-mathfield");
  await field.press("ControlOrMeta+A");
  await field.press("Backspace");
  await dialog.getByRole("button", { name: "Phân số", exact: true }).click();
  await dialog.getByRole("button", { name: "Cập nhật công thức", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("điền đủ");
  await dialog.getByRole("button", { name: "Nhập 1", exact: true }).click();
  await dialog.getByRole("button", { name: "Ô tiếp", exact: true }).click();
  await dialog.getByRole("button", { name: "Nhập 2", exact: true }).click();
  await dialog.getByRole("button", { name: "Cập nhật công thức", exact: true }).click();
  await expect(answer.locator("[data-math-token]")).toHaveAttribute("data-latex", String.raw`\frac12`);

  // Insert before the first character, then type after the inserted formula.
  await content.focus();
  await content.press("ControlOrMeta+Home");
  await page.getByRole("button", { name: "Chèn công thức", exact: true }).first().click();
  dialog = page.getByRole("dialog", { name: "Chèn công thức toán", exact: true });
  await dialog.getByLabel("Tìm ký hiệu", { exact: true }).fill("sigma");
  await dialog.getByRole("button", { name: "sigma", exact: true }).click();
  await dialog.getByRole("button", { name: "Chèn vào nội dung", exact: true }).click();
  await expect(content.locator("[data-math-token]")).toHaveCount(2);
  await expect(content.locator("[data-math-token]").first()).toHaveAttribute("data-latex", String.raw`\sigma`);
  await content.pressSequentially(" ");

  await page.setViewportSize({ width: 390, height: 844 });
  await content.getByRole("button", { name: "Sửa công thức toán" }).first().click();
  dialog = page.getByRole("dialog", { name: "Chỉnh sửa công thức", exact: true });
  await dialog.getByRole("button", { name: "Đạo hàm · Tích phân", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Tích phân có cận", exact: true })).toBeVisible();
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("math-palette-mobile.png") });
  // Verify the visual engine understands every advertised template (no remote services).
  const invalid = await dialog.getByTestId("teacher-mathfield").evaluate((el, symbols) => {
    const mf = el as HTMLElement & { value: string; insert: (s: string, o: object) => void; errors: { code: string }[] };
    return symbols.flatMap((symbol) => {
      mf.value = ""; mf.insert(symbol.insert, { format: "latex" });
      return mf.errors.length ? [{ id: symbol.id, errors: mf.errors }] : [];
    });
  }, MATH_SYMBOL_GROUPS.flatMap((g) => g.symbols));
  expect(invalid).toEqual([]);
  await dialog.getByRole("button", { name: "Hủy", exact: true }).click();
  const solution = page.getByLabel("Lời giải", { exact: true });
  await solution.focus();
  await solution.press("ControlOrMeta+End");
  await solution.press("Enter");
  await page.getByRole("button", { name: "Lưu nháp", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã lưu bản nháp duyệt" })).toBeVisible();
  expect(saved!.decisions[0].explanation).toBe("Lời giải tiếng Việt\n");
  await solution.focus();
  await solution.press("ControlOrMeta+End");
  await solution.pressSequentially("Dòng mới");
  await solution.press("Enter");
  await solution.press("Enter");
  await solution.pressSequentially("Hết");
  await page.getByRole("button", { name: "Lưu nháp", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã lưu bản nháp duyệt" })).toBeVisible();
  expect(saved!.decisions[0].content).toMatch(/^\$\\sigma\$ Trước \$9\\lambda\$ sau\.\nDòng thứ hai\.$/);
  expect(saved!.decisions[0].answer).toBe(String.raw`$\frac12$`);
  expect(saved!.decisions[0].explanation).toBe("Lời giải tiếng Việt\nDòng mới\n\nHết");
  await page.reload();
  await page.getByRole("button", { name: "Chỉnh sửa câu hỏi", exact: true }).click();
  await expect(content.locator("[data-math-token]")).toHaveCount(2);
  await expect(answer.locator("[data-math-token]")).toHaveAttribute("data-latex", String.raw`\frac12`);
  expect(externalRequests).toEqual([]);
  expect(errors).toEqual([]);
});
