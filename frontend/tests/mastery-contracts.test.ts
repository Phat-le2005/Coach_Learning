import assert from "node:assert/strict";
import test from "node:test";

import { createApiClient } from "../src/lib/api/client";
import {
  parseConceptMastery,
  parseDerivedMasteryState,
  parseProblemTypeMastery,
  parseStudentMastery,
  type StudentMasteryRead,
  type SubjectMasteryRead,
} from "../src/lib/api/contracts";
import { ApiContractError } from "../src/lib/api/validation";

const mockSubjectMastery: SubjectMasteryRead = {
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

const mockStudentMastery: StudentMasteryRead = {
  student_id: "student-uuid-1",
  subjects: [mockSubjectMastery],
};

test("parseDerivedMasteryState accepts all 6 backend mastery states", () => {
  const states = ["NOT_STARTED", "LEARNING", "WEAK", "PRACTICING", "MASTERED", "REVIEW_DUE"] as const;
  for (const st of states) {
    assert.equal(parseDerivedMasteryState(st), st);
  }
  assert.throws(() => parseDerivedMasteryState("UNKNOWN_STATE"), ApiContractError);
});

test("parseStudentMastery validates valid curriculum hierarchy", () => {
  const parsed = parseStudentMastery(mockStudentMastery);
  assert.equal(parsed.student_id, "student-uuid-1");
  assert.equal(parsed.subjects.length, 1);
  assert.equal(parsed.subjects[0].code, "MATH12");
  assert.equal(parsed.subjects[0].chapters[0].topics[0].problem_types.length, 2);
  assert.equal(parsed.subjects[0].concepts.length, 1);
});

test("parseStudentMastery rejects invalid payload structure", () => {
  assert.throws(() => parseStudentMastery(null), ApiContractError);
  assert.throws(() => parseStudentMastery({ student_id: 123 }), ApiContractError);
  assert.throws(() => parseStudentMastery({ student_id: "s1", subjects: "not-an-array" }), ApiContractError);
});

test("parseProblemTypeMastery validates single problem type drill-down", () => {
  const ptData = mockSubjectMastery.chapters[0].topics[0].problem_types[0];
  const parsed = parseProblemTypeMastery(ptData);
  assert.equal(parsed.problem_type_id, "pt-1");
  assert.equal(parsed.state, "MASTERED");
  assert.equal(parsed.mastery_score, 0.85);
  assert.equal(parsed.attempt_count, 12);
});

test("parseConceptMastery validates single concept drill-down", () => {
  const conceptData = mockSubjectMastery.concepts[0];
  const parsed = parseConceptMastery(conceptData);
  assert.equal(parsed.concept_id, "c-1");
  assert.equal(parsed.state, "MASTERED");
  assert.equal(parsed.attempt_count, 15);
});

test("apiClient.studentMastery requests canonical /students/me/mastery endpoint", async () => {
  let requestedUrl = "";
  let authHeader = "";
  const api = createApiClient({
    baseUrl: "http://api.example.test",
    fetcher: async (input, init) => {
      requestedUrl = String(input);
      authHeader = new Headers(init?.headers).get("Authorization") ?? "";
      return Response.json(mockStudentMastery);
    },
  });

  const res = await api.studentMastery("test-access-token");
  assert.equal(requestedUrl, "http://api.example.test/students/me/mastery");
  assert.equal(authHeader, "Bearer test-access-token");
  assert.equal(res.student_id, "student-uuid-1");
});

test("apiClient.studentProblemTypeMastery requests canonical /students/me/mastery/problem-types/:id", async () => {
  let requestedUrl = "";
  const api = createApiClient({
    baseUrl: "http://api.example.test",
    fetcher: async (input) => {
      requestedUrl = String(input);
      return Response.json(mockSubjectMastery.chapters[0].topics[0].problem_types[0]);
    },
  });

  const res = await api.studentProblemTypeMastery("token", "pt-1");
  assert.equal(requestedUrl, "http://api.example.test/students/me/mastery/problem-types/pt-1");
  assert.equal(res.problem_type_id, "pt-1");
});

test("apiClient.studentConceptMastery requests canonical /students/me/mastery/concepts/:id", async () => {
  let requestedUrl = "";
  const api = createApiClient({
    baseUrl: "http://api.example.test",
    fetcher: async (input) => {
      requestedUrl = String(input);
      return Response.json(mockSubjectMastery.concepts[0]);
    },
  });

  const res = await api.studentConceptMastery("token", "c-1");
  assert.equal(requestedUrl, "http://api.example.test/students/me/mastery/concepts/c-1");
  assert.equal(res.concept_id, "c-1");
});
