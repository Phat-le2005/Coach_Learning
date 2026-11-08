import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const manifest = process.env.LIVE_QA_SESSION_FILE;
test.skip(!manifest, "Requires an explicitly supplied local QA account.");
test.use({ trace: "off", video: "off", screenshot: "only-on-failure" });
const account = () => JSON.parse(fs.readFileSync(manifest!, "utf8"));
const artifacts = process.env.UI_QA_ARTIFACT_DIR;
test.beforeEach(async ({ page }) => {
  const data = account();
  await page.goto("/login?returnTo=%2Fstudent");
  await page.locator('input[name=email]').fill(data.email);
  await page.locator('input[name=password]').fill(data.password);
  await page.locator('button[type=submit]').click();
  await expect(page.getByRole("region", { name: "Ba cách học cùng EduMS" })).toBeVisible();
});

test("student surfaces keep shared navigation, mobile tree controls and theme", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/student/knowledge");
  await expect(page.getByRole("button", { name: "Mở bảng điều khiển", exact: true })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Bảng điều khiển môn học" })).toHaveCount(0);
  await page.getByRole("button", { name: "Mở bảng điều khiển", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Bảng điều khiển môn học" })).toBeVisible();
  await page.getByRole("button", { name: "Thu gọn bảng điều khiển", exact: true }).click();
  await page.getByRole("button", { name: "Bản đồ 2D", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Vũ Trụ Tri Thức", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Khám phá cây 3D", exact: true }).click();
  await expect(page.getByRole("button", { name: "Cây 3D", exact: true })).toBeVisible();
  for (const [route, heading] of [["/student/theory", "Kho lý thuyết"], ["/student/attempts?tab=history", "Bài tập & luyện tập"], ["/account", "Hồ sơ của tôi"]]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Điều hướng học sinh", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  }
  await page.getByRole("button", { name: "Chuyển sang giao diện tối", exact: true }).click();
  await page.goto("/student/theory");
  await expect(page.locator("[data-home-theme]")).toHaveAttribute("data-home-theme", "dark");
  if (artifacts) await page.screenshot({ path: path.join(artifacts, "theory-dark-mobile.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("unmatched theory link offers a document choice, never an unrelated lesson", async ({ page }) => {
  // Synthetic content is supplied to the real reader; no teacher data or database mutation.
  const summary = { id: "qa-derivative", classroom_id: "qa-class", subject_id: "math", title: "Đạo hàm", file_name: "qa.pdf", sha256: "fixture", page_count: 1, status: "PUBLISHED", revision: 1, source_available: false };
  const requests: string[] = [];
  await page.route("**/api/student/theory**", async route => {
    const url = new URL(route.request().url()); requests.push(url.pathname);
    if (url.pathname === "/api/student/theory") return route.fulfill({ json: [summary] });
    return route.fulfill({ json: { ...summary, nodes: [{ id: "qa-node", parent_id: null, kind: "ROOT", title: "Đạo hàm", body: "Nội dung kiểm thử giao diện", latex: null, source_page: 1, source_quote: "", reviewed: true }], ai_model: null, extraction_warning_pages: [], source_outline: [] } });
  });
  await page.goto("/student/theory?topic=Hình%20học%20không%20gian");
  await expect(page.getByRole("heading", { name: "Chọn tài liệu để tiếp tục" })).toBeVisible();
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every(url => url === "/api/student/theory")).toBe(true);
  await page.getByLabel("Chọn tài liệu bài học").selectOption(summary.id);
  await expect(page.getByRole("tab", { name: "Sơ đồ tư duy" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mở PDF gốc trang 1" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Chọn tài liệu để tiếp tục" })).toHaveCount(0);
  expect(new URL(page.url()).searchParams.has("topic")).toBe(false);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    if (width === 390 && await page.getByRole("button", { name: "Đóng bảng chi tiết" }).count()) {
      const drawer = page.locator('[class*="floatingDrawerOverlay"]');
      const bounds = (await drawer.boundingBox())!;
      expect(bounds.height).toBeLessThanOrEqual(900 * .65 + 1);
      expect(bounds.y + bounds.height).toBeLessThan(900 - 70);
    }
    if (artifacts) await page.screenshot({ path: path.join(artifacts, `theory-fixture-${width}.png`), fullPage: true });
  }
});

test("workspace tools stay available and touch mode restores the problem pane", async ({ page }) => {
  const data = account();
  test.skip(!data.attemptId, "Requires a dedicated QA practice attempt.");
  await page.goto(`/student/attempts/${data.attemptId}`);
  const pane = page.locator("aside");
  await expect(pane).toBeVisible();
  const before = (await pane.boundingBox())!.width;
  await page.getByRole("button", { name: "Chế độ viết cảm ứng", exact: true }).click();
  await expect(pane).toHaveCount(0);
  const paperBefore = (await page.getByRole('region',{name:'Không gian giấy A4 viết tay',exact:true}).boundingBox())!.y;
  await page.locator("summary").filter({ hasText: "Công cụ toán" }).click();
  const palette = page.getByRole('group',{name:'Nhận dạng, giấy và góc nhìn',exact:true});
  expect((await palette.boundingBox())!.height).toBeLessThan(300);
  expect(Math.abs((await page.getByRole('region',{name:'Không gian giấy A4 viết tay',exact:true}).boundingBox())!.y-paperBefore)).toBeLessThan(2);
  for (const name of ["Math View", "Khoanh vùng", "Bảng biến thiên", "Tải bài giấy"]) {
    await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "Về MathWorkspace", exact: true }).click();
  await expect(pane).toBeVisible();
  expect(Math.abs((await pane.boundingBox())!.width - before)).toBeLessThan(2);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Chế độ viết cảm ứng", exact: true }).click();
  await expect(page.getByRole("button", { name: "Trích xuất trang", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  if (artifacts) await page.screenshot({ path: path.join(artifacts, "writing-mode-mobile.png") });
  await page.keyboard.press('Escape');
  await expect(palette).not.toBeVisible();
  await page.locator('summary').filter({hasText:'Công cụ toán'}).click();
  expect((await palette.boundingBox())!.height).toBeLessThan(300);
  expect((await palette.boundingBox())!.width).toBeLessThanOrEqual(390);
  await page.getByRole('button',{name:'Bút',exact:true}).click();
  await expect(palette).not.toBeVisible();
});

test("mobile pages prioritize the working content and retain all pen settings", async ({ page }) => {
  const data = account();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/student/attempts?tab=practice');
  const header = page.locator('[class*="hubHeader"]').first();
  await expect(header).toBeVisible();
  expect((await header.boundingBox())!.height).toBeLessThan(200);
  const resume = page.getByRole('heading', { name: 'Bài làm đang thực hiện', exact: true });
  if (await resume.count()) {
    expect((await resume.boundingBox())!.y).toBeLessThan((await page.getByRole('heading', { name:'Bắt đầu một bài làm mới', exact:true }).boundingBox())!.y);
  }
  await expect(page.locator('summary').filter({hasText:'Bài mẫu để thử chấm từng bước'})).toBeVisible();
  test.skip(!data.attemptId, 'Requires an isolated QA practice page.');
  await page.goto(`/student/attempts/${data.attemptId}`);
  const paper = page.getByRole('region', { name:'Không gian giấy A4 viết tay', exact:true });
  await expect(paper).toBeVisible();
  const box=(await paper.boundingBox())!;
  expect(Math.min(844, box.y + box.height) - Math.max(0, box.y)).toBeGreaterThan(844 * .45);
  await page.getByLabel('Màu và độ dày bút', {exact:true}).click();
  await page.getByRole('button',{name:'Màu Xanh lá',exact:true}).click();
  await page.getByRole('button',{name:'Độ dày 3px',exact:true}).click();
  await expect(page.getByRole('button',{name:'Độ dày 3px',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByLabel('Màu và độ dày bút', {exact:true}).click();
});

test("review labels preserve canonical values, corrections and explicit save guards", async ({ page }) => {
  const data=account();
  test.skip(process.env.UI_QA_WRITE!=='1'||!data.attemptId||!data.email.startsWith('ui-qa-'), 'Only a dedicated synthetic QA attempt may be written.');
  const grading: string[]=[];
  page.on('request',r=>{if(r.method()!=='GET'&&/\/(steps|submit)(?:\?|$)/.test(new URL(r.url()).pathname))grading.push(new URL(r.url()).pathname);});
  await page.goto(`/student/attempts/${data.attemptId}?writing=1`);
  const read=()=>page.evaluate(async id=>(await fetch(`/api/v2/math-solutions/attempts/${id}/ink/pages/0`,{headers:{'X-EduMS-BFF':'1'}})).json(),data.attemptId);
  const initial=await read();
  test.skip(initial.strokes.length!==0,'Never clear pre-existing ink to prepare this UI test.');
  const canvas=page.getByLabel('Giấy viết MathCanvas',{exact:true});
  await expect(canvas).toBeVisible();
  const b=(await canvas.boundingBox())!;
  await page.mouse.move(b.x+b.width*.35,b.y+Math.min(b.height*.2,80));await page.mouse.down();await page.mouse.move(b.x+b.width*.45,b.y+Math.min(b.height*.2,80)+6,{steps:5});await page.mouse.up();
  await expect.poll(async()=>(await read()).strokes.length).toBe(1);
  await page.getByRole('button',{name:'Trích xuất trang',exact:true}).click();
  const modal=page.getByTestId('ocr-v2-main-review');
  await expect(modal).toBeVisible();await expect(modal).toHaveAttribute('aria-busy','false',{timeout:60000});
  await modal.getByTestId('ocr-v2-kind').selectOption('TEXT');
  await modal.getByTestId('ocr-v2-content').fill('Nội dung kiểm thử giao diện');
  await modal.getByTestId('ocr-v2-approve').click();
  await modal.locator('summary').filter({hasText:'Lưu thành bước giải'}).click();
  await expect(modal.getByTestId('ocr-v2-prepare-save')).toBeDisabled();
  await modal.getByTestId('ocr-v2-order').click();
  await modal.getByTestId('ocr-v2-boundary').check();
  await modal.getByTestId('ocr-v2-step-kind').selectOption({label:'Diễn giải'});
  expect(await modal.getByTestId('ocr-v2-step-kind').inputValue()).toBe('EXPLANATION');
  await expect(modal.getByTestId('ocr-v2-prepare-save')).toBeEnabled();
  if(artifacts)await page.screenshot({path:path.join(artifacts,'review-real-pipeline-desktop.png')});
  await modal.getByRole('button',{name:'Đóng',exact:true}).click();await expect(modal).toHaveCount(0);await page.reload();
  await page.getByRole('button',{name:'Trích xuất trang',exact:true}).click();await expect(modal).toHaveAttribute('aria-busy','false');
  await expect(modal.getByTestId('ocr-v2-content')).toHaveValue('Nội dung kiểm thử giao diện');
  await expect(modal.getByTestId('ocr-v2-kind')).toHaveValue('TEXT');
  await expect(modal.getByTestId('ocr-v2-prepare-save')).toBeDisabled();
  await page.setViewportSize({width:390,height:844});
  if(artifacts)await page.screenshot({path:path.join(artifacts,'review-real-pipeline-mobile.png')});
  await modal.getByRole('button',{name:'Đóng',exact:true}).click();
  await page.locator('summary').filter({hasText:'Công cụ toán'}).click();
  page.once('dialog',d=>d.accept());await page.getByTitle('Xóa trắng trang hiện tại',{exact:true}).click();
  await expect.poll(async()=>(await read()).strokes.length).toBe(0);
  expect(grading).toEqual([]);
});
