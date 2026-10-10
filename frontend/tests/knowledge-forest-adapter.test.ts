import assert from "node:assert/strict";
import test from "node:test";

import { toKnowledgeForestViewModel } from "../src/features/knowledge-forest/adapter";
import type { StudentLearningSubjectRead, StudentMasteryRead } from "../src/lib/api/contracts";
import { ApiContractError } from "../src/lib/api/validation";

const mockAvailableSubjects: StudentLearningSubjectRead[] = [
  { id: "sub-math", code: "MATH12", name: "Toán 12" },
  { id: "sub-phys", code: "PHYS12", name: "Vật lý 12" },
];

function createMockMasteryData(): StudentMasteryRead {
  return {
    student_id: "student-1",
    subjects: [
      {
        subject_id: "sub-math",
        code: "MATH12",
        name: "Toán 12",
        problem_type_count: 3,
        started_problem_type_count: 2,
        mastery_score: 0.74,
        confidence: 0.85,
        attempt_count: 15,
        correct_count: 11,
        last_practiced_at: "2026-10-07T00:00:00Z",
        last_updated_at: "2026-10-07T00:00:00Z",
        state: "LEARNING",
        chapters: [
          {
            chapter_id: "ch-1",
            subject_id: "sub-math",
            code: "CH01",
            name: "Ứng dụng đạo hàm",
            problem_type_count: 3,
            started_problem_type_count: 2,
            mastery_score: 0.8,
            confidence: 0.85,
            attempt_count: 15,
            correct_count: 11,
            last_practiced_at: "2026-10-07T00:00:00Z",
            last_updated_at: "2026-10-07T00:00:00Z",
            state: "LEARNING",
            topics: [
              {
                topic_id: "top-1",
                chapter_id: "ch-1",
                code: "TOP01",
                name: "Đơn điệu hàm số",
                problem_type_count: 3,
                started_problem_type_count: 2,
                mastery_score: 0.8,
                confidence: 0.85,
                attempt_count: 15,
                correct_count: 11,
                last_practiced_at: "2026-10-07T00:00:00Z",
                last_updated_at: "2026-10-07T00:00:00Z",
                state: "LEARNING",
                problem_types: [
                  {
                    problem_type_id: "pt-1",
                    topic_id: "top-1",
                    code: "MATH12-PT-01",
                    name: "Đơn điệu hàm bậc ba",
                    mastery_score: 0.92,
                    confidence: 0.9,
                    attempt_count: 10,
                    correct_count: 9,
                    last_practiced_at: "2026-10-07T00:00:00Z",
                    last_updated_at: "2026-10-07T00:00:00Z",
                    state: "MASTERED",
                  },
                  {
                    problem_type_id: "pt-2",
                    topic_id: "top-1",
                    code: "MATH12-PT-02",
                    name: "Cực trị có tham số m",
                    mastery_score: 0.45,
                    confidence: 0.6,
                    attempt_count: 5,
                    correct_count: 2,
                    last_practiced_at: "2026-10-06T00:00:00Z",
                    last_updated_at: "2026-10-06T00:00:00Z",
                    state: "WEAK",
                  },
                  {
                    problem_type_id: "pt-3",
                    topic_id: "top-1",
                    code: "MATH12-PT-03",
                    name: "Tiệm cận đứng và ngang",
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
            subject_id: "sub-math",
            code: "CON-01",
            name: "Định lý Fermat về cực trị",
            mastery_score: 0.88,
            confidence: 0.9,
            attempt_count: 8,
            correct_count: 7,
            last_practiced_at: "2026-10-05T00:00:00Z",
            last_updated_at: "2026-10-05T00:00:00Z",
            state: "MASTERED",
          },
        ],
      },
      {
        // Out of scope subject that the student does not have enrolled
        subject_id: "sub-out-of-scope",
        code: "CHEM12",
        name: "Hóa học 12",
        problem_type_count: 0,
        started_problem_type_count: 0,
        mastery_score: 0.5,
        confidence: 0.5,
        attempt_count: 0,
        correct_count: 0,
        last_practiced_at: null,
        last_updated_at: null,
        state: "NOT_STARTED",
        chapters: [],
        concepts: [],
      },
    ],
  };
}

test("scopes subjects strictly to availableSubjects from Learning State", () => {
  const masteryData = createMockMasteryData();

  const vm = toKnowledgeForestViewModel(masteryData, mockAvailableSubjects);

  // Out of scope CHEM12 must not appear in availableSubjects
  assert.equal(vm.availableSubjects.length, 2);
  assert.deepEqual(
    vm.availableSubjects.map((s) => s.code),
    ["MATH12", "PHYS12"]
  );
  assert.equal(vm.subject.code, "MATH12");
});

test("correctly differentiates NOT_STARTED from WEAK without fabricating 0% score", () => {
  const masteryData = createMockMasteryData();

  const vm = toKnowledgeForestViewModel(masteryData, mockAvailableSubjects);
  const topic = vm.chapters[0].topics[0];

  const masteredPt = topic.problemTypes.find((pt) => pt.id === "pt-1");
  const weakPt = topic.problemTypes.find((pt) => pt.id === "pt-2");
  const notStartedPt = topic.problemTypes.find((pt) => pt.id === "pt-3");

  // Mastered pt has 92%
  assert.equal(masteredPt?.state, "MASTERED");
  assert.equal(masteredPt?.masteryScore, 92);
  assert.equal(masteredPt?.attemptCount, 10);

  // Weak pt has 45%
  assert.equal(weakPt?.state, "WEAK");
  assert.equal(weakPt?.masteryScore, 45);
  assert.equal(weakPt?.attemptCount, 5);

  // Crucial invariant: attempt_count === 0 is NOT_STARTED and masteryScore is undefined (NOT 0%!)
  assert.equal(notStartedPt?.state, "NOT_STARTED");
  assert.equal(notStartedPt?.masteryScore, undefined);
  assert.equal(notStartedPt?.attemptCount, 0);
});

test("calculates accurate forest summary counters", () => {
  const masteryData = createMockMasteryData();

  const vm = toKnowledgeForestViewModel(masteryData, mockAvailableSubjects);

  assert.equal(vm.summary.problemTypeCount, 3);
  assert.equal(vm.summary.masteredCount, 1);
  assert.equal(vm.summary.weakCount, 1);
  assert.equal(vm.summary.notStartedCount, 1);
  assert.equal(vm.summary.learningCount, 0);
  assert.equal(vm.summary.practicingCount, 0);
  assert.equal(vm.summary.reviewDueCount, 0);
  assert.equal(vm.concepts.length, 1);
  assert.equal(vm.hasCurriculum, true);
  assert.equal(vm.hasEvidence, true);
});

test("maps biomes deterministically to chapters", () => {
  const masteryData = createMockMasteryData();

  const vm = toKnowledgeForestViewModel(masteryData, mockAvailableSubjects);
  assert.equal(vm.chapters[0].biome, "meadow");
});

test("handles selectedSubjectId override within allowed scope", () => {
  const masteryData = createMockMasteryData();

  const vm = toKnowledgeForestViewModel(
    masteryData,
    mockAvailableSubjects,
    "sub-phys"
  );

  assert.equal(vm.subject.id, "sub-phys");
  assert.equal(vm.subject.code, "PHYS12");
  // Physics has no chapters in mockMasteryData
  assert.equal(vm.chapters.length, 0);
});

test("falls back gracefully when masteryData is absent", () => {
  const vm = toKnowledgeForestViewModel(undefined, mockAvailableSubjects);

  assert.equal(vm.hasCurriculum, false);
  assert.equal(vm.chapters.length, 0);
  assert.equal(vm.summary.problemTypeCount, 0);
  assert.equal(vm.availableSubjects.length, 2);
});

test("falls back gracefully when availableSubjects is empty", () => {
  const vm = toKnowledgeForestViewModel(undefined, []);

  assert.equal(vm.hasCurriculum, false);
  assert.equal(vm.availableSubjects.length, 0);
  assert.equal(vm.subject.id, "");
});

test("enforces student data isolation: student_id mismatch throws ApiContractError", () => {
  const masteryData = createMockMasteryData(); // student_id: "student-1"

  assert.throws(
    () =>
      toKnowledgeForestViewModel(
        masteryData,
        mockAvailableSubjects,
        undefined,
        "different-student-uuid"
      ),
    ApiContractError
  );
});

test("marks hasCurriculum true when subject has concepts even if chapters are empty", () => {
  const masteryData: StudentMasteryRead = {
    student_id: "student-1",
    subjects: [
      {
        subject_id: "sub-math",
        code: "MATH12",
        name: "Toán 12",
        problem_type_count: 0,
        started_problem_type_count: 0,
        mastery_score: 0.8,
        confidence: 0.8,
        attempt_count: 5,
        correct_count: 4,
        last_practiced_at: "2026-10-08T00:00:00Z",
        last_updated_at: "2026-10-08T00:00:00Z",
        state: "MASTERED",
        chapters: [],
        concepts: [
          {
            concept_id: "c-only",
            subject_id: "sub-math",
            code: "CON-ONLY",
            name: "Khái niệm độc lập",
            mastery_score: 0.85,
            confidence: 0.9,
            attempt_count: 4,
            correct_count: 3,
            last_practiced_at: "2026-10-07T00:00:00Z",
            last_updated_at: "2026-10-07T00:00:00Z",
            state: "MASTERED",
          },
        ],
      },
    ],
  };

  const vm = toKnowledgeForestViewModel(masteryData, mockAvailableSubjects);
  assert.equal(vm.chapters.length, 0);
  assert.equal(vm.concepts.length, 1);
  assert.equal(vm.hasCurriculum, true);
});

test("safely validates out-of-range mastery scores to undefined", () => {
  const masteryData: StudentMasteryRead = {
    student_id: "student-1",
    subjects: [
      {
        subject_id: "sub-math",
        code: "MATH12",
        name: "Toán 12",
        problem_type_count: 1,
        started_problem_type_count: 1,
        mastery_score: 1.5, // Out of bounds
        confidence: 0.8,
        attempt_count: 5,
        correct_count: 4,
        last_practiced_at: "2026-10-08T00:00:00Z",
        last_updated_at: "2026-10-08T00:00:00Z",
        state: "MASTERED",
        chapters: [
          {
            chapter_id: "ch-1",
            subject_id: "sub-math",
            code: "CH01",
            name: "Chương 1",
            problem_type_count: 1,
            started_problem_type_count: 1,
            mastery_score: -0.2, // Out of bounds
            confidence: 0.8,
            attempt_count: 5,
            correct_count: 4,
            last_practiced_at: "2026-10-08T00:00:00Z",
            last_updated_at: "2026-10-08T00:00:00Z",
            state: "MASTERED",
            topics: [
              {
                topic_id: "top-1",
                chapter_id: "ch-1",
                code: "TOP01",
                name: "Chủ đề 1",
                problem_type_count: 1,
                started_problem_type_count: 1,
                mastery_score: 0.5,
                confidence: 0.8,
                attempt_count: 5,
                correct_count: 4,
                last_practiced_at: "2026-10-08T00:00:00Z",
                last_updated_at: "2026-10-08T00:00:00Z",
                state: "MASTERED",
                problem_types: [
                  {
                    problem_type_id: "pt-invalid",
                    topic_id: "top-1",
                    code: "PT-INV",
                    name: "Dạng bài điểm số lỗi",
                    mastery_score: 2.5, // Out of bounds
                    confidence: 0.8,
                    attempt_count: 3,
                    correct_count: 2,
                    last_practiced_at: "2026-10-08T00:00:00Z",
                    last_updated_at: "2026-10-08T00:00:00Z",
                    state: "MASTERED",
                  },
                ],
              },
            ],
          },
        ],
        concepts: [],
      },
    ],
  };

  const vm = toKnowledgeForestViewModel(masteryData, mockAvailableSubjects);
  assert.equal(vm.summary.masteryScore, undefined);
  assert.equal(vm.chapters[0].masteryScore, undefined);
  assert.equal(vm.chapters[0].topics[0].problemTypes[0].masteryScore, undefined);
});

test("distinguishes empty available subjects from subjects with no curriculum in DB", () => {
  // Case A: Student has no assigned subjects at all
  const unassignedVm = toKnowledgeForestViewModel(undefined, []);
  assert.equal(unassignedVm.availableSubjects.length, 0);
  assert.equal(unassignedVm.hasCurriculum, false);
  assert.equal(unassignedVm.subject.name, "Chưa có môn học");

  // Case B: Student has assigned subject, but no curriculum in DB for that subject
  const emptyCurriculumVm = toKnowledgeForestViewModel(
    { student_id: "student-1", subjects: [] },
    [{ id: "sub-math", code: "MATH12", name: "Toán 12" }],
    "sub-math",
    "student-1"
  );
  assert.equal(emptyCurriculumVm.availableSubjects.length, 1);
  assert.equal(emptyCurriculumVm.hasCurriculum, false);
  assert.equal(emptyCurriculumVm.subject.name, "Toán 12");
  assert.equal(emptyCurriculumVm.chapters.length, 0);
});


test("marks a released subject as self-study discovery while preserving real hierarchy", () => {
  const masteryData = createMockMasteryData();
  const selfStudySubjects = [{ id: "sub-math", code: "MATH12", name: "Toán 12" }];

  const vm = toKnowledgeForestViewModel(
    masteryData,
    selfStudySubjects,
    "sub-math",
    "student-1",
    ["sub-math"]
  );

  assert.equal(vm.accessMode, "SELF_STUDY_DISCOVERY");
  assert.equal(vm.hasCurriculum, true);
  assert.equal(vm.chapters[0].topics[0].problemTypes.length, 3);
});
test("new student sees the complete published 6/8/9 catalog with every leaf NOT_STARTED", () => {
  const metric = {
    mastery_score: 0,
    confidence: 0,
    attempt_count: 0,
    correct_count: 0,
    last_practiced_at: null,
    last_updated_at: null,
    state: "NOT_STARTED" as const,
  };
  const topicCounts = [2, 2, 1, 1, 1, 1];
  let problemTypeIndex = 0;
  const chapters = topicCounts.map((topicCount, chapterIndex) => ({
    chapter_id: `chapter-${chapterIndex}`,
    subject_id: "math-g12",
    code: `CHAPTER_${chapterIndex}`,
    name: `Chapter ${chapterIndex + 1}`,
    ...metric,
    problem_type_count: topicCount + (chapterIndex === 0 ? 1 : 0),
    started_problem_type_count: 0,
    topics: Array.from({ length: topicCount }, (_, topicIndex) => {
      const problemCount = chapterIndex === 0 && topicIndex === 0 ? 2 : 1;
      const topicId = `topic-${chapterIndex}-${topicIndex}`;
      return {
        topic_id: topicId,
        chapter_id: `chapter-${chapterIndex}`,
        code: `TOPIC_${chapterIndex}_${topicIndex}`,
        name: `Topic ${chapterIndex + 1}.${topicIndex + 1}`,
        ...metric,
        problem_type_count: problemCount,
        started_problem_type_count: 0,
        problem_types: Array.from({ length: problemCount }, () => {
          const index = problemTypeIndex++;
          return {
            problem_type_id: `problem-type-${index}`,
            topic_id: topicId,
            code: `PROBLEM_TYPE_${index}`,
            name: `Problem type ${index + 1}`,
            ...metric,
          };
        }),
      };
    }),
  }));
  const mastery: StudentMasteryRead = {
    student_id: "new-student",
    subjects: [
      {
        subject_id: "math-g12",
        code: "MATH_G12",
        name: "Grade 12 Mathematics",
        ...metric,
        problem_type_count: 9,
        started_problem_type_count: 0,
        chapters,
        concepts: [],
      },
    ],
  };

  const viewModel = toKnowledgeForestViewModel(
    mastery,
    [{ id: "math-g12", code: "MATH_G12", name: "Grade 12 Mathematics" }],
    "math-g12",
    "new-student",
    ["math-g12"]
  );
  const topics = viewModel.chapters.flatMap((chapter) => chapter.topics);
  const leaves = topics.flatMap((topic) => topic.problemTypes);

  assert.equal(viewModel.accessMode, "SELF_STUDY_DISCOVERY");
  assert.equal(viewModel.chapters.length, 6);
  assert.equal(topics.length, 8);
  assert.equal(leaves.length, 9);
  assert.equal(viewModel.summary.problemTypeCount, 9);
  assert.equal(viewModel.summary.notStartedCount, 9);
  assert.equal(viewModel.summary.masteredCount, 0);
  assert.ok(leaves.every((leaf) => leaf.state === "NOT_STARTED"));
  assert.ok(leaves.every((leaf) => leaf.masteryScore === undefined));
});