"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.STUDENT_HOME_API_ADAPTER_STATUS = exports.studentHomeAdapter = void 0;
exports.safeMasteryPercent = safeMasteryPercent;
exports.toStudentHomeViewModel = toStudentHomeViewModel;
const validation_1 = require("../../lib/api/validation");
const action_resolver_1 = require("./action-resolver");
const actionTypes = [
    "CONTINUE_REPAIR",
    "CONTINUE_VERIFICATION",
    "CONTINUE_ASSIGNMENT",
    "COMPLETE_OVERDUE_ASSIGNMENT",
    "CONTINUE_PRACTICE",
    "REVIEW_DUE",
    "TODAY_TASK",
    "LEARNING_PRIORITY",
    "IDLE",
];
/**
 * Safely converts a fractional mastery score in [0.0, 1.0] to an integer percentage in [0, 100].
 * Rejects null, undefined, NaN, and values outside the [0.0, 1.0] unit interval without clamping.
 */
function safeMasteryPercent(value) {
    if (value === null || value === undefined || typeof value !== "number" || Number.isNaN(value)) {
        return undefined;
    }
    if (value < 0 || value > 1) {
        return undefined;
    }
    return Math.round(value * 100);
}
function toStudentHomeViewModel(source, fullName, email, masteryData, options = {}) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p;
    if (!actionTypes.includes(source.current_action.action_type)) {
        throw new validation_1.ApiContractError("Unknown StudentCurrentActionType", "response.current_action.action_type");
    }
    const effectiveSubjects = (_a = options.availableSubjects) !== null && _a !== void 0 ? _a : source.available_subjects;
    const availableSubjects = effectiveSubjects.map((subject) => ({
        id: subject.id,
        code: subject.code,
        name: subject.name,
    }));
    const requestedSubject = options.selectedSubjectId
        ? effectiveSubjects.find((subject) => {
            var _a;
            return subject.id === options.selectedSubjectId ||
                subject.code.toLowerCase() === ((_a = options.selectedSubjectId) === null || _a === void 0 ? void 0 : _a.toLowerCase());
        })
        : undefined;
    const focus = (_b = requestedSubject !== null && requestedSubject !== void 0 ? requestedSubject : effectiveSubjects.find((subject) => subject.id === source.focus_subject_id)) !== null && _b !== void 0 ? _b : effectiveSubjects[0];
    const subject = focus
        ? { id: focus.id, name: focus.name, code: focus.code }
        : { id: "", name: "Chưa có môn học", code: "" };
    const subjectHasActivity = source.available_subjects.some((availableSubject) => availableSubject.id === subject.id);
    const isFocusedLearningState = subjectHasActivity && source.focus_subject_id === subject.id;
    const isDiscoveryOnly = ((_c = options.discoveryOnlySubjectIds) !== null && _c !== void 0 ? _c : []).includes(subject.id);
    const classContextCount = isFocusedLearningState ? source.class_contexts.length : 0;
    const learningMode = !subject.id
        ? "UNAVAILABLE"
        : isDiscoveryOnly
            ? "SELF_STUDY_ONBOARDING"
            : classContextCount > 0
                ? "CLASSROOM"
                : "SELF_STUDY";
    const idleAction = {
        action_type: "IDLE",
        subject_id: subject.id || null,
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
    };
    const currentAction = isFocusedLearningState ? source.current_action : idleAction;
    const resolvedAction = (0, action_resolver_1.resolveStudentAction)(currentAction);
    const activeMasterySubject = masteryData === null || masteryData === void 0 ? void 0 : masteryData.subjects.find((masterySubject) => masterySubject.subject_id === subject.id);
    const rawMastery = isFocusedLearningState
        ? (_d = source.mastery_summary.average_problem_type_mastery) !== null && _d !== void 0 ? _d : source.mastery_summary.average_concept_mastery
        : (activeMasterySubject === null || activeMasterySubject === void 0 ? void 0 : activeMasterySubject.attempt_count)
            ? activeMasterySubject.mastery_score
            : null;
    const masteryScore = safeMasteryPercent(rawMastery);
    const hasEvidence = isFocusedLearningState
        ? source.mastery_summary.problem_type_started_count > 0 ||
            source.mastery_summary.concept_started_count > 0
        : ((_e = activeMasterySubject === null || activeMasterySubject === void 0 ? void 0 : activeMasterySubject.attempt_count) !== null && _e !== void 0 ? _e : 0) > 0;
    const selectedProblemTypes = (_f = activeMasterySubject === null || activeMasterySubject === void 0 ? void 0 : activeMasterySubject.chapters.flatMap((chapter) => chapter.topics.flatMap((topic) => topic.problem_types))) !== null && _f !== void 0 ? _f : [];
    const selectedConcepts = (_g = activeMasterySubject === null || activeMasterySubject === void 0 ? void 0 : activeMasterySubject.concepts) !== null && _g !== void 0 ? _g : [];
    const problemTypeStartedCount = isFocusedLearningState
        ? source.mastery_summary.problem_type_started_count
        : selectedProblemTypes.filter((item) => item.attempt_count > 0).length;
    const conceptStartedCount = isFocusedLearningState
        ? source.mastery_summary.concept_started_count
        : selectedConcepts.filter((item) => item.attempt_count > 0).length;
    const masteredProblemTypeCount = isFocusedLearningState
        ? source.mastery_summary.mastered_problem_type_count
        : selectedProblemTypes.filter((item) => item.state === "MASTERED").length;
    const weakProblemTypeCount = isFocusedLearningState
        ? source.mastery_summary.weak_problem_type_count
        : selectedProblemTypes.filter((item) => item.state === "WEAK").length;
    const overdueCount = isFocusedLearningState ? source.assignments.overdue_count : 0;
    const inProgressCount = isFocusedLearningState ? source.assignments.in_progress_count : 0;
    const pendingCount = isFocusedLearningState ? source.assignments.pending_count : 0;
    const activeCount = overdueCount + inProgressCount + pendingCount;
    const todayPlan = isFocusedLearningState && source.today_plan
        ? {
            date: source.today_plan.date,
            totalCount: source.today_plan.total_count,
            completedCount: source.today_plan.completed_count,
            totalEstimatedMinutes: source.today_plan.total_estimated_minutes,
            availableMinutes: source.today_plan.available_daily_minutes,
            notice: source.today_plan.notice,
        }
        : null;
    return {
        student: {
            displayName: fullName,
            email,
        },
        subject,
        availableSubjects,
        learningContext: {
            mode: learningMode,
            classContextCount,
            subjectHasActivity,
        },
        currentAction: {
            type: currentAction.action_type,
            targetName: (_h = currentAction.target_name) !== null && _h !== void 0 ? _h : undefined,
            targetCode: (_j = currentAction.target_code) !== null && _j !== void 0 ? _j : undefined,
            reasonCode: (_k = currentAction.reason_code) !== null && _k !== void 0 ? _k : undefined,
            resourceId: (_l = currentAction.resource_id) !== null && _l !== void 0 ? _l : undefined,
            resourceType: (_m = currentAction.target_type) !== null && _m !== void 0 ? _m : undefined,
            phase: (_o = currentAction.phase) !== null && _o !== void 0 ? _o : undefined,
            repairCycleIndex: (_p = currentAction.repair_cycle_index) !== null && _p !== void 0 ? _p : undefined,
        },
        resolvedAction,
        mastery: {
            score: masteryScore,
            rawScore: rawMastery === null ? undefined : rawMastery,
            label: masteryScore === undefined ? "Chưa đủ dữ liệu" : "Độ vững hiện tại",
            hasEvidence,
            problemTypeStartedCount,
            conceptStartedCount,
            masteredProblemTypeCount,
            weakProblemTypeCount,
        },
        review: {
            dueCount: isFocusedLearningState ? source.review.due_now_count : 0,
            upcomingCount: isFocusedLearningState ? source.review.upcoming_count : 0,
            dueTargets: (isFocusedLearningState ? source.review.due_targets : []).map((target) => ({
                scheduleId: target.schedule_id,
                targetType: target.target_type,
                targetName: target.target_name,
                targetCode: target.target_code,
                nextReviewAt: target.next_review_at,
            })),
        },
        assignments: {
            activeCount,
            overdueCount,
            inProgressCount,
            pendingCount,
            upcoming: (isFocusedLearningState ? source.assignments.upcoming : []).map((item) => ({
                assignmentId: item.assignment_id,
                title: item.title,
                status: item.status,
                dueAt: item.due_at,
                isOverdue: item.is_overdue,
            })),
        },
        todayPlan,
        momentum: {},
        knowledgeRegions: (() => {
            if (!(masteryData === null || masteryData === void 0 ? void 0 : masteryData.subjects))
                return [];
            if (masteryData.student_id && source.student_id && masteryData.student_id !== source.student_id)
                return [];
            const activeMasterySubject = masteryData.subjects.find((s) => s.subject_id === subject.id);
            if (!(activeMasterySubject === null || activeMasterySubject === void 0 ? void 0 : activeMasterySubject.chapters))
                return [];
            const fallbackBiomes = ["meadow", "river", "mountain", "forest", "sky"];
            const accents = [
                "mint",
                "aqua",
                "sky",
                "violet",
                "amber",
            ];
            return activeMasterySubject.chapters.map((chapter, index) => {
                let state = "not_started";
                if (chapter.state === "MASTERED")
                    state = "mastered";
                else if (chapter.state === "WEAK")
                    state = "weak";
                else if (chapter.state === "REVIEW_DUE")
                    state = "review";
                else if (chapter.state === "LEARNING" || chapter.state === "PRACTICING")
                    state = "developing";
                else if (chapter.attempt_count === 0 || chapter.state === "NOT_STARTED")
                    state = "not_started";
                return {
                    id: chapter.chapter_id,
                    label: chapter.name,
                    progress: chapter.attempt_count > 0 ? safeMasteryPercent(chapter.mastery_score) : undefined,
                    state,
                    accent: accents[index % accents.length],
                    biome: fallbackBiomes[index % fallbackBiomes.length],
                };
            });
        })(),
        priorities: (isFocusedLearningState ? source.priority_targets : []).map((priority) => {
            var _a, _b;
            return ({
                id: (_b = (_a = priority.problem_type_id) !== null && _a !== void 0 ? _a : priority.concept_id) !== null && _b !== void 0 ? _b : `${priority.target_type}:${priority.target_code}`,
                targetType: priority.target_type,
                targetName: priority.target_name,
                targetCode: priority.target_code,
                reasonCode: priority.reason_code,
                mastery: safeMasteryPercent(priority.mastery_score),
                rawMastery: priority.mastery_score,
                confidence: priority.confidence,
                desiredDifficulty: priority.desired_difficulty,
                priorityScore: priority.priority_score,
            });
        }),
    };
}
exports.studentHomeAdapter = {
    toViewModel: (source, fullName, email) => toStudentHomeViewModel(source, fullName, email),
};
exports.STUDENT_HOME_API_ADAPTER_STATUS = "CONNECTED";
