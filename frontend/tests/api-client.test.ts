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

test("studentLearningState without subject_id omits query parameter", async () => {
  let requested = "";
  const response = {
    student_id: "student-1", as_of: "2026-10-08T03:00:00Z", available_subjects: [], focus_subject_id: null,
    current_action: { action_type: "IDLE", subject_id: null, resource_id: null, practice_session_id: null, assignment_id: null, verification_id: null, adaptive_repair_session_id: null, study_task_id: null, target_type: null, problem_type_id: null, concept_id: null, target_name: null, target_code: null, reason_code: null, repair_cycle_index: null, phase: null },
    mastery_summary: { problem_type_started_count: 0, concept_started_count: 0, mastered_problem_type_count: 0, weak_problem_type_count: 0, mastered_concept_count: 0, weak_concept_count: 0, average_problem_type_mastery: null, average_concept_mastery: null, weak_problem_types: [], weak_concepts: [] },
    priority_targets: [], active_learning: { practice_session_id: null, practice_session_type: null, verification_id: null, adaptive_repair_session_id: null, assignment_id: null },
    verified_root_causes: [], repair: null, review: { due_now_count: 0, upcoming_count: 0, due_targets: [] },
    assignments: { overdue_count: 0, in_progress_count: 0, pending_count: 0, upcoming: [] }, today_plan: null, latest_feedback: null, class_contexts: [],
  };
  const api = createApiClient({ baseUrl: "http://api.example.test", fetcher: async (input) => { requested = String(input); return Response.json(response); } });
  const result = await api.studentLearningState("token");
  assert.equal(result.student_id, "student-1");
  assert.equal(requested, "http://api.example.test/students/me/learning-state");
});

test("studentLearningState parses fully populated nested real models", async () => {
  const fullResponse = {
    student_id: "student-1", as_of: "2026-10-08T03:00:00Z",
    available_subjects: [{ id: "sub-1", code: "MATH12", name: "Toán 12" }],
    focus_subject_id: "sub-1",
    current_action: { action_type: "REVIEW_DUE", subject_id: "sub-1", resource_id: "pt-1", practice_session_id: null, assignment_id: null, verification_id: null, adaptive_repair_session_id: null, study_task_id: null, target_type: "PROBLEM_TYPE", problem_type_id: "pt-1", concept_id: null, target_name: "Cực trị hàm số", target_code: "MATH12-PT-03", reason_code: "REVIEW_DUE", repair_cycle_index: null, phase: null },
    mastery_summary: { problem_type_started_count: 1, concept_started_count: 0, mastered_problem_type_count: 1, weak_problem_type_count: 0, mastered_concept_count: 0, weak_concept_count: 0, average_problem_type_mastery: 0.85, average_concept_mastery: null, weak_problem_types: [], weak_concepts: [] },
    priority_targets: [{ target_type: "PROBLEM_TYPE", problem_type_id: "pt-1", concept_id: null, target_name: "Cực trị hàm số", target_code: "MATH12-PT-03", reason_code: "REVIEW_DUE", priority_score: 0.9, mastery_score: 0.85, confidence: 0.95, desired_difficulty: 0.7 }],
    active_learning: { practice_session_id: null, practice_session_type: null, verification_id: null, adaptive_repair_session_id: null, assignment_id: null },
    verified_root_causes: [], repair: null,
    review: {
      due_now_count: 1, upcoming_count: 0,
      due_targets: [{ schedule_id: "sch-1", target_type: "PROBLEM_TYPE", problem_type_id: "pt-1", concept_id: null, target_name: "Cực trị hàm số", target_code: "MATH12-PT-03", next_review_at: "2026-10-08T00:00:00Z", review_interval_days: 2.0, review_count: 3, last_review_result: "CORRECT" }]
    },
    assignments: {
      overdue_count: 0, in_progress_count: 1, pending_count: 0,
      upcoming: [{ assignment_id: "asg-1", student_assignment_id: "sasg-1", classroom_id: "cls-1", subject_id: "sub-1", title: "Khảo sát hàm số", status: "IN_PROGRESS", start_at: "2026-10-01T00:00:00Z", due_at: "2026-10-15T00:00:00Z", score: null, is_overdue: false }]
    },
    today_plan: {
      date: "2026-10-08", available_daily_minutes: 60, total_estimated_minutes: 30, completed_count: 0, total_count: 1, days_to_exam: 200, notice: "Kế hoạch ngày",
      tasks: [{ id: "tsk-1", study_plan_id: "sp-1", task_type: "PRACTICE", status: "PENDING", planned_date: "2026-10-08", problem_type_id: "pt-1", problem_type_name: "Cực trị", concept_id: null, concept_name: null, topic_id: null, topic_name: null, chapter_id: null, chapter_name: null, subject_id: "sub-1", subject_name: "Toán 12", estimated_duration_minutes: 30, priority: 1, order_index: 0, reason_code: "REVIEW", completed_at: null, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:00Z" }]
    },
    latest_feedback: null, class_contexts: [{ classroom_id: "cls-1", classroom_name: "12A1" }]
  };
  const api = createApiClient({ baseUrl: "http://api.example.test", fetcher: async () => Response.json(fullResponse) });
  const result = await api.studentLearningState("token", "sub-1");
  assert.equal(result.review.due_targets[0].schedule_id, "sch-1");
  assert.equal(result.assignments.upcoming[0].title, "Khảo sát hàm số");
  assert.equal(result.today_plan?.tasks[0].estimated_duration_minutes, 30);
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

test("student workspace starts from a real approved problem through canonical API routes", async () => {
  const calls: { path: string; method: string; body: Record<string, unknown> | null }[] = [];
  const api = createApiClient({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
    const path = new URL(String(input)).pathname + new URL(String(input)).search;
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : null;
    calls.push({ path, method: init?.method ?? "GET", body });
    if (path === "/practice/sessions") return Response.json({ id: "session-1", subject_id: "subject-1" });
    if (path.endsWith("/next-problem")) return Response.json({ id: "question-1", content: "Bài toán thật", question_type: "OPEN_RESPONSE", options: [], is_read_only: false });
    if (path === "/api/v2/math-solutions/attempts" && init?.method === "POST") return Response.json({ id: "attempt-1", question_id: "question-1", status: "DRAFT", attempt_revision_number: 1, started_at: "2026-10-19T00:00:00Z" });
    return Response.json({ items: [], total: 0, page: 1, size: 20, total_pages: 0 });
  } });
  const history = await api.listMathAttempts("student-token");
  const session = await api.createPracticeSession("student-token", "subject-1");
  const problem = await api.getMathPracticeNextProblem("student-token", session.id);
  const attempt = await api.createMathAttempt("student-token", session.id, problem.id);
  assert.equal(history.total, 0);
  assert.equal(attempt.id, "attempt-1");
  assert.deepEqual(calls.map((call) => [call.method, call.path]), [
    ["GET", "/api/v2/math-solutions/attempts?page=1&size=20"],
    ["POST", "/practice/sessions"],
    ["GET", "/api/v2/math-solutions/practice-sessions/session-1/next-problem"],
    ["POST", "/api/v2/math-solutions/attempts"],
  ]);
  assert.deepEqual(calls[1].body, { subject_id: "subject-1", session_type: "PRACTICE", problem_type_ids: [], concept_ids: [] });
  assert.equal(calls[3].body?.question_id, "question-1");
  assert.equal(calls[3].body?.practice_session_id, "session-1");
});
