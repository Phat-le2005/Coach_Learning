import { test, expect } from "@playwright/test";
import { populatedHome, renderHomeContent } from "./helpers/home-content-fixture";

test.use({ trace: "off", video: "off", screenshot: "only-on-failure" });

test("populated content keeps targeted actions, task expansion, review names and class breakdown", async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await renderHomeContent(page, populatedHome());
  await expect(page.getByRole("link", { name: "Ôn nội dung được gợi ý", exact: true })).toHaveAttribute("href", "/student/practice?concept_id=concept-ref");
  await expect(page.getByText("Tính đơn điệu của hàm số", { exact: true })).toBeVisible();
  await expect(page.getByText("3 nội dung sắp đến lịch ôn.", { exact: true })).toBeVisible();
  await expect(page.getByText("2 đang làm", { exact: true })).toBeVisible();
  await expect(page.getByText("1 chưa nộp", { exact: true })).toBeVisible();
  await expect(page.getByText("Dạng đã vững", { exact: true })).toBeVisible();
  await expect(page.getByText("Đã học 8 dạng và 12 khái niệm.", { exact: true })).toBeVisible();
  const more = page.getByRole("button", { name: "Xem thêm 2 nhiệm vụ", exact: true });
  await more.click();
  await expect(page.getByRole("heading", { name: "Xác suất có điều kiện", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tọa độ trong không gian", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Luyện: Xác suất có điều kiện", exact: true })).toHaveAttribute("href", "/student/practice?subject_id=subject-ref&concept_id=concept-3");
  await page.screenshot({ path: info.outputPath("populated-desktop.png"), fullPage: true });
});

test("empty state retains feature groups without fabricating scores or classroom content", async ({ page }, info) => {
  const data = populatedHome();
  data.learningContext.mode = "SELF_STUDY_ONBOARDING";
  data.resolvedAction.type = "IDLE"; data.currentAction.type = "IDLE";
  data.mastery.hasEvidence = false; data.mastery.score = undefined;
  data.review = { dueCount: 0, upcomingCount: 0, dueTargets: [] };
  data.todayPlan = null; data.priorities = [];
  await page.setViewportSize({ width: 390, height: 844 });
  await renderHomeContent(page, data);
  await expect(page.getByRole("heading", { name: "Lịch học & việc cần làm", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Năng lực & trọng tâm học", exact: true })).toBeVisible();
  await expect(page.getByText("Chưa đủ dữ liệu đánh giá.", { exact: true })).toBeVisible();
  await expect(page.getByText("Chưa có đề xuất củng cố.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bài tập từ lớp", exact: true })).toHaveCount(0);
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: info.outputPath("empty-mobile.png"), fullPage: true });
});

test("zero mastery and long populated content remain truthful and fit the dark mobile layout", async ({ page }, info) => {
  const data = populatedHome();
  data.mastery.score = 0;
  data.priorities[0].targetName = "Xét sự biến thiên và tìm cực trị của hàm số có tham số trong những điều kiện khác nhau";
  data.todayPlan!.tasks[0].title = "Ôn lại cách xét dấu đạo hàm và trình bày đầy đủ các bước lập bảng biến thiên của hàm số";
  await page.setViewportSize({ width: 390, height: 844 });
  await renderHomeContent(page, data, "dark");
  await expect(page.getByRole("progressbar", { name: "Mức độ nắm vững 0 phần trăm", exact: true })).toHaveAttribute("value", "0");
  await page.getByRole("button", { name: "Xem thêm 2 nhiệm vụ", exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await expect(page.getByRole("button", { name: "Thu gọn danh sách", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("populated-dark-mobile.png"), fullPage: true });
});

test("priority order and knowledge preview keep actual data and the Coach opens the existing workflow", async ({ page }, info) => {
  const data = populatedHome();
  data.knowledgeRegions = [
    { id: "region-a", label: "Ứng dụng đạo hàm", progress: 0, state: "weak", accent: "mint" },
    { id: "region-b", label: "Nguyên hàm và tích phân", state: "not_started", accent: "aqua" },
    { id: "region-c", label: "Xác suất có điều kiện", progress: 72, state: "developing", accent: "sky" },
    { id: "region-d", label: "Tọa độ trong không gian", state: "not_started", accent: "amber" },
  ];
  await page.setViewportSize({ width: 1440, height: 1000 });
  await renderHomeContent(page, data);
  const priorities = page.getByRole("region", { name: "Lộ trình khắc phục & luyện tập ưu tiên", exact: true });
  await expect(priorities.getByRole("listitem")).toHaveCount(2);
  await expect(priorities.getByLabel("Ưu tiên 1", { exact: true })).toHaveText("1");
  const forest = page.getByRole("region", { name: "Khu rừng tri thức", exact: true });
  await expect(forest.getByRole("listitem")).toHaveCount(3);
  await expect(forest.getByRole("link", { name: /Ứng dụng đạo hàm/ })).toHaveAttribute("href", "/student/knowledge?subject_id=subject-ref&node=region-a");
  await expect(forest.getByText("Cần chăm sóc · 0%", { exact: true })).toBeVisible();
  await expect(forest.getByText("Chưa bắt đầu", { exact: true })).toBeVisible();
  await expect(forest.getByText("Xem trước 3 trong 4 chủ đề. Các nhánh còn lại nằm trong bản đồ tri thức.", { exact: true })).toBeVisible();
  const coach = page.getByRole("region", { name: "Trợ lý AI Coach dưới tán cây tri thức", exact: true });
  await expect(coach.getByRole("link", { name: "Mở bài tập của tôi", exact: true })).toHaveAttribute("href", "/student/attempts");
  await expect(coach.getByRole("textbox")).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("discovery-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => document.body.dataset.homeTheme = "dark");
  await page.waitForTimeout(220); // Let the existing background-color theme transition settle.
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await forest.screenshot({ path: info.outputPath("forest-dark-mobile.png") });
});

test("roadmap preserves zero and missing dates, uses the concept target and restores focus", async ({ page }, info) => {
  let countdown: number | null = null;
  const mutations: string[] = [];
  await page.route("**/api/student/study-plan", route => {
    if (route.request().method() !== "GET") { mutations.push(route.request().method()); return route.abort(); }
    return route.fulfill({ status: 200, headers: { "access-control-allow-origin": "*" }, json: { hasPlan: true, plan: {
      days_to_exam: countdown, target_date: null, available_daily_minutes: 30, total_tasks: 1, completed_tasks: 0,
      tasks: [{ id: "task", planned_date: "2027-06-20", order_index: 0, status: "PENDING", task_type: "LEARN", estimated_duration_minutes: 10, concept_id: "concept-target", concept_name: "Nguyên hàm", subject_id: "task-subject" }],
    } } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await renderHomeContent(page, populatedHome(), "dark");
  const trigger = page.getByRole("button", { name: "Xem lộ trình 7 ngày", exact: true });
  const dialog = page.getByRole("dialog", { name: "Kế hoạch học 7 ngày", exact: true });
  await trigger.click();
  await expect(dialog.getByText("Chưa có mốc mục tiêu", { exact: true })).toBeVisible();
  await expect(dialog.getByText("230 ngày", { exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("link", { name: "Mở nhiệm vụ", exact: true })).toHaveAttribute("href", "/student/practice?subject_id=task-subject&concept_id=concept-target");
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate(el => el.contains(document.activeElement))).toBe(true);
  await page.screenshot({ path: info.outputPath("roadmap-dark-mobile.png") });
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  countdown = 0;
  await trigger.click();
  await expect(dialog.getByText("Đến mốc mục tiêu hôm nay", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  expect(mutations).toEqual([]);
});
