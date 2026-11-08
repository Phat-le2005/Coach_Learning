import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QuestionContent } from "../src/components/ui/QuestionContent.js";
import { parseQuestionVisuals, prepareQuestionVisuals, type QuestionVisual } from "../src/lib/api/question-visuals.js";
import { parseProblemRead } from "../src/lib/api/contracts.js";
import { parseMaterialItem, parseStudentSubmission } from "../src/features/teacher/api.js";
import { studentQuestionImagePath } from "../src/lib/api/question-image-path.js";
import { teacherBackendPath } from "../src/features/teacher/route-path.js";

const id = "01234567-89ab-4cde-8012-3456789abcde";
const visual: QuestionVisual = { index: 0, path: "visual_assets/page-0002/truck.png",
  url: `/api/student/assignments/${id}/material-items/${id}/assets/0`, role: "question" };
const solution: QuestionVisual = { ...visual, index: 1, path: "visual_assets/solution.png", role: "solution", url: visual.url.replace(/0$/, "1") };

test("question view resolves legacy relative images once and keeps formulas and answer space", () => {
  const content = `Tính $v_0=15$.\n\n![Hình nguồn](${visual.path})\n\n![Lặp lại](./${visual.path})\n\nTrả lời: ........`;
  const html = renderToStaticMarkup(React.createElement(QuestionContent, { content, visuals: [visual] }));
  assert.equal((html.match(/<img /g) ?? []).length, 1);
  assert.ok(html.includes(`src="${visual.url}"`));
  assert.match(html, /class="katex"/);
  assert.match(html, /max-width:100%;height:auto/);
  assert.match(html, /Trả lời: \.{8}/);
  assert.doesNotMatch(html, /!\[Hình nguồn\]|visual_assets\/page/);
});

test("approved attachments survive removing the Markdown link and reference images stay in their role", () => {
  const content = "Nội dung giáo viên đã sửa, không còn liên kết ảnh.";
  const normal = prepareQuestionVisuals(content, [visual, solution]);
  assert.ok(normal.includes(visual.url));
  assert.ok(!normal.includes(solution.url));
  const reference = prepareQuestionVisuals("Lời giải", [visual, solution], "solution");
  assert.ok(reference.includes(solution.url));
  assert.ok(!reference.includes(visual.url));
  const option = `![Hình lựa chọn](${visual.path})`;
  assert.ok(!prepareQuestionVisuals(content, [visual], "question", true, [option]).includes(visual.url));
  assert.ok(prepareQuestionVisuals(option, [visual], "question", false).includes(visual.url));
});

test("images between display formulas are not swallowed by standalone formula detection", () => {
  const html = renderToStaticMarkup(React.createElement(QuestionContent, {
    content: `$$v_0=15$$\n\n![Hình nguồn](${visual.path})\n\n$$a(t)=t^2+4t$$`, visuals: [visual],
  }));
  assert.equal((html.match(/<img /g) ?? []).length, 1);
  assert.equal((html.match(/class="katex-display"/g) ?? []).length, 2);
});

test("question images reject external sources and escape labels instead of inserting source HTML", () => {
  for (const url of ["https://evil.test/a.png", "//evil.test/a.png", "/api/a/../b", "/api/a?token=secret", "javascript:bad", "/api/%2e%2e/b"]) {
    assert.throws(() => parseQuestionVisuals([{ ...visual, url }]));
  }
  const html = renderToStaticMarkup(React.createElement(QuestionContent, {
    content: `![<script>alert('x')</script>](${visual.path})`, visuals: [visual],
  }));
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /alt="&lt;script&gt;/);
  assert.equal(prepareQuestionVisuals("![Nguồn](visual_assets/missing.png)", []), "[Hình minh họa chưa khả dụng]");
});

test("problem and teacher question contracts retain the shared image list", () => {
  const problem = parseProblemRead({ id, content: "Đề bài", question_type: "OPEN_RESPONSE", options: [], visuals: [visual] });
  assert.deepEqual(problem.visuals, [visual]);
  const material = parseMaterialItem({ id, order_index: 0, content: "Đề bài", extraction_status: "READY",
    evaluation_mode: "TEACHER_REVIEW", options: [], visuals: [visual], raw_metadata: {} });
  assert.deepEqual(material.visuals, [visual]);
  const submission = parseStudentSubmission({ assignment_id: id, assignment_title: "Test", classroom_id: id,
    student_id: id, student_name: "Test", status: "IN_PROGRESS", items: [{ id, source_kind: "TEACHER_MATERIAL", order_index: 0, visuals: [visual] }] });
  assert.deepEqual(submission.items[0].visuals, [visual]);
});

test("student and teacher image proxies allow only exact question image routes", () => {
  assert.equal(studentQuestionImagePath(id, id, "0"), `/students/me/assignments/${id}/material-items/${id}/assets/0`);
  assert.equal(studentQuestionImagePath("../secret", id, "0"), null);
  assert.equal(studentQuestionImagePath(id, id, "-1"), null);
  assert.equal(studentQuestionImagePath(id, id, "0/../1"), null);
  const parts = ["assignments", id, "students", id, "material-items", id, "assets", "0"];
  assert.equal(teacherBackendPath(parts, "GET", ""), `/teacher/assignments/${id}/students/${id}/material-items/${id}/assets/0`);
  assert.equal(teacherBackendPath(parts, "POST", ""), null);
});
