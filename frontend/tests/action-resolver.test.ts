import assert from "node:assert/strict";
import test from "node:test";

import { resolveStudentAction } from "../src/features/student-home/action-resolver";
import type { StudentCurrentActionRead } from "../src/lib/api/contracts";

function createAction(overrides: Partial<StudentCurrentActionRead>): StudentCurrentActionRead {
  return {
    action_type: "IDLE",
    subject_id: "subject-1",
    resource_id: null,
    practice_session_id: null,
    assignment_id: null,
    verification_id: null,
    adaptive_repair_session_id: null,
    study_task_id: null,
    target_type: null,
    problem_type_id: null,
    concept_id: null,
    target_name: null,
    target_code: null,
    reason_code: null,
    repair_cycle_index: null,
    phase: null,
    ...overrides,
  };
}

test("resolves CONTINUE_REPAIR with adaptive repair session and phase", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "CONTINUE_REPAIR",
      adaptive_repair_session_id: "repair-uuid-1",
      target_name: "Đơn điệu hàm trị tuyệt đối",
      target_code: "MATH12-PT-01",
      target_type: "PROBLEM_TYPE",
      repair_cycle_index: 2,
      phase: "PRACTICE",
    })
  );

  assert.equal(resolved.type, "CONTINUE_REPAIR");
  assert.equal(resolved.resourceId, "repair-uuid-1");
  assert.equal(resolved.resourceType, "adaptive_repair_session");
  assert.equal(resolved.targetName, "Đơn điệu hàm trị tuyệt đối");
  assert.equal(resolved.targetCode, "MATH12-PT-01");
  assert.equal(resolved.repairCycleIndex, 2);
  assert.equal(resolved.phase, "PRACTICE");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.equal(resolved.route, undefined);
  assert.match(resolved.title, /vá mắt xích/iu);
});

test("resolves CONTINUE_VERIFICATION with verification target", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "CONTINUE_VERIFICATION",
      verification_id: "verif-uuid-2",
      target_name: "Ngộ nhận dấu đạo hàm",
      target_code: "MATH12-MIS-01",
      target_type: "CONCEPT",
    })
  );

  assert.equal(resolved.type, "CONTINUE_VERIFICATION");
  assert.equal(resolved.resourceId, "verif-uuid-2");
  assert.equal(resolved.resourceType, "root_cause_verification");
  assert.equal(resolved.targetName, "Ngộ nhận dấu đạo hàm");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /xác minh/iu);
});

test("resolves CONTINUE_ASSIGNMENT with assignment id", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "CONTINUE_ASSIGNMENT",
      assignment_id: "assign-uuid-3",
      target_name: "Bài tập tuần 3 - Khảo sát hàm số",
    })
  );

  assert.equal(resolved.type, "CONTINUE_ASSIGNMENT");
  assert.equal(resolved.resourceId, "assign-uuid-3");
  assert.equal(resolved.resourceType, "classroom_assignment");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /bài tập/iu);
});

test("resolves COMPLETE_OVERDUE_ASSIGNMENT with urgency", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "COMPLETE_OVERDUE_ASSIGNMENT",
      assignment_id: "assign-uuid-4",
      target_name: "Bài kiểm tra chương 1",
    })
  );

  assert.equal(resolved.type, "COMPLETE_OVERDUE_ASSIGNMENT");
  assert.equal(resolved.resourceId, "assign-uuid-4");
  assert.equal(resolved.resourceType, "classroom_assignment");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /quá hạn/iu);
});

test("resolves CONTINUE_PRACTICE with practice session", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "CONTINUE_PRACTICE",
      practice_session_id: "practice-uuid-5",
      target_name: "Luyện tập tích phân",
    })
  );

  assert.equal(resolved.type, "CONTINUE_PRACTICE");
  assert.equal(resolved.resourceId, "practice-uuid-5");
  assert.equal(resolved.resourceType, "practice_session");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /luyện tập/iu);
});

test("resolves REVIEW_DUE with target and spaced repetition context", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "REVIEW_DUE",
      problem_type_id: "pt-uuid-6",
      target_name: "Cực trị hàm trùng phương",
      target_code: "MATH12-PT-04",
      target_type: "PROBLEM_TYPE",
    })
  );

  assert.equal(resolved.type, "REVIEW_DUE");
  assert.equal(resolved.resourceId, "pt-uuid-6");
  assert.equal(resolved.targetName, "Cực trị hàm trùng phương");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /ôn tập/iu);
});

test("resolves TODAY_TASK with study task id", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "TODAY_TASK",
      study_task_id: "task-uuid-7",
      target_name: "Giải 5 bài tiệm cận đứng",
    })
  );

  assert.equal(resolved.type, "TODAY_TASK");
  assert.equal(resolved.resourceId, "task-uuid-7");
  assert.equal(resolved.resourceType, "study_task");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /kế hoạch hôm nay/iu);
});

test("resolves LEARNING_PRIORITY with algorithmic recommendation", () => {
  const resolved = resolveStudentAction(
    createAction({
      action_type: "LEARNING_PRIORITY",
      problem_type_id: "pt-uuid-8",
      target_name: "Tương giao đồ thị hàm số bậc ba",
      target_code: "MATH12-PT-09",
      target_type: "PROBLEM_TYPE",
      reason_code: "WEAK_PROBLEM_TYPE",
    })
  );

  assert.equal(resolved.type, "LEARNING_PRIORITY");
  assert.equal(resolved.resourceId, "pt-uuid-8");
  assert.equal(resolved.targetName, "Tương giao đồ thị hàm số bậc ba");
  assert.equal(resolved.reasonCode, "WEAK_PROBLEM_TYPE");
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /ưu tiên/iu);
});

test("resolves IDLE safely with resting state", () => {
  const resolved = resolveStudentAction(createAction({ action_type: "IDLE" }));

  assert.equal(resolved.type, "IDLE");
  assert.equal(resolved.resourceId, undefined);
  assert.equal(resolved.hasAvailableRoute, false);
  assert.match(resolved.title, /sẵn sàng/iu);
});
