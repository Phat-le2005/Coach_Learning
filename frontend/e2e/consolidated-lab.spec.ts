import { test, expect } from "@playwright/test";
import fs from "node:fs";

test.use({ trace: "off", video: "off", screenshot: "only-on-failure" });
const manifest = process.env.WORKSPACE_QA_SESSION_FILE;
test.skip(!manifest, "Requires isolated QA credentials and the real development Lab");

test("clean checkout Lab supports real CoMER and annotation without private datasets", async ({ page }) => {
  test.setTimeout(120000);
  const credentials = JSON.parse(fs.readFileSync(manifest!, "utf8"));
  const writes: string[] = [];
  page.on("request", r => { if (r.method() !== "GET" && /\/steps|\/submit/.test(new URL(r.url()).pathname)) writes.push(r.url()); });
  await page.goto(`${process.env.E2E_BASE_URL}/login?returnTo=/ocr-v2-lab`);
  await page.locator('input[name="email"]').fill(credentials.email);
  await page.locator('input[name="password"]').fill(credentials.password);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/ocr-v2-lab$/);
  await expect(page.getByTestId("v2-live-canvas")).toBeVisible();
  const catalogue = await page.request.get("/api/ocr-v2-lab/htr");
  expect(catalogue.ok()).toBe(true);
  expect((await catalogue.json()).candidates).toEqual([]); // No private three-crop catalogue.
  const paths = [ [[.1,.1],[.14,.14]], [[.14,.1],[.1,.14]], [[.18,.112],[.23,.112]], [[.18,.128],[.23,.128]],
    [[.29,.1],[.30,.105],[.305,.12],[.30,.135],[.29,.14],[.28,.135],[.275,.12],[.28,.105],[.29,.1]] ];
  const strokes = paths.map((points,i) => ({ id: `software-ink-${i}`, tool: "PEN", color: "#101010", width: 2, points: points.map(([x,y]) => ({x,y,pressure:.5})) }));
  const file = { schemaVersion: "ocr-v2-experimental/1", source: { pageIndex: 0, strokes } };
  await page.getByLabel("Import capture V2", { exact: true }).setInputFiles({name: "software-fixture.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(file))});
  await page.getByLabel("Nguồn nét V2", { exact: true }).selectOption("SYNTHETIC_INK");
  await page.getByLabel("Chế độ OCR V2", { exact: true }).selectOption("GEOMETRY");
  await page.getByTestId("v2-run").click();
  await expect(page.getByTestId("ocr-v2-panel")).toHaveAttribute("aria-busy", "false", {timeout: 90000});
  await expect(page.getByTestId("v2-wrapper-output")).not.toHaveText("UNRESOLVED");
  await expect(page.getByTestId("v2-pre-repair")).not.toBeEmpty();
  const popup = page.waitForEvent("popup");
  await page.getByTestId("eval-transfer").click();
  const annotation = await popup;
  await expect(annotation).toHaveURL(/\/ocr-v2-lab\/evaluation\?transfer=/);
  await expect(annotation.locator("body")).toContainText("MathCanvas trang 1");
  expect(writes).toEqual([]);
  if (process.env.LIVE_QA_ARTIFACT_DIR) await page.screenshot({path: `${process.env.LIVE_QA_ARTIFACT_DIR}/clean-lab.png`});
});
