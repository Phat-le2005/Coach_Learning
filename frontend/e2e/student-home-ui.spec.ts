import { test, expect } from "@playwright/test";
import fs from "node:fs";

test.use({ trace: "off", video: "off", screenshot: "only-on-failure", reducedMotion: "no-preference" });
const manifest = process.env.LIVE_QA_SESSION_FILE;
test.skip(!manifest, "Requires an existing isolated QA student account; never seeds or resets data.");

test("homepage carousel, theme and plan entry preserve read-only browsing", async ({ page }) => {
  const account = JSON.parse(fs.readFileSync(manifest!, "utf8"));
  await page.goto("/login?returnTo=%2Fstudent");
  await page.locator('input[name="email"]').fill(account.email);
  await page.locator('input[name="password"]').fill(account.password);
  await page.locator('button[type="submit"]').click();
  const first = page.getByRole("tab", { name: "1. Vườn tri thức", exact: true });
  await expect(first).toHaveAttribute("aria-selected", "true");
  const mutations: string[] = [];
  page.on("request", request => {
    if (request.method() !== "GET") mutations.push(new URL(request.url()).pathname);
  });
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    const heights: number[] = [];
    for (const [index, name] of ["Vườn tri thức", "Bài viết tay", "Kế hoạch học"].entries()) {
      await page.getByRole("tab", { name: `${index + 1}. ${name}`, exact: true }).click();
      await expect(page.getByRole("tabpanel")).toHaveCount(1);
      await expect(page.getByRole("tabpanel").locator('[class*="heroActions"]').locator("a,button")).toHaveCount(2);
      heights.push((await page.getByRole("region", { name: "Ba cách học cùng EduMS" }).boundingBox())!.height);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    }
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThan(1);
  }
  await page.getByRole("button", { name: "Chuyển sang giao diện tối", exact: true }).click();
  await expect(page.locator("[data-home-theme]")).toHaveAttribute("data-home-theme", "dark");
  const details = page.getByRole("button", { name: "Chi tiết bước học", exact: true });
  if (await details.count()) {
    await details.click();
    const detailDialog = page.getByRole("dialog");
    await expect(detailDialog).toBeVisible();
    const themeColors = await detailDialog.evaluate(el => ({ modal: getComputedStyle(el.querySelector('[class*="modal"]')!).backgroundColor, expected: getComputedStyle(el.closest('[data-home-theme]')!).getPropertyValue('--surface').trim() }));
    expect(themeColors.modal).toBe("rgb(34, 46, 40)");
    await page.keyboard.press("Escape");
    await expect(details).toBeFocused();
  }
  await page.reload();
  await expect(page.locator("[data-home-theme]")).toHaveAttribute("data-home-theme", "dark");
  await first.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "2. Bài viết tay", exact: true })).toHaveAttribute("aria-selected", "true");
  const wind = page.getByRole("button", { name: "Tắt hiệu ứng lá rơi", exact: true });
  await wind.click();
  await expect(page.locator("[data-garden-motion]")).toHaveAttribute("data-garden-motion", "off");
  await page.getByRole("tab", { name: "3. Kế hoạch học", exact: true }).click();
  const create = page.getByRole("tabpanel").getByRole("button", { name: "Lập kế hoạch học", exact: true });
  if (await create.count()) {
    await create.click();
    const dialog = page.getByRole("dialog", { name: "Kế hoạch học của bạn" });
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
  } else {
    await page.getByRole("button", { name: "Xem kế hoạch học", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  }
  expect(mutations).toEqual([]);
  await page.getByRole("heading", { name: "Khu rừng tri thức", exact: true }).scrollIntoViewIfNeeded();
  const header = page.locator("header").filter({ has: page.getByRole("navigation", { name: "Điều hướng học sinh", exact: true }) });
  expect((await header.boundingBox())!.y).toBeCloseTo(0, 0);
  await expect(page.getByRole("heading", { name: "Lộ trình khắc phục & luyện tập ưu tiên", exact: true })).toBeAttached();
  await expect(page.getByRole("heading", { name: "Trợ lý AI Coach dưới tán cây tri thức", exact: true })).toBeAttached();
});

test("goal form preserves choices and remains retryable after an intercepted service error", async ({ page }) => {
  const account = JSON.parse(fs.readFileSync(manifest!, "utf8"));
  await page.goto("/login?returnTo=%2Fstudent");
  await page.locator('input[name="email"]').fill(account.email);
  await page.locator('input[name="password"]').fill(account.password);
  await page.locator('button[type="submit"]').click();
  await page.getByRole("tab", { name: "3. Kế hoạch học", exact: true }).click();
  const create = page.getByRole("tabpanel").getByRole("button", { name: "Lập kế hoạch học", exact: true });
  test.skip(await create.count() === 0, "QA account already has a plan; do not reset it.");
  await create.click();
  const dialog = page.getByRole("dialog", { name: "Kế hoạch học của bạn" });
  await dialog.getByRole("button", { name: "7.0+ Vững cơ bản", exact: true }).click();
  await dialog.getByRole("button", { name: "45 phút", exact: true }).click();
  await dialog.getByLabel("Mốc hoàn thành", { exact: false }).fill("2027-06-20");
  const payloads: Record<string, unknown>[] = [];
  let existingGoal = false;
  await page.route("**/api/student/study-plan", async route => {
    if (route.request().method() !== "POST") return route.continue();
    payloads.push(route.request().postDataJSON());
    if (existingGoal && route.request().postDataJSON().action === "create_goal") {
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: { code: "ACTIVE_GOAL_EXISTS", message: "Mục tiêu hiện có chưa được thay đổi." } }) });
    }
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ message: "Chưa kết nối được dịch vụ kế hoạch." }) });
  });
  await dialog.getByRole("button", { name: "Tạo kế hoạch học", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText("Chưa kết nối được dịch vụ kế hoạch.");
  await expect(dialog.getByRole("button", { name: "45 phút", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(dialog.getByRole("button", { name: "Tạo kế hoạch học", exact: true })).toBeEnabled();
  expect(payloads).toHaveLength(1);
  expect(payloads[0]).toMatchObject({ action: "create_goal", target_score: 7, available_daily_minutes: 45, exam_date: "2027-06-20" });
  expect(typeof payloads[0].subject_id).toBe("string");
  expect(String(payloads[0].subject_id).length).toBeGreaterThan(0);
  existingGoal = true;
  await dialog.getByRole("button", { name: "Tạo kế hoạch học", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText("Mục tiêu hiện có chưa được thay đổi.");
  expect(payloads).toHaveLength(2); // No automatic recalculate on a goal conflict.
  await expect(dialog.getByLabel("Mốc hoàn thành", { exact: false })).toHaveValue("2027-06-20");
  await dialog.getByRole("button", { name: "Dùng mục tiêu hiện có", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Chưa cập nhật được kế hoạch");
  expect(payloads[2]).toMatchObject({ action: "recalculate", horizon_days: 7 });
  await dialog.getByRole("button", { name: "Đóng kế hoạch học", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  const missingDate = await page.request.post("/api/student/study-plan", { data: { action: "create_goal" } });
  expect(missingDate.status()).toBe(400); // Rejects before any backend goal mutation.
});

test("banner rotates after five seconds and pauses for reading, manual pause and reduced motion", async ({ page }) => {
  const account = JSON.parse(fs.readFileSync(manifest!, "utf8"));
  await page.goto("/login?returnTo=%2Fstudent");
  await page.locator('input[name="email"]').fill(account.email);
  await page.locator('input[name="password"]').fill(account.password);
  await page.locator('button[type="submit"]').click();
  const carousel = page.getByRole("region", { name: "Ba cách học cùng EduMS" });
  await page.mouse.move(3, 3);
  await expect(carousel).toHaveAttribute("data-rotation", "running");
  await expect(page.getByRole("tab", { name: "2. Bài viết tay", exact: true })).toHaveAttribute("aria-selected", "true", { timeout: 6500 });
  await carousel.hover();
  await expect(carousel).toHaveAttribute("data-rotation", "paused");
  const selected = await page.getByRole("tab", { selected: true }).getAttribute("id");
  await page.waitForTimeout(5300); // Prove a complete rotation interval passes while reading.
  expect(await page.getByRole("tab", { selected: true }).getAttribute("id")).toBe(selected);
  await page.getByRole("button", { name: "Tạm dừng tự chuyển banner", exact: true }).click();
  await page.mouse.move(3, 3);
  await page.getByRole("navigation", { name: "Điều hướng học sinh", exact: true }).locator("a").first().focus();
  await expect(carousel).toHaveAttribute("data-rotation", "paused");
  await page.getByRole("button", { name: "Bật tự chuyển banner", exact: true }).click();
  await page.mouse.move(3, 3);
  await page.getByRole("navigation", { name: "Điều hướng học sinh", exact: true }).locator("a").first().focus();
  await expect(carousel).toHaveAttribute("data-rotation", "running");
  await expect(page.getByRole("tab", { name: "3. Kế hoạch học", exact: true })).toHaveAttribute("aria-selected", "true", { timeout: 6500 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(carousel).toHaveAttribute("data-rotation", "paused");
  await expect(page.getByRole("button", { name: "Đã giảm chuyển động", exact: true })).toBeDisabled();
});
