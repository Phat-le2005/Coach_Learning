import { expect, test, type Page, type BrowserContext } from "@playwright/test";
import { signSession } from "../src/lib/auth/session-codec";
import { AUTH_COOKIES } from "../src/lib/auth/constants";
import type { SolutionAttemptRead } from "../src/lib/api/contracts";
import fixture from "./fixtures/gemini-review.json";

test.skip(!process.env.GEMINI_REVIEW_E2E_SECRET, "Use playwright.gemini-review.config.ts; no live database.");
const raw = String.raw`y' = 2x
y' = 0 \Leftrightarrow 3x^2 - 3 = 0
\begin{cases}x = 1 \\ x = -1\end{cases}
\begin{array}{c|ccccc}x & -\infty & -1 & 0 & 1 & +\infty \\ y' & + & 0 & - & 0 & +\end{array}`;

async function open(page: Page, context: BrowserContext, baseURL: string, failOcr = false, split = false) {
  if (baseURL !== "http://127.0.0.1:3108") throw Error("Requires isolated Gemini UI server");
  const signed = await signSession({ v: 1, userId: "gemini-ui-test", email: "student@example.test",
    fullName: "Học sinh kiểm thử", role: "STUDENT", expiresAt: Date.now() + 600_000 },
  process.env.GEMINI_REVIEW_E2E_SECRET!);
  await context.addCookies([
    { name: AUTH_COOKIES.session, value: signed, url: baseURL, httpOnly: true, sameSite: "Lax" },
    { name: AUTH_COOKIES.access, value: "isolated-test-access", url: baseURL, httpOnly: true, sameSite: "Lax" },
  ]);
  const state = { attempt: structuredClone(fixture.attempt) as SolutionAttemptRead,
    ocrCalls: 0, gradeCalls: 0, submitCalls: 0, assets: [] as string[],
    rejectNextStep: false, stepRequests: [] as unknown[], gradedStepCount: 0 };
  page.on("request", request => { if (request.url().endsWith(".onnx")) state.assets.push(request.url()); });
  await page.route("**/auth/me", route => route.fulfill({ json: { role: "STUDENT" } }));
  await page.route("**/auth/csrf", route => route.fulfill({ json: { csrf_token: "isolated-ui-token" } }));
  await page.route(/\/api\/v[23]\/math-solutions\//, async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let body: unknown = state.attempt;
    if (path.endsWith("/ocr/recognize")) {
      state.ocrCalls++;
      if (failOcr) return route.fulfill({ status: 503, json: { error: { code: "OCR_RECOGNITION_FAILED", message: "Gemini đang bận. Thử lại sau." } } });
      body = { latex: raw, confidence: .9, suggested_step_type: "CUSTOM", explanation_text: null,
        detected_symbols: [], alternative_latex: [], steps: split ? [
          { title:"Tính đạo hàm",content_kind:"MATH",latex:"y'=2x",explanation_text:null,suggested_step_type:"DERIVATIVE_CALCULATION",source_stroke_ids:fixture.page.strokes.slice(0,2).map(s=>s.id) },
          { title:"Giải phương trình đạo hàm",content_kind:"MATH",latex:String.raw`y'=0 \Leftrightarrow x=1 \lor x=-1`,explanation_text:null,suggested_step_type:"ROOT_FINDING",source_stroke_ids:fixture.page.strokes.slice(2,4).map(s=>s.id) },
          { title:"Lập bảng biến thiên",content_kind:"MATH",latex:String.raw`\begin{array}{c|ccc}x&-1&1&+\infty\\y'&0&0&+\\y&2&-2&+\infty\end{array}`,explanation_text:null,suggested_step_type:"VARIATION_TABLE",source_stroke_ids:fixture.page.strokes.slice(4).map(s=>s.id) },
        ] : [{ title:"Bản chép",content_kind:"MATH",latex:raw,explanation_text:null,suggested_step_type:"CUSTOM",source_stroke_ids:fixture.page.strokes.map(s=>s.id) }] };
    } else if (path.endsWith("/steps") && request.method() === "POST") {
      const payload = request.postDataJSON();
      state.stepRequests.push(payload);
      if (state.rejectNextStep) {
        state.rejectNextStep = false;
        return route.fulfill({ status: 503, json: { error: { code: "TEMPORARY_UNAVAILABLE", message: "Connection interrupted" } } });
      }
      const index = (state.attempt.steps?.length ?? 0) + 1;
      state.attempt.steps = [...(state.attempt.steps ?? []), { id: `00000000-0000-4000-8000-${String(200+index).padStart(12,"0")}`, step_index: index,
        step_revision_number: 1, ...payload }];
      state.attempt.current_revision++;
      state.attempt.status = "IN_PROGRESS";
    } else if (path.endsWith("/submit")) {
      state.submitCalls++;
      state.attempt.status = "SUBMITTED";
      state.attempt.current_revision++;
    } else if (path.endsWith("/ai-review")) {
      if (request.method() === "GET") body = { available: true, reason_code: null };
      else {
        state.gradeCalls++;
        state.gradedStepCount = state.attempt.steps?.length ?? 0;
        body = { attempt_id: fixture.attempt.id, is_final: false, needs_teacher_review: false,
          review_source: "ANSWER_GROUNDED_AI", final_score: null,
          step_grades: state.attempt.steps!.map(step => ({ step_index: step.step_index, verdict: "VALID", score: null, confidence: .95,
            feedback: "Bản đã xác nhận khớp với dữ liệu lời giải của bài." })) };
      }
    } else if (path.endsWith("/problem")) body = fixture.problem;
    else if (path.endsWith("/ink")) body = fixture.document;
    else if (path.endsWith("/ink/pages/0")) body = fixture.page;
    await route.fulfill({ json: body });
  });
  await page.goto(`/student/attempts/${fixture.attempt.id}`);
  await expect(page.locator("aside").getByRole("button", { name: "Nộp bài & kiểm tra", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Trích xuất trang", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Trích xuất trang (OCR)", exact: true }).click();
  const review = page.getByTestId("ocr-v2-main-review");
  await expect(review).toHaveAttribute("aria-busy", "false");
  return { state, review };
}

test("corrected OCR is saved and submitted without a second OCR overwriting it", async ({ page, context, baseURL }, testInfo) => {
  const { state, review } = await open(page, context, baseURL!);
  const corrected = raw.replace("y' = 2x", "y' = 3x^2 - 3");
  await review.getByTestId("ocr-v2-content").fill(corrected);
  const preview = review.getByTestId("ocr-v2-math-preview");
  await expect(preview.locator(".katex-display")).toBeVisible();
  await review.getByTestId("ocr-v2-step-kind").selectOption("CUSTOM");
  await review.getByTestId("ocr-v2-boundary").check();
  await expect(review.getByTestId("ocr-v2-prepare-save")).toBeEnabled();
  await review.getByTestId("ocr-v2-content").fill(corrected + " ");
  await expect(review.getByTestId("ocr-v2-boundary")).not.toBeChecked();
  await expect(review.getByTestId("ocr-v2-prepare-save")).toBeDisabled();
  await review.getByTestId("ocr-v2-boundary").check();
  await page.screenshot({ path: testInfo.outputPath("corrected-transcription.png") });
  const saveBounds = await review.getByTestId("ocr-v2-prepare-save").boundingBox();
  expect(saveBounds!.y + saveBounds!.height).toBeLessThanOrEqual(1000);
  await page.setViewportSize({ width: 1366, height: 768 });
  const laptopSave = await review.getByTestId("ocr-v2-prepare-save").boundingBox();
  expect(laptopSave!.y + laptopSave!.height).toBeLessThanOrEqual(768);
  await page.screenshot({ path: testInfo.outputPath("review-laptop.png") });
  await review.getByTestId("ocr-v2-prepare-save").click();
  await expect.poll(() => state.attempt.steps?.[0]?.content_latex).toBe(corrected);
  await expect(review.getByText("Đã lưu 1 bước giải vào bài làm", { exact: true })).toBeVisible();
  await review.getByRole("button", { name: "Đóng & tiếp tục", exact: true }).click();
  await page.locator("aside").getByRole("button", { name: "Nộp bài & kiểm tra", exact: true }).click();
  await expect.poll(() => state.gradeCalls).toBe(1);
  expect(state.submitCalls).toBe(1);
  expect(state.ocrCalls).toBe(1);
  expect(state.attempt.steps![0].content_latex).toBe(corrected);
  expect(state.assets).toEqual([]);
});

test("Gemini failure leaves a manually editable draft and never downloads a fallback model", async ({ page, context, baseURL }) => {
  const { state, review } = await open(page, context, baseURL!, true);
  await expect(review.getByRole("alert")).toContainText("Gemini đang bận");
  await review.getByTestId("ocr-v2-content").fill("y'=3x^2-3");
  await review.getByTestId("ocr-v2-step-kind").selectOption("CUSTOM");
  await review.getByTestId("ocr-v2-boundary").check();
  await expect(review.getByTestId("ocr-v2-prepare-save")).toBeEnabled();
  expect(state.ocrCalls).toBe(1);
  expect(state.gradeCalls).toBe(0);
  expect(state.assets).toEqual([]);
});

test("mobile keeps save controls visible and restores corrections after closing", async ({ page, context, baseURL }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { state, review } = await open(page, context, baseURL!);
  await expect(review.getByTestId("ocr-v2-content")).toBeVisible();
  const panels = review.getByRole("group", { name: "Chế độ đối chiếu" });
  await panels.getByRole("button", { name: "Nét gốc", exact: true }).click();
  await expect(review.getByRole("img", { name: "Nét viết tay đã gửi để nhận diện" })).toBeVisible();
  await panels.getByRole("button", { name: "Bản chép", exact: true }).click();
  const corrected = "y'=3x^2-3\nx=1 \\lor x=-1";
  await review.getByTestId("ocr-v2-content").fill(corrected);
  await review.getByTestId("ocr-v2-step-kind").selectOption("CUSTOM");
  await review.getByTestId("ocr-v2-boundary").check();
  const button = review.getByTestId("ocr-v2-prepare-save");
  const bounds = await button.boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(844);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  expect(await review.evaluate(element => element.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("review-mobile.png") });
  await review.getByRole("button", { name: "Đóng", exact: true }).click();
  await page.getByRole("button", { name: "Trích xuất trang", exact: true }).click();
  await expect(review).toHaveAttribute("aria-busy", "false");
  await expect(review.getByTestId("ocr-v2-content")).toHaveValue(corrected);
  expect(state.ocrCalls).toBe(1);
  expect(state.attempt.steps).toEqual([]);
});

test("interrupted saving resumes the exact confirmed content and action", async ({ page, context, baseURL }) => {
  const { state, review } = await open(page, context, baseURL!);
  await review.getByTestId("ocr-v2-content").fill("y'=3x^2-3");
  await review.getByTestId("ocr-v2-step-kind").selectOption("CUSTOM");
  await review.getByTestId("ocr-v2-boundary").check();
  state.rejectNextStep = true;
  await review.getByTestId("ocr-v2-prepare-save").click();
  await expect(review.getByRole("button", { name: "Thử lưu lại", exact: true })).toBeEnabled();
  await expect(review.getByTestId("ocr-v2-content")).toBeDisabled();
  await review.getByRole("button", { name: "Thử lưu lại", exact: true }).click();
  await expect(review.getByText("Đã lưu 1 bước giải vào bài làm", { exact: true })).toBeVisible();
  expect(state.stepRequests).toHaveLength(2);
  expect(state.stepRequests[1]).toEqual(state.stepRequests[0]);
  expect(state.attempt.steps).toHaveLength(1);
});

test("recognition retry preserves a manual correction and asks for fresh confirmation", async ({ page, context, baseURL }) => {
  const { state, review } = await open(page, context, baseURL!);
  const content = "y'=3x^2-3";
  await review.getByTestId("ocr-v2-content").fill(content);
  await review.getByTestId("ocr-v2-boundary").check();
  await review.getByRole("button", { name: "Nhận diện lại bằng Gemini", exact: true }).click();
  await expect(review).toHaveAttribute("aria-busy", "false");
  await expect(review.getByTestId("ocr-v2-content")).toHaveValue(content);
  await expect(review.getByTestId("ocr-v2-boundary")).not.toBeChecked();
  expect(state.ocrCalls).toBe(2);
  expect(state.attempt.steps).toEqual([]);
});

test("page is predicted as three steps and only confirmed steps reach Gemini grading", async ({ page, context, baseURL }, testInfo) => {
  const {state,review}=await open(page,context,baseURL!,false,true);
  await expect(review.getByTestId("ocr-v2-unit")).toHaveCount(3);
  await expect(review.getByTestId("ocr-step-count")).toContainText("3 bước");
  await expect(review.getByTestId("ocr-v2-step-kind")).toHaveValue("DERIVATIVE_CALCULATION");
  expect(state.gradeCalls).toBe(0);expect(state.stepRequests).toEqual([]);
  await review.getByTestId("ocr-v2-content").fill("y'=3x^2-3");
  await review.getByTestId("ocr-v2-unit").nth(1).click();
  await expect(review.getByTestId("ocr-v2-step-kind")).toHaveValue("ROOT_FINDING");
  await expect(review.getByTestId("ocr-v2-content")).toHaveValue(/x=1.*x=-1/);
  await review.getByTestId("ocr-v2-unit").nth(2).click();
  await expect(review.getByTestId("ocr-v2-step-kind")).toHaveValue("VARIATION_TABLE");
  await expect(review.getByTestId("ocr-v2-math-preview").locator(".katex-display")).toBeVisible();
  await review.getByTestId("ocr-v2-boundary").check();
  await page.screenshot({path:testInfo.outputPath("three-logical-steps.png")});
  await review.getByRole("button",{name:"Xác nhận & lưu 3 bước",exact:true}).click();
  await expect(review.getByText("Đã lưu 3 bước giải vào bài làm",{exact:true})).toBeVisible();
  expect(state.attempt.steps!.map(s=>s.step_type)).toEqual(["DERIVATIVE_CALCULATION","ROOT_FINDING","VARIATION_TABLE"]);
  expect(state.attempt.steps![0].content_latex).toBe("y'=3x^2-3");
  expect(state.gradeCalls).toBe(0);
  await review.getByRole("button",{name:"Đóng & tiếp tục",exact:true}).click();
  await page.locator("aside").getByRole("button",{name:"Nộp bài & kiểm tra",exact:true}).click();
  await expect.poll(()=>state.gradeCalls).toBe(1);
  expect(state.gradedStepCount).toBe(3);
  expect(state.ocrCalls).toBe(1);
});
