import assert from "node:assert/strict";
import test from "node:test";
import { teacherBackendPath } from "../src/features/teacher/route-path.js";
import { TeacherApiError, parseAnalytics, parseClassroom, parseMaterial, teacherApi, teacherRequest } from "../src/features/teacher/api.js";
import { ApiContractError } from "../src/lib/api/validation.js";
import { parsePdfImport } from "../src/features/teacher/pdf-api.js";
import { MATERIAL_DIFFICULTY_LEVELS, parseMaterialDifficulty } from "../src/features/teacher/material-difficulty.js";
import { materialColumns, materialPage, materialPageNumbers } from "../src/features/teacher/material-pagination.js";

const id = "00000000-0000-4000-8000-000000000001";

test("material pages always have at most two rows and retain every document across pages", () => {
  const documents = Array.from({ length: 27 }, (_, index) => `material-${index}`);
  for (const width of [360, 650, 1050, 1600]) {
    const columns = materialColumns(width);
    const all = [];
    for (let page = 0; page < materialPage(documents, 0, columns).pageCount; page++) {
      const result = materialPage(documents, page, columns);
      assert.ok(result.items.length <= columns * 2);
      all.push(...result.items);
    }
    assert.deepEqual(all, documents);
  }
});

test("material pagination clamps after deletion and handles empty filtered results", () => {
  const result = materialPage(["one", "two", "three"], 12, 1);
  assert.equal(result.page, 1);
  assert.deepEqual(result.items, ["three"]);
  const afterDelete = materialPage(["one", "two"], result.page, 1);
  assert.equal(afterDelete.page, 0);
  assert.deepEqual(materialPage([], 5, 4).items, []);
  assert.deepEqual(materialPageNumbers(4, 10), [0, "gap", 3, 4, 5, "gap", 9]);
});

test("OCR review save preserves edits and renews CSRF after refreshing an expired session", async () => {
  const original = globalThis.fetch;
  const body = JSON.stringify({ title: "Edited PDF", decisions: [{ question_id: "q1", content: "Corrected integral", answer: "C" }] });
  let csrf = "";
  let csrfReads = 0;
  let saves = 0;
  let refreshes = 0;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/auth/csrf") return Response.json({ csrf_token: (csrf = `csrf-${++csrfReads}`) });
    if (path === "/auth/me") return Response.json({ error: { code: "SESSION_EXPIRED" } }, { status: 401 });
    assert.equal(new Headers(init?.headers).get("X-CSRF-Token"), csrf);
    if (path === "/auth/refresh") {
      refreshes += 1;
      return Response.json({ user: { role: "TEACHER" } });
    }
    assert.equal(path, `/api/teacher/materials/pdf-imports/${id}/review`);
    assert.equal(init?.method, "PUT");
    assert.equal(init?.body, body);
    return ++saves === 1
      ? Response.json({ error: { code: "SESSION_EXPIRED" } }, { status: 401 })
      : Response.json({ saved: true });
  }) as typeof fetch;
  try {
    const result = await teacherRequest(`materials/pdf-imports/${id}/review`, value => value, {
      method: "PUT", headers: { "Content-Type": "application/json", "X-CSRF-Token": "old-csrf" }, body,
    });
    assert.deepEqual(result, { saved: true });
    assert.equal(saves, 2);
    assert.equal(refreshes, 1);
  } finally { globalThis.fetch = original; }
});

test("teacher mutations recover once from CSRF rejection and never retry other 403 errors", async () => {
  const original = globalThis.fetch;
  try {
    for (const [code, recover] of [["CSRF_TOKEN_INVALID", true], ["CSRF_ORIGIN_REJECTED", false], ["FORBIDDEN", false]] as const) {
      let mutations = 0;
      let csrfReads = 0;
      const body = JSON.stringify({ title: "Unsaved review", decisions: [] });
      globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) === "/auth/csrf") return Response.json({ csrf_token: `csrf-${++csrfReads}` });
        assert.equal(init?.body, body);
        assert.equal(new Headers(init?.headers).get("X-CSRF-Token"), `csrf-${csrfReads}`);
        return ++mutations === 1
          ? Response.json({ error: { code, message: "Rejected" } }, { status: 403 })
          : Response.json({ saved: true });
      }) as typeof fetch;
      const save = () => teacherRequest("materials/pdf-imports/id/review", value => value, { method: "PUT", body });
      if (recover) assert.deepEqual(await save(), { saved: true });
      else await assert.rejects(save, error => error instanceof TeacherApiError && error.code === code);
      assert.equal(mutations, recover ? 2 : 1);
    }
  } finally { globalThis.fetch = original; }
});

test("repeated CSRF rejection stops after one retry", async () => {
  const original = globalThis.fetch;
  let mutations = 0;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (String(input) === "/auth/csrf") return Response.json({ csrf_token: "csrf-test" });
    mutations += 1;
    return Response.json({ error: { code: "CSRF_TOKEN_INVALID", message: "Rejected" } }, { status: 403 });
  }) as typeof fetch;
  try {
    await assert.rejects(() => teacherRequest("materials/pdf-imports/id/submit", value => value, { method: "POST", body: "{}" }),
      error => error instanceof TeacherApiError && error.code === "CSRF_TOKEN_INVALID");
    assert.equal(mutations, 2);
  } finally { globalThis.fetch = original; }
});

test("PDF import proxy restricts job, review, source and asset routes", () => {
  const base = `/teacher-materials/pdf-imports/${id}`;
  assert.equal(teacherBackendPath(["materials", "pdf-imports"], "POST", ""), "/teacher-materials/pdf-imports");
  assert.equal(teacherBackendPath(["materials", "pdf-imports"], "GET", `?classroom_id=${id}`), `/teacher-materials/pdf-imports?classroom_id=${id}`);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id], "GET", ""), base);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id, "submit"], "POST", ""), `${base}/submit`);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id, "revise"], "POST", ""), `${base}/revise`);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id, "revise"], "GET", ""), null);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id, "review"], "PUT", ""), `${base}/review`);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id], "DELETE", ""), base);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id], "DELETE", "?all=true"), null);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id, "source"], "GET", ""), `${base}/source`);
  assert.equal(teacherBackendPath(["materials", "pdf-imports", id, "assets", "1"], "GET", ""), `${base}/assets/1`);
  assert.equal(teacherBackendPath(["materials", id, "document"], "GET", ""), `/teacher-materials/${id}/document`);
  assert.equal(teacherBackendPath(["materials", id], "DELETE", ""), `/teacher-materials/${id}`);
  assert.equal(teacherBackendPath(["materials", id], "DELETE", "?classroom_id=extra"), null);
  assert.equal(teacherBackendPath(["materials", ".."], "DELETE", ""), null);
  assert.equal(teacherBackendPath(["materials", id, "assets", "3"], "GET", ""), `/teacher-materials/${id}/assets/3`);
  for (const [parts, method, query] of [
    [["materials", "pdf-imports", "..", "source"], "GET", ""],
    [["materials", "pdf-imports", id, "assets", ".."], "GET", ""],
    [["materials", "pdf-imports", id, "source"], "POST", ""],
    [["materials", "pdf-imports", id, "submit"], "GET", ""],
    [["materials", "pdf-imports", id, "review"], "GET", ""],
    [["materials", "pdf-imports", id, "assets", "1"], "GET", "?path=secret"],
  ] as const) assert.equal(teacherBackendPath([...parts], method, query), null);
});

test("PDF import contract preserves warnings and human decisions", () => {
  const value = { id, classroom_id: id, subject_id: id, title: "PDF", original_file_name: "x.pdf", status: "NEEDS_REVIEW", created_at: "2026-11-08T00:00:00Z", error: null, material_id: null, progress: { selected_pages: 1 }, review: null,
    questions: [{ question_id: "q1", number: 1, source_number: 4, content: "Câu 4", answer: "A", explanation: "", pages: [1], warnings: ["INCOMPLETE"], suggested: false, source_assets: [0], visual_assets: [] }] };
  const parsed = parsePdfImport(value);
  assert.equal(parsed.questions[0].suggested, false);
  assert.deepEqual(parsed.questions[0].warnings, ["INCOMPLETE"]);
  assert.equal(parsed.review, null);
  const replacement = parsePdfImport({ ...value, revision_of: id, revision_title: "Original", review: {
    title: "Edited", decisions: [], save_mode: "REPLACE",
  } });
  assert.equal(replacement.review?.save_mode, "REPLACE");
  assert.equal(replacement.revision_title, "Original");
  assert.throws(() => parsePdfImport({ ...value, review: { title: "Edited", decisions: [], save_mode: "UNKNOWN" } }), ApiContractError);
  assert.equal(parsed.source_kind, "PDF");
  const image = parsePdfImport({ ...value, source_kind: "IMAGE", source_mime_type: "image/png", original_file_name: "question.png" });
  assert.equal(image.source_kind, "IMAGE");
  assert.equal(image.source_mime_type, "image/png");
  assert.throws(() => parsePdfImport({ ...value, source_kind: "VIDEO" }), ApiContractError);
  assert.equal(parsed.questions[0].difficulty_level, null);
  for (const level of MATERIAL_DIFFICULTY_LEVELS) {
    assert.equal(parseMaterialDifficulty(level, "difficulty"), level);
    const review = { title: "Edited", decisions: [{ question_id: "q1", accepted: true, source_checked: true, content: "Đề mới", answer: "Đáp án mới", explanation: "Giải mới", difficulty_level: level }] };
    assert.equal(parsePdfImport({ ...value, review }).review!.decisions[0].difficulty_level, level);
  }
  assert.throws(() => parseMaterialDifficulty("MADE_UP_LEVEL", "difficulty"), ApiContractError);
  assert.throws(() => parsePdfImport({ ...value, questions: [{ ...value.questions[0], warnings: "not-an-array" }] }), ApiContractError);
  assert.throws(() => parsePdfImport({ ...value, title: undefined }), ApiContractError);
});

test("teacher proxy only exposes explicit teacher paths", () => {
  assert.equal(teacherBackendPath(["classes"], "GET", "?offset=0&limit=200"), "/teacher/classes?offset=0&limit=200");
  assert.equal(teacherBackendPath(["classes", id, "students"], "GET", "?offset=0&limit=200"), `/teacher/classes/${id}/students?offset=0&limit=200`);
  assert.equal(teacherBackendPath(["materials"], "GET", `?classroom_id=${id}`), `/teacher-materials?classroom_id=${id}`);
  assert.equal(teacherBackendPath(["subjects"], "GET", ""), "/api/v2/teacher/subjects");
  assert.equal(teacherBackendPath(["classes", id, "students"], "POST", ""), null);
  assert.equal(teacherBackendPath(["classes", "..", "students"], "GET", ""), null);
  assert.equal(teacherBackendPath(["assignments", id, "submissions"], "POST", ""), null);
  assert.equal(teacherBackendPath(["classes"], "GET", "?limit=200&role=ADMIN"), null);
  assert.equal(teacherBackendPath(["materials", "upload"], "POST", ""), "/teacher-materials/upload");
  assert.equal(teacherBackendPath(["theory"], "GET", `?classroom_id=${id}`), `/api/v2/teacher/theory?classroom_id=${id}`);
  assert.equal(teacherBackendPath(["theory", "upload"], "POST", ""), "/api/v2/teacher/theory/upload");
  assert.equal(teacherBackendPath(["theory", id, "map"], "PUT", ""), `/api/v2/teacher/theory/${id}/map`);
  assert.equal(teacherBackendPath(["theory", id, "publish"], "POST", ""), `/api/v2/teacher/theory/${id}/publish`);
  assert.equal(teacherBackendPath(["theory", id, "share-source"], "POST", ""), `/api/v2/teacher/theory/${id}/share-source`);
  assert.equal(teacherBackendPath(["theory", id, "unshare-source"], "POST", ""), `/api/v2/teacher/theory/${id}/unshare-source`);
  assert.equal(teacherBackendPath(["theory", id, "share-source"], "GET", ""), null);
  assert.equal(teacherBackendPath(["theory", id, "regenerate"], "POST", ""), `/api/v2/teacher/theory/${id}/regenerate`);
  assert.equal(teacherBackendPath(["theory", id, "prefill"], "POST", ""), `/api/v2/teacher/theory/${id}/prefill`);
  assert.equal(teacherBackendPath(["theory", id, "prefill"], "GET", ""), null);
  assert.equal(teacherBackendPath(["theory", id, "regenerate"], "GET", ""), null);
  assert.equal(teacherBackendPath(["theory", id, "publish"], "GET", ""), null);
  assert.equal(teacherBackendPath(["theory", id, "notebook"], "GET", ""), "/api/v2/teacher/theory/" + id + "/notebook");
  assert.equal(teacherBackendPath(["theory", id, "notebook", "blocks", "4", "2"], "GET", ""), "/api/v2/teacher/theory/" + id + "/notebook/blocks/4/2");
  assert.equal(teacherBackendPath(["theory", id, "notebook", "blocks", "..", "2"], "GET", ""), null);
  assert.equal(teacherBackendPath(["theory", id, "notebook", "blocks", "4", "2"], "POST", ""), null);
  assert.equal(teacherBackendPath(["theory", "..", "source"], "GET", ""), null);
});

test("teacher contract accepts real API shapes and rejects missing fields", () => {
  assert.deepEqual(parseClassroom({ id, name: "12A", academic_year: "2026-2027", grade_level: 12 }), { id, name: "12A", academic_year: "2026-2027", grade_level: 12 });
  assert.equal(parseMaterial({ id, title: "Notes", original_file_name: "notes.pdf", mime_type: "application/pdf", file_size_bytes: 400, status: "NEEDS_REVIEW", subject_id: id, created_at: "2026-10-29T00:00:00Z" }).status, "NEEDS_REVIEW");
  assert.throws(() => parseClassroom({ id, name: "12A", grade_level: 12 }), ApiContractError);
  assert.throws(() => parseAnalytics({ student_count: 0, subject_progress: [], chapter_progress: [], weak_problem_types: [], students_needing_attention: [] }), ApiContractError);
});

test("teacher class list uses authenticated BFF and never fabricates a fallback", async () => {
  const original = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(JSON.stringify([{ id, name: "12A", academic_year: "2026-2027", grade_level: 12 }]), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    const classes = await teacherApi.classes();
    assert.equal(classes.length, 1);
    assert.equal(calls[0], "/api/teacher/classes?offset=0&limit=200");
  } finally { globalThis.fetch = original; }
});

test("teacher API reports backend errors without substituting sample data", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({ error: { code: "API_UNAVAILABLE", message: "Backend unavailable" } }), { status: 503 })) as typeof fetch;
  try { await assert.rejects(() => teacherApi.classes(), (error: unknown) => error instanceof TeacherApiError && error.code === "API_UNAVAILABLE"); }
  finally { globalThis.fetch = original; }
});
