"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const discovery_1 = require("../src/features/self-study/discovery");
function subject(id, code, name, withHierarchy = true) {
    const metric = {
        mastery_score: 0,
        confidence: 0,
        attempt_count: 0,
        correct_count: 0,
        last_practiced_at: null,
        last_updated_at: null,
        state: "NOT_STARTED",
    };
    return Object.assign(Object.assign({ subject_id: id, code,
        name }, metric), { problem_type_count: withHierarchy ? 1 : 0, started_problem_type_count: 0, chapters: withHierarchy
            ? [
                Object.assign(Object.assign({ chapter_id: `${id}-chapter`, subject_id: id, code: `${code}_CHAPTER`, name: "Chương 1" }, metric), { problem_type_count: 1, started_problem_type_count: 0, topics: [
                        Object.assign(Object.assign({ topic_id: `${id}-topic`, chapter_id: `${id}-chapter`, code: `${code}_TOPIC`, name: "Chủ đề 1" }, metric), { problem_type_count: 1, started_problem_type_count: 0, problem_types: [
                                Object.assign({ problem_type_id: `${id}-problem-type`, topic_id: `${id}-topic`, code: `${code}_PT`, name: "Dạng bài 1" }, metric),
                            ] }),
                    ] }),
            ]
            : [], concepts: [] });
}
function mastery(...subjects) {
    return { student_id: "student-1", subjects };
}
(0, node_test_1.default)("publication policy parsing is normalized, deterministic, and rejects invalid codes", () => {
    strict_1.default.deepEqual((0, discovery_1.parsePublishedSelfStudySubjectCodes)(" math_g12,PHYS_G12, math_g12,not allowed! "), ["MATH_G12", "PHYS_G12"]);
    strict_1.default.deepEqual((0, discovery_1.parsePublishedSelfStudySubjectCodes)(undefined), []);
});
(0, node_test_1.default)("deployment publication policy must be explicit and valid", () => {
    strict_1.default.throws(() => (0, discovery_1.requirePublishedSelfStudySubjectCodes)(undefined), discovery_1.SelfStudyPublicationPolicyError);
    strict_1.default.throws(() => (0, discovery_1.requirePublishedSelfStudySubjectCodes)("MATH_G12,not allowed!"), discovery_1.SelfStudyPublicationPolicyError);
    strict_1.default.deepEqual((0, discovery_1.requirePublishedSelfStudySubjectCodes)(""), []);
    strict_1.default.deepEqual((0, discovery_1.requirePublishedSelfStudySubjectCodes)("math_g12,MATH_G12"), ["MATH_G12"]);
});
(0, node_test_1.default)("new student can discover only explicitly released subjects with browsable hierarchy", () => {
    const access = (0, discovery_1.resolveStudentSubjectAccess)([], mastery(subject("math-id", "MATH_G12", "Toán 12"), subject("chem-id", "CHEM_G12", "Hóa học 12"), subject("empty-id", "EMPTY_G12", "Môn chưa có cấu trúc", false)), ["MATH_G12", "EMPTY_G12"]);
    strict_1.default.deepEqual(access.subjects, [
        { id: "math-id", code: "MATH_G12", name: "Toán 12" },
    ]);
    strict_1.default.deepEqual(access.discoveryOnlySubjectIds, ["math-id"]);
});
(0, node_test_1.default)("real activity scope is preserved while a released self-study subject is added", () => {
    const access = (0, discovery_1.resolveStudentSubjectAccess)([{ id: "class-id", code: "PHYS_G12", name: "Vật lý 12" }], mastery(subject("class-id", "PHYS_G12", "Vật lý 12"), subject("math-id", "MATH_G12", "Toán 12")), ["MATH_G12"]);
    strict_1.default.deepEqual(access.subjects.map((item) => item.id), ["class-id", "math-id"]);
    strict_1.default.deepEqual(access.discoveryOnlySubjectIds, ["math-id"]);
});
(0, node_test_1.default)("activity subjects do not require the self-study allowlist and are never duplicated by code", () => {
    const access = (0, discovery_1.resolveStudentSubjectAccess)([{ id: "real-id", code: "MATH_G12", name: "Toán 12" }], mastery(subject("different-id", "MATH_G12", "Toán 12")), ["MATH_G12"]);
    strict_1.default.equal(access.subjects.length, 1);
    strict_1.default.equal(access.subjects[0].id, "real-id");
    strict_1.default.deepEqual(access.discoveryOnlySubjectIds, []);
});
(0, node_test_1.default)("subject selection accepts only the merged accessible scope", () => {
    var _a, _b;
    const access = (0, discovery_1.resolveStudentSubjectAccess)([{ id: "class-id", code: "PHYS_G12", name: "Vật lý 12" }], mastery(subject("math-id", "MATH_G12", "Toán 12")), ["MATH_G12"]);
    strict_1.default.equal((_a = (0, discovery_1.selectAccessibleSubject)(access, undefined, "class-id")) === null || _a === void 0 ? void 0 : _a.id, "class-id");
    strict_1.default.equal((_b = (0, discovery_1.selectAccessibleSubject)(access, "math_g12", "class-id")) === null || _b === void 0 ? void 0 : _b.id, "math-id");
    strict_1.default.equal((0, discovery_1.selectAccessibleSubject)(access, "unknown-id", "class-id"), undefined);
});
