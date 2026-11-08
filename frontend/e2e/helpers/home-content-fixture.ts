import fs from "node:fs";
import path from "node:path";
import ts from "typescript";
import type { Page } from "@playwright/test";
import type { StudentHomeViewModel } from "../../src/features/student-home/types";

/** Actual React components with synthetic UI state; no app router, backend or database. */
export async function renderHomeContent(page: Page, data: StudentHomeViewModel, theme = "light") {
  const frontend = path.resolve(__dirname, "../..");
  const feature = path.join(frontend, "src/features/student-home");
  const read = (file: string) => fs.readFileSync(file, "utf8");
  const compile = (file: string) => ts.transpileModule(read(path.join(feature, file)), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  const modules: Record<string, string> = {
    react: read(path.join(frontend, "node_modules/react/cjs/react.development.js")),
    "react/jsx-runtime": read(path.join(frontend, "node_modules/react/cjs/react-jsx-runtime.development.js")),
    "react-dom": read(path.join(frontend, "node_modules/react-dom/cjs/react-dom.development.js")),
    "react-dom/client": read(path.join(frontend, "node_modules/react-dom/cjs/react-dom-client.development.js")),
    scheduler: read(path.join(frontend, "node_modules/scheduler/cjs/scheduler.development.js")),
    "lucide-react": read(path.join(frontend, "node_modules/lucide-react/dist/cjs/lucide-react.js")),
    "next/link": `module.exports={__esModule:true,default:function Link({href,children,prefetch,...rest}){return require('react').createElement('a',{href,...rest},children)}};`,
    "../HomeContent.module.css": `module.exports={__esModule:true,default:new Proxy({},{get:(_,key)=>String(key)})};`,
    "./home-icons.json": `module.exports=${read(path.join(feature, "components/home-icons.json"))};`,
    "./HomeIcon": compile("components/HomeIcon.tsx"),
    "../home-presentation": compile("home-presentation.ts"),
    "../copy": compile("copy.ts"),
    HomeToday: compile("components/HomeToday.tsx"),
    PriorityPath: compile("components/PriorityPath.tsx"),
    KnowledgeGarden: compile("components/KnowledgeGarden.tsx"),
    CoachCard: compile("components/CoachCard.tsx"),
    StudyPlanRoadmapModal: compile("components/StudyPlanRoadmapModal.tsx"),
    "./StudyPlanRoadmapModal.module.css": `module.exports={__esModule:true,default:new Proxy({},{get:(_,key)=>'roadmap-'+String(key)})};`,
    "@/features/knowledge-forest/components/MathChapterIllustration": compile("../knowledge-forest/components/MathChapterIllustration.tsx"),
  };
  let styles = read(path.join(feature, "HomeRefresh.module.css")) + read(path.join(feature, "HomeContent.module.css"));
  styles += read(path.join(feature, "components/StudyPlanRoadmapModal.module.css")).replace(/\.([a-zA-Z][\w-]*)/g, ".roadmap-$1");
  styles = styles.replace(/url\(['"]?\.\/assets\/([^'")]+)['"]?\)/g, (_, file: string) =>
    `url(data:font/woff2;base64,${fs.readFileSync(path.join(feature, "assets", file)).toString("base64")})`);
  styles = styles.replace(/:global\(([^)]+)\)/g, "$1");
  const script = `
    const process={env:{NODE_ENV:'development'}};
    const factories={${Object.entries(modules).map(([id, body]) => `${JSON.stringify(id)}:function(module,exports,require){\n${body}\n}`).join(",\n")}};
    const cache={};function require(id){if(cache[id])return cache[id].exports;const m={exports:{}};cache[id]=m;if(!factories[id])throw Error('Missing test module: '+id);factories[id](m,m.exports,require);return m.exports;}
    const React=require('react');const data=${JSON.stringify(data)};
    const HomeToday=require('HomeToday').HomeToday,PriorityPath=require('PriorityPath').PriorityPath;
    const KnowledgeGarden=require('KnowledgeGarden').KnowledgeGarden,CoachCard=require('CoachCard').CoachCard;
    const StudyPlanRoadmapModal=require('StudyPlanRoadmapModal').StudyPlanRoadmapModal;
    window.fixtureCalls=[];const call=name=>()=>window.fixtureCalls.push(name);
    function Fixture(){const [open,setOpen]=React.useState(false);return React.createElement(React.Fragment,null,
      React.createElement(HomeToday,{data,onOpenPlan:()=>{call('plan')();setOpen(true)},onDetails:call('details'),onRecalculate:call('recalculate'),recalculating:false}),
      React.createElement(PriorityPath,{priorities:data.priorities,mastery:data.mastery,momentum:data.momentum,subjectId:data.subject.id,onSelectPriority:call('priority')}),
      React.createElement(KnowledgeGarden,{regions:data.knowledgeRegions,subjectId:data.subject.id}),
      React.createElement(CoachCard,{data}),
      React.createElement(StudyPlanRoadmapModal,{isOpen:open,onClose:()=>setOpen(false),subjectId:data.subject.id})
    )} require('react-dom/client').createRoot(document.getElementById('fixture')).render(React.createElement(Fixture));
  `;
  await page.setContent(`<!doctype html><html lang="vi"><head><base href="http://fixture.local/"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${styles}</style></head><body class="home" data-home-theme="${theme}"><p style="max-width:1320px;margin:20px auto 0;font-size:11px;color:var(--muted)">Dữ liệu kiểm thử minh họa · Render component thật · Không phải dữ liệu tài khoản</p><main id="fixture"></main><script>${script.replace(/<\/script/gi, "<\\/script")}</script></body></html>`);
  await page.getByRole("heading", { name: "Việc nên làm tiếp theo", exact: true }).waitFor();
  await page.evaluate(() => document.fonts.ready);
}

export function populatedHome(): StudentHomeViewModel {
  return {
    student: { displayName: "Học sinh kiểm thử" }, subject: { id: "subject-ref", name: "Toán 12" },
    availableSubjects: [{ id: "subject-ref", code: "MATH12", name: "Toán 12" }],
    learningContext: { mode: "CLASSROOM", classContextCount: 1, subjectHasActivity: true },
    currentAction: { type: "REVIEW_DUE", targetCode: "concept-ref" },
    resolvedAction: { type: "REVIEW_DUE", title: "Ôn tính đơn điệu của hàm số", description: "Nội dung này đã đến lịch ôn trong kế hoạch của bạn.", primaryLabel: "Ôn nội dung được gợi ý", hasAvailableRoute: true, route: "/student/practice?concept_id=concept-ref", badgeLabel: "Ôn tập", guidanceText: "Nội dung kiểm thử." },
    mastery: { hasEvidence: true, score: 72, label: "Đang củng cố kiến thức", problemTypeStartedCount: 8, conceptStartedCount: 12, masteredProblemTypeCount: 3, weakProblemTypeCount: 2 },
    review: { dueCount: 2, upcomingCount: 3, dueTargets: [{ scheduleId: "review-1", targetType: "CONCEPT", targetName: "Tính đơn điệu của hàm số", targetCode: "concept-ref", nextReviewAt: "2026-11-08T00:00:00Z" }, { scheduleId: "review-2", targetType: "CONCEPT", targetName: "Nguyên hàm cơ bản", targetCode: "integral-ref", nextReviewAt: "2026-11-08T00:00:00Z" }] },
    assignments: { activeCount: 4, overdueCount: 1, inProgressCount: 2, pendingCount: 1, upcoming: [{ assignmentId: "assignment-1", title: "Bài tập ứng dụng đạo hàm", status: "IN_PROGRESS", dueAt: "2026-11-09T00:00:00Z", isOverdue: false }] },
    todayPlan: { date: "2026-11-08", totalCount: 5, completedCount: 1, totalEstimatedMinutes: 45, availableMinutes: 60,
      tasks: ["Ôn tính đơn điệu", "Lập bảng biến thiên", "Nguyên hàm cơ bản", "Xác suất có điều kiện", "Tọa độ trong không gian"].map((title, i) => ({ id: `task-${i}`, title, taskType: ["REVIEW", "REPAIR", "LEARN", "MINI_TEST", "EXAM"][i], status: i === 2 ? "COMPLETED" : "PENDING", isCompleted: i === 2, estimatedMinutes: 9, conceptId: `concept-${i}`, topicName: "Toán 12" })) },
    momentum: {}, knowledgeRegions: [],
    priorities: [{ id: "priority-1", targetType: "PROBLEM_TYPE", targetName: "Xét dấu đạo hàm", targetCode: "derivative-ref", reasonCode: "LOW_MASTERY", mastery: 42, practiceRoute: "/student/practice?problem_type_id=derivative-ref" }, { id: "priority-2", targetType: "CONCEPT", targetName: "Tính chất nguyên hàm", targetCode: "integral-ref", reasonCode: "LOW_MASTERY", practiceRoute: "/student/practice?concept_id=integral-ref" }],
  };
}
