import assert from "node:assert/strict";
import test from "node:test";

import { safeMasteryPercent, toStudentHomeViewModel } from "../src/features/student-home/adapter";
import type { StudentLearningStateRead, StudentMasteryRead } from "../src/lib/api/contracts";
import { ApiContractError } from "../src/lib/api/validation";

function createLearningState(overrides: Partial<StudentLearningStateRead> = {}): StudentLearningStateRead {
  return {
    student_id: "student-uuid-1",
    as_of: "2026-10-08T05:00:00Z",
    available_subjects: [
      { id: "sub-1", code: "MATH12", name: "Toán 12" },
      { id: "sub-2", code: "PHYS12", name: "Vật lý 12" },
    ],
    focus_subject_id: "sub-1",
    current_action: {
      action_type: "CONTINUE_REPAIR",
      subject_id: "sub-1",
      resource_id: "repair-session-1",
      practice_session_id: null,
      assignment_id: null,
      verification_id: null,
      adaptive_repair_session_id: "repair-session-1",
      study_task_id: null,
      target_type: "PROBLEM_TYPE",
      problem_type_id: "pt-1",
      concept_id: null,
      target_name: "Đơn điệu hàm phân thức bậc nhất",
      target_code: "MATH12-PT-02",
      reason_code: "VERIFIED_ROOT_CAUSE",
      repair_cycle_index: 1,
      phase: "PRACTICE",
    },
    mastery_summary: {
      problem_type_started_count: 5,
      concept_started_count: 8,
      mastered_problem_type_count: 3,
      weak_problem_type_count: 2,
      mastered_concept_count: 6,
      weak_concept_count: 2,
      average_problem_type_mastery: 0.725,
      average_concept_mastery: 0.81,
      weak_problem_types: [],
      weak_concepts: [],
    },
    priority_targets: [
      {
        target_type: "PROBLEM_TYPE",
        problem_type_id: "pt-1",
        concept_id: null,
        target_name: "Đơn điệu hàm phân thức bậc nhất",
        target_code: "MATH12-PT-02",
        reason_code: "VERIFIED_ROOT_CAUSE",
        priority_score: 0.94,
        mastery_score: 0.42,
        confidence: 0.88,
        desired_difficulty: 0.65,
      },
    ],
    active_learning: {
      practice_session_id: null,
      practice_session_type: null,
      verification_id: null,
      adaptive_repair_session_id: "repair-session-1",
      assignment_id: null,
    },
    verified_root_causes: [],
    repair: null,
    review: {
      due_now_count: 2,
      upcoming_count: 4,
      due_targets: [
        {
          schedule_id: "sched-1",
          target_type: "PROBLEM_TYPE",
          problem_type_id: "pt-2",
          concept_id: null,
          target_name: "Cực trị hàm trùng phương",
          target_code: "MATH12-PT-04",
          next_review_at: "2026-10-08T00:00:00Z",
          review_interval_days: 3.5,
          review_count: 2,
          last_review_result: "CORRECT",
        },
      ],
    },
    assignments: {
      overdue_count: 1,
      in_progress_count: 2,
      pending_count: 1,
      upcoming: [
        {
          assignment_id: "asg-1",
          student_assignment_id: "sasg-1",
          classroom_id: "class-1",
          subject_id: "sub-1",
          title: "Bài tập tuần 4",
          status: "IN_PROGRESS",
          start_at: "2026-10-01T00:00:00Z",
          due_at: "2026-10-07T23:59:59Z",
          score: null,
          is_overdue: true,
        },
      ],
    },
    today_plan: {
      date: "2026-10-08",
      available_daily_minutes: 90,
      total_estimated_minutes: 45,
      tasks: [
        {
          id: "task-1",
          study_plan_id: "sp-1",
          task_type: "PRACTICE",
          status: "PENDING",
          planned_date: "2026-10-08",
          problem_type_id: "pt-1",
          problem_type_name: "Đơn điệu",
          concept_id: null,
          concept_name: null,
          topic_id: null,
          topic_name: null,
          chapter_id: null,
          chapter_name: null,
          subject_id: "sub-1",
          subject_name: "Toán 12",
          estimated_duration_minutes: 45,
          priority: 1,
          order_index: 0,
          reason_code: "TARGET_WEAKNESS",
          completed_at: null,
          created_at: "2026-10-08T00:00:00Z",
          updated_at: "2026-10-08T00:00:00Z",
        },
      ],
      completed_count: 0,
      total_count: 1,
      days_to_exam: 240,
      notice: "Ưu tiên củng cố dạng bài yếu",
    },
    latest_feedback: null,
    class_contexts: [],
    ...overrides,
  };
}

test("safeMasteryPercent strictly distinguishes zero, null, and out-of-range bounds", () => {
  assert.equal(safeMasteryPercent(0.0), 0);
  assert.equal(safeMasteryPercent(0.684), 68);
  assert.equal(safeMasteryPercent(1.0), 100);
  assert.equal(safeMasteryPercent(null), undefined);
  assert.equal(safeMasteryPercent(undefined), undefined);
  assert.equal(safeMasteryPercent(Number.NaN), undefined);
  assert.equal(safeMasteryPercent(-0.1), undefined);
  assert.equal(safeMasteryPercent(1.05), undefined);
});

test("toStudentHomeViewModel maps real learning state accurately", () => {
  const source = createLearningState();
  const vm = toStudentHomeViewModel(source, "Nguyễn Văn A", "a@example.com");

  assert.equal(vm.student.displayName, "Nguyễn Văn A");
  assert.equal(vm.student.email, "a@example.com");
  assert.equal(vm.subject.id, "sub-1");
  assert.equal(vm.subject.name, "Toán 12");
  assert.equal(vm.availableSubjects.length, 2);

  // Resolved action
  assert.equal(vm.resolvedAction.type, "CONTINUE_REPAIR");
  assert.equal(vm.resolvedAction.resourceId, "repair-session-1");
  assert.equal(vm.resolvedAction.targetName, "Đơn điệu hàm phân thức bậc nhất");
  assert.equal(vm.resolvedAction.hasAvailableRoute, false);

  // Mastery summary
  assert.equal(vm.mastery.score, 73);
  assert.equal(vm.mastery.label, "Độ vững hiện tại");
  assert.equal(vm.mastery.hasEvidence, true);
  assert.equal(vm.mastery.problemTypeStartedCount, 5);
  assert.equal(vm.mastery.weakProblemTypeCount, 2);

  // Assignments breakdown (overdue=1, in_progress=2, pending=1 -> active=4)
  assert.equal(vm.assignments.activeCount, 4);
  assert.equal(vm.assignments.overdueCount, 1);
  assert.equal(vm.assignments.inProgressCount, 2);
  assert.equal(vm.assignments.pendingCount, 1);
  assert.equal(vm.assignments.upcoming.length, 1);
  assert.equal(vm.assignments.upcoming[0].title, "Bài tập tuần 4");

  // Reviews
  assert.equal(vm.review.dueCount, 2);
  assert.equal(vm.review.upcomingCount, 4);
  assert.equal(vm.review.dueTargets.length, 1);
  assert.equal(vm.review.dueTargets[0].targetName, "Cực trị hàm trùng phương");

  // Today's plan
  assert.ok(vm.todayPlan);
  assert.equal(vm.todayPlan.totalCount, 1);
  assert.equal(vm.todayPlan.completedCount, 0);
  assert.equal(vm.todayPlan.totalEstimatedMinutes, 45);
  assert.equal(vm.todayPlan.notice, "Ưu tiên củng cố dạng bài yếu");

  // Priorities
  assert.equal(vm.priorities.length, 1);
  assert.equal(vm.priorities[0].targetName, "Đơn điệu hàm phân thức bậc nhất");
  assert.equal(vm.priorities[0].mastery, 42);
  assert.equal(vm.priorities[0].desiredDifficulty, 0.65);
});

test("toStudentHomeViewModel handles null mastery and empty study history gracefully", () => {
  const source = createLearningState({
    mastery_summary: {
      problem_type_started_count: 0,
      concept_started_count: 0,
      mastered_problem_type_count: 0,
      weak_problem_type_count: 0,
      mastered_concept_count: 0,
      weak_concept_count: 0,
      average_problem_type_mastery: null,
      average_concept_mastery: null,
      weak_problem_types: [],
      weak_concepts: [],
    },
    today_plan: null,
  });

  const vm = toStudentHomeViewModel(source, "Học sinh mới");
  assert.equal(vm.mastery.score, undefined);
  assert.equal(vm.mastery.label, "Chưa đủ dữ liệu");
  assert.equal(vm.mastery.hasEvidence, false);
  assert.equal(vm.todayPlan, null);
});

test("toStudentHomeViewModel handles 0.0 mastery distinct from null", () => {
  const source = createLearningState({
    mastery_summary: {
      problem_type_started_count: 2,
      concept_started_count: 2,
      mastered_problem_type_count: 0,
      weak_problem_type_count: 2,
      mastered_concept_count: 0,
      weak_concept_count: 2,
      average_problem_type_mastery: 0.0,
      average_concept_mastery: 0.0,
      weak_problem_types: [],
      weak_concepts: [],
    },
  });

  const vm = toStudentHomeViewModel(source, "Học sinh");
  assert.equal(vm.mastery.score, 0);
  assert.equal(vm.mastery.label, "Độ vững hiện tại");
  assert.equal(vm.mastery.hasEvidence, true);
});

test("toStudentHomeViewModel handles empty available_subjects without crashing", () => {
  const source = createLearningState({
    available_subjects: [],
    focus_subject_id: null,
  });

  const vm = toStudentHomeViewModel(source, "Học sinh");
  assert.equal(vm.availableSubjects.length, 0);
  assert.equal(vm.subject.name, "Chưa có môn học");
  assert.equal(vm.subject.id, "");
});

test("toStudentHomeViewModel throws ApiContractError for invalid current_action type", () => {
  const source = createLearningState({
    current_action: {
      ...createLearningState().current_action,
      action_type: "UNSUPPORTED_ACTION" as any,
    },
  });

  assert.throws(
    () => toStudentHomeViewModel(source, "Học sinh"),
    (err: unknown) => err instanceof ApiContractError && err.path === "response.current_action.action_type"
  );
});

test("new student receives truthful self-study onboarding without classroom data leakage", () => {
  const source = createLearningState({
    available_subjects: [],
    focus_subject_id: null,
    class_contexts: [],
  });
  const mastery: StudentMasteryRead = {
    student_id: source.student_id,
    subjects: [
      {
        subject_id: "math-self-study",
        code: "MATH_G12",
        name: "Toán 12",
        mastery_score: 0,
        confidence: 0,
        attempt_count: 0,
        correct_count: 0,
        last_practiced_at: null,
        last_updated_at: null,
        state: "NOT_STARTED",
        problem_type_count: 1,
        started_problem_type_count: 0,
        chapters: [
          {
            chapter_id: "chapter-1",
            subject_id: "math-self-study",
            code: "CHAPTER_1",
            name: "Ứng dụng đạo hàm",
            mastery_score: 0,
            confidence: 0,
            attempt_count: 0,
            correct_count: 0,
            last_practiced_at: null,
            last_updated_at: null,
            state: "NOT_STARTED",
            problem_type_count: 1,
            started_problem_type_count: 0,
            topics: [],
          },
        ],
        concepts: [],
      },
    ],
  };

  const vm = toStudentHomeViewModel(source, "Học sinh mới", undefined, mastery, {
    availableSubjects: [
      { id: "math-self-study", code: "MATH_G12", name: "Toán 12" },
    ],
    selectedSubjectId: "math-self-study",
    discoveryOnlySubjectIds: ["math-self-study"],
  });

  assert.equal(vm.learningContext.mode, "SELF_STUDY_ONBOARDING");
  assert.equal(vm.learningContext.subjectHasActivity, false);
  assert.equal(vm.subject.name, "Toán 12");
  assert.equal(vm.currentAction.type, "IDLE");
  assert.equal(vm.mastery.hasEvidence, false);
  assert.equal(vm.mastery.score, undefined);
  assert.equal(vm.assignments.activeCount, 0);
  assert.equal(vm.review.dueCount, 0);
  assert.equal(vm.todayPlan, null);
  assert.equal(vm.priorities.length, 0);
  assert.equal(vm.knowledgeRegions[0].state, "not_started");
  assert.equal(vm.knowledgeRegions[0].progress, undefined);
});
