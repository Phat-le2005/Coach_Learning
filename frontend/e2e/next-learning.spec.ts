import { expect, test, type Page, type BrowserContext } from "@playwright/test";
import { signSession } from "../src/lib/auth/session-codec";
import { AUTH_COOKIES } from "../src/lib/auth/constants";
import plan from "./fixtures/next-learning.json";
import { populatedHome, renderHomeContent } from './helpers/home-content-fixture';

test.skip(!process.env.NEXT_LEARNING_E2E_SECRET, "Use isolated next-learning config; no live backend.");
async function open(page:Page, context:BrowserContext, baseURL:string, advice:unknown=plan) {
  if (baseURL !== "http://127.0.0.1:3112") throw Error("Requires isolated UI server");
  const signed = await signSession({v:1,userId:"next-learning-fixture",email:"student@example.test",fullName:"Học sinh kiểm thử",role:"STUDENT",expiresAt:Date.now()+600_000},process.env.NEXT_LEARNING_E2E_SECRET!);
  await context.addCookies([
    {name:AUTH_COOKIES.session,value:signed,url:baseURL,httpOnly:true,sameSite:"Lax"},
    {name:AUTH_COOKIES.access,value:"isolated-access",url:baseURL,httpOnly:true,sameSite:"Lax"},
  ]);
  await page.route("**/auth/me",route=>route.fulfill({json:{role:"STUDENT"}}));
  if (advice !== plan) await page.route("**/next-learning",route=>route.fulfill({json:advice}));
  await page.route(/googleapis\.com/,route=>route.abort());
  await page.goto(`/student/attempts/${plan.attempt_id}`);
  await page.getByRole("button",{name:"Xem kết quả",exact:true}).first().click();
  const card=page.getByTestId("next-learning-card");
  await expect(card).toHaveAttribute("aria-busy","false");
  await card.scrollIntoViewIfNeeded();
  return card;
}

test("50 percent with two valid steps shows reinforcement and launches the exact recommendation",async({page,context,baseURL},info)=>{
  const card=await open(page,context,baseURL!);
  await expect(card.getByRole("heading",{name:"Bạn nên học gì tiếp?"})).toBeVisible();
  await expect(card.getByText("Củng cố",{exact:true})).toBeVisible();
  await expect(card.getByRole("heading",{name:plan.target.name})).toBeVisible();
  await expect(page.getByText("Đã ghi nhận độ vững",{exact:true})).toHaveCount(0);
  await expect(card.getByText("35%",{exact:true})).toBeVisible();
  await expect(card.locator(".katex")).not.toHaveCount(0);
  await page.screenshot({path:info.outputPath("desktop.png")});
  await card.screenshot({path:info.outputPath("card-desktop.png")});
  const pending=page.waitForRequest(request=>request.method()==="POST" && request.url().endsWith("/next-learning"));
  await card.getByRole("button",{name:"Làm bài củng cố",exact:true}).click();
  expect((await pending).postDataJSON()).toEqual({decision_id:plan.decision_id,question_id:plan.question.id});
  await expect(page).toHaveURL(/00000000-0000-4000-8000-000000000204$/);
});

test("mobile keeps the plan readable without horizontal overflow",async({page,context,baseURL},info)=>{
  await page.setViewportSize({width:390,height:844});
  const card=await open(page,context,baseURL!);
  expect(await card.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  const bounds=await card.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(390);
  await expect(page.getByRole('button',{name:'Luyện tập bài tiếp theo →',exact:true})).toHaveCount(0);
  await expect(card.getByRole("link",{name:"Tìm lý thuyết liên quan"})).toHaveAttribute("href",/topic=/);
  await card.getByRole("button",{name:"Làm bài củng cố"}).scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath("mobile.png")});
  await card.evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));
  await page.screenshot({path:info.outputPath("mobile-top.png")});
});

test("pending and empty supply never display invented progress or launch controls",async({page,context,baseURL})=>{
  const card=await open(page,context,baseURL!,{...plan,status:"WAITING_REVIEW",score:null,decision_id:null,evidence_recorded:false,
    headline:"Đối chiếu bài làm trước khi học tiếp",explanation:"Bài chưa có điểm chính thức.",target:null,question:null,criterion_gaps:[]});
  await expect(card.getByText("Cần đối chiếu",{exact:true})).toBeVisible();
  await expect(card.getByRole("button",{name:"Làm bài củng cố"})).toHaveCount(0);
  await expect(card.getByText("Điểm bài đã lưu")).toHaveCount(0);
});

test("unavailable advice can retry without hiding the saved grade",async({page,context,baseURL})=>{
  let fail=true;
  await page.route("**/next-learning",route=>fail ? route.fulfill({status:503,json:{error:{message:"Unavailable"}}}) : route.fulfill({json:plan}));
  const card=await open(page,context,baseURL!);
  await expect(card.getByRole("alert")).toContainText("Kết quả chấm của bạn vẫn được giữ");
  fail=false;
  await card.getByRole("button",{name:"Tải lại",exact:true}).click();
  await expect(card.getByRole("button",{name:"Làm bài củng cố"})).toBeVisible();
});

test("BFF protects launch with CSRF and validates IDs",async({page,context,baseURL})=>{
  await open(page,context,baseURL!);
  const url=`${baseURL}/api/v3/math-solutions/attempts/${plan.attempt_id}/next-learning`;
  const denied=await context.request.post(url,{data:{decision_id:plan.decision_id,question_id:plan.question.id},headers:{Origin:baseURL!}});
  expect(denied.status()).toBe(403);
  const wrong=await context.request.get(`${baseURL}/api/v3/math-solutions/attempts/not-an-id/next-learning`);
  expect(wrong.status()).toBe(404);
});

test('AI explanation is explicit and leaves the chosen target and question intact',async({page,context,baseURL})=>{
  let calls=0;
  page.on('request', request=>{if(request.url().endsWith('/next-learning/explain')) calls++;});
  const card=await open(page,context,baseURL!);
  expect(calls).toBe(0);
  await card.getByRole('button',{name:'Gợi ý cách ôn cùng AI',exact:true}).click();
  await expect(card.getByText('AI gợi ý cách ôn',{exact:true})).toBeVisible();
  expect(calls).toBe(1);
  await expect(card.getByRole('heading',{name:plan.target.name})).toBeVisible();
  await expect(card.getByRole('button',{name:'Làm bài củng cố',exact:true})).toBeEnabled();
});

test('an empty bank explains the missing supply instead of choosing a random exercise',async({page,context,baseURL})=>{
  const card=await open(page,context,baseURL!,{...plan,question:null,supply_message:'Chưa có bài tự luận mới phù hợp cho mục tiêu này.'});
  await expect(card.getByText('Chưa có bài tự luận mới phù hợp cho mục tiêu này.',{exact:true})).toBeVisible();
  await expect(card.getByRole('button',{name:'Làm bài củng cố'})).toHaveCount(0);
  await expect(card.getByRole('link',{name:'Tìm lý thuyết liên quan'})).toBeVisible();
});

test('the same target is visible again beside today\'s plan after returning from the result',async({page},info)=>{
  await page.route('http://fixture.local/**',route=>route.request().url().endsWith('/next-learning') ? route.fulfill({json:plan}) : route.fulfill({contentType:'text/html',body:'<html></html>'}));
  await page.goto(`http://fixture.local/student?after_attempt=${plan.attempt_id}`);
  await renderHomeContent(page,populatedHome());
  const reminder=page.getByRole('region',{name:'Tiếp nối bài vừa làm'});
  await expect(reminder.getByRole('heading',{name:plan.target.name})).toBeVisible();
  await expect(reminder.getByRole('link',{name:'Xem kết quả & bài luyện'})).toHaveAttribute('href',`/student/attempts/${plan.attempt_id}`);
  await reminder.screenshot({path:info.outputPath('home-reminder.png')});
});
