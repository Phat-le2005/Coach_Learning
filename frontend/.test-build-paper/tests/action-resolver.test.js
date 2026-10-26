"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const action_resolver_1 = require("../src/features/student-home/action-resolver");
function createAction(overrides) {
    return Object.assign({ action_type: "IDLE", subject_id: "subject-1", resource_id: null, practice_session_id: null, assignment_id: null, verification_id: null, adaptive_repair_session_id: null, study_task_id: null, target_type: null, problem_type_id: null, concept_id: null, target_name: null, target_code: null, reason_code: null, repair_cycle_index: null, phase: null }, overrides);
}
(0, node_test_1.default)("resolves CONTINUE_REPAIR with adaptive repair session and phase", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "CONTINUE_REPAIR",
        adaptive_repair_session_id: "repair-uuid-1",
        target_name: "Đơn điệu hàm trị tuyệt đối",
        target_code: "MATH12-PT-01",
        target_type: "PROBLEM_TYPE",
        repair_cycle_index: 2,
        phase: "PRACTICE",
    }));
    strict_1.default.equal(resolved.type, "CONTINUE_REPAIR");
    strict_1.default.equal(resolved.resourceId, "repair-uuid-1");
    strict_1.default.equal(resolved.resourceType, "adaptive_repair_session");
    strict_1.default.equal(resolved.targetName, "Đơn điệu hàm trị tuyệt đối");
    strict_1.default.equal(resolved.targetCode, "MATH12-PT-01");
    strict_1.default.equal(resolved.repairCycleIndex, 2);
    strict_1.default.equal(resolved.phase, "PRACTICE");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.equal(resolved.route, undefined);
    strict_1.default.match(resolved.title, /vá mắt xích/iu);
});
(0, node_test_1.default)("resolves CONTINUE_VERIFICATION with verification target", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "CONTINUE_VERIFICATION",
        verification_id: "verif-uuid-2",
        target_name: "Ngộ nhận dấu đạo hàm",
        target_code: "MATH12-MIS-01",
        target_type: "CONCEPT",
    }));
    strict_1.default.equal(resolved.type, "CONTINUE_VERIFICATION");
    strict_1.default.equal(resolved.resourceId, "verif-uuid-2");
    strict_1.default.equal(resolved.resourceType, "root_cause_verification");
    strict_1.default.equal(resolved.targetName, "Ngộ nhận dấu đạo hàm");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /xác minh/iu);
});
(0, node_test_1.default)("resolves CONTINUE_ASSIGNMENT with assignment id", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "CONTINUE_ASSIGNMENT",
        assignment_id: "assign-uuid-3",
        target_name: "Bài tập tuần 3 - Khảo sát hàm số",
    }));
    strict_1.default.equal(resolved.type, "CONTINUE_ASSIGNMENT");
    strict_1.default.equal(resolved.resourceId, "assign-uuid-3");
    strict_1.default.equal(resolved.resourceType, "classroom_assignment");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /bài tập/iu);
});
(0, node_test_1.default)("resolves COMPLETE_OVERDUE_ASSIGNMENT with urgency", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "COMPLETE_OVERDUE_ASSIGNMENT",
        assignment_id: "assign-uuid-4",
        target_name: "Bài kiểm tra chương 1",
    }));
    strict_1.default.equal(resolved.type, "COMPLETE_OVERDUE_ASSIGNMENT");
    strict_1.default.equal(resolved.resourceId, "assign-uuid-4");
    strict_1.default.equal(resolved.resourceType, "classroom_assignment");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /quá hạn/iu);
});
(0, node_test_1.default)("resolves CONTINUE_PRACTICE with practice session", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "CONTINUE_PRACTICE",
        practice_session_id: "practice-uuid-5",
        target_name: "Luyện tập tích phân",
    }));
    strict_1.default.equal(resolved.type, "CONTINUE_PRACTICE");
    strict_1.default.equal(resolved.resourceId, "practice-uuid-5");
    strict_1.default.equal(resolved.resourceType, "practice_session");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /luyện tập/iu);
});
(0, node_test_1.default)("resolves REVIEW_DUE with target and spaced repetition context", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "REVIEW_DUE",
        problem_type_id: "pt-uuid-6",
        target_name: "Cực trị hàm trùng phương",
        target_code: "MATH12-PT-04",
        target_type: "PROBLEM_TYPE",
    }));
    strict_1.default.equal(resolved.type, "REVIEW_DUE");
    strict_1.default.equal(resolved.resourceId, "pt-uuid-6");
    strict_1.default.equal(resolved.targetName, "Cực trị hàm trùng phương");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /ôn tập/iu);
});
(0, node_test_1.default)("resolves TODAY_TASK with study task id", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "TODAY_TASK",
        study_task_id: "task-uuid-7",
        target_name: "Giải 5 bài tiệm cận đứng",
    }));
    strict_1.default.equal(resolved.type, "TODAY_TASK");
    strict_1.default.equal(resolved.resourceId, "task-uuid-7");
    strict_1.default.equal(resolved.resourceType, "study_task");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /kế hoạch hôm nay/iu);
});
(0, node_test_1.default)("resolves LEARNING_PRIORITY with algorithmic recommendation", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({
        action_type: "LEARNING_PRIORITY",
        problem_type_id: "pt-uuid-8",
        target_name: "Tương giao đồ thị hàm số bậc ba",
        target_code: "MATH12-PT-09",
        target_type: "PROBLEM_TYPE",
        reason_code: "WEAK_PROBLEM_TYPE",
    }));
    strict_1.default.equal(resolved.type, "LEARNING_PRIORITY");
    strict_1.default.equal(resolved.resourceId, "pt-uuid-8");
    strict_1.default.equal(resolved.targetName, "Tương giao đồ thị hàm số bậc ba");
    strict_1.default.equal(resolved.reasonCode, "WEAK_PROBLEM_TYPE");
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /ưu tiên/iu);
});
(0, node_test_1.default)("resolves IDLE safely with resting state", () => {
    const resolved = (0, action_resolver_1.resolveStudentAction)(createAction({ action_type: "IDLE" }));
    strict_1.default.equal(resolved.type, "IDLE");
    strict_1.default.equal(resolved.resourceId, undefined);
    strict_1.default.equal(resolved.hasAvailableRoute, false);
    strict_1.default.match(resolved.title, /sẵn sàng/iu);
});
