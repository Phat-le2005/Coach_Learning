import type { DerivedMasteryState, StudentLearningSubjectRead } from "../../lib/api/contracts";

export type KnowledgeBiome = "meadow" | "river" | "mountain" | "forest" | "sky";

export type KnowledgeStatusFilter = "ALL" | DerivedMasteryState;

export type KnowledgeScopeState = "CURRENT_TEACHING" | "UNLOCKED" | "FOG_OF_WAR";

export interface KnowledgeNodeConceptItem {
  id: string;
  code: string;
  name: string;
  masteryScore?: number;
  confidence?: number;
  attemptCount: number;
  state: DerivedMasteryState;
  isWeakPrerequisite: boolean;
}

export interface KnowledgeRecommendedTaskItem {
  id: string;
  taskType: string;
  reasonCode: string;
  title: string;
  subtitle: string;
  rationale?: string;
  estimatedMinutes: number;
  problemTypeId?: string;
  conceptId?: string;
}

export interface KnowledgeClassroomContext {
  classroomName: string;
  hasActiveTeachingPlan: boolean;
  hasActiveTeacherScope?: boolean;
  currentTeachingCount: number;
  unlockedCount: number;
  fogCount: number;
  fogOfWarCount?: number;
}

export interface KnowledgeProblemTypeNode {
  id: string;
  code: string;
  name: string;
  availableQuestionCount?: number;
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
  scopeState?: KnowledgeScopeState;
  teacherScopeLabel?: string;
  priorityReasonCode?: string;
  diagnosticSummary?: string;
  relatedConcepts?: KnowledgeNodeConceptItem[];
  recommendedTasks?: KnowledgeRecommendedTaskItem[];
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
  scopeState?: KnowledgeScopeState;
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
  scopeState?: KnowledgeScopeState;
  currentTeachingCount?: number;
  unlockedCount?: number;
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
  classroomContext?: KnowledgeClassroomContext;
}
