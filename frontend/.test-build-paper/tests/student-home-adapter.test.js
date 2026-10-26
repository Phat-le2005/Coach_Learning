"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const adapter_1 = require("../src/features/student-home/adapter");
const validation_1 = require("../src/lib/api/validation");
function createLearningState(overrides = {}) {
    return Object.assign({ student_id: "student-uuid-1", as_of: "2026-10-08T05:00:00Z", available_subjects: [
            { id: "sub-1", code: "MATH12", name: "Toán 12" },
            { id: "sub-2", code: "PHYS12", name: "Vật lý 12" },
        ], focus_subject_id: "sub-1", current_action: {
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
        }, mastery_summary: {
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
        }, priority_targets: [
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
        ], active_learning: {
            practice_session_id: null,
            practice_session_type: null,
            verification_id: null,
            adaptive_repair_session_id: "repair-session-1",
            assignment_id: null,
        }, verified_root_causes: [], repair: null, review: {
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
        }, assignments: {
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
        }, today_plan: {
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
        }, latest_feedback: null, class_contexts: [] }, overrides);
}
(0, node_test_1.default)("safeMasteryPercent strictly distinguishes zero, null, and out-of-range bounds", () => {
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(0.0), 0);
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(0.684), 68);
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(1.0), 100);
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(null), undefined);
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(undefined), undefined);
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(Number.NaN), undefined);
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(-0.1), undefined);
    strict_1.default.equal((0, adapter_1.safeMasteryPercent)(1.05), undefined);
});
(0, node_test_1.default)("toStudentHomeViewModel maps real learning state accurately", () => {
    const source = createLearningState();
    const vm = (0, adapter_1.toStudentHomeViewModel)(source, "Nguyễn Văn A", "a@example.com");
    strict_1.default.equal(vm.student.displayName, "Nguyễn Văn A");
    strict_1.default.equal(vm.student.email, "a@example.com");
    strict_1.default.equal(vm.subject.id, "sub-1");
    strict_1.default.equal(vm.subject.name, "Toán 12");
    strict_1.default.equal(vm.availableSubjects.length, 2);
    // Resolved action
    strict_1.default.equal(vm.resolvedAction.type, "CONTINUE_REPAIR");
    strict_1.default.equal(vm.resolvedAction.resourceId, "repair-session-1");
    strict_1.default.equal(vm.resolvedAction.targetName, "Đơn điệu hàm phân thức bậc nhất");
    strict_1.default.equal(vm.resolvedAction.hasAvailableRoute, false);
    // Mastery summary
    strict_1.default.equal(vm.mastery.score, 73);
    strict_1.default.equal(vm.mastery.label, "Độ vững hiện tại");
    strict_1.default.equal(vm.mastery.hasEvidence, true);
    strict_1.default.equal(vm.mastery.problemTypeStartedCount, 5);
    strict_1.default.equal(vm.mastery.weakProblemTypeCount, 2);
    // Assignments breakdown (overdue=1, in_progress=2, pending=1 -> active=4)
    strict_1.default.equal(vm.assignments.activeCount, 4);
    strict_1.default.equal(vm.assignments.overdueCount, 1);
    strict_1.default.equal(vm.assignments.inProgressCount, 2);
    strict_1.default.equal(vm.assignments.pendingCount, 1);
    strict_1.default.equal(vm.assignments.upcoming.length, 1);
    strict_1.default.equal(vm.assignments.upcoming[0].title, "Bài tập tuần 4");
    // Reviews
    strict_1.default.equal(vm.review.dueCount, 2);
    strict_1.default.equal(vm.review.upcomingCount, 4);
    strict_1.default.equal(vm.review.dueTargets.length, 1);
    strict_1.default.equal(vm.review.dueTargets[0].targetName, "Cực trị hàm trùng phương");
    // Today's plan
    strict_1.default.ok(vm.todayPlan);
    strict_1.default.equal(vm.todayPlan.totalCount, 1);
    strict_1.default.equal(vm.todayPlan.completedCount, 0);
    strict_1.default.equal(vm.todayPlan.totalEstimatedMinutes, 45);
    strict_1.default.equal(vm.todayPlan.notice, "Ưu tiên củng cố dạng bài yếu");
    // Priorities
    strict_1.default.equal(vm.priorities.length, 1);
    strict_1.default.equal(vm.priorities[0].targetName, "Đơn điệu hàm phân thức bậc nhất");
    strict_1.default.equal(vm.priorities[0].mastery, 42);
    strict_1.default.equal(vm.priorities[0].desiredDifficulty, 0.65);
});
(0, node_test_1.default)("toStudentHomeViewModel handles null mastery and empty study history gracefully", () => {
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
    const vm = (0, adapter_1.toStudentHomeViewModel)(source, "Học sinh mới");
    strict_1.default.equal(vm.mastery.score, undefined);
    strict_1.default.equal(vm.mastery.label, "Chưa đủ dữ liệu");
    strict_1.default.equal(vm.mastery.hasEvidence, false);
    strict_1.default.equal(vm.todayPlan, null);
});
(0, node_test_1.default)("toStudentHomeViewModel handles 0.0 mastery distinct from null", () => {
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
    const vm = (0, adapter_1.toStudentHomeViewModel)(source, "Học sinh");
    strict_1.default.equal(vm.mastery.score, 0);
    strict_1.default.equal(vm.mastery.label, "Độ vững hiện tại");
    strict_1.default.equal(vm.mastery.hasEvidence, true);
});
(0, node_test_1.default)("toStudentHomeViewModel handles empty available_subjects without crashing", () => {
    const source = createLearningState({
        available_subjects: [],
        focus_subject_id: null,
    });
    const vm = (0, adapter_1.toStudentHomeViewModel)(source, "Học sinh");
    strict_1.default.equal(vm.availableSubjects.length, 0);
    strict_1.default.equal(vm.subject.name, "Chưa có môn học");
    strict_1.default.equal(vm.subject.id, "");
});
(0, node_test_1.default)("toStudentHomeViewModel throws ApiContractError for invalid current_action type", () => {
    const source = createLearningState({
        current_action: Object.assign(Object.assign({}, createLearningState().current_action), { action_type: "UNSUPPORTED_ACTION" }),
    });
    strict_1.default.throws(() => (0, adapter_1.toStudentHomeViewModel)(source, "Học sinh"), (err) => err instanceof validation_1.ApiContractError && err.path === "response.current_action.action_type");
});
(0, node_test_1.default)("new student receives truthful self-study onboarding without classroom data leakage", () => {
    const source = createLearningState({
        available_subjects: [],
        focus_subject_id: null,
        class_contexts: [],
    });
    const mastery = {
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
    const vm = (0, adapter_1.toStudentHomeViewModel)(source, "Học sinh mới", undefined, mastery, {
        availableSubjects: [
            { id: "math-self-study", code: "MATH_G12", name: "Toán 12" },
        ],
        selectedSubjectId: "math-self-study",
        discoveryOnlySubjectIds: ["math-self-study"],
    });
    strict_1.default.equal(vm.learningContext.mode, "SELF_STUDY_ONBOARDING");
    strict_1.default.equal(vm.learningContext.subjectHasActivity, false);
    strict_1.default.equal(vm.subject.name, "Toán 12");
    strict_1.default.equal(vm.currentAction.type, "IDLE");
    strict_1.default.equal(vm.mastery.hasEvidence, false);
    strict_1.default.equal(vm.mastery.score, undefined);
    strict_1.default.equal(vm.assignments.activeCount, 0);
    strict_1.default.equal(vm.review.dueCount, 0);
    strict_1.default.equal(vm.todayPlan, null);
    strict_1.default.equal(vm.priorities.length, 0);
    strict_1.default.equal(vm.knowledgeRegions[0].state, "not_started");
    strict_1.default.equal(vm.knowledgeRegions[0].progress, undefined);
});
