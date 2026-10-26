"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const client_1 = require("../src/lib/api/client");
const contracts_1 = require("../src/lib/api/contracts");
const validation_1 = require("../src/lib/api/validation");
const mockSubjectMastery = {
    subject_id: "sub-1",
    code: "MATH12",
    name: "Toán 12",
    problem_type_count: 2,
    started_problem_type_count: 1,
    mastery_score: 0.78,
    confidence: 0.85,
    attempt_count: 12,
    correct_count: 10,
    last_practiced_at: "2026-10-08T00:00:00Z",
    last_updated_at: "2026-10-08T00:00:00Z",
    state: "LEARNING",
    chapters: [
        {
            chapter_id: "ch-1",
            subject_id: "sub-1",
            code: "CH01",
            name: "Ứng dụng đạo hàm",
            problem_type_count: 2,
            started_problem_type_count: 1,
            mastery_score: 0.75,
            confidence: 0.82,
            attempt_count: 12,
            correct_count: 10,
            last_practiced_at: "2026-10-08T00:00:00Z",
            last_updated_at: "2026-10-08T00:00:00Z",
            state: "LEARNING",
            topics: [
                {
                    topic_id: "top-1",
                    chapter_id: "ch-1",
                    code: "TOP01",
                    name: "Tính đơn điệu của hàm số",
                    problem_type_count: 2,
                    started_problem_type_count: 1,
                    mastery_score: 0.72,
                    confidence: 0.8,
                    attempt_count: 12,
                    correct_count: 10,
                    last_practiced_at: "2026-10-08T00:00:00Z",
                    last_updated_at: "2026-10-08T00:00:00Z",
                    state: "LEARNING",
                    problem_types: [
                        {
                            problem_type_id: "pt-1",
                            topic_id: "top-1",
                            code: "MATH12-PT-01",
                            name: "Xét tính đơn điệu bằng bảng biến thiên",
                            mastery_score: 0.85,
                            confidence: 0.9,
                            attempt_count: 12,
                            correct_count: 10,
                            last_practiced_at: "2026-10-08T00:00:00Z",
                            last_updated_at: "2026-10-08T00:00:00Z",
                            state: "MASTERED",
                        },
                        {
                            problem_type_id: "pt-2",
                            topic_id: "top-1",
                            code: "MATH12-PT-02",
                            name: "Cực trị hàm hợp",
                            mastery_score: 0.0,
                            confidence: 0.0,
                            attempt_count: 0,
                            correct_count: 0,
                            last_practiced_at: null,
                            last_updated_at: null,
                            state: "NOT_STARTED",
                        },
                    ],
                },
            ],
        },
    ],
    concepts: [
        {
            concept_id: "c-1",
            subject_id: "sub-1",
            code: "CON-01",
            name: "Đạo hàm cấp một",
            mastery_score: 0.9,
            confidence: 0.95,
            attempt_count: 15,
            correct_count: 14,
            last_practiced_at: "2026-10-07T00:00:00Z",
            last_updated_at: "2026-10-07T00:00:00Z",
            state: "MASTERED",
        },
    ],
};
const mockStudentMastery = {
    student_id: "student-uuid-1",
    subjects: [mockSubjectMastery],
};
(0, node_test_1.default)("parseDerivedMasteryState accepts all 6 backend mastery states", () => {
    const states = ["NOT_STARTED", "LEARNING", "WEAK", "PRACTICING", "MASTERED", "REVIEW_DUE"];
    for (const st of states) {
        strict_1.default.equal((0, contracts_1.parseDerivedMasteryState)(st), st);
    }
    strict_1.default.throws(() => (0, contracts_1.parseDerivedMasteryState)("UNKNOWN_STATE"), validation_1.ApiContractError);
});
(0, node_test_1.default)("parseStudentMastery validates valid curriculum hierarchy", () => {
    const parsed = (0, contracts_1.parseStudentMastery)(mockStudentMastery);
    strict_1.default.equal(parsed.student_id, "student-uuid-1");
    strict_1.default.equal(parsed.subjects.length, 1);
    strict_1.default.equal(parsed.subjects[0].code, "MATH12");
    strict_1.default.equal(parsed.subjects[0].chapters[0].topics[0].problem_types.length, 2);
    strict_1.default.equal(parsed.subjects[0].concepts.length, 1);
});
(0, node_test_1.default)("parseStudentMastery rejects invalid payload structure", () => {
    strict_1.default.throws(() => (0, contracts_1.parseStudentMastery)(null), validation_1.ApiContractError);
    strict_1.default.throws(() => (0, contracts_1.parseStudentMastery)({ student_id: 123 }), validation_1.ApiContractError);
    strict_1.default.throws(() => (0, contracts_1.parseStudentMastery)({ student_id: "s1", subjects: "not-an-array" }), validation_1.ApiContractError);
});
(0, node_test_1.default)("parseProblemTypeMastery validates single problem type drill-down", () => {
    const ptData = mockSubjectMastery.chapters[0].topics[0].problem_types[0];
    const parsed = (0, contracts_1.parseProblemTypeMastery)(ptData);
    strict_1.default.equal(parsed.problem_type_id, "pt-1");
    strict_1.default.equal(parsed.state, "MASTERED");
    strict_1.default.equal(parsed.mastery_score, 0.85);
    strict_1.default.equal(parsed.attempt_count, 12);
});
(0, node_test_1.default)("parseConceptMastery validates single concept drill-down", () => {
    const conceptData = mockSubjectMastery.concepts[0];
    const parsed = (0, contracts_1.parseConceptMastery)(conceptData);
    strict_1.default.equal(parsed.concept_id, "c-1");
    strict_1.default.equal(parsed.state, "MASTERED");
    strict_1.default.equal(parsed.attempt_count, 15);
});
(0, node_test_1.default)("apiClient.studentMastery requests canonical /students/me/mastery endpoint", async () => {
    let requestedUrl = "";
    let authHeader = "";
    const api = (0, client_1.createApiClient)({
        baseUrl: "http://api.example.test",
        fetcher: async (input, init) => {
            var _a;
            requestedUrl = String(input);
            authHeader = (_a = new Headers(init === null || init === void 0 ? void 0 : init.headers).get("Authorization")) !== null && _a !== void 0 ? _a : "";
            return Response.json(mockStudentMastery);
        },
    });
    const res = await api.studentMastery("test-access-token");
    strict_1.default.equal(requestedUrl, "http://api.example.test/students/me/mastery");
    strict_1.default.equal(authHeader, "Bearer test-access-token");
    strict_1.default.equal(res.student_id, "student-uuid-1");
});
(0, node_test_1.default)("apiClient.studentProblemTypeMastery requests canonical /students/me/mastery/problem-types/:id", async () => {
    let requestedUrl = "";
    const api = (0, client_1.createApiClient)({
        baseUrl: "http://api.example.test",
        fetcher: async (input) => {
            requestedUrl = String(input);
            return Response.json(mockSubjectMastery.chapters[0].topics[0].problem_types[0]);
        },
    });
    const res = await api.studentProblemTypeMastery("token", "pt-1");
    strict_1.default.equal(requestedUrl, "http://api.example.test/students/me/mastery/problem-types/pt-1");
    strict_1.default.equal(res.problem_type_id, "pt-1");
});
(0, node_test_1.default)("apiClient.studentConceptMastery requests canonical /students/me/mastery/concepts/:id", async () => {
    let requestedUrl = "";
    const api = (0, client_1.createApiClient)({
        baseUrl: "http://api.example.test",
        fetcher: async (input) => {
            requestedUrl = String(input);
            return Response.json(mockSubjectMastery.concepts[0]);
        },
    });
    const res = await api.studentConceptMastery("token", "c-1");
    strict_1.default.equal(requestedUrl, "http://api.example.test/students/me/mastery/concepts/c-1");
    strict_1.default.equal(res.concept_id, "c-1");
});
