import assert from "node:assert/strict";
import test from "node:test";
import { teacherBackendPath } from "../src/features/teacher/route-path.js";
import { TeacherApiError, parseAnalytics, parseClassroom, parseMaterial, teacherApi } from "../src/features/teacher/api.js";
import { ApiContractError } from "../src/lib/api/validation.js";

const id = "00000000-0000-4000-8000-000000000001";

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
