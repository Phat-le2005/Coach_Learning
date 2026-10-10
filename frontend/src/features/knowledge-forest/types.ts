import type { DerivedMasteryState, StudentLearningSubjectRead } from "../../lib/api/contracts";

export type KnowledgeBiome = "meadow" | "river" | "mountain" | "forest" | "sky";

export type KnowledgeStatusFilter = "ALL" | DerivedMasteryState;

export interface KnowledgeProblemTypeNode {
  id: string;
  code: string;
  name: string;
  topicId: string;
  topicName: string;
  chapterId: string;
  chapterName: string;
  masteryScore?: number;
  rawMasteryScore: number;
  confidence?: number;
  attemptCount: number;
  correctCount: number;
  state: DerivedMasteryState;
  lastPracticedAt: string | null;
  isReviewDue: boolean;
}

export interface KnowledgeTopicNode {
  id: string;
  code: string;
  name: string;
  chapterId: string;
  problemTypeCount: number;
  startedProblemTypeCount: number;
  masteryScore?: number;
  rawMasteryScore: number;
  state: DerivedMasteryState;
  attemptCount: number;
  problemTypes: KnowledgeProblemTypeNode[];
}

export interface KnowledgeChapterNode {
  id: string;
  code: string;
  name: string;
  biome: KnowledgeBiome;
  problemTypeCount: number;
  startedProblemTypeCount: number;
  masteryScore?: number;
  rawMasteryScore: number;
  state: DerivedMasteryState;
  attemptCount: number;
  topics: KnowledgeTopicNode[];
}

export interface KnowledgeConceptNode {
  id: string;
  code: string;
  name: string;
  subjectId: string;
  masteryScore?: number;
  rawMasteryScore: number;
  confidence?: number;
  attemptCount: number;
  correctCount: number;
  state: DerivedMasteryState;
  lastPracticedAt: string | null;
}

export interface KnowledgeForestSummary {
  problemTypeCount: number;
  startedProblemTypeCount: number;
  masteryScore?: number;
  rawMasteryScore: number;
  confidence?: number;
  attemptCount: number;
  state: DerivedMasteryState;
  masteredCount: number;
  weakCount: number;
  learningCount: number;
  practicingCount: number;
  reviewDueCount: number;
  notStartedCount: number;
}

export interface KnowledgeForestViewModel {
  subject: {
    id: string;
    code: string;
    name: string;
  };
  availableSubjects: StudentLearningSubjectRead[];
  accessMode: "UNAVAILABLE" | "SELF_STUDY_DISCOVERY" | "LEARNING_ACTIVITY";
  summary: KnowledgeForestSummary;
  chapters: KnowledgeChapterNode[];
  concepts: KnowledgeConceptNode[];
  hasCurriculum: boolean;
  hasEvidence: boolean;
}
