import assert from "node:assert/strict";
import test from "node:test";
import { parentBackendPath } from "../src/features/parent/route-path.js";
import {
  ParentApiError,
  parentApi,
  parseParentStudentProgress,
  parseParentStudentSummary,
  parseParentWeeklyAISummary,
  parseParentWeeklyData
} from "../src/features/parent/api.js";
import { ApiContractError } from "../src/lib/api/validation.js";

const id = "00000000-0000-4000-8000-000000000001";

test("parent proxy only exposes explicit parent paths", () => {
  assert.equal(parentBackendPath(["me"], "GET", ""), "/parents/me");
  assert.equal(parentBackendPath(["students"], "GET", ""), "/parent/students");
  assert.equal(parentBackendPath(["students", id, "progress"], "GET", ""), `/parent/students/${id}/progress`);
  assert.equal(parentBackendPath(["students", id, "weekly-data"], "GET", "?target_date=2026-10-27"), `/parent/students/${id}/weekly-data?target_date=2026-10-27`);
  assert.equal(parentBackendPath(["students", id, "ai-summary"], "POST", ""), `/parent/students/${id}/ai-summary`);
  assert.equal(parentBackendPath(["students", id, "ai-summary"], "GET", ""), null);
  assert.equal(parentBackendPath(["students", "..", "progress"], "GET", ""), null);
  assert.equal(parentBackendPath(["students", id, "progress"], "POST", ""), null);
  assert.equal(parentBackendPath(["students"], "GET", "?role=ADMIN"), null);
});

test("parent contract accepts real API shapes and rejects invalid payloads", () => {
  const summary = parseParentStudentSummary({
    student_id: id,
    student_name: "Student One",
    grade_level: 12,
    relationship_type: "GUARDIAN",
    school_name: "THPT Chuyên",
    overall_learning_trend: "IMPROVING",
    weekly_study_time_minutes: 185,
    active_alerts_count: 1
  });
  assert.equal(summary.student_name, "Student One");
  assert.equal(summary.weekly_study_time_minutes, 185);

  const progress = parseParentStudentProgress({
    student_id: id,
    student_name: "Student One",
    grade_level: 12,
    relationship_type: "GUARDIAN",
    subject_progress: [
      {
        subject_id: id,
        subject_name: "Toán 12",
        mastery_score: 0.78,
        completed_topics_count: 4,
        total_topics_count: 6
      }
    ],
    chapter_progress: [],
    topic_progress: [],
    major_weak_areas: [],
    study_plan_completion: {
      total_tasks: 10,
      completed_tasks: 8,
      completion_rate: 80
    },
    exam_trend: [],
    important_intervention_alerts: [],
    overall_learning_trend: "IMPROVING",
    trend_description: "Tiến độ học tập tăng trưởng ổn định."
  });
  assert.equal(progress.subject_progress[0]?.subject_name, "Toán 12");

  const weekly = parseParentWeeklyData({
    student_id: id,
    student_name: "Student One",
    week_start_date: "2026-10-20",
    week_end_date: "2026-10-27",
    total_study_time_minutes: 185,
    daily_study_time: [
      {
        date: "2026-10-20",
        day_of_week: "Monday",
        study_time_minutes: 45,
        questions_attempted: 12
      }
    ],
    tasks_completed_this_week: 8,
    tasks_total_this_week: 10,
    weekly_completion_rate: 80,
    exam_trend: [],
    overall_weekly_summary: "Hoàn thành 8/10 nhiệm vụ trong tuần."
  });
  assert.equal(weekly.total_study_time_minutes, 185);

  const aiSummary = parseParentWeeklyAISummary({
    student_id: id,
    student_name: "Student One",
    week_start_date: "2026-10-20",
    week_end_date: "2026-10-27",
    progress: "Học sinh duy trì nhịp độ tốt.",
    current_challenge: "Cần củng cố nguyên hàm từng phần.",
    next_week: "Luyện thêm 15 câu vận dụng.",
    how_parent_can_help: ["Động viên con duy trì lịch ôn tập"],
    is_fallback: true,
    generated_at: "2026-10-27T10:00:00Z"
  });
  assert.equal(aiSummary.is_fallback, true);

  assert.throws(() => parseParentStudentSummary({ student_id: id }), ApiContractError);
});

test("parent student list uses authenticated BFF and never fabricates a fallback", async () => {
  const original = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(
      JSON.stringify([
        {
          student_id: id,
          student_name: "Student One",
          grade_level: 12,
          relationship_type: "GUARDIAN",
          school_name: null,
          overall_learning_trend: "STABLE",
          weekly_study_time_minutes: 120,
          active_alerts_count: 0
        }
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }) as typeof fetch;
  try {
    const students = await parentApi.students();
    assert.equal(students.length, 1);
    assert.equal(calls[0], "/api/parent/students");
  } finally {
    globalThis.fetch = original;
  }
});

test("parent API reports backend errors without substituting sample data", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ error: { code: "API_UNAVAILABLE", message: "Backend unavailable" } }), {
      status: 503
    })) as typeof fetch;
  try {
    await assert.rejects(
      () => parentApi.students(),
      (error: unknown) => error instanceof ParentApiError && error.code === "API_UNAVAILABLE"
    );
  } finally {
    globalThis.fetch = original;
  }
});
