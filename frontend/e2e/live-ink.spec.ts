import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";

// Auth cookies and single-use tickets must not be written into Playwright traces.
test.use({ trace: "off", video: "off", screenshot: "only-on-failure" });

// Deliberate opt-in: the harness owns an isolated DB, uses real login and APIs.
const manifest = process.env.LIVE_QA_SESSION_FILE;
test.skip(!manifest, "Start the isolated live_sync_harness and supply LIVE_QA_SESSION_FILE");
test("desktop/mobile stream before pointerup, persist, reverse direction and reconnect without loss", async ({ browser }) => {
  test.setTimeout(180000);
  const session = JSON.parse(fs.readFileSync(manifest!, "utf8"));
  expect(session.source).toBe("DISPOSABLE_QA_POINTER_REPLAY");
  const base = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3050";
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  const a = await desktop.newPage(), b = await mobile.newPage();
  const mutations: string[] = [];
  for (const page of [a, b]) page.on("request", request => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method()) && /\/api\/v[23]\//.test(request.url())) mutations.push(request.url());
  });
  async function login(page: Page, writing: boolean) {
    const target = `/student/attempts/${session.attemptId}?live=1&writing=${writing ? 1 : 0}`;
    await page.goto(`${base}/login?returnTo=${encodeURIComponent(target)}`);
    await page.locator('input[name="email"]').fill(session.email);
    await page.locator('input[name="password"]').fill(session.password);
    await page.locator('button[type="submit"]').click();
    await expect(page.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected", { timeout: 60000 });
  }
  async function read(page: Page, index = 0) {
    return page.evaluate(async ({ attemptId, index }) => {
      const response = await fetch(`/api/v2/math-solutions/attempts/${attemptId}/ink/pages/${index}`, { headers: { "X-EduMS-BFF": "1" } });
      return response.json();
    }, { attemptId: session.attemptId, index });
  }
  async function drawStart(page: Page, x: number, y: number) {
    const canvas = page.getByLabel("Giấy viết MathCanvas", { exact: true });
    await canvas.scrollIntoViewIfNeeded();
    const box = (await canvas.boundingBox())!;
    await page.mouse.move(box.x + box.width * x, box.y + box.height * y);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * (x + .08), box.y + box.height * (y + .03), { steps: 5 });
  }
  try {
    await login(a, false); await login(b, true);
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await drawStart(b, .2, .15);
    await expect(a.locator("[data-live-draft]")).toHaveCount(1);
    expect((await read(a)).strokes).toHaveLength(0); // Still pointer down; no durable commit yet.
    await a.screenshot({ path: `${process.env.LIVE_QA_ARTIFACT_DIR}/stream-before-pointerup.png` });
    await b.mouse.up();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(1);
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-pending", "0");
    await a.reload();
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    expect((await read(a)).strokes).toHaveLength(1);
    await drawStart(a, .35, .18);
    await expect(b.locator("[data-live-draft]")).toHaveCount(1);
    await a.mouse.up();
    await expect.poll(async () => (await read(b)).strokes.length).toBe(2);
    // Actual concurrent pointer streams and competing DB writes.
    await Promise.all([drawStart(a, .5, .22), drawStart(b, .65, .26)]);
    await Promise.all([a.mouse.up(), b.mouse.up()]);
    await expect.poll(async () => (await read(a)).strokes.length).toBe(4);
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-pending", "0");
    await mobile.setOffline(true);
    await drawStart(b, .2, .3); await b.mouse.up();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-pending", "1");
    await drawStart(a, .4, .32); await a.mouse.up();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(5);
    await mobile.setOffline(false);
    await expect.poll(async () => (await read(a)).strokes.length, { timeout: 40000 }).toBe(6);
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    const snapshot = await read(a);
    expect(new Set(snapshot.strokes.map((s: { id: string }) => s.id)).size).toBe(6);
    expect(snapshot.strokes[0].points[0].x).toBeCloseTo(.2, 2);
    expect(snapshot.strokes[0].points[0].y).toBeCloseTo(.15, 2);
    await b.getByRole("button", { name: /Hoàn tác|Undo/ }).click();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(5);
    await b.getByRole("button", { name: /Làm lại|Redo/ }).click();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(6);
    await b.reload();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    expect((await read(b)).strokes.map((s: { id: string }) => s.id).sort()).toEqual(snapshot.strokes.map((s: { id: string }) => s.id).sort());
    expect((await b.getByLabel("Giấy viết MathCanvas", { exact: true }).boundingBox())!.width).toBeLessThan(400);
    await b.keyboard.press("e");
    await drawStart(b, .2, .15); await b.mouse.up();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(5);
    await b.getByRole("button", { name: /Hoàn tác/ }).click();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(6);
    a.once("dialog", dialog => dialog.accept());
    await a.getByTitle("Xóa trắng trang hiện tại").click();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(0);
    await a.getByRole("button", { name: /Hoàn tác/ }).click();
    await expect.poll(async () => (await read(a)).strokes.length).toBe(6);
    await a.getByRole("button", { name: "Thêm trang", exact: true }).click();
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await drawStart(a, .3, .2); await a.mouse.up();
    await expect.poll(async () => (await read(a, 1)).strokes.length).toBe(1);
    await expect(b.getByRole("button", { name: "Trang sau", exact: true })).toBeEnabled();
    await b.getByRole("button", { name: "Trang sau", exact: true }).click();
    await expect(b).toHaveURL(/page=1/);
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await b.reload();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    expect((await read(b, 1)).strokes).toHaveLength(1);
    await a.getByRole("button", { name: "Kết nối thiết bị viết", exact: true }).click();
    await expect(a.getByAltText("Quét mã để kết nối thiết bị viết")).toBeVisible();
    await expect(a.getByRole("dialog")).toContainText("không cần đăng nhập lại");
    await a.getByRole("button", { name: "Đóng", exact: true }).click();
    expect(mutations.filter(url => /\/steps|\/submit|\/evaluate/.test(url))).toEqual([]);
    expect(mutations.filter(url => /\/ink\/pages\/\d+$/.test(url))).toEqual([]); // No legacy PUT alongside live operations.
    await a.getByRole("button", { name: "Dừng đồng bộ", exact: true }).click();
    await expect(a.locator("[data-live-status]")).toHaveCount(0);
    await drawStart(a, .5, .3); await a.mouse.up();
    await expect.poll(async () => (await read(a, 1)).strokes.length).toBe(2);
    expect(mutations.filter(url => /\/ink\/pages\/\d+$/.test(url)).length).toBeGreaterThan(0);
    await b.screenshot({ path: `${process.env.LIVE_QA_ARTIFACT_DIR}/mobile-saved.png` });
    fs.writeFileSync(`${process.env.LIVE_QA_ARTIFACT_DIR}/browser-acceptance.json`, JSON.stringify({
      status: "PASS", source: "BROWSER_POINTER_REPLAY", strokes: snapshot.strokes, revision: snapshot.document_revision,
      streamBeforePointerup: true, twoWay: true, concurrent: true, offlineReconnect: true, persistedAfterReload: true,
      eraseUndo: true, clearUndo: true, pageNavigation: true, pairingQr: "UI_ONLY_LAN_UNVERIFIED",
      legacyAutosaveAfterDisconnect: true,
      mutationPaths: mutations.map(url => new URL(url).pathname),
    }, null, 2));
  } finally { await desktop.close(); await mobile.close(); }
});
