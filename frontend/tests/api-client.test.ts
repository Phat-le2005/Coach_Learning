import assert from "node:assert/strict";
import test from "node:test";

import { ApiNetworkError, ApiResponseError, createApiClient, normalizeApiBaseUrl } from "../src/lib/api/client";
import { ApiContractError } from "../src/lib/api/validation";

const tokenPair = { access_token: "access", refresh_token: "refresh", token_type: "bearer", expires_in: 900 };

test("login uses the canonical root path and validates the token response", async () => {
  let requested = "";
  const api = createApiClient({ baseUrl: "http://api.example.test", fetcher: async (input) => {
    requested = String(input);
    return Response.json(tokenPair);
  } });
  assert.deepEqual(await api.login({ email: " Student@Example.com ", password: "safe-password" }), tokenPair);
  assert.equal(requested, "http://api.example.test/auth/login");
});

test("refresh and current-user calls use canonical auth paths without exposing token in a query", async () => {
  const calls: Array<{ url: string; authorization: string | null }> = [];
  const api = createApiClient({ baseUrl: "http://api.example.test", fetcher: async (input, init) => {
    calls.push({ url: String(input), authorization: new Headers(init?.headers).get("Authorization") });
    return calls.length === 1 ? Response.json(tokenPair) : Response.json({ id: "u1", email: "s@example.com", full_name: "Student", role: "STUDENT", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });
  } });
  await api.refresh("refresh-secret");
  await api.me("access-secret");
  assert.deepEqual(calls, [
    { url: "http://api.example.test/auth/refresh", authorization: null },
    { url: "http://api.example.test/auth/me", authorization: "Bearer access-secret" },
  ]);
});

test("validates the real Student Learning State boundary", async () => {
  const response = {
    student_id: "student-1", as_of: "2026-10-08T03:00:00Z", available_subjects: [], focus_subject_id: null,
    current_action: { action_type: "IDLE", subject_id: null, resource_id: null, practice_session_id: null, assignment_id: null, verification_id: null, adaptive_repair_session_id: null, study_task_id: null, target_type: null, problem_type_id: null, concept_id: null, target_name: null, target_code: null, reason_code: null, repair_cycle_index: null, phase: null },
    mastery_summary: { problem_type_started_count: 0, concept_started_count: 0, mastered_problem_type_count: 0, weak_problem_type_count: 0, mastered_concept_count: 0, weak_concept_count: 0, average_problem_type_mastery: null, average_concept_mastery: null, weak_problem_types: [], weak_concepts: [] },
    priority_targets: [], active_learning: { practice_session_id: null, practice_session_type: null, verification_id: null, adaptive_repair_session_id: null, assignment_id: null },
    verified_root_causes: [], repair: null, review: { due_now_count: 0, upcoming_count: 0, due_targets: [] },
    assignments: { overdue_count: 0, in_progress_count: 0, pending_count: 0, upcoming: [] }, today_plan: null, latest_feedback: null, class_contexts: [],
  };
  let requested = "";
  const api = createApiClient({ baseUrl: "http://api.example.test", fetcher: async (input) => { requested = String(input); return Response.json(response); } });
  assert.equal((await api.studentLearningState("access", "math-id")).student_id, "student-1");
  assert.equal(requested, "http://api.example.test/students/me/learning-state?subject_id=math-id");
});

for (const [status, category] of [[401, "unauthorized"], [403, "forbidden"], [404, "not_found"], [409, "conflict"], [422, "validation"], [503, "unavailable"]] as const) {
  test(`maps HTTP ${status} to ${category}`, async () => {
    const api = createApiClient({ baseUrl: "https://api.example.test", fetcher: async () => Response.json({ error: { code: `E_${status}`, message: "backend error", details: [{ field: "email", message: "invalid" }] } }, { status }) });
    await assert.rejects(api.login({ email: "a@example.com", password: "x" }), (error: unknown) => error instanceof ApiResponseError && error.status === status && error.category === category && error.code === `E_${status}`);
  });
}

test("distinguishes a network failure", async () => {
  const api = createApiClient({ baseUrl: "https://api.example.test", fetcher: async () => { throw new TypeError("offline"); } });
  await assert.rejects(api.login({ email: "a@example.com", password: "x" }), ApiNetworkError);
});

test("rejects a successful response that violates the contract", async () => {
  const api = createApiClient({ baseUrl: "https://api.example.test", fetcher: async () => Response.json({ access_token: "missing fields" }) });
  await assert.rejects(api.login({ email: "a@example.com", password: "x" }), ApiContractError);
});

test("rejects API base URLs with an invented prefix", () => {
  assert.throws(() => normalizeApiBaseUrl("https://api.example.test/api/v1"), /root paths/u);
});
