import assert from "node:assert/strict";
import test from "node:test";

import {
  parsePublishedSelfStudySubjectCodes,
  resolveStudentSubjectAccess,
  selectAccessibleSubject,
} from "../src/features/self-study/discovery";
import type { StudentMasteryRead, SubjectMasteryRead } from "../src/lib/api/contracts";

function subject(
  id: string,
  code: string,
  name: string,
  withHierarchy = true
): SubjectMasteryRead {
  const metric = {
    mastery_score: 0,
    confidence: 0,
    attempt_count: 0,
    correct_count: 0,
    last_practiced_at: null,
    last_updated_at: null,
    state: "NOT_STARTED" as const,
  };

  return {
    subject_id: id,
    code,
    name,
    ...metric,
    problem_type_count: withHierarchy ? 1 : 0,
    started_problem_type_count: 0,
    chapters: withHierarchy
      ? [
          {
            chapter_id: `${id}-chapter`,
            subject_id: id,
            code: `${code}_CHAPTER`,
            name: "Chương 1",
            ...metric,
            problem_type_count: 1,
            started_problem_type_count: 0,
            topics: [
              {
                topic_id: `${id}-topic`,
                chapter_id: `${id}-chapter`,
                code: `${code}_TOPIC`,
                name: "Chủ đề 1",
                ...metric,
                problem_type_count: 1,
                started_problem_type_count: 0,
                problem_types: [
                  {
                    problem_type_id: `${id}-problem-type`,
                    topic_id: `${id}-topic`,
                    code: `${code}_PT`,
                    name: "Dạng bài 1",
                    ...metric,
                  },
                ],
              },
            ],
          },
        ]
      : [],
    concepts: [],
  };
}

function mastery(...subjects: SubjectMasteryRead[]): StudentMasteryRead {
  return { student_id: "student-1", subjects };
}

test("publication policy parsing is normalized, deterministic, and rejects invalid codes", () => {
  assert.deepEqual(
    parsePublishedSelfStudySubjectCodes(" math_g12,PHYS_G12, math_g12,not allowed! "),
    ["MATH_G12", "PHYS_G12"]
  );
  assert.deepEqual(parsePublishedSelfStudySubjectCodes(undefined), []);
});

test("new student can discover only explicitly released subjects with browsable hierarchy", () => {
  const access = resolveStudentSubjectAccess(
    [],
    mastery(
      subject("math-id", "MATH_G12", "Toán 12"),
      subject("chem-id", "CHEM_G12", "Hóa học 12"),
      subject("empty-id", "EMPTY_G12", "Môn chưa có cấu trúc", false)
    ),
    ["MATH_G12", "EMPTY_G12"]
  );

  assert.deepEqual(access.subjects, [
    { id: "math-id", code: "MATH_G12", name: "Toán 12" },
  ]);
  assert.deepEqual(access.discoveryOnlySubjectIds, ["math-id"]);
});

test("real activity scope is preserved while a released self-study subject is added", () => {
  const access = resolveStudentSubjectAccess(
    [{ id: "class-id", code: "PHYS_G12", name: "Vật lý 12" }],
    mastery(
      subject("class-id", "PHYS_G12", "Vật lý 12"),
      subject("math-id", "MATH_G12", "Toán 12")
    ),
    ["MATH_G12"]
  );

  assert.deepEqual(access.subjects.map((item) => item.id), ["class-id", "math-id"]);
  assert.deepEqual(access.discoveryOnlySubjectIds, ["math-id"]);
});

test("activity subjects do not require the self-study allowlist and are never duplicated by code", () => {
  const access = resolveStudentSubjectAccess(
    [{ id: "real-id", code: "MATH_G12", name: "Toán 12" }],
    mastery(subject("different-id", "MATH_G12", "Toán 12")),
    ["MATH_G12"]
  );

  assert.equal(access.subjects.length, 1);
  assert.equal(access.subjects[0].id, "real-id");
  assert.deepEqual(access.discoveryOnlySubjectIds, []);
});

test("subject selection accepts only the merged accessible scope", () => {
  const access = resolveStudentSubjectAccess(
    [{ id: "class-id", code: "PHYS_G12", name: "Vật lý 12" }],
    mastery(subject("math-id", "MATH_G12", "Toán 12")),
    ["MATH_G12"]
  );

  assert.equal(selectAccessibleSubject(access, undefined, "class-id")?.id, "class-id");
  assert.equal(selectAccessibleSubject(access, "math_g12", "class-id")?.id, "math-id");
  assert.equal(selectAccessibleSubject(access, "unknown-id", "class-id"), undefined);
});
