import assert from "node:assert/strict";
import test from "node:test";

import {
  filterKnowledgeForest,
  matchesKeyword,
  normalizeSearchText,
} from "../src/features/knowledge-forest/filter";
import type {
  KnowledgeChapterNode,
  KnowledgeConceptNode,
} from "../src/features/knowledge-forest/types";

const mockSampleChapters: KnowledgeChapterNode[] = [
  {
    id: "ch-1",
    code: "CH01",
    name: "Ứng dụng đạo hàm để khảo sát hàm số",
    biome: "meadow",
    problemTypeCount: 3,
    startedProblemTypeCount: 2,
    rawMasteryScore: 0.75,
    masteryScore: 75,
    state: "LEARNING",
    attemptCount: 15,
    topics: [
      {
        id: "top-1",
        code: "TOP01",
        name: "Tính đơn điệu của hàm số",
        chapterId: "ch-1",
        problemTypeCount: 2,
        startedProblemTypeCount: 2,
        rawMasteryScore: 0.8,
        masteryScore: 80,
        state: "LEARNING",
        attemptCount: 12,
        problemTypes: [
          {
            id: "pt-1",
            code: "MATH12-PT-01",
            name: "Xét tính đơn điệu bằng bảng biến thiên",
            topicId: "top-1",
            topicName: "Tính đơn điệu của hàm số",
            chapterId: "ch-1",
            chapterName: "Ứng dụng đạo hàm để khảo sát hàm số",
            masteryScore: 90,
            rawMasteryScore: 0.9,
            confidence: 95,
            attemptCount: 8,
            correctCount: 7,
            state: "MASTERED",
            lastPracticedAt: "2026-10-07T00:00:00Z",
            isReviewDue: false,
          },
          {
            id: "pt-2",
            code: "MATH12-PT-02",
            name: "Đơn điệu hàm phân thức bậc nhất trên bậc nhất",
            topicId: "top-1",
            topicName: "Tính đơn điệu của hàm số",
            chapterId: "ch-1",
            chapterName: "Ứng dụng đạo hàm để khảo sát hàm số",
            masteryScore: 42,
            rawMasteryScore: 0.42,
            confidence: 60,
            attemptCount: 4,
            correctCount: 1,
            state: "WEAK",
            lastPracticedAt: "2026-10-06T00:00:00Z",
            isReviewDue: true,
          },
        ],
      },
      {
        id: "top-2",
        code: "TOP02",
        name: "Cực trị của hàm số",
        chapterId: "ch-1",
        problemTypeCount: 1,
        startedProblemTypeCount: 0,
        rawMasteryScore: 0,
        masteryScore: undefined,
        state: "NOT_STARTED",
        attemptCount: 0,
        problemTypes: [
          {
            id: "pt-3",
            code: "MATH12-PT-03",
            name: "Cực trị hàm hợp chứa tham số m",
            topicId: "top-2",
            topicName: "Cực trị của hàm số",
            chapterId: "ch-1",
            chapterName: "Ứng dụng đạo hàm để khảo sát hàm số",
            masteryScore: undefined,
            rawMasteryScore: 0,
            confidence: undefined,
            attemptCount: 0,
            correctCount: 0,
            state: "NOT_STARTED",
            lastPracticedAt: null,
            isReviewDue: false,
          },
        ],
      },
    ],
  },
  {
    id: "ch-2",
    code: "CH02",
    name: "Tọa độ trong không gian Oxyz",
    biome: "mountain",
    problemTypeCount: 1,
    startedProblemTypeCount: 1,
    rawMasteryScore: 0.65,
    masteryScore: 65,
    state: "PRACTICING",
    attemptCount: 6,
    topics: [
      {
        id: "top-3",
        code: "TOP03",
        name: "Hệ tọa độ Oxyz",
        chapterId: "ch-2",
        problemTypeCount: 1,
        startedProblemTypeCount: 1,
        rawMasteryScore: 0.65,
        masteryScore: 65,
        state: "PRACTICING",
        attemptCount: 6,
        problemTypes: [
          {
            id: "pt-4",
            code: "MATH12-PT-04",
            name: "Phương trình mặt cầu đi qua bốn điểm",
            topicId: "top-3",
            topicName: "Hệ tọa độ Oxyz",
            chapterId: "ch-2",
            chapterName: "Tọa độ trong không gian Oxyz",
            masteryScore: 65,
            rawMasteryScore: 0.65,
            confidence: 70,
            attemptCount: 6,
            correctCount: 4,
            state: "PRACTICING",
            lastPracticedAt: "2026-10-05T00:00:00Z",
            isReviewDue: false,
          },
        ],
      },
    ],
  },
];

const mockSampleConcepts: KnowledgeConceptNode[] = [
  {
    id: "c-1",
    code: "CON-01",
    name: "Định lý Fermat về điểm cực trị",
    subjectId: "sub-1",
    masteryScore: 88,
    rawMasteryScore: 0.88,
    confidence: 90,
    attemptCount: 5,
    correctCount: 4,
    state: "MASTERED",
    lastPracticedAt: "2026-10-04T00:00:00Z",
  },
  {
    id: "c-2",
    code: "CON-02",
    name: "Tích có hướng của hai vectơ",
    subjectId: "sub-1",
    masteryScore: undefined,
    rawMasteryScore: 0,
    confidence: undefined,
    attemptCount: 0,
    correctCount: 0,
    state: "NOT_STARTED",
    lastPracticedAt: null,
  },
];

test("normalizeSearchText strips Vietnamese diacritics and converts Đ/đ to d", () => {
  assert.equal(normalizeSearchText("Đạo Hàm"), "dao ham");
  assert.equal(normalizeSearchText("Cực trị hàm phân thức"), "cuc tri ham phan thuc");
  assert.equal(normalizeSearchText("Tọa độ Oxyz"), "toa do oxyz");
});

test("matchesKeyword matches both accented and non-accented search terms", () => {
  const normQuery = normalizeSearchText("dao ham");
  assert.equal(matchesKeyword("Ứng dụng đạo hàm", "dao ham", normQuery), true);
  assert.equal(matchesKeyword("Xét tính đơn điệu", "dao ham", normQuery), false);

  const normOxyz = normalizeSearchText("oxyz");
  assert.equal(matchesKeyword("Tọa độ trong không gian Oxyz", "oxyz", normOxyz), true);
});

test("hierarchical search: matching chapter query displays all problem types of chapter conforming to status filter", () => {
  const res = filterKnowledgeForest({
    chapters: mockSampleChapters,
    concepts: mockSampleConcepts,
    searchQuery: "dao ham", // matches Chapter 1
    statusFilter: "ALL",
  });

  // Chapter 1 matches, so all 3 problem types in Chapter 1 are retained
  assert.equal(res.filteredChapters.length, 1);
  assert.equal(res.filteredChapters[0].id, "ch-1");
  assert.equal(res.matchingProblemTypeCount, 3);
  assert.equal(res.autoExpandedChapterIds.has("ch-1"), true);
});

test("hierarchical search: matching topic query displays its problem types", () => {
  const res = filterKnowledgeForest({
    chapters: mockSampleChapters,
    concepts: mockSampleConcepts,
    searchQuery: "cuc tri", // matches Topic "Cực trị của hàm số" and Concept "Fermat về điểm cực trị"
    statusFilter: "ALL",
  });

  assert.equal(res.filteredChapters.length, 1);
  assert.equal(res.filteredChapters[0].topics.length, 1);
  assert.equal(res.filteredChapters[0].topics[0].id, "top-2");
  assert.equal(res.filteredConcepts.length, 1);
  assert.equal(res.filteredConcepts[0].id, "c-1");
  assert.equal(res.totalMatchedCount, 2);
});

test("status filtering prunes empty topics and chapters without matching nodes", () => {
  const res = filterKnowledgeForest({
    chapters: mockSampleChapters,
    concepts: mockSampleConcepts,
    searchQuery: "",
    statusFilter: "WEAK",
  });

  // Only Chapter 1 has a WEAK problem type (pt-2 in topic 1)
  assert.equal(res.filteredChapters.length, 1);
  assert.equal(res.filteredChapters[0].topics.length, 1);
  assert.equal(res.filteredChapters[0].topics[0].problemTypes.length, 1);
  assert.equal(res.filteredChapters[0].topics[0].problemTypes[0].id, "pt-2");
  // Chapter 2 has no WEAK nodes and must be completely pruned
  assert.equal(res.filteredChapters.some((c) => c.id === "ch-2"), false);
});

test("concept-only matches: displays concept result without marking entire forest empty", () => {
  const res = filterKnowledgeForest({
    chapters: mockSampleChapters,
    concepts: mockSampleConcepts,
    searchQuery: "Fermat", // matches only Concept 1
    statusFilter: "ALL",
  });

  assert.equal(res.filteredChapters.length, 0);
  assert.equal(res.filteredConcepts.length, 1);
  assert.equal(res.filteredConcepts[0].name, "Định lý Fermat về điểm cực trị");
  assert.equal(res.matchingProblemTypeCount, 0);
  assert.equal(res.matchingConceptCount, 1);
  assert.equal(res.totalMatchedCount, 1);
  assert.equal(res.isFiltered, true);
});

test("no-match state returns totalMatchedCount === 0 and isFiltered === true", () => {
  const res = filterKnowledgeForest({
    chapters: mockSampleChapters,
    concepts: mockSampleConcepts,
    searchQuery: "tu_khoa_khong_ton_tai_xyz",
    statusFilter: "ALL",
  });

  assert.equal(res.filteredChapters.length, 0);
  assert.equal(res.filteredConcepts.length, 0);
  assert.equal(res.totalMatchedCount, 0);
  assert.equal(res.isFiltered, true);
});
