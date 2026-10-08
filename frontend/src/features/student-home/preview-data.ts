import type { StudentHomeViewModel } from "./types";

/**
 * Visual-design fixture only.
 * Do not use as production learning data.
 */
export const studentHomePreviewData: StudentHomeViewModel = {
  student: {
    displayName: "Minh",
    avatarLabel: "M",
  },
  subject: {
    id: "preview-math-12",
    name: "Toán 12 · Không gian luyện tập",
  },
  currentAction: {
    type: "CONTINUE_REPAIR",
    targetName: "Mắt xích nền tảng",
    reasonCode: "VERIFIED_ROOT_CAUSE",
  },
  mastery: {
    score: 68,
    label: "Độ vững hiện tại",
  },
  review: {
    dueCount: 3,
  },
  assignments: {
    activeCount: 1,
    completion: 64,
  },
  momentum: {
    activeDays: 7,
    week: [true, true, true, true, true, true, true],
  },
  knowledgeRegions: [
    {
      id: "preview-foundation",
      label: "Vùng nền tảng",
      progress: 86,
      state: "mastered",
      accent: "mint",
      biome: "meadow",
    },
    {
      id: "preview-change",
      label: "Vùng biến thiên",
      progress: 64,
      state: "developing",
      accent: "aqua",
      biome: "river",
    },
    {
      id: "preview-accumulation",
      label: "Vùng tích lũy",
      progress: 48,
      state: "weak",
      accent: "amber",
      biome: "mountain",
    },
    {
      id: "preview-space",
      label: "Vùng không gian",
      progress: 57,
      state: "review",
      accent: "violet",
      biome: "forest",
    },
    {
      id: "preview-uncertainty",
      label: "Vùng xác suất",
      state: "not_started",
      accent: "sky",
      biome: "sky",
    },
  ],
  priorities: [
    {
      id: "preview-priority-1",
      targetName: "Củng cố mắt xích nền tảng",
      reasonCode: "VERIFIED_ROOT_CAUSE",
      mastery: 42,
    },
    {
      id: "preview-priority-2",
      targetName: "Luyện dạng bài đang học",
      reasonCode: "CURRENT_LESSON",
      mastery: 61,
    },
    {
      id: "preview-priority-3",
      targetName: "Ôn lại vùng kiến thức sắp quên",
      reasonCode: "REVIEW_DUE",
      mastery: 73,
    },
    {
      id: "preview-priority-4",
      targetName: "Mở rộng sang mục tiêu tiếp theo",
      reasonCode: "WEAK_PROBLEM_TYPE",
    },
  ],
};
