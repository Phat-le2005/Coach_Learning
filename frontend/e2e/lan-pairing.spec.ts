import { test, expect } from "@playwright/test";
import fs from "node:fs";

test.use({trace: "off", video: "off", screenshot: "only-on-failure"});
test.skip(!process.env.LAN_QA_SESSION_FILE, "Requires a new disposable QA attempt and LAN-enabled servers");

test("localhost owner pairs a logged-out LAN writer with real two-way ink and durable reload", async ({browser}) => {
  const data = JSON.parse(fs.readFileSync(process.env.LAN_QA_SESSION_FILE!, "utf8"));
  expect(data.source).toBe("DISPOSABLE_QA_POINTER_REPLAY");
  const desktop = await browser.newContext();
  const mobile = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
  const a = await desktop.newPage(), b = await mobile.newPage();
  const base = process.env.E2E_BASE_URL || "http://localhost:3050";
  const mutations: string[] = [];
  a.on("request", r => {if (r.method() !== "GET" && /\/steps|\/submit/.test(r.url())) mutations.push(r.url());});
  const read = () => a.evaluate(async (id: string) => {
    const r = await fetch(`/api/v2/math-solutions/attempts/${id}/ink/pages/0`, {headers: {"X-EduMS-BFF": "1"}});
    if (!r.ok) throw Error(`INK_READ_${r.status}`);
    return r.json();
  }, data.attemptId);
  const draw = async (page: typeof a, x: number) => {
    const canvas = page.getByLabel("Giấy viết MathCanvas", {exact: true});
    await canvas.scrollIntoViewIfNeeded();
    const box = (await canvas.boundingBox())!;
    await page.mouse.move(box.x + box.width * x, box.y + box.height * .2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * (x + .08), box.y + box.height * .23, {steps: 5});
  };
  try {
    expect((await mobile.request.get(`${base}/api/lan`)).status()).toBe(401);
    await a.goto(`${base}/login?returnTo=${encodeURIComponent(`/student/attempts/${data.attemptId}`)}`);
    await a.locator('input[name="email"]').fill(data.email);
    await a.locator('input[name="password"]').fill(data.password);
    await a.locator('button[type="submit"]').click();
    await expect(a.getByRole("button", {name: "Kết nối thiết bị viết", exact: true})).toBeVisible();
    expect((await read()).strokes).toEqual([]); // Never modify a non-empty user capture.
    const network = await (await desktop.request.get(`${base}/api/lan`)).json();
    expect(network.enabled).toBe(true);
    expect(network.origin).not.toContain("localhost");
    await a.getByRole("button", {name: "Kết nối thiết bị viết", exact: true}).click();
    const dialog = a.getByRole("dialog");
    await dialog.getByAltText("Quét mã để kết nối thiết bị viết").waitFor();
    await dialog.locator("summary").click();
    const link = (await dialog.getByRole("link", {name: "Mở bảng viết trên thiết bị này"}).getAttribute("href"))!;
    expect(new URL(link).origin).toBe(network.origin);
    await b.goto(link);
    await expect(dialog.getByRole("button", {name: "Cho phép viết", exact: true})).toBeVisible();
    await dialog.getByRole("button", {name: "Cho phép viết", exact: true}).click();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await dialog.getByRole("button", {name: "Tiếp tục làm bài"}).click();
    await draw(b, .15);
    await expect(a.locator("[data-live-draft]")).toHaveCount(1);
    expect((await read()).strokes).toHaveLength(0);
    await b.mouse.up();
    await expect.poll(async () => (await read()).strokes.length).toBe(1);
    await draw(a, .4);
    await expect(b.locator("[data-live-draft]")).toHaveCount(1);
    await a.mouse.up();
    await expect.poll(async () => (await read()).strokes.length).toBe(2);
    const ids = (await read()).strokes.map((s: {id: string}) => s.id).sort();
    await a.reload();
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    expect((await read()).strokes.map((s: {id: string}) => s.id).sort()).toEqual(ids);
    expect(mutations).toEqual([]);
    const dir = process.env.LIVE_QA_ARTIFACT_DIR!;
    fs.mkdirSync(dir, {recursive: true});
    await a.screenshot({path: `${dir}/desktop.png`});
    await b.screenshot({path: `${dir}/writer.png`});
    fs.writeFileSync(`${dir}/lan-browser.json`, JSON.stringify({status: "PASS", source: data.source, network,
      desktopOrigin: new URL(a.url()).origin, writerOrigin: new URL(b.url()).origin, strokeIds: ids, gradingMutations: mutations}, null, 2));
  } finally {await desktop.close(); await mobile.close();}
});
