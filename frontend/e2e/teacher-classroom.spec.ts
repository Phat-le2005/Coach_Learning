import { expect, test } from "@playwright/test";
import { signSession } from "../src/lib/auth/session-codec";
import { AUTH_COOKIES } from "../src/lib/auth/constants";
import fs from "node:fs/promises";

test.skip(process.env.CLASSROOM_E2E !== "1", "Run with playwright.classroom.config.ts against the isolated classroom server.");

const classId = "00000000-0000-4000-8000-000000000001";
const otherClassId = "00000000-0000-4000-8000-000000000002";
const assignmentId = "00000000-0000-4000-8000-000000000003";
const liveStudents = Array.from({ length: 10 }, (_, index) => ({
  student_id: `real-student-${index + 1}`, full_name: `Học sinh thật ${String(index + 1).padStart(2, "0")}`,
  email: `student${index + 1}@example.test`, status: index === 9 ? "INACTIVE" : "ACTIVE", is_synthetic: false,
}));

test.beforeEach(async ({ context, page, baseURL }, testInfo) => {
  if (baseURL !== "http://127.0.0.1:3105" || !process.env.CLASSROOM_E2E_SECRET) throw new Error("Classroom UI tests require the isolated local server.");
  const value = await signSession({
    v: 1, userId: "classroom-ui-qa", email: "teacher@example.test", fullName: "Giáo viên kiểm thử",
    role: "TEACHER", expiresAt: Date.now() + 5 * 60_000,
  }, process.env.CLASSROOM_E2E_SECRET);
  await context.addCookies([{ name: AUTH_COOKIES.session, value, url: baseURL, httpOnly: true, sameSite: "Lax" }]);
  await page.route("**/api/teacher/**", async (route) => {
    const path = new URL(route.request().url()).pathname.slice("/api/teacher/".length);
    let body: unknown;
    if (path === "classes") body = [
      { id: classId, name: "12A · Dữ liệu kiểm thử", academic_year: "2026-2027", grade_level: 12 },
      { id: otherClassId, name: "12B · Dữ liệu kiểm thử", academic_year: "2026-2027", grade_level: 12 },
    ];
    else if (path === "subjects" || path === "materials") body = [];
    else if (path.endsWith("/students")) body = path.includes(otherClassId) ? [] : [...liveStudents, { ...liveStudents[0], student_id: "synthetic-student", full_name: "Synthetic pupil", is_synthetic: true }];
    else if (path.endsWith("/assignments")) body = [{ id: assignmentId, title: "Bài kiểm tra dữ liệu thật", status: "PUBLISHED", question_count: 5, due_at: null, subject_id: classId }];
    else if (path.endsWith("/analytics")) body = { student_count: 10, subject_progress: [], chapter_progress: [], weak_problem_types: [], students_needing_attention: [], assignment_completion: { assignment_count: 1, submitted_count: 2, graded_count: 1, completion_rate: 20 }, evidence_summary: { scored_events: 1, needs_teacher_review_count: 0 } };
    else if (path.endsWith("/submissions")) body = { assignment_id: assignmentId, title: "Bài kiểm tra dữ liệu thật", total_students: 10, submitted_count: 2, graded_count: 1, roster: liveStudents.slice(0, 2).map((student, index) => ({ student_id: student.student_id, student_name: student.full_name, status: "SUBMITTED", score: index === 0 ? 8 : null, submitted_at: "2026-11-05T03:00:00Z" })) };
    else { await route.fulfill({ status: 404, json: { error: { code: "QA_UNMOCKED_PATH", message: path } } }); return; }
    await route.fulfill({ json: body });
  });
  await page.goto("/teacher");
  if (!testInfo.title.includes("[live]")) await page.getByRole("button", { name: "Minh họa 10 bạn", exact: true }).click();
  await expect(page.locator('[data-scene-state="ready"]')).toBeVisible();
});

test("3D picking, support profile and motion controls in the explicit preview", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const stage = page.locator('[data-scene-state="ready"]');
  await expect(page.locator('[aria-label="Hồ sơ học sinh được chọn"]')).toHaveCount(0);
  const profile = page.locator('[aria-label="Hồ sơ học sinh được chọn"]');
  await expect(stage.getByRole("button")).toHaveCount(10);
  await expect(stage.getByText("Góc nhìn giáo viên", { exact: true })).toBeVisible();
  await expect(stage.getByText("5 hàng × 2 bàn", { exact: true })).toBeVisible();
  await expect(page.getByText("9/10 online", { exact: true })).toBeVisible();
  await stage.getByRole("button", { name: /Trần Thị Mai Anh/ }).click();
  await expect(profile.getByRole("heading", { name: "Trần Thị Mai Anh (Demo 03)" })).toBeVisible();
  await expect(profile.getByText("11/16", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Tạm dừng chuyển động" }).click();
  await expect(page.getByRole("button", { name: "Bật chuyển động" })).toHaveAttribute("aria-pressed", "true");
  const point = await stage.evaluate((element) => {
    const canvas = element.querySelector("canvas")!.getBoundingClientRect();
    // The first pupil sits in the front-left desk in the teacher's view.
    return { x: canvas.width / 2 - canvas.height * .19, y: canvas.height * .65 };
  });
  await stage.locator("canvas").click({ position: point });
  await expect(profile.getByRole("heading", { name: "Demo Student 01" })).toBeVisible();
  await stage.getByRole("button", { name: /Trần Thị Mai Anh/ }).click();
  await page.screenshot({ path: testInfo.outputPath("classroom-desktop.png"), fullPage: true });
  await expect(profile.getByRole("button", { name: "Bài làm minh họa chưa kết nối" })).toBeDisabled();
  expect(errors).toEqual([]);
});

test("teacher view shows five rows with perspective and unobstructed name labels", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1760, height: 1800 });
  await page.evaluate(() => window.scrollTo(0, 0));
  const stage = page.locator('[data-scene-state="ready"]');
  await expect.poll(() => stage.evaluate((element) => element.clientWidth)).toBeGreaterThan(1600);
  await expect.poll(() => stage.evaluate((element) => element.clientHeight)).toBeGreaterThanOrEqual(700);
  const positions = await stage.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const boxes = [...element.querySelectorAll("button")].map((button) => button.getBoundingClientRect());
    return {
      frontY: (boxes[0].top + boxes[1].top) / 2,
      backY: (boxes[8].top + boxes[9].top) / 2,
      frontSpan: boxes[1].left + boxes[1].width / 2 - boxes[0].left - boxes[0].width / 2,
      backSpan: boxes[9].left + boxes[9].width / 2 - boxes[8].left - boxes[8].width / 2,
      clipped: boxes.some((box) => box.left < bounds.left || box.right > bounds.right || box.top < bounds.top || box.bottom > bounds.bottom),
      overlap: boxes.some((a, i) => boxes.some((b, j) => i !== j && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)),
    };
  });
  expect(positions.frontY).toBeGreaterThan(positions.backY);
  expect(positions.frontSpan).toBeGreaterThan(positions.backSpan);
  expect(positions.clipped).toBe(false);
  expect(positions.overlap).toBe(false);
  await stage.getByRole("button", { name: /Trần Thị Mai Anh/ }).click();
  await page.locator('[aria-label="Lớp học 3D"]').screenshot({ path: testInfo.outputPath("teacher-view.png") });
});

test("[live] roster, unknown evidence and matching submissions stay connected", async ({ page }) => {
  const stage = page.locator('[data-scene-state="ready"]');
  await expect(stage.getByRole("button")).toHaveCount(10);
  await expect(page.getByText("Synthetic pupil", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Chưa có trạng thái online", { exact: true })).toBeVisible();
  await stage.getByRole("button", { name: /Học sinh thật 01/ }).click();
  const profile = page.getByRole("complementary", { name: "Hồ sơ học sinh được chọn" });
  await expect(profile.getByText("Chưa có dữ liệu", { exact: true })).toHaveCount(2);
  await expect(profile.getByRole("progressbar")).toHaveCount(0);
  await profile.getByRole("button", { name: "Xem bài làm", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Bài kiểm tra dữ liệu thật", exact: true })).toHaveCount(2);
  const table = page.getByRole("table");
  await expect(table.getByText("Học sinh thật 01", { exact: true })).toBeVisible();
  await expect(table.getByText("Học sinh thật 02", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Xem cả lớp", exact: true }).click();
  await expect(table.getByText("Học sinh thật 02", { exact: true })).toBeVisible();
});

test("[live] a pupil missing from an assignment never sees another pupil's work", async ({ page }) => {
  await page.getByRole("button", { name: /Học sinh thật 10.*bàn 10/ }).click();
  const profile = page.getByRole("complementary", { name: "Hồ sơ học sinh được chọn" });
  await expect(profile.getByText("Chưa có trạng thái online", { exact: true })).toBeVisible();
  await profile.getByRole("button", { name: "Xem bài làm", exact: true }).click();
  await expect(page.getByText("Chưa có bài làm của học sinh này trong bài tập đã chọn.", { exact: true })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
});

test("[live] class changes clear old pupils and API failure never substitutes demo pupils", async ({ page }) => {
  await page.getByRole("combobox", { name: "Chọn lớp học quản lý" }).selectOption(otherClassId);
  await expect(page.getByText("Lớp học chưa có học sinh. Danh sách sẽ xuất hiện khi các em tham gia lớp.", { exact: true })).toBeVisible();
  await expect(page.locator('[data-scene-state="ready"]')).toBeVisible();
  await expect(page.locator('[data-scene-state="ready"]').getByRole("button", { disabled: true })).toHaveCount(10);
  await page.route(`**/api/teacher/classes/${classId}/students?*`, (route) => route.fulfill({ status: 503, json: { error: { code: "QA_UNAVAILABLE", message: "Không tải được danh sách kiểm thử" } } }));
  await page.getByRole("combobox", { name: "Chọn lớp học quản lý" }).selectOption(classId);
  await expect(page.getByRole("alert").filter({ hasText: "Không tải được danh sách kiểm thử" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Demo Student 01, bàn/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Minh họa 10 bạn", exact: true }).click();
  await expect(page.locator('[data-scene-state="ready"]')).toBeVisible();
  await expect(page.getByText("Lớp minh họa", { exact: true })).toBeVisible();
});

test("[live] the teacher homepage opens in 3D before the class management cards", async ({ page }) => {
  await expect(page.getByRole("button", { name: /Lớp học & Học sinh/ })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("button", { name: "Lớp học 3D", exact: true })).toHaveAttribute("aria-pressed", "true");
  const room = await page.getByRole("region", { name: "Lớp học 3D", exact: true }).boundingBox();
  const classes = await page.getByRole("heading", { name: "Các lớp học phụ trách", exact: true }).boundingBox();
  expect(room).not.toBeNull(); expect(classes).not.toBeNull();
  expect(room!.y + room!.height).toBeLessThan(classes!.y);
});

test("search, empty results, list mode and repeated scene mounts", async ({ page }) => {
  const search = page.getByRole("textbox", { name: "Tìm học sinh theo tên hoặc email" });
  await search.fill("do gia han");
  const stage = page.locator('[data-scene-state="ready"]');
  await expect(stage.getByRole("button", { disabled: false })).toHaveCount(1);
  await expect(stage.getByRole("button", { name: /Đỗ Gia Hân.*bàn 7/ })).toBeEnabled();
  await stage.getByRole("button", { name: /Đỗ Gia Hân.*bàn 7/ }).click();
  await expect(page.getByRole("heading", { name: "Đỗ Gia Hân (Demo 07)" })).toBeVisible();
  await search.fill("no-student-matches");
  await expect(page.getByRole("heading", { name: "Không tìm thấy học sinh" })).toBeVisible();
  await search.fill("");
  await expect(page.locator('[data-scene-state="ready"]')).toBeVisible();
  for (let index = 0; index < 3; index++) {
    await page.getByRole("button", { name: "Danh sách", exact: true }).click();
    await expect(page.getByRole("table").getByRole("row")).toHaveCount(11);
    await expect(page.locator("canvas")).toHaveCount(0);
    await page.getByRole("button", { name: "Lớp học 3D", exact: true }).click();
    await expect(page.locator('[data-scene-state="ready"]')).toBeVisible();
    await expect(page.locator("canvas")).toHaveCount(1);
  }
});

test("desk colors, props and glasses survive reload without recreating the canvas", async ({ page }) => {
  await page.getByRole("button", { name: /Trần Thị Mai Anh.*bàn 3/ }).click();
  const profile = page.locator('[aria-label="Hồ sơ học sinh được chọn"]');
  const canvas = await page.locator("canvas").elementHandle();
  await profile.getByRole("button", { name: "Cam đào", exact: true }).click();
  await profile.getByRole("button", { name: "Ngôi sao", exact: true }).click();
  await profile.getByRole("checkbox", { name: "Đeo kính cho bạn học" }).check();
  expect(await page.locator("canvas").evaluate((node, previous) => node === previous, canvas)).toBe(true);
  await profile.getByRole("button", { name: "Đóng hồ sơ học sinh" }).click();
  await expect(profile).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Minh họa 10 bạn", exact: true }).click();
  await expect(page.locator('[data-scene-state="ready"]')).toBeVisible();
  await page.getByRole("button", { name: /Trần Thị Mai Anh.*bàn 3/ }).click();
  await expect(profile.getByRole("button", { name: "Cam đào", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(profile.getByRole("button", { name: "Ngôi sao", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(profile.getByRole("checkbox", { name: "Đeo kính cho bạn học" })).toBeChecked();
});

test("moment cards download real PNGs in both formats and keep identities hidden", async ({ page }, testInfo) => {
  await page.getByRole("button", { name: "Khoảnh khắc", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Khoảnh khắc lớp mình" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("checkbox", { name: "Hiển thị tên lớp trên ảnh" })).not.toBeChecked();
  await expect(dialog.getByRole("img")).toBeVisible();
  for (const [format, height] of [["post", 1350], ["story", 1920]] as const) {
    if (format === "story") await dialog.getByRole("button", { name: "Story · 9:16", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Tải ảnh PNG", exact: true })).toBeEnabled();
    const downloadPromise = page.waitForEvent("download");
    await dialog.getByRole("button", { name: "Tải ảnh PNG", exact: true }).click();
    const download = await downloadPromise;
    const output = testInfo.outputPath(`moment-${format}.png`); await download.saveAs(output);
    const bytes = await fs.readFile(output);
    expect([...bytes.subarray(0, 8)]).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
    expect(bytes.readUInt32BE(16)).toBe(1080); expect(bytes.readUInt32BE(20)).toBe(height);
  }
  const stickerPromise = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "Tải sticker Mầm", exact: true }).click();
  const sticker = await stickerPromise;
  const stickerOutput = testInfo.outputPath("mam-sticker.png"); await sticker.saveAs(stickerOutput);
  const stickerBytes = await fs.readFile(stickerOutput);
  expect(stickerBytes.readUInt32BE(16)).toBe(512); expect(stickerBytes.readUInt32BE(20)).toBe(512);
  expect(stickerBytes[25]).toBe(6); // RGBA PNG keeps the sticker's transparent background.
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("Mam greets the teacher and preview celebrations do not change academic progress", async ({ page }) => {
  const canvas = page.locator("canvas");
  const point = await canvas.evaluate((node) => { const rect = node.getBoundingClientRect(); return { x: rect.width / 2, y: rect.height * .79 }; });
  await canvas.click({ position: point });
  await expect(page.getByText(/Chào bạn, mình là Mầm!/)).toBeVisible();
  const goal = page.getByRole("progressbar", { name: "Mục tiêu hoàn thành bài tập" });
  await expect(goal).toHaveAttribute("aria-valuenow", "3");
  await page.getByRole("button", { name: "Khoảnh khắc", exact: true }).click();
  await page.getByRole("button", { name: "Xem thử ăn mừng trên lớp" }).click();
  await expect(page.locator('[data-celebration="active"]')).toHaveCount(1);
  await expect(page.locator('[data-celebration="active"]')).toHaveCount(0, { timeout: 5000 });
  await expect(goal).toHaveAttribute("aria-valuenow", "3");
});

test("mobile seats fit and reduced motion is honored", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole("button", { name: "Đã giảm chuyển động" })).toBeDisabled();
    const stage = page.locator('[data-scene-state="ready"]');
    await stage.scrollIntoViewIfNeeded();
    const layout = await stage.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      const boxes = [...element.querySelectorAll("button")].map((button) => button.getBoundingClientRect());
      return {
        overflow: document.documentElement.scrollWidth > window.innerWidth,
        outOfBounds: boxes.some((box) => box.left < bounds.left || box.right > bounds.right),
        overlap: boxes.some((a, i) => boxes.some((b, j) => i !== j && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)),
        minHeight: Math.min(...boxes.map((box) => box.height)),
      };
    });
    expect(layout).toEqual({ overflow: false, outOfBounds: false, overlap: false, minHeight: 44 });
    await stage.getByRole("button", { name: /Trần Thị Mai Anh/ }).click();
    await expect(page.getByRole("heading", { name: "Trần Thị Mai Anh (Demo 03)" })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`classroom-mobile-${width}.png`), fullPage: true });
  }
});

test("lost WebGL context leaves student profiles and list mode usable", async ({ page }) => {
  await page.locator("canvas").evaluate((canvas) => canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true })));
  const fallback = page.locator('[data-scene-state="unavailable"]');
  await expect(fallback.getByRole("status")).toContainText("Chưa hiển thị được 3D");
  await fallback.getByRole("button", { name: /Trần Thị Mai Anh/ }).click();
  await expect(page.getByRole("heading", { name: "Trần Thị Mai Anh (Demo 03)" })).toBeVisible();
  await page.getByRole("button", { name: "Khoảnh khắc", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Khoảnh khắc lớp mình" });
  await expect(dialog.getByRole("img")).toBeVisible();
  await dialog.getByRole("button", { name: "Đóng khoảnh khắc" }).click();
  await page.getByRole("button", { name: "Danh sách", exact: true }).click();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(11);
});
