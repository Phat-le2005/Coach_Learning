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
  targetName: string;
  reasonCode: StudentPriorityReasonCode;
  mastery?: number;
}

export interface StudentHomeViewModel {
  student: {
    displayName: string;
    avatarLabel: string;
  };
  subject: {
    id: string;
    name: string;
  };
  currentAction: {
    type: StudentHomeActionType;
    targetName?: string;
    reasonCode?: string;
  };
  mastery: {
    score?: number;
    label: string;
  };
  review: {
    dueCount: number;
  };
  assignments: {
    activeCount: number;
    completion?: number;
  };
  momentum: {
    activeDays?: number;
    week?: boolean[];
  };
  knowledgeRegions: KnowledgeRegionViewModel[];
  priorities: PriorityViewModel[];
}
