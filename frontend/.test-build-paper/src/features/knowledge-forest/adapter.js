"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.toKnowledgeForestViewModel = toKnowledgeForestViewModel;
const validation_1 = require("../../lib/api/validation");
const fallbackBiomes = ["meadow", "river", "mountain", "forest", "sky"];
/**
 * Validates a unit interval score [0.0, 1.0] and converts it to whole integer percentage [0, 100].
 * Returns undefined if score is null, undefined, NaN, or out of valid bounds.
 */
function safePercent(score) {
    if (score === null || score === undefined || typeof score !== "number" || Number.isNaN(score)) {
        return undefined;
    }
    if (score < 0 || score > 1) {
        return undefined;
    }
    return Math.round(score * 100);
}
function toKnowledgeForestViewModel(mastery, availableSubjects = [], selectedSubjectId, studentId, discoveryOnlySubjectIds = []) {
    var _a;
    // P0 Data Isolation invariant: Mastery student_id must match learning state student_id
    if (mastery && studentId && mastery.student_id !== studentId) {
        throw new validation_1.ApiContractError(`Hồ sơ học sinh không đồng nhất: Mastery student_id (${mastery.student_id}) không khớp Learning State (${studentId}).`);
    }
    // Safe fallback when availableSubjects is empty
    if (!availableSubjects || availableSubjects.length === 0) {
        return {
            subject: { id: "", code: "", name: "Chưa có môn học" },
            availableSubjects: [],
            accessMode: "UNAVAILABLE",
            summary: createEmptySummary(),
            chapters: [],
            concepts: [],
            hasCurriculum: false,
            hasEvidence: false,
        };
    }
    // Filter mastery subjects strictly to the student's available scope:
    // Match strictly by subject_id to prevent mixing data across different IDs.
    const availableIds = new Set(availableSubjects.map((s) => s.id));
    const scopedMasterySubjects = ((_a = mastery === null || mastery === void 0 ? void 0 : mastery.subjects) !== null && _a !== void 0 ? _a : []).filter((subj) => availableIds.has(subj.subject_id));
    // Determine active subject from student's available scope
    const requestedAvailableSubject = selectedSubjectId
        ? availableSubjects.find((s) => s.id === selectedSubjectId || s.code.toLowerCase() === selectedSubjectId.toLowerCase())
        : undefined;
    const activeSubjectInfo = requestedAvailableSubject !== null && requestedAvailableSubject !== void 0 ? requestedAvailableSubject : availableSubjects[0];
    // Find corresponding mastery data for this active subject by exact subject_id
    const activeMasterySubject = scopedMasterySubjects.find((subj) => subj.subject_id === activeSubjectInfo.id);
    if (!activeMasterySubject) {
        return {
            subject: {
                id: activeSubjectInfo.id,
                code: activeSubjectInfo.code,
                name: activeSubjectInfo.name,
            },
            availableSubjects,
            accessMode: discoveryOnlySubjectIds.includes(activeSubjectInfo.id)
                ? "SELF_STUDY_DISCOVERY"
                : "LEARNING_ACTIVITY",
            summary: createEmptySummary(),
            chapters: [],
            concepts: [],
            hasCurriculum: false,
            hasEvidence: false,
        };
    }
    // Map chapters, topics, problem types
    let totalMastered = 0;
    let totalPracticing = 0;
    let totalLearning = 0;
    let totalWeak = 0;
    let totalReviewDue = 0;
    let totalNotStarted = 0;
    let totalProblemTypes = 0;
    const chapters = activeMasterySubject.chapters.map((chapter, chapterIndex) => {
        const biome = fallbackBiomes[chapterIndex % fallbackBiomes.length];
        const topics = chapter.topics.map((topic) => {
            const problemTypes = topic.problem_types.map((pt) => {
                totalProblemTypes += 1;
                switch (pt.state) {
                    case "MASTERED":
                        totalMastered += 1;
                        break;
                    case "PRACTICING":
                        totalPracticing += 1;
                        break;
                    case "LEARNING":
                        totalLearning += 1;
                        break;
                    case "WEAK":
                        totalWeak += 1;
                        break;
                    case "REVIEW_DUE":
                        totalReviewDue += 1;
                        break;
                    case "NOT_STARTED":
                    default:
                        totalNotStarted += 1;
                        break;
                }
                const hasEvidence = pt.attempt_count > 0;
                return {
                    id: pt.problem_type_id,
                    code: pt.code,
                    name: pt.name,
                    topicId: topic.topic_id,
                    topicName: topic.name,
                    chapterId: chapter.chapter_id,
                    chapterName: chapter.name,
                    masteryScore: hasEvidence ? safePercent(pt.mastery_score) : undefined,
                    rawMasteryScore: pt.mastery_score,
                    confidence: hasEvidence ? safePercent(pt.confidence) : undefined,
                    attemptCount: pt.attempt_count,
                    correctCount: pt.correct_count,
                    state: pt.state,
                    lastPracticedAt: pt.last_practiced_at,
                    isReviewDue: pt.state === "REVIEW_DUE",
                };
            });
            const hasTopicEvidence = topic.attempt_count > 0;
            return {
                id: topic.topic_id,
                code: topic.code,
                name: topic.name,
                chapterId: chapter.chapter_id,
                problemTypeCount: topic.problem_type_count,
                startedProblemTypeCount: topic.started_problem_type_count,
                masteryScore: hasTopicEvidence ? safePercent(topic.mastery_score) : undefined,
                rawMasteryScore: topic.mastery_score,
                state: topic.state,
                attemptCount: topic.attempt_count,
                problemTypes,
            };
        });
        const hasChapterEvidence = chapter.attempt_count > 0;
        return {
            id: chapter.chapter_id,
            code: chapter.code,
            name: chapter.name,
            biome,
            problemTypeCount: chapter.problem_type_count,
            startedProblemTypeCount: chapter.started_problem_type_count,
            masteryScore: hasChapterEvidence ? safePercent(chapter.mastery_score) : undefined,
            rawMasteryScore: chapter.mastery_score,
            state: chapter.state,
            attemptCount: chapter.attempt_count,
            topics,
        };
    });
    // Map concepts (subject-level knowledge nodes)
    const concepts = activeMasterySubject.concepts.map((concept) => {
        const hasEvidence = concept.attempt_count > 0;
        return {
            id: concept.concept_id,
            code: concept.code,
            name: concept.name,
            subjectId: concept.subject_id,
            masteryScore: hasEvidence ? safePercent(concept.mastery_score) : undefined,
            rawMasteryScore: concept.mastery_score,
            confidence: hasEvidence ? safePercent(concept.confidence) : undefined,
            attemptCount: concept.attempt_count,
            correctCount: concept.correct_count,
            state: concept.state,
            lastPracticedAt: concept.last_practiced_at,
        };
    });
    const hasSubjectEvidence = activeMasterySubject.attempt_count > 0;
    const summary = {
        problemTypeCount: totalProblemTypes || activeMasterySubject.problem_type_count,
        startedProblemTypeCount: activeMasterySubject.started_problem_type_count,
        masteryScore: hasSubjectEvidence ? safePercent(activeMasterySubject.mastery_score) : undefined,
        rawMasteryScore: activeMasterySubject.mastery_score,
        confidence: hasSubjectEvidence ? safePercent(activeMasterySubject.confidence) : undefined,
        attemptCount: activeMasterySubject.attempt_count,
        state: activeMasterySubject.state,
        masteredCount: totalMastered,
        practicingCount: totalPracticing,
        learningCount: totalLearning,
        weakCount: totalWeak,
        reviewDueCount: totalReviewDue,
        notStartedCount: totalNotStarted,
    };
    return {
        subject: {
            id: activeSubjectInfo.id,
            code: activeSubjectInfo.code,
            name: activeSubjectInfo.name,
        },
        availableSubjects,
        accessMode: discoveryOnlySubjectIds.includes(activeSubjectInfo.id)
            ? "SELF_STUDY_DISCOVERY"
            : "LEARNING_ACTIVITY",
        summary,
        chapters,
        concepts,
        hasCurriculum: chapters.length > 0 || concepts.length > 0,
        hasEvidence: hasSubjectEvidence,
    };
}
function createEmptySummary() {
    return {
        problemTypeCount: 0,
        startedProblemTypeCount: 0,
        rawMasteryScore: 0,
        attemptCount: 0,
        state: "NOT_STARTED",
        masteredCount: 0,
        weakCount: 0,
        learningCount: 0,
        practicingCount: 0,
        reviewDueCount: 0,
        notStartedCount: 0,
    };
}
