import {test, expect, type Page} from "@playwright/test";
import fs from "node:fs";

test.use({trace: "off", video: "off", screenshot: "only-on-failure"});
const manifest = process.env.LIVE_QA_SESSION_FILE;
test.skip(!manifest, "Requires the isolated QA server");
test("restore workspace layout and pair a logged-out phone with explicit owner approval", async ({browser}) => {
  test.setTimeout(120000);
  const data = JSON.parse(fs.readFileSync(manifest!, "utf8"));
  const base = process.env.E2E_BASE_URL ?? "http://172.20.10.4:3050";
  const artifacts = process.env.LIVE_QA_ARTIFACT_DIR!;
  const desktop = await browser.newContext({viewport: {width: 1440, height: 1000}});
  const mobile = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 2});
  const a = await desktop.newPage(), b = await mobile.newPage();
  const phoneRequests: string[] = [];
  b.on("request", request => phoneRequests.push(new URL(request.url()).pathname));
  const read = () => a.evaluate(async (attemptId: string) => {
    const response = await fetch(`/api/v2/math-solutions/attempts/${attemptId}/ink/pages/0`, {headers: {"X-EduMS-BFF": "1"}});
    return response.json();
  }, data.attemptId);
  try {
    await a.goto(`${base}/login?returnTo=${encodeURIComponent(`/student/attempts/${data.attemptId}`)}`);
    await a.locator('input[name="email"]').fill(data.email); await a.locator('input[name="password"]').fill(data.password);
    await a.locator('button[type="submit"]').click();
    await expect(a.getByRole("button", {name: "Chế độ viết cảm ứng", exact: true})).toBeVisible();
    const before = (await a.locator("aside").boundingBox())!;
    expect(before.width).toBeGreaterThan(200);
    const original = await read();
    await a.getByRole("button", {name: "Chế độ viết cảm ứng", exact: true}).click();
    await expect(a.locator("aside")).toHaveCount(0);
    await a.getByRole("button", {name: "Về MathWorkspace", exact: true}).click();
    await expect(a.locator("aside")).toBeVisible();
    expect(Math.abs((await a.locator("aside").boundingBox())!.width - before.width)).toBeLessThan(2);
    await a.getByRole("button", {name: "Thu gọn đề bài", exact: true}).click();
    const collapsedWidth = (await a.locator("aside").boundingBox())!.width;
    await a.getByRole("button", {name: "Chế độ viết cảm ứng", exact: true}).click();
    await a.getByRole("button", {name: "Về MathWorkspace", exact: true}).click();
    expect(Math.abs((await a.locator("aside").boundingBox())!.width - collapsedWidth)).toBeLessThan(2);
    await a.getByRole("button", {name: "Mở rộng bảng đề bài", exact: true}).click();
    await a.getByRole("button", {name: "Kết nối thiết bị viết", exact: true}).click();
    const modal = a.getByRole("dialog");
    await expect(modal.getByAltText("Quét mã để kết nối thiết bị viết")).toBeVisible();
    await expect(modal).not.toContainText("frontend");
    await expect(modal).not.toContainText("connected");
    await a.screenshot({path: `${artifacts}/pairing-new-desktop.png`});
    await modal.locator("summary").click();
    const link = await modal.getByRole("link", {name: "Mở bảng viết trên thiết bị này"}).getAttribute("href");
    expect(link).toContain("/write#code=");
    await b.goto(link!);
    await expect(b.getByRole("heading", {name: "Chỉ còn một bước nữa"})).toBeVisible();
    await expect(b).toHaveURL(new URL("/write", link!).toString()); // One-use secret removed from browser address.
    const denied = await b.evaluate(async () => (await fetch("/api/ink-device/ink/pages/0")).status);
    expect(denied).toBe(403);
    const cookie = (await mobile.cookies()).find(value => value.name === "edums_ink_device");
    expect(cookie?.httpOnly).toBe(true);
    expect((await mobile.cookies()).some(value => ["edums_access", "edums_session", "edums_refresh"].includes(value.name))).toBe(false);
    await expect(modal.getByRole("button", {name: "Cho phép viết", exact: true})).toBeVisible();
    await modal.getByRole("button", {name: "Cho phép viết", exact: true}).click();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected", {timeout: 30000});
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await modal.getByRole("button", {name: "Tiếp tục làm bài"}).click();
    await b.screenshot({path: `${artifacts}/pairing-new-phone.png`});
    const canvas = b.getByLabel("Giấy viết MathCanvas", {exact: true});
    const box = (await canvas.boundingBox())!;
    expect(box.width).toBeLessThan(400);
    await b.mouse.move(box.x + box.width * .75, box.y + box.height * .4);
    await b.mouse.down(); await b.mouse.move(box.x + box.width * .85, box.y + box.height * .44, {steps: 5});
    await expect(a.locator("[data-live-draft]")).toHaveCount(1);
    expect((await read()).strokes.length).toBe(original.strokes.length);
    await b.mouse.up();
    await expect.poll(async () => (await read()).strokes.length).toBe(original.strokes.length + 1);
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-pending", "0");
    await mobile.setOffline(true);
    await b.waitForTimeout(3000); // Let the device-session poll fail; the canvas must stay mounted.
    await expect(canvas).toBeVisible();
    await b.mouse.move(box.x + box.width * .55, box.y + box.height * .35);
    await b.mouse.down(); await b.mouse.move(box.x + box.width * .6, box.y + box.height * .36, {steps: 3}); await b.mouse.up();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-pending", "1");
    await mobile.setOffline(false);
    await expect.poll(async () => (await read()).strokes.length, {timeout: 30000}).toBe(original.strokes.length + 2);
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-pending", "0");
    await b.getByRole("button", {name: "Hoàn tác", exact: true}).click();
    await expect.poll(async () => (await read()).strokes.length).toBe(original.strokes.length + 1);
    await b.getByRole("button", {name: "Hoàn tác", exact: true}).click();
    await expect.poll(async () => (await read()).strokes.length).toBe(original.strokes.length);
    expect((await read()).strokes.map((stroke: {id: string}) => stroke.id).sort()).toEqual(original.strokes.map((stroke: {id: string}) => stroke.id).sort());
    await b.reload();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await a.getByRole("button", {name: "Thiết bị viết (Đang kết nối)", exact: true}).click();
    await a.getByRole("button", {name: "Ngắt thiết bị", exact: true}).click();
    await expect(b.getByRole("heading", {name: "Chưa thể kết nối"})).toBeVisible({timeout: 15000});
    expect(await b.evaluate(async () => (await fetch("/api/ink-device/ink/pages/0")).status)).toBe(401);
    expect(phoneRequests.filter(path => path === "/auth/login" || /\/steps|\/submit/.test(path))).toEqual([]);
    fs.writeFileSync(`${artifacts}/ux-acceptance.json`, JSON.stringify({status: "PASS", source: "TWO_BROWSER_CONTEXTS_POINTER_REPLAY",
      restoredExpandedLayout: true, phoneLoggedIn: false, approvalRequired: true, streamedBeforePointerUp: true,
      persisted: true, offlineCanvasPreserved: true, survivesReload: true, revocationEnforced: true, originalStrokeIdsPreserved: true,
      originalStrokeCount: original.strokes.length}, null, 2));
  } finally {await desktop.close(); await mobile.close();}
});
