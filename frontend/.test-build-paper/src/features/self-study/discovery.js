"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SelfStudyPublicationPolicyError = void 0;
exports.parsePublishedSelfStudySubjectCodes = parsePublishedSelfStudySubjectCodes;
exports.requirePublishedSelfStudySubjectCodes = requirePublishedSelfStudySubjectCodes;
exports.resolveStudentSubjectAccess = resolveStudentSubjectAccess;
exports.selectAccessibleSubject = selectAccessibleSubject;
const SUBJECT_CODE_PATTERN = /^[A-Z0-9][A-Z0-9_:-]{0,63}$/;
class SelfStudyPublicationPolicyError extends Error {
    constructor(message) {
        super(message);
        this.name = "SelfStudyPublicationPolicyError";
    }
}
exports.SelfStudyPublicationPolicyError = SelfStudyPublicationPolicyError;
function parsePublishedSelfStudySubjectCodes(rawValue) {
    if (!rawValue)
        return [];
    const codes = rawValue
        .split(",")
        .map((value) => value.trim().toUpperCase())
        .filter((value) => SUBJECT_CODE_PATTERN.test(value));
    return [...new Set(codes)];
}
/**
 * Reads an environment-owned publication policy without silently converting a
 * missing or malformed deployment setting into "no subjects are available".
 * An explicitly empty value remains a valid fail-closed policy.
 */
function requirePublishedSelfStudySubjectCodes(rawValue) {
    if (rawValue === undefined) {
        throw new SelfStudyPublicationPolicyError("SELF_STUDY_PUBLISHED_SUBJECT_CODES must be configured explicitly.");
    }
    const configuredValues = rawValue
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
    if (configuredValues.some((value) => !SUBJECT_CODE_PATTERN.test(value.toUpperCase()))) {
        throw new SelfStudyPublicationPolicyError("SELF_STUDY_PUBLISHED_SUBJECT_CODES contains an invalid subject code.");
    }
    return parsePublishedSelfStudySubjectCodes(rawValue);
}
function hasBrowsableCurriculum(subject) {
    return subject.chapters.some((chapter) => chapter.topics.some((topic) => topic.problem_types.length > 0));
}
/**
 * Extends the student's real activity scope with curriculum subjects that have been
 * explicitly released for self-study by server configuration. Mastery is used only
 * as the authenticated curriculum read model; it is never treated as a publication
 * decision on its own.
 */
function resolveStudentSubjectAccess(activitySubjects, mastery, publishedSelfStudyCodes) {
    var _a;
    const subjects = activitySubjects.map((subject) => (Object.assign({}, subject)));
    const knownIds = new Set(subjects.map((subject) => subject.id));
    const knownCodes = new Set(subjects.map((subject) => subject.code.toUpperCase()));
    const allowedCodes = new Set(publishedSelfStudyCodes.map((code) => code.toUpperCase()));
    const discoveryOnlySubjectIds = [];
    for (const subject of (_a = mastery === null || mastery === void 0 ? void 0 : mastery.subjects) !== null && _a !== void 0 ? _a : []) {
        const normalizedCode = subject.code.toUpperCase();
        if (!allowedCodes.has(normalizedCode) ||
            knownIds.has(subject.subject_id) ||
            knownCodes.has(normalizedCode) ||
            !hasBrowsableCurriculum(subject)) {
            continue;
        }
        subjects.push({
            id: subject.subject_id,
            code: subject.code,
            name: subject.name,
        });
        knownIds.add(subject.subject_id);
        knownCodes.add(normalizedCode);
        discoveryOnlySubjectIds.push(subject.subject_id);
    }
    return { subjects, discoveryOnlySubjectIds };
}
function selectAccessibleSubject(access, requestedSubjectId, focusSubjectId) {
    var _a;
    if (requestedSubjectId) {
        const normalizedRequest = requestedSubjectId.toLowerCase();
        return access.subjects.find((subject) => subject.id === requestedSubjectId || subject.code.toLowerCase() === normalizedRequest);
    }
    return ((_a = access.subjects.find((subject) => subject.id === focusSubjectId)) !== null && _a !== void 0 ? _a : access.subjects[0]);
}
