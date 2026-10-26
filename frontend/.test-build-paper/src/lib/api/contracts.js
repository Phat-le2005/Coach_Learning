"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.STEP_KINDS = exports.DERIVED_MASTERY_STATES = exports.ROLES = void 0;
exports.validateLoginRequest = validateLoginRequest;
exports.parseTokenPair = parseTokenPair;
exports.parseUserRead = parseUserRead;
exports.parseStudentLearningState = parseStudentLearningState;
exports.parseDerivedMasteryState = parseDerivedMasteryState;
exports.parseProblemTypeMastery = parseProblemTypeMastery;
exports.parseConceptMastery = parseConceptMastery;
exports.parseTopicMastery = parseTopicMastery;
exports.parseChapterMastery = parseChapterMastery;
exports.parseSubjectMastery = parseSubjectMastery;
exports.parseStudentMastery = parseStudentMastery;
exports.parseVariationTablePayload = parseVariationTablePayload;
exports.parseAIReviewAvailabilityRead = parseAIReviewAvailabilityRead;
exports.parseAIReviewRead = parseAIReviewRead;
exports.parseInkPoint = parseInkPoint;
exports.parseInkStroke = parseInkStroke;
exports.parseInkPageSummary = parseInkPageSummary;
exports.parseInkDocumentRead = parseInkDocumentRead;
exports.parseInkPageRead = parseInkPageRead;
exports.parseInkSaveRead = parseInkSaveRead;
exports.parseProblemOptionRead = parseProblemOptionRead;
exports.parseProblemRead = parseProblemRead;
exports.parseSolutionAttemptRead = parseSolutionAttemptRead;
exports.parseMathAttemptsPageRead = parseMathAttemptsPageRead;
exports.parsePracticeSessionStartRead = parsePracticeSessionStartRead;
exports.parseOCRRecognizeResponse = parseOCRRecognizeResponse;
const validation_1 = require("./validation");
exports.ROLES = ["STUDENT", "TEACHER", "PARENT", "ADMIN"];
exports.DERIVED_MASTERY_STATES = [
    "NOT_STARTED",
    "LEARNING",
    "WEAK",
    "PRACTICING",
    "MASTERED",
    "REVIEW_DUE",
];
const nullableString = (value, path) => (0, validation_1.nullable)(value, path, validation_1.string);
const optionalNullableRecord = (value, path) => (0, validation_1.optional)(value, path, (item, itemPath) => (0, validation_1.nullable)(item, itemPath, validation_1.record));
function validateLoginRequest(value) {
    const email = value.email.trim().toLowerCase();
    if (!email || !email.includes("@") || email.length > 254)
        throw new Error("Email không hợp lệ.");
    if (!value.password || value.password.length > 128)
        throw new Error("Mật khẩu không hợp lệ.");
    return { email, password: value.password };
}
function parseTokenPair(value, path = "response") {
    const source = (0, validation_1.record)(value, path);
    const expiresIn = (0, validation_1.integer)(source.expires_in, `${path}.expires_in`);
    if (expiresIn <= 0)
        throw new Error("Token expiry must be positive.");
    return {
        access_token: (0, validation_1.nonEmptyString)(source.access_token, `${path}.access_token`),
        refresh_token: (0, validation_1.nonEmptyString)(source.refresh_token, `${path}.refresh_token`),
        token_type: (0, validation_1.oneOf)(source.token_type, `${path}.token_type`, ["bearer"]),
        expires_in: expiresIn,
    };
}
function parseUserRead(value, path = "response") {
    const source = (0, validation_1.record)(value, path);
    return {
        id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`), email: (0, validation_1.nonEmptyString)(source.email, `${path}.email`),
        full_name: (0, validation_1.nonEmptyString)(source.full_name, `${path}.full_name`), role: (0, validation_1.oneOf)(source.role, `${path}.role`, exports.ROLES),
        is_active: (0, validation_1.boolean)(source.is_active, `${path}.is_active`), created_at: (0, validation_1.nonEmptyString)(source.created_at, `${path}.created_at`),
        updated_at: (0, validation_1.nonEmptyString)(source.updated_at, `${path}.updated_at`),
    };
}
function parseSubject(value, path) {
    const source = (0, validation_1.record)(value, path);
    return { id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`), code: (0, validation_1.nonEmptyString)(source.code, `${path}.code`), name: (0, validation_1.nonEmptyString)(source.name, `${path}.name`) };
}
function parseCurrentAction(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        action_type: (0, validation_1.nonEmptyString)(source.action_type, `${path}.action_type`), subject_id: nullableString(source.subject_id, `${path}.subject_id`),
        resource_id: nullableString(source.resource_id, `${path}.resource_id`), practice_session_id: nullableString(source.practice_session_id, `${path}.practice_session_id`),
        assignment_id: nullableString(source.assignment_id, `${path}.assignment_id`), verification_id: nullableString(source.verification_id, `${path}.verification_id`),
        adaptive_repair_session_id: nullableString(source.adaptive_repair_session_id, `${path}.adaptive_repair_session_id`),
        study_task_id: nullableString(source.study_task_id, `${path}.study_task_id`), target_type: nullableString(source.target_type, `${path}.target_type`),
        problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`), concept_id: nullableString(source.concept_id, `${path}.concept_id`),
        target_name: nullableString(source.target_name, `${path}.target_name`), target_code: nullableString(source.target_code, `${path}.target_code`),
        reason_code: nullableString(source.reason_code, `${path}.reason_code`),
        repair_cycle_index: (0, validation_1.nullable)(source.repair_cycle_index, `${path}.repair_cycle_index`, validation_1.integer), phase: nullableString(source.phase, `${path}.phase`),
    };
}
function parseWeakTarget(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`), concept_id: nullableString(source.concept_id, `${path}.concept_id`),
        target_name: (0, validation_1.nonEmptyString)(source.target_name, `${path}.target_name`), target_code: (0, validation_1.nonEmptyString)(source.target_code, `${path}.target_code`),
        code: nullableString(source.code, `${path}.code`), name: nullableString(source.name, `${path}.name`),
        mastery_score: (0, validation_1.number)(source.mastery_score, `${path}.mastery_score`), confidence: (0, validation_1.number)(source.confidence, `${path}.confidence`),
        last_practiced_at: nullableString(source.last_practiced_at, `${path}.last_practiced_at`),
    };
}
function parseMastery(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        problem_type_started_count: (0, validation_1.integer)(source.problem_type_started_count, `${path}.problem_type_started_count`), concept_started_count: (0, validation_1.integer)(source.concept_started_count, `${path}.concept_started_count`),
        mastered_problem_type_count: (0, validation_1.integer)(source.mastered_problem_type_count, `${path}.mastered_problem_type_count`), weak_problem_type_count: (0, validation_1.integer)(source.weak_problem_type_count, `${path}.weak_problem_type_count`),
        mastered_concept_count: (0, validation_1.integer)(source.mastered_concept_count, `${path}.mastered_concept_count`), weak_concept_count: (0, validation_1.integer)(source.weak_concept_count, `${path}.weak_concept_count`),
        average_problem_type_mastery: (0, validation_1.nullable)(source.average_problem_type_mastery, `${path}.average_problem_type_mastery`, validation_1.number),
        average_concept_mastery: (0, validation_1.nullable)(source.average_concept_mastery, `${path}.average_concept_mastery`, validation_1.number),
        weak_problem_types: (0, validation_1.array)(source.weak_problem_types, `${path}.weak_problem_types`, parseWeakTarget),
        weak_concepts: (0, validation_1.array)(source.weak_concepts, `${path}.weak_concepts`, parseWeakTarget),
    };
}
function parsePriority(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        target_type: (0, validation_1.nonEmptyString)(source.target_type, `${path}.target_type`), problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`),
        concept_id: nullableString(source.concept_id, `${path}.concept_id`), target_name: (0, validation_1.nonEmptyString)(source.target_name, `${path}.target_name`),
        target_code: (0, validation_1.nonEmptyString)(source.target_code, `${path}.target_code`), reason_code: (0, validation_1.nonEmptyString)(source.reason_code, `${path}.reason_code`),
        priority_score: (0, validation_1.number)(source.priority_score, `${path}.priority_score`), mastery_score: (0, validation_1.number)(source.mastery_score, `${path}.mastery_score`),
        confidence: (0, validation_1.number)(source.confidence, `${path}.confidence`), desired_difficulty: (0, validation_1.number)(source.desired_difficulty, `${path}.desired_difficulty`),
    };
}
function parseActiveLearning(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        practice_session_id: nullableString(source.practice_session_id, `${path}.practice_session_id`), practice_session_type: nullableString(source.practice_session_type, `${path}.practice_session_type`),
        verification_id: nullableString(source.verification_id, `${path}.verification_id`), adaptive_repair_session_id: nullableString(source.adaptive_repair_session_id, `${path}.adaptive_repair_session_id`),
        assignment_id: nullableString(source.assignment_id, `${path}.assignment_id`),
    };
}
function parseReviewTarget(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        schedule_id: (0, validation_1.nonEmptyString)(source.schedule_id, `${path}.schedule_id`),
        target_type: (0, validation_1.nonEmptyString)(source.target_type, `${path}.target_type`),
        problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`),
        concept_id: nullableString(source.concept_id, `${path}.concept_id`),
        target_name: (0, validation_1.nonEmptyString)(source.target_name, `${path}.target_name`),
        target_code: (0, validation_1.nonEmptyString)(source.target_code, `${path}.target_code`),
        next_review_at: (0, validation_1.nonEmptyString)(source.next_review_at, `${path}.next_review_at`),
        review_interval_days: (0, validation_1.number)(source.review_interval_days, `${path}.review_interval_days`),
        review_count: (0, validation_1.integer)(source.review_count, `${path}.review_count`),
        last_review_result: nullableString(source.last_review_result, `${path}.last_review_result`),
    };
}
function parseReview(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        due_now_count: (0, validation_1.integer)(source.due_now_count, `${path}.due_now_count`),
        upcoming_count: (0, validation_1.integer)(source.upcoming_count, `${path}.upcoming_count`),
        due_targets: (0, validation_1.array)(source.due_targets, `${path}.due_targets`, parseReviewTarget),
    };
}
function parseAssignmentItem(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        assignment_id: (0, validation_1.nonEmptyString)(source.assignment_id, `${path}.assignment_id`),
        student_assignment_id: (0, validation_1.nonEmptyString)(source.student_assignment_id, `${path}.student_assignment_id`),
        classroom_id: (0, validation_1.nonEmptyString)(source.classroom_id, `${path}.classroom_id`),
        subject_id: (0, validation_1.nonEmptyString)(source.subject_id, `${path}.subject_id`),
        title: (0, validation_1.nonEmptyString)(source.title, `${path}.title`),
        status: (0, validation_1.nonEmptyString)(source.status, `${path}.status`),
        start_at: (0, validation_1.nonEmptyString)(source.start_at, `${path}.start_at`),
        due_at: nullableString(source.due_at, `${path}.due_at`),
        score: (0, validation_1.nullable)(source.score, `${path}.score`, validation_1.number),
        is_overdue: (0, validation_1.boolean)(source.is_overdue, `${path}.is_overdue`),
    };
}
function parseAssignments(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        overdue_count: (0, validation_1.integer)(source.overdue_count, `${path}.overdue_count`),
        in_progress_count: (0, validation_1.integer)(source.in_progress_count, `${path}.in_progress_count`),
        pending_count: (0, validation_1.integer)(source.pending_count, `${path}.pending_count`),
        upcoming: (0, validation_1.array)(source.upcoming, `${path}.upcoming`, parseAssignmentItem),
    };
}
function parseStudyTask(value, path) {
    const source = (0, validation_1.record)(value, path);
    return {
        id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`),
        study_plan_id: (0, validation_1.nonEmptyString)(source.study_plan_id, `${path}.study_plan_id`),
        task_type: (0, validation_1.nonEmptyString)(source.task_type, `${path}.task_type`),
        status: (0, validation_1.nonEmptyString)(source.status, `${path}.status`),
        planned_date: (0, validation_1.nonEmptyString)(source.planned_date, `${path}.planned_date`),
        problem_type_id: nullableString(source.problem_type_id, `${path}.problem_type_id`),
        problem_type_name: nullableString(source.problem_type_name, `${path}.problem_type_name`),
        concept_id: nullableString(source.concept_id, `${path}.concept_id`),
        concept_name: nullableString(source.concept_name, `${path}.concept_name`),
        topic_id: nullableString(source.topic_id, `${path}.topic_id`),
        topic_name: nullableString(source.topic_name, `${path}.topic_name`),
        chapter_id: nullableString(source.chapter_id, `${path}.chapter_id`),
        chapter_name: nullableString(source.chapter_name, `${path}.chapter_name`),
        subject_id: nullableString(source.subject_id, `${path}.subject_id`),
        subject_name: nullableString(source.subject_name, `${path}.subject_name`),
        estimated_duration_minutes: (0, validation_1.integer)(source.estimated_duration_minutes, `${path}.estimated_duration_minutes`),
        priority: (0, validation_1.integer)(source.priority, `${path}.priority`),
        order_index: (0, validation_1.integer)(source.order_index, `${path}.order_index`),
        reason_code: (0, validation_1.nonEmptyString)(source.reason_code, `${path}.reason_code`),
        completed_at: nullableString(source.completed_at, `${path}.completed_at`),
        created_at: (0, validation_1.nonEmptyString)(source.created_at, `${path}.created_at`),
        updated_at: (0, validation_1.nonEmptyString)(source.updated_at, `${path}.updated_at`),
    };
}
function parseTodayPlan(value, path) {
    if (value === null || value === undefined)
        return null;
    const source = (0, validation_1.record)(value, path);
    return {
        date: (0, validation_1.nonEmptyString)(source.date, `${path}.date`),
        available_daily_minutes: (0, validation_1.integer)(source.available_daily_minutes, `${path}.available_daily_minutes`),
        total_estimated_minutes: (0, validation_1.integer)(source.total_estimated_minutes, `${path}.total_estimated_minutes`),
        tasks: (0, validation_1.array)(source.tasks, `${path}.tasks`, parseStudyTask),
        completed_count: (0, validation_1.integer)(source.completed_count, `${path}.completed_count`),
        total_count: (0, validation_1.integer)(source.total_count, `${path}.total_count`),
        days_to_exam: (0, validation_1.nullable)(source.days_to_exam, `${path}.days_to_exam`, validation_1.integer),
        notice: nullableString(source.notice, `${path}.notice`),
    };
}
function parseStudentLearningState(value, path = "response") {
    var _a;
    const source = (0, validation_1.record)(value, path);
    return {
        student_id: (0, validation_1.nonEmptyString)(source.student_id, `${path}.student_id`), as_of: (0, validation_1.nonEmptyString)(source.as_of, `${path}.as_of`),
        available_subjects: (0, validation_1.array)(source.available_subjects, `${path}.available_subjects`, parseSubject), focus_subject_id: nullableString(source.focus_subject_id, `${path}.focus_subject_id`),
        current_action: parseCurrentAction(source.current_action, `${path}.current_action`), mastery_summary: parseMastery(source.mastery_summary, `${path}.mastery_summary`),
        priority_targets: (0, validation_1.array)(source.priority_targets, `${path}.priority_targets`, parsePriority), active_learning: parseActiveLearning(source.active_learning, `${path}.active_learning`),
        verified_root_causes: (0, validation_1.array)(source.verified_root_causes, `${path}.verified_root_causes`, validation_1.record), repair: (0, validation_1.nullable)(source.repair, `${path}.repair`, validation_1.record),
        review: parseReview(source.review, `${path}.review`), assignments: parseAssignments(source.assignments, `${path}.assignments`),
        today_plan: parseTodayPlan(source.today_plan, `${path}.today_plan`), latest_feedback: optionalNullableRecord(source.latest_feedback, `${path}.latest_feedback`),
        class_contexts: (0, validation_1.array)((_a = source.class_contexts) !== null && _a !== void 0 ? _a : [], `${path}.class_contexts`, validation_1.record),
    };
}
function parseDerivedMasteryState(value, path = "state") {
    return (0, validation_1.oneOf)(value, path, exports.DERIVED_MASTERY_STATES);
}
function parseMetricFields(source, path) {
    return {
        mastery_score: (0, validation_1.number)(source.mastery_score, `${path}.mastery_score`),
        confidence: (0, validation_1.number)(source.confidence, `${path}.confidence`),
        attempt_count: (0, validation_1.integer)(source.attempt_count, `${path}.attempt_count`),
        correct_count: (0, validation_1.integer)(source.correct_count, `${path}.correct_count`),
        last_practiced_at: nullableString(source.last_practiced_at, `${path}.last_practiced_at`),
        last_updated_at: nullableString(source.last_updated_at, `${path}.last_updated_at`),
        state: parseDerivedMasteryState(source.state, `${path}.state`),
    };
}
function parseProblemTypeMastery(value, path = "problem_type") {
    const source = (0, validation_1.record)(value, path);
    return Object.assign(Object.assign({}, parseMetricFields(source, path)), { problem_type_id: (0, validation_1.nonEmptyString)(source.problem_type_id, `${path}.problem_type_id`), topic_id: (0, validation_1.nonEmptyString)(source.topic_id, `${path}.topic_id`), code: (0, validation_1.nonEmptyString)(source.code, `${path}.code`), name: (0, validation_1.nonEmptyString)(source.name, `${path}.name`) });
}
function parseConceptMastery(value, path = "concept") {
    const source = (0, validation_1.record)(value, path);
    return Object.assign(Object.assign({}, parseMetricFields(source, path)), { concept_id: (0, validation_1.nonEmptyString)(source.concept_id, `${path}.concept_id`), subject_id: (0, validation_1.nonEmptyString)(source.subject_id, `${path}.subject_id`), code: (0, validation_1.nonEmptyString)(source.code, `${path}.code`), name: (0, validation_1.nonEmptyString)(source.name, `${path}.name`) });
}
function parseTopicMastery(value, path = "topic") {
    const source = (0, validation_1.record)(value, path);
    return Object.assign(Object.assign({}, parseMetricFields(source, path)), { topic_id: (0, validation_1.nonEmptyString)(source.topic_id, `${path}.topic_id`), chapter_id: (0, validation_1.nonEmptyString)(source.chapter_id, `${path}.chapter_id`), code: (0, validation_1.nonEmptyString)(source.code, `${path}.code`), name: (0, validation_1.nonEmptyString)(source.name, `${path}.name`), problem_type_count: (0, validation_1.integer)(source.problem_type_count, `${path}.problem_type_count`), started_problem_type_count: (0, validation_1.integer)(source.started_problem_type_count, `${path}.started_problem_type_count`), problem_types: (0, validation_1.array)(source.problem_types, `${path}.problem_types`, parseProblemTypeMastery) });
}
function parseChapterMastery(value, path = "chapter") {
    const source = (0, validation_1.record)(value, path);
    return Object.assign(Object.assign({}, parseMetricFields(source, path)), { chapter_id: (0, validation_1.nonEmptyString)(source.chapter_id, `${path}.chapter_id`), subject_id: (0, validation_1.nonEmptyString)(source.subject_id, `${path}.subject_id`), code: (0, validation_1.nonEmptyString)(source.code, `${path}.code`), name: (0, validation_1.nonEmptyString)(source.name, `${path}.name`), problem_type_count: (0, validation_1.integer)(source.problem_type_count, `${path}.problem_type_count`), started_problem_type_count: (0, validation_1.integer)(source.started_problem_type_count, `${path}.started_problem_type_count`), topics: (0, validation_1.array)(source.topics, `${path}.topics`, parseTopicMastery) });
}
function parseSubjectMastery(value, path = "subject") {
    const source = (0, validation_1.record)(value, path);
    return Object.assign(Object.assign({}, parseMetricFields(source, path)), { subject_id: (0, validation_1.nonEmptyString)(source.subject_id, `${path}.subject_id`), code: (0, validation_1.nonEmptyString)(source.code, `${path}.code`), name: (0, validation_1.nonEmptyString)(source.name, `${path}.name`), problem_type_count: (0, validation_1.integer)(source.problem_type_count, `${path}.problem_type_count`), started_problem_type_count: (0, validation_1.integer)(source.started_problem_type_count, `${path}.started_problem_type_count`), chapters: (0, validation_1.array)(source.chapters, `${path}.chapters`, parseChapterMastery), concepts: (0, validation_1.array)(source.concepts, `${path}.concepts`, parseConceptMastery) });
}
function parseStudentMastery(value, path = "response") {
    const source = (0, validation_1.record)(value, path);
    return {
        student_id: (0, validation_1.nonEmptyString)(source.student_id, `${path}.student_id`),
        subjects: (0, validation_1.array)(source.subjects, `${path}.subjects`, parseSubjectMastery),
    };
}
exports.STEP_KINDS = [
    "ASSUMPTION",
    "DERIVATIVE_CALCULATION",
    "ROOT_FINDING",
    "SIGN_TABLE",
    "VARIATION_TABLE",
    "CONCLUSION",
    "EXPLANATION",
    "CUSTOM",
];
function parseVariationTablePayload(value, path = "variation_table") {
    const source = (0, validation_1.record)(value, path);
    if (source.version !== 1)
        throw new validation_1.ApiContractError("Unknown variation table version", `${path}.version`);
    const points = (0, validation_1.array)(source.points, `${path}.points`, (item, itemPath) => {
        const point = (0, validation_1.record)(item, itemPath);
        return {
            x: (0, validation_1.nonEmptyString)(point.x, `${itemPath}.x`),
            derivative: (0, validation_1.oneOf)(point.derivative, `${itemPath}.derivative`, ["", "0", "undefined", "?"]),
            y: (0, validation_1.string)(point.y, `${itemPath}.y`),
        };
    });
    const intervals = (0, validation_1.array)(source.intervals, `${path}.intervals`, (item, itemPath) => {
        const interval = (0, validation_1.record)(item, itemPath);
        return {
            sign: (0, validation_1.oneOf)(interval.sign, `${itemPath}.sign`, ["+", "-", "0", "?"]),
            trend: (0, validation_1.oneOf)(interval.trend, `${itemPath}.trend`, ["UP", "DOWN", "FLAT", "UNKNOWN"]),
        };
    });
    if (points.length < 2 || points.length > 12 || intervals.length !== points.length - 1) {
        throw new validation_1.ApiContractError("Variation table columns do not align", path);
    }
    if (new Set(points.map((point) => point.x.trim())).size !== points.length) {
        throw new validation_1.ApiContractError("Variation table x boundaries must be distinct", path);
    }
    const expected = { "+": "UP", "-": "DOWN", "0": "FLAT", "?": "UNKNOWN" };
    if (intervals.some((interval) => interval.trend !== expected[interval.sign])) {
        throw new validation_1.ApiContractError("Variation table sign and trend conflict", path);
    }
    return { version: 1, points, intervals };
}
function parseAIReviewAvailabilityRead(value, path = "ai_review_availability") {
    const source = (0, validation_1.record)(value, path);
    return {
        available: (0, validation_1.boolean)(source.available, `${path}.available`),
        reason_code: source.reason_code === null ? null : (0, validation_1.string)(source.reason_code, `${path}.reason_code`),
    };
}
function parseAIReviewRead(value, path = "ai_review") {
    const source = (0, validation_1.record)(value, path);
    if (source.is_final !== false)
        throw new validation_1.ApiContractError("AI review must be provisional", `${path}.is_final`);
    const steps = (0, validation_1.array)(source.step_grades, `${path}.step_grades`, (item, stepPath) => {
        const row = (0, validation_1.record)(item, stepPath);
        const verdict = (0, validation_1.string)(row.verdict, `${stepPath}.verdict`);
        if (verdict !== "VALID" && verdict !== "INVALID" && verdict !== "NEEDS_REVIEW") {
            throw new validation_1.ApiContractError("Unknown AI step verdict", `${stepPath}.verdict`);
        }
        const score = row.score === null ? null : (0, validation_1.number)(row.score, `${stepPath}.score`);
        const confidence = (0, validation_1.number)(row.confidence, `${stepPath}.confidence`);
        if ((score !== null && (score < 0 || score > 1)) || confidence < 0 || confidence > 1) {
            throw new validation_1.ApiContractError("AI grade outside 0..1", stepPath);
        }
        if ((verdict === "NEEDS_REVIEW") !== (score === null)) {
            throw new validation_1.ApiContractError("AI verdict and score conflict", stepPath);
        }
        return { step_index: (0, validation_1.integer)(row.step_index, `${stepPath}.step_index`), verdict, score,
            confidence, feedback: (0, validation_1.nonEmptyString)(row.feedback, `${stepPath}.feedback`) };
    });
    if (steps.length === 0 || new Set(steps.map((step) => step.step_index)).size !== steps.length) {
        throw new validation_1.ApiContractError("AI review must contain unique steps", `${path}.step_grades`);
    }
    return { attempt_id: (0, validation_1.nonEmptyString)(source.attempt_id, `${path}.attempt_id`), step_grades: steps,
        needs_teacher_review: (0, validation_1.boolean)(source.needs_teacher_review, `${path}.needs_teacher_review`), is_final: false };
}
function parseInkPoint(value, path = "point") {
    const source = (0, validation_1.record)(value, path);
    return {
        x: (0, validation_1.number)(source.x, `${path}.x`),
        y: (0, validation_1.number)(source.y, `${path}.y`),
        pressure: typeof source.pressure === "number" ? source.pressure : 0.5,
    };
}
function parseInkStroke(value, path = "stroke") {
    const source = (0, validation_1.record)(value, path);
    const toolVal = (0, validation_1.string)(source.tool, `${path}.tool`);
    if (toolVal !== "PEN" && toolVal !== "HIGHLIGHTER") {
        throw new validation_1.ApiContractError(`Invalid stroke tool: ${toolVal}`, `${path}.tool`);
    }
    return {
        id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`),
        tool: toolVal,
        color: (0, validation_1.string)(source.color, `${path}.color`),
        width: (0, validation_1.number)(source.width, `${path}.width`),
        points: (0, validation_1.array)(source.points, `${path}.points`, parseInkPoint),
    };
}
function parseInkPageSummary(value, path = "page_summary") {
    const source = (0, validation_1.record)(value, path);
    return {
        page_index: (0, validation_1.integer)(source.page_index, `${path}.page_index`),
        stroke_count: (0, validation_1.integer)(source.stroke_count, `${path}.stroke_count`),
        point_count: (0, validation_1.integer)(source.point_count, `${path}.point_count`),
        sha256: (0, validation_1.string)(source.sha256, `${path}.sha256`),
    };
}
function parseInkDocumentRead(value, path = "ink_document") {
    const source = (0, validation_1.record)(value, path);
    return {
        document_revision: (0, validation_1.integer)(source.document_revision, `${path}.document_revision`),
        pages: (0, validation_1.array)(source.pages, `${path}.pages`, parseInkPageSummary),
    };
}
function parseInkPageRead(value, path = "ink_page") {
    const source = (0, validation_1.record)(value, path);
    return {
        document_revision: (0, validation_1.integer)(source.document_revision, `${path}.document_revision`),
        page_index: (0, validation_1.integer)(source.page_index, `${path}.page_index`),
        strokes: (0, validation_1.array)(source.strokes, `${path}.strokes`, parseInkStroke),
    };
}
function parseInkSaveRead(value, path = "ink_save") {
    const source = (0, validation_1.record)(value, path);
    return {
        document_revision: (0, validation_1.integer)(source.document_revision, `${path}.document_revision`),
        page_index: (0, validation_1.integer)(source.page_index, `${path}.page_index`),
        sha256: (0, validation_1.string)(source.sha256, `${path}.sha256`),
    };
}
function parseProblemOptionRead(value, path = "option") {
    const source = (0, validation_1.record)(value, path);
    return {
        id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`),
        label: (0, validation_1.string)(source.label, `${path}.label`),
        content: (0, validation_1.string)(source.content, `${path}.content`),
        order_index: (0, validation_1.integer)(source.order_index, `${path}.order_index`),
    };
}
function parseProblemRead(value, path = "problem") {
    const source = (0, validation_1.record)(value, path);
    return {
        id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`),
        content: (0, validation_1.string)(source.content, `${path}.content`),
        question_type: (0, validation_1.string)(source.question_type, `${path}.question_type`),
        options: (0, validation_1.array)(source.options, `${path}.options`, parseProblemOptionRead),
        order_index: typeof source.order_index === "number" ? source.order_index : null,
        is_read_only: typeof source.is_read_only === "boolean" ? source.is_read_only : false,
        source_kind: typeof source.source_kind === "string" ? source.source_kind : undefined,
        context_type: typeof source.context_type === "string" ? source.context_type : undefined,
    };
}
function parseSolutionAttemptRead(value, path = "attempt") {
    const source = (0, validation_1.record)(value, path);
    const rev = typeof source.attempt_revision_number === "number"
        ? source.attempt_revision_number
        : (typeof source.current_revision === "number" ? (0, validation_1.integer)(source.current_revision, `${path}.current_revision`) : 1);
    return {
        id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`),
        student_id: typeof source.student_id === "string" ? source.student_id : undefined,
        question_id: typeof source.question_id === "string" ? source.question_id : null,
        status: (0, validation_1.string)(source.status, `${path}.status`),
        context_type: typeof source.context_type === "string" ? source.context_type : undefined,
        source_kind: typeof source.source_kind === "string" ? source.source_kind : undefined,
        mode: typeof source.mode === "string" ? source.mode : undefined,
        current_revision: rev,
        created_at: typeof source.created_at === "string" ? source.created_at : (typeof source.started_at === "string" ? source.started_at : ""),
        updated_at: typeof source.updated_at === "string" ? source.updated_at : undefined,
        submitted_at: typeof source.submitted_at === "string" ? source.submitted_at : (source.submitted_at === null ? null : undefined),
        steps: source.steps === undefined ? undefined : (0, validation_1.array)(source.steps, `${path}.steps`, (value, stepPath) => {
            const step = (0, validation_1.record)(value, stepPath);
            const kind = (0, validation_1.string)(step.step_type, `${stepPath}.step_type`);
            if (!exports.STEP_KINDS.includes(kind)) {
                throw new validation_1.ApiContractError(`Invalid step type: ${kind}`, `${stepPath}.step_type`);
            }
            return {
                id: (0, validation_1.nonEmptyString)(step.id, `${stepPath}.id`),
                step_index: (0, validation_1.integer)(step.step_index, `${stepPath}.step_index`),
                step_type: kind,
                content_latex: step.content_latex === null ? null : (0, validation_1.string)(step.content_latex, `${stepPath}.content_latex`),
                explanation_text: step.explanation_text === null ? null : (0, validation_1.string)(step.explanation_text, `${stepPath}.explanation_text`),
                step_revision_number: (0, validation_1.integer)(step.step_revision_number, `${stepPath}.step_revision_number`),
                artifact: step.artifact === undefined || step.artifact === null ? null : (() => {
                    const artifact = (0, validation_1.record)(step.artifact, `${stepPath}.artifact`);
                    return { artifact_type: (0, validation_1.string)(artifact.artifact_type, `${stepPath}.artifact.artifact_type`),
                        payload: (0, validation_1.record)(artifact.payload, `${stepPath}.artifact.payload`) };
                })(),
            };
        }),
    };
}
function parseMathAttemptsPageRead(value, path = "attempts") {
    const source = (0, validation_1.record)(value, path);
    return {
        items: (0, validation_1.array)(source.items, `${path}.items`, parseSolutionAttemptRead),
        total: (0, validation_1.integer)(source.total, `${path}.total`),
        page: (0, validation_1.integer)(source.page, `${path}.page`),
        size: (0, validation_1.integer)(source.size, `${path}.size`),
        total_pages: (0, validation_1.integer)(source.total_pages, `${path}.total_pages`),
    };
}
function parsePracticeSessionStartRead(value, path = "practice_session") {
    const source = (0, validation_1.record)(value, path);
    return {
        id: (0, validation_1.nonEmptyString)(source.id, `${path}.id`),
        subject_id: (0, validation_1.nonEmptyString)(source.subject_id, `${path}.subject_id`),
    };
}
function parseOCRRecognizeResponse(value, path = "ocr_recognize") {
    var _a, _b;
    const source = (0, validation_1.record)(value, path);
    const stepTypeVal = (0, validation_1.string)(source.suggested_step_type, `${path}.suggested_step_type`);
    return {
        latex: (0, validation_1.string)(source.latex, `${path}.latex`),
        confidence: (0, validation_1.number)(source.confidence, `${path}.confidence`),
        suggested_step_type: stepTypeVal,
        explanation_text: typeof source.explanation_text === "string" ? source.explanation_text : null,
        detected_symbols: (0, validation_1.array)((_a = source.detected_symbols) !== null && _a !== void 0 ? _a : [], `${path}.detected_symbols`, (v, p) => (0, validation_1.string)(v, p)),
        alternative_latex: (0, validation_1.array)((_b = source.alternative_latex) !== null && _b !== void 0 ? _b : [], `${path}.alternative_latex`, (v, p) => (0, validation_1.string)(v, p)),
    };
}
