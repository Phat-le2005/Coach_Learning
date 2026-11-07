import assert from "node:assert/strict";
import test from "node:test";
import { adminBackendPath } from "../src/features/admin/route-path.js";
import {
  AdminApiError,
  adminApi,
  parseAdminAIUsageSummary,
  parseAdminSubject,
  parseAdminSubjectTree,
  parseAdminSupplyGap
} from "../src/features/admin/api.js";
import { ApiContractError } from "../src/lib/api/validation.js";

const id = "00000000-0000-4000-8000-000000000001";

test("admin proxy only exposes explicit admin paths", () => {
  assert.equal(adminBackendPath(["subjects"], "GET", ""), "/admin/subjects");
  assert.equal(adminBackendPath(["subjects", id, "curriculum-tree"], "GET", ""), `/admin/subjects/${id}/curriculum-tree`);
  assert.equal(adminBackendPath(["curricula"], "POST", ""), "/admin/curricula");
  assert.equal(adminBackendPath(["chapters"], "POST", ""), "/admin/chapters");
  assert.equal(adminBackendPath(["topics"], "POST", ""), "/admin/topics");
  assert.equal(adminBackendPath(["problem-types"], "POST", ""), "/admin/problem-types");
  assert.equal(adminBackendPath(["concepts"], "POST", ""), "/admin/concepts");
  assert.equal(adminBackendPath(["questions"], "GET", `?subject_id=${id}`), `/questions?subject_id=${id}`);
  assert.equal(adminBackendPath(["questions", id, "approve"], "POST", ""), `/questions/${id}/approve`);
  assert.equal(adminBackendPath(["question-supply", "gaps"], "GET", ""), "/question-supply/gaps");
  assert.equal(adminBackendPath(["question-supply", "gaps", "reassess-open"], "POST", ""), "/question-supply/gaps/reassess-open");
  assert.equal(adminBackendPath(["ai", "usage", "summary"], "GET", ""), "/admin/ai/usage/summary");
  assert.equal(adminBackendPath(["admission", "universities"], "GET", ""), "/admission/universities");
  assert.equal(adminBackendPath(["subjects", "..", "curriculum-tree"], "GET", ""), null);
  assert.equal(adminBackendPath(["unknown-endpoint"], "GET", ""), null);
});

test("admin contract accepts real API shapes and rejects invalid payloads", () => {
  const subject = parseAdminSubject({
    id,
    curriculum_version_id: id,
    code: "MATH12",
    name: "Toán 12",
    grade_level: 12,
    description: "Chương trình Toán 12",
    order_index: 1
  });
  assert.equal(subject.code, "MATH12");

  const tree = parseAdminSubjectTree({
    id,
    curriculum_version_id: id,
    code: "MATH12",
    name: "Toán 12",
    grade_level: 12,
    chapters: [
      {
        id,
        code: "CH1",
        name: "Ứng dụng đạo hàm",
        order_index: 1,
        topics: [
          {
            id,
            code: "TP1",
            name: "Tính đơn điệu",
            order_index: 1,
            problem_types: [
              {
                id,
                code: "PT1",
                name: "Xét chiều biến thiên",
                order_index: 1,
                is_active: true,
                concept_count: 2,
                learning_outcome_count: 1
              }
            ]
          }
        ]
      }
    ]
  });
  assert.equal(tree.chapters[0]?.topics[0]?.problem_types[0]?.code, "PT1");

  const gap = parseAdminSupplyGap({
    id,
    signature: "MATH12:PT1:BAND3",
    subject_id: id,
    use_case: "PRACTICE",
    target_type: "PROBLEM_TYPE",
    concept_id: null,
    problem_type_id: id,
    misconception_definition_id: null,
    desired_difficulty: 3,
    difficulty_min: 2,
    difficulty_max: 4,
    minimum_required_count: 20,
    preferred_count: 30,
    approved_eligible_count: 5,
    approved_in_band_count: 4,
    pipeline_candidate_count: 2,
    pipeline_runtime_eligible_count: 1,
    severity: "HIGH",
    status: "OPEN",
    reason_code: "LOW_APPROVED_SUPPLY",
    demand_count: 15,
    last_observed_at: "2026-10-29T00:00:00Z",
    last_assessed_at: "2026-10-29T00:00:00Z"
  });
  assert.equal(gap.demand_count, 15);

  const aiSummary = parseAdminAIUsageSummary({
    total_requests: 42,
    successful_requests: 40,
    failed_requests: 2,
    failure_rate: 0.047,
    average_latency_ms: 820,
    total_input_tokens: 12000,
    total_output_tokens: 6400,
    total_tokens: 18400,
    total_estimated_cost: 0.092,
    average_requests_per_student_per_day: 2.1,
    requests_per_task: [
      {
        task: "PARENT_SUMMARY",
        requests: 5,
        successful_requests: 5,
        failed_requests: 0,
        failure_rate: 0,
        average_latency_ms: 910,
        total_tokens: 3200,
        estimated_cost: 0.015
      }
    ]
  });
  assert.equal(aiSummary.total_requests, 42);

  assert.throws(() => parseAdminSubject({ id, code: "MATH12" }), ApiContractError);
});

test("admin subjects uses authenticated BFF and never fabricates a fallback", async () => {
  const original = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(
      JSON.stringify([
        {
          id,
          curriculum_version_id: id,
          code: "MATH12",
          name: "Toán 12",
          grade_level: 12,
          description: null,
          order_index: 1
        }
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }) as typeof fetch;
  try {
    const subjects = await adminApi.subjects();
    assert.equal(subjects.length, 1);
    assert.equal(calls[0], "/api/admin/subjects?offset=0&limit=200");
  } finally {
    globalThis.fetch = original;
  }
});

test("admin API reports backend errors without substituting sample data", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ error: { code: "API_UNAVAILABLE", message: "Backend unavailable" } }), {
      status: 503
    })) as typeof fetch;
  try {
    await assert.rejects(
      () => adminApi.subjects(),
      (error: unknown) => error instanceof AdminApiError && error.code === "API_UNAVAILABLE"
    );
  } finally {
    globalThis.fetch = original;
  }
});
