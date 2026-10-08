import type { ResolvedStudentAction } from "./action-resolver";

export type StudentHomeActionType =
  | "CONTINUE_REPAIR"
  | "CONTINUE_VERIFICATION"
  | "CONTINUE_ASSIGNMENT"
  | "COMPLETE_OVERDUE_ASSIGNMENT"
  | "CONTINUE_PRACTICE"
  | "REVIEW_DUE"
  | "TODAY_TASK"
  | "LEARNING_PRIORITY"
  | "IDLE";

export type KnowledgeRegionState =
  | "mastered"
  | "developing"
  | "weak"
  | "review"
  | "not_started";

export type KnowledgeBiome = "meadow" | "river" | "mountain" | "forest" | "sky";

export type StudentPriorityReasonCode = string;

export interface KnowledgeRegionViewModel {
  id: string;
  label: string;
  progress?: number;
  state: KnowledgeRegionState;
  accent: "mint" | "aqua" | "sky" | "violet" | "amber";
  /** Presentation-only scenery. It is not part of the academic API contract. */
  biome?: KnowledgeBiome;
}

export interface PriorityViewModel {
  id: string;
  targetType: string;
  targetName: string;
  targetCode: string;
  reasonCode: StudentPriorityReasonCode;
  mastery?: number;
  rawMastery?: number;
  confidence?: number;
  desiredDifficulty?: number;
  priorityScore?: number;
}

export interface StudentHomeSubjectViewModel {
  id: string;
  code: string;
  name: string;
}

export interface StudentHomeViewModel {
  student: {
    displayName: string;
    email?: string;
  };
  subject: {
    id: string;
    name: string;
    code?: string;
  };
  availableSubjects: StudentHomeSubjectViewModel[];
  currentAction: {
    type: StudentHomeActionType;
    targetName?: string;
    targetCode?: string;
    reasonCode?: string;
    resourceId?: string;
    resourceType?: string;
    phase?: string;
    repairCycleIndex?: number;
  };
  resolvedAction: ResolvedStudentAction;
  mastery: {
    score?: number;
    rawScore?: number;
    label: string;
    hasEvidence: boolean;
    problemTypeStartedCount: number;
    conceptStartedCount: number;
    masteredProblemTypeCount: number;
    weakProblemTypeCount: number;
  };
  review: {
    dueCount: number;
    upcomingCount: number;
    dueTargets: Array<{
      scheduleId: string;
      targetType: string;
      targetName: string;
      targetCode: string;
      nextReviewAt: string;
    }>;
  };
  assignments: {
    activeCount: number;
    overdueCount: number;
    inProgressCount: number;
    pendingCount: number;
    upcoming: Array<{
      assignmentId: string;
      title: string;
      status: string;
      dueAt?: string | null;
      isOverdue: boolean;
    }>;
  };
  todayPlan?: {
    date: string;
    totalCount: number;
    completedCount: number;
    totalEstimatedMinutes: number;
    availableMinutes: number;
    notice?: string | null;
  } | null;
  momentum: {
    activeDays?: number;
    week?: boolean[];
  };
  knowledgeRegions: KnowledgeRegionViewModel[];
  priorities: PriorityViewModel[];
}
