import { test, expect } from "@playwright/test";
import fs from "node:fs";

test.use({ trace: "off", video: "off", screenshot: "only-on-failure" });
const manifest = process.env.WORKSPACE_QA_SESSION_FILE;
test.skip(!manifest, "Requires a separate, empty attempt in the isolated live-ink QA database");

test("touch tools and paired ink reach real OCR and review on the configured origin", async ({ browser }) => {
  test.setTimeout(180000);
  const data = JSON.parse(fs.readFileSync(manifest!, "utf8"));
  const base = process.env.E2E_BASE_URL!;
  const artifacts = process.env.LIVE_QA_ARTIFACT_DIR!;
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const a = await desktop.newPage(), b = await mobile.newPage();
  const mutations: string[] = [], modelAssets: string[] = [];
  a.on("request", request => {
    if (request.method() !== "GET" && /\/steps|\/submit/.test(new URL(request.url()).pathname)) mutations.push(request.url());
  });
  a.on("response", response => { if (response.url().endsWith(".onnx") && response.ok()) modelAssets.push(new URL(response.url()).pathname); });
  const read = () => a.evaluate(async (id: string) => {
    const response = await fetch(`/api/v2/math-solutions/attempts/${id}/ink/pages/0`, { headers: { "X-EduMS-BFF": "1" } });
    if (!response.ok) throw Error(`INK_READ_${response.status}`);
    return response.json();
  }, data.attemptId);
  try {
    await a.goto(`${base}/login?returnTo=${encodeURIComponent(`/student/attempts/${data.attemptId}`)}`);
    await a.locator('input[name="email"]').fill(data.email);
    await a.locator('input[name="password"]').fill(data.password);
    await a.locator('button[type="submit"]').click();
    await expect(a.getByRole("button", { name: "Chế độ viết cảm ứng", exact: true })).toBeVisible();
    // Never overwrite an existing user's capture if the test manifest points at the wrong attempt.
    expect((await read()).strokes).toEqual([]);
    const capabilityNames = [/Khoanh vùng/, /Math View/, /^Bút$/, /Dạ quang/, /^Tẩy$/, /Trích xuất trang/, /Bảng biến thiên/, /Tải bài giấy/];
    const toolbar = a.getByRole("toolbar", { name: "Thanh công cụ vẽ" });
    const names = await toolbar.getByRole("button").evaluateAll(nodes => nodes.map(n => n.getAttribute("title") ?? n.textContent));
    await a.getByRole("button", { name: "Chế độ viết cảm ứng", exact: true }).click();
    expect(await toolbar.getByRole("button").evaluateAll(nodes => nodes.map(n => n.getAttribute("title") ?? n.textContent))).toEqual(names);
    await a.setViewportSize({ width: 390, height: 844 });
    for (const name of capabilityNames) await expect(toolbar.getByRole("button", { name }).first()).toBeVisible();
    expect(await toolbar.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
    await a.screenshot({ path: `${artifacts}/touch-full-toolbar.png` });
    await a.setViewportSize({ width: 1440, height: 1000 });
    await a.getByRole("button", { name: "Về MathWorkspace", exact: true }).click();
    await expect(a.locator("aside")).toBeVisible();

    await a.getByRole("button", { name: "Kết nối thiết bị viết", exact: true }).click();
    const pairing = a.getByRole("dialog");
    await pairing.getByAltText("Quét mã để kết nối thiết bị viết").waitFor();
    await pairing.locator("summary").click();
    await b.goto((await pairing.getByRole("link", { name: "Mở bảng viết trên thiết bị này" }).getAttribute("href"))!);
    await expect(pairing.getByRole("button", { name: "Cho phép viết", exact: true })).toBeVisible();
    await pairing.getByRole("button", { name: "Cho phép viết", exact: true }).click();
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    await pairing.getByRole("button", { name: "Tiếp tục làm bài" }).click();
    const canvas = b.getByLabel("Giấy viết MathCanvas", { exact: true });
    const box = (await canvas.boundingBox())!;
    // BROWSER POINTER REPLAY fixture x=0; not new human handwriting or an accuracy benchmark.
    const paths = [ [[.10,.10],[.14,.14]], [[.14,.10],[.10,.14]], [[.18,.112],[.23,.112]], [[.18,.128],[.23,.128]],
      [[.29,.10],[.30,.105],[.305,.12],[.30,.135],[.29,.14],[.28,.135],[.275,.12],[.28,.105],[.29,.10]] ];
    for (const [index, points] of paths.entries()) {
      await b.mouse.move(box.x + points[0][0] * box.width, box.y + points[0][1] * box.height);
      await b.mouse.down();
      for (const [x,y] of points.slice(1)) await b.mouse.move(box.x + x * box.width, box.y + y * box.height, { steps: 4 });
      if (index === 0) {
        await expect(a.locator("[data-live-draft]")).toHaveCount(1);
        await expect(a.getByRole("button", { name: "Trích xuất trang", exact: true })).toBeDisabled();
        expect((await read()).strokes).toHaveLength(0);
      }
      await b.mouse.up();
      await expect.poll(async () => (await read()).strokes.length).toBe(index + 1);
    }
    await expect(b.locator("[data-live-status]")).toHaveAttribute("data-pending", "0");
    const committed = await read();
    const ids = committed.strokes.map((s: { id: string }) => s.id).sort();
    await a.reload();
    await expect(a.locator("[data-live-status]")).toHaveAttribute("data-live-status", "connected");
    expect((await read()).strokes.map((s: { id: string }) => s.id).sort()).toEqual(ids);
    const context = await a.evaluate(() => ({ secure: window.isSecureContext, subtle: !!crypto.subtle, randomUUID: typeof crypto.randomUUID === "function" }));
    const secureOrigin = new URL(base).protocol === "https:" || ["127.0.0.1", "localhost"].includes(new URL(base).hostname);
    expect(context).toEqual({ secure: secureOrigin, subtle: secureOrigin, randomUUID: secureOrigin });
    await a.getByRole("button", { name: "Trích xuất trang", exact: true }).click();
    const review = a.getByTestId("ocr-v2-main-review");
    await expect(review).toHaveAttribute("aria-busy", "false", { timeout: 90000 });
    await expect(review.getByRole("alert")).toHaveCount(0);
    await expect(review.getByTestId("ocr-v2-unit")).toHaveCount(1);
    const raw = await review.getByTestId("ocr-v2-raw").textContent();
    expect(raw?.trim()).toBeTruthy(); expect(raw).not.toBe("UNRESOLVED");
    await expect(review.getByRole("status")).toContainText("Đã lưu bản chép trên thiết bị");
    const downloadEvidence = async (filename: string) => {
      const event = a.waitForEvent("download");
      await review.getByRole("button", { name: "Xuất bản chép và nguồn nét" }).click();
      const download = await event; await download.saveAs(`${artifacts}/${filename}`);
      return JSON.parse(fs.readFileSync(`${artifacts}/${filename}`, "utf8"));
    };
    const initial = await downloadEvidence("paired-ink-ocr.json");
    expect(initial.ir.sourceSnapshot.strokes.map((s: { id: string }) => s.id).sort()).toEqual(ids);
    expect(initial.evidence[0].sourceStrokeIds.slice().sort()).toEqual(ids);
    expect(initial.evidence[0].status).toBe("COMPLETED");
    expect(initial.evidence[0].result.tokenIds.length).toBeGreaterThan(0);
    expect(initial.evidence[0].result.decoderMs).toBeGreaterThan(0);
    expect(modelAssets).toContain("/ocr/comer/v0_1/encoder_int8.onnx");
    await review.getByTestId("ocr-v2-content").fill("x=5");
    await review.getByTestId("ocr-v2-approve").click();
    await expect(review.getByRole("status")).toContainText("Đã lưu bản chép trên thiết bị");
    await review.getByRole("button", { name: "Nhận diện lại bằng CoMER" }).click();
    await expect(review).toHaveAttribute("aria-busy", "false", { timeout: 90000 });
    await expect(review.getByTestId("ocr-v2-content")).toHaveValue("x=5");
    await review.getByRole("button", { name: "Đóng", exact: true }).click();
    await a.reload();
    await a.getByRole("button", { name: "Trích xuất trang", exact: true }).click();
    await expect(review).toHaveAttribute("aria-busy", "false");
    await expect(review.getByTestId("ocr-v2-content")).toHaveValue("x=5");
    await expect(review.getByTestId("ocr-v2-unit")).toContainText("APPROVED");
    const restored = await downloadEvidence("paired-ink-review-restored.json");
    expect(restored.ir.contentUnits[0].approvedContent).toBe("x=5");
    expect(restored.evidence[0].result.rawLatex).toBe(initial.evidence[0].result.rawLatex);
    expect((await read()).strokes).toEqual(committed.strokes);
    expect(mutations).toEqual([]);
    await a.screenshot({ path: `${artifacts}/paired-ink-ocr-review.png` });
    fs.writeFileSync(`${artifacts}/acceptance.json`, JSON.stringify({ status: "PASS", inputKind: "BROWSER_POINTER_REPLAY", context,
      pairedStrokeIds: ids, sourceRevision: committed.document_revision, rawCoMER: raw, modelAssets,
      evidence: initial.evidence, savedCorrection: "x=5", survivesRetryAndReload: true, gradingMutations: mutations }, null, 2));
  } finally { await desktop.close(); await mobile.close(); }
});
