"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const client_1 = require("../src/lib/api/client");
const validation_1 = require("../src/lib/api/validation");
const tokenPair = { access_token: "access", refresh_token: "refresh", token_type: "bearer", expires_in: 900 };
(0, node_test_1.default)("login uses the canonical root path and validates the token response", async () => {
    let requested = "";
    const api = (0, client_1.createApiClient)({ baseUrl: "http://api.example.test", fetcher: async (input) => {
            requested = String(input);
            return Response.json(tokenPair);
        } });
    strict_1.default.deepEqual(await api.login({ email: " Student@Example.com ", password: "safe-password" }), tokenPair);
    strict_1.default.equal(requested, "http://api.example.test/auth/login");
});
(0, node_test_1.default)("refresh and current-user calls use canonical auth paths without exposing token in a query", async () => {
    const calls = [];
    const api = (0, client_1.createApiClient)({ baseUrl: "http://api.example.test", fetcher: async (input, init) => {
            calls.push({ url: String(input), authorization: new Headers(init === null || init === void 0 ? void 0 : init.headers).get("Authorization") });
            return calls.length === 1 ? Response.json(tokenPair) : Response.json({ id: "u1", email: "s@example.com", full_name: "Student", role: "STUDENT", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });
        } });
    await api.refresh("refresh-secret");
    await api.me("access-secret");
    strict_1.default.deepEqual(calls, [
        { url: "http://api.example.test/auth/refresh", authorization: null },
        { url: "http://api.example.test/auth/me", authorization: "Bearer access-secret" },
    ]);
});
(0, node_test_1.default)("validates the real Student Learning State boundary", async () => {
    const response = {
        student_id: "student-1", as_of: "2026-10-08T03:00:00Z", available_subjects: [], focus_subject_id: null,
        current_action: { action_type: "IDLE", subject_id: null, resource_id: null, practice_session_id: null, assignment_id: null, verification_id: null, adaptive_repair_session_id: null, study_task_id: null, target_type: null, problem_type_id: null, concept_id: null, target_name: null, target_code: null, reason_code: null, repair_cycle_index: null, phase: null },
        mastery_summary: { problem_type_started_count: 0, concept_started_count: 0, mastered_problem_type_count: 0, weak_problem_type_count: 0, mastered_concept_count: 0, weak_concept_count: 0, average_problem_type_mastery: null, average_concept_mastery: null, weak_problem_types: [], weak_concepts: [] },
        priority_targets: [], active_learning: { practice_session_id: null, practice_session_type: null, verification_id: null, adaptive_repair_session_id: null, assignment_id: null },
        verified_root_causes: [], repair: null, review: { due_now_count: 0, upcoming_count: 0, due_targets: [] },
        assignments: { overdue_count: 0, in_progress_count: 0, pending_count: 0, upcoming: [] }, today_plan: null, latest_feedback: null, class_contexts: [],
    };
    let requested = "";
    const api = (0, client_1.createApiClient)({ baseUrl: "http://api.example.test", fetcher: async (input) => { requested = String(input); return Response.json(response); } });
    strict_1.default.equal((await api.studentLearningState("access", "math-id")).student_id, "student-1");
    strict_1.default.equal(requested, "http://api.example.test/students/me/learning-state?subject_id=math-id");
});
(0, node_test_1.default)("studentLearningState without subject_id omits query parameter", async () => {
    let requested = "";
    const response = {
        student_id: "student-1", as_of: "2026-10-08T03:00:00Z", available_subjects: [], focus_subject_id: null,
        current_action: { action_type: "IDLE", subject_id: null, resource_id: null, practice_session_id: null, assignment_id: null, verification_id: null, adaptive_repair_session_id: null, study_task_id: null, target_type: null, problem_type_id: null, concept_id: null, target_name: null, target_code: null, reason_code: null, repair_cycle_index: null, phase: null },
        mastery_summary: { problem_type_started_count: 0, concept_started_count: 0, mastered_problem_type_count: 0, weak_problem_type_count: 0, mastered_concept_count: 0, weak_concept_count: 0, average_problem_type_mastery: null, average_concept_mastery: null, weak_problem_types: [], weak_concepts: [] },
        priority_targets: [], active_learning: { practice_session_id: null, practice_session_type: null, verification_id: null, adaptive_repair_session_id: null, assignment_id: null },
        verified_root_causes: [], repair: null, review: { due_now_count: 0, upcoming_count: 0, due_targets: [] },
        assignments: { overdue_count: 0, in_progress_count: 0, pending_count: 0, upcoming: [] }, today_plan: null, latest_feedback: null, class_contexts: [],
    };
    const api = (0, client_1.createApiClient)({ baseUrl: "http://api.example.test", fetcher: async (input) => { requested = String(input); return Response.json(response); } });
    const result = await api.studentLearningState("token");
    strict_1.default.equal(result.student_id, "student-1");
    strict_1.default.equal(requested, "http://api.example.test/students/me/learning-state");
});
(0, node_test_1.default)("studentLearningState parses fully populated nested real models", async () => {
    var _a;
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
    const api = (0, client_1.createApiClient)({ baseUrl: "http://api.example.test", fetcher: async () => Response.json(fullResponse) });
    const result = await api.studentLearningState("token", "sub-1");
    strict_1.default.equal(result.review.due_targets[0].schedule_id, "sch-1");
    strict_1.default.equal(result.assignments.upcoming[0].title, "Khảo sát hàm số");
    strict_1.default.equal((_a = result.today_plan) === null || _a === void 0 ? void 0 : _a.tasks[0].estimated_duration_minutes, 30);
});
for (const [status, category] of [[401, "unauthorized"], [403, "forbidden"], [404, "not_found"], [409, "conflict"], [422, "validation"], [503, "unavailable"]]) {
    (0, node_test_1.default)(`maps HTTP ${status} to ${category}`, async () => {
        const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async () => Response.json({ error: { code: `E_${status}`, message: "backend error", details: [{ field: "email", message: "invalid" }] } }, { status }) });
        await strict_1.default.rejects(api.login({ email: "a@example.com", password: "x" }), (error) => error instanceof client_1.ApiResponseError && error.status === status && error.category === category && error.code === `E_${status}`);
    });
}
(0, node_test_1.default)("distinguishes a network failure", async () => {
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async () => { throw new TypeError("offline"); } });
    await strict_1.default.rejects(api.login({ email: "a@example.com", password: "x" }), client_1.ApiNetworkError);
});
(0, node_test_1.default)("rejects a successful response that violates the contract", async () => {
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async () => Response.json({ access_token: "missing fields" }) });
    await strict_1.default.rejects(api.login({ email: "a@example.com", password: "x" }), validation_1.ApiContractError);
});
(0, node_test_1.default)("rejects API base URLs with an invented prefix", () => {
    strict_1.default.throws(() => (0, client_1.normalizeApiBaseUrl)("https://api.example.test/api/v1"), /root paths/u);
});
(0, node_test_1.default)("student workspace starts from a real approved problem through canonical API routes", async () => {
    var _a, _b;
    const calls = [];
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
            var _a;
            const path = new URL(String(input)).pathname + new URL(String(input)).search;
            const body = (init === null || init === void 0 ? void 0 : init.body) ? JSON.parse(String(init.body)) : null;
            calls.push({ path, method: (_a = init === null || init === void 0 ? void 0 : init.method) !== null && _a !== void 0 ? _a : "GET", body });
            if (path === "/practice/sessions")
                return Response.json({ id: "session-1", subject_id: "subject-1" });
            if (path.endsWith("/next-problem"))
                return Response.json({ id: "question-1", content: "Bài toán thật", question_type: "OPEN_RESPONSE", options: [], is_read_only: false });
            if (path === "/api/v2/math-solutions/attempts" && (init === null || init === void 0 ? void 0 : init.method) === "POST")
                return Response.json({ id: "attempt-1", question_id: "question-1", status: "DRAFT", attempt_revision_number: 1, started_at: "2026-10-19T00:00:00Z" });
            return Response.json({ items: [], total: 0, page: 1, size: 20, total_pages: 0 });
        } });
    const history = await api.listMathAttempts("student-token");
    const session = await api.createPracticeSession("student-token", "subject-1");
    const problem = await api.getMathPracticeNextProblem("student-token", session.id);
    const attempt = await api.createMathAttempt("student-token", session.id, problem.id);
    strict_1.default.equal(history.total, 0);
    strict_1.default.equal(attempt.id, "attempt-1");
    strict_1.default.deepEqual(calls.map((call) => [call.method, call.path]), [
        ["GET", "/api/v2/math-solutions/attempts?page=1&size=20"],
        ["POST", "/practice/sessions"],
        ["GET", "/api/v2/math-solutions/practice-sessions/session-1/next-problem"],
        ["POST", "/api/v2/math-solutions/attempts"],
    ]);
    strict_1.default.deepEqual(calls[1].body, { subject_id: "subject-1", session_type: "PRACTICE", problem_type_ids: [], concept_ids: [] });
    strict_1.default.equal((_a = calls[3].body) === null || _a === void 0 ? void 0 : _a.question_id, "question-1");
    strict_1.default.equal((_b = calls[3].body) === null || _b === void 0 ? void 0 : _b.practice_session_id, "session-1");
});
(0, node_test_1.default)("deleting a saved math step sends the revision and idempotency key to the scoped v2 route", async () => {
    const calls = [];
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
            var _a;
            calls.push({
                path: new URL(String(input)).pathname,
                method: (_a = init === null || init === void 0 ? void 0 : init.method) !== null && _a !== void 0 ? _a : "GET",
                body: (init === null || init === void 0 ? void 0 : init.body) ? JSON.parse(String(init.body)) : null,
            });
            return Response.json({
                id: "attempt-1", question_id: "question-1", status: "IN_PROGRESS",
                attempt_revision_number: 6, started_at: "2026-10-23T00:00:00Z", steps: [],
            });
        } });
    const token = { expected_attempt_revision: 5, client_action_id: "a1234567-89ab-4cde-8012-3456789abcde" };
    const result = await api.deleteMathStep("student-token", "attempt-1", "step-2", token);
    strict_1.default.equal(result.current_revision, 6);
    strict_1.default.deepEqual(result.steps, []);
    strict_1.default.deepEqual(calls, [{
            path: "/api/v2/math-solutions/attempts/attempt-1/steps/step-2/delete",
            method: "POST", body: token,
        }]);
});
(0, node_test_1.default)("student submits a confirmed attempt then receives only provisional AI step feedback", async () => {
    const calls = [];
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
            var _a;
            const path = new URL(String(input)).pathname;
            calls.push({ path, method: (_a = init === null || init === void 0 ? void 0 : init.method) !== null && _a !== void 0 ? _a : "GET", body: (init === null || init === void 0 ? void 0 : init.body) ? JSON.parse(String(init.body)) : null });
            if (path.endsWith("/submit"))
                return Response.json({
                    id: "attempt-1", question_id: "question-1", status: "SUBMITTED",
                    attempt_revision_number: 3, started_at: "2026-10-24T00:00:00Z", steps: [],
                });
            return Response.json({ attempt_id: "attempt-1", is_final: false, needs_teacher_review: false,
                step_grades: [{ step_index: 1, verdict: "VALID", score: 0.8,
                        confidence: 0.92, feedback: "The step matches the reviewed answer." }] });
        } });
    const token = { expected_attempt_revision: 2, client_action_id: "a1234567-89ab-4cde-8012-3456789abcde" };
    strict_1.default.equal((await api.submitMathAttempt("student-token", "attempt-1", token)).status, "SUBMITTED");
    const review = await api.reviewMathAttempt("student-token", "attempt-1");
    strict_1.default.equal(review.is_final, false);
    strict_1.default.equal(review.step_grades[0].score, 0.8);
    strict_1.default.deepEqual(calls, [
        { path: "/api/v2/math-solutions/attempts/attempt-1/submit", method: "POST", body: token },
        { path: "/api/v3/math-solutions/attempts/attempt-1/ai-review", method: "POST", body: null },
    ]);
});
(0, node_test_1.default)("frontend rejects AI feedback that claims a final grade", async () => {
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async () => Response.json({ attempt_id: "attempt-1", is_final: true, needs_teacher_review: false,
            step_grades: [{ step_index: 1, verdict: "VALID", score: 1, confidence: 0.9, feedback: "OK" }] }) });
    await strict_1.default.rejects(api.reviewMathAttempt("student-token", "attempt-1"), validation_1.ApiContractError);
});
(0, node_test_1.default)("paper upload sends multipart bytes without a fake JSON response", async () => {
    let contentType = null;
    let uploadedName = "";
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
            strict_1.default.equal(new URL(String(input)).pathname, "/api/v3/math-solutions/attempts/attempt-1/paper");
            contentType = new Headers(init === null || init === void 0 ? void 0 : init.headers).get("Content-Type");
            uploadedName = (init === null || init === void 0 ? void 0 : init.body).get("file") instanceof File
                ? (init === null || init === void 0 ? void 0 : init.body).get("file").name : "";
            return Response.json({ id: "paper-1", file_name: "work.png", content_type: "image/png",
                size_bytes: 4, sha256: "a".repeat(64), created_at: "2026-10-26T00:00:00Z" }, { status: 201 });
        } });
    const file = new File([new Uint8Array([1, 2, 3, 4])], "work.png", { type: "image/png" });
    const result = await api.uploadMathPaper("student-token", "attempt-1", file);
    strict_1.default.equal(contentType, null);
    strict_1.default.equal(uploadedName, "work.png");
    strict_1.default.equal(result.id, "paper-1");
});
(0, node_test_1.default)("paper OCR returns editable suggestions without creating solution steps", async () => {
    let called = "";
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
            called = `${init === null || init === void 0 ? void 0 : init.method} ${new URL(String(input)).pathname}`;
            return Response.json({ paper_id: "paper-1", file_sha256: "a".repeat(64), provider: "GEMINI",
                suggestions: [{ page_number: 1, kind: "TABLE", text: "x: -1, 3\ny': +, -, +", uncertain: true }] });
        } });
    const result = await api.recognizeMathPaper("student-token", "attempt-1", "paper-1");
    strict_1.default.equal(called, "POST /api/v3/math-solutions/attempts/attempt-1/paper/paper-1/ocr");
    strict_1.default.equal(result.suggestions[0].kind, "TABLE");
    strict_1.default.equal(result.suggestions[0].uncertain, true);
});
(0, node_test_1.default)("review readiness explains missing approved answers without requesting a grade", async () => {
    const calls = [];
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
            calls.push(`${init === null || init === void 0 ? void 0 : init.method} ${new URL(String(input)).pathname}`);
            return Response.json({ available: false, reason_code: "GRADING_ANSWER_REQUIRED" });
        } });
    const result = await api.getMathAIReviewAvailability("student-token", "attempt-1");
    strict_1.default.deepEqual(result, { available: false, reason_code: "GRADING_ANSWER_REQUIRED" });
    strict_1.default.deepEqual(calls, ["GET /api/v3/math-solutions/attempts/attempt-1/ai-review"]);
});
(0, node_test_1.default)("editing a student variation table uses scoped PATCH with structured artifact", async () => {
    let method = "";
    let path = "";
    let sent;
    const api = (0, client_1.createApiClient)({ baseUrl: "https://api.example.test", fetcher: async (input, init) => {
            var _a;
            method = (_a = init === null || init === void 0 ? void 0 : init.method) !== null && _a !== void 0 ? _a : "";
            path = new URL(String(input)).pathname;
            sent = JSON.parse(String(init === null || init === void 0 ? void 0 : init.body));
            return Response.json({ id: "attempt-1", question_id: "question-1", status: "IN_PROGRESS",
                attempt_revision_number: 5, started_at: "2026-10-25T00:00:00Z", steps: [] });
        } });
    const artifact = { artifact_type: "VARIATION_TABLE", payload: {
            version: 1,
            points: [{ x: "left", derivative: "", y: "" }, { x: "right", derivative: "", y: "" }],
            intervals: [{ sign: "+", trend: "UP" }],
        } };
    await api.updateMathStep("student-token", "attempt-1", "step-1", {
        expected_attempt_revision: 4, client_action_id: "a1234567-89ab-4cde-8012-3456789abcde",
        step_type: "VARIATION_TABLE", content_latex: null, explanation_text: null, artifact,
    });
    strict_1.default.equal(method, "PATCH");
    strict_1.default.equal(path, "/api/v2/math-solutions/attempts/attempt-1/steps/step-1");
    strict_1.default.deepEqual(sent.artifact, artifact);
});
