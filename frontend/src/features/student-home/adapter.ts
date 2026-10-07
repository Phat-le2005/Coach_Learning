import type { StudentHomeViewModel } from "./types";

/**
 * Boundary for the future API-V1 adapter.
 * The source shape stays generic until StudentLearningStateRead is integrated.
 */
export interface StudentHomeAdapter<TStudentLearningState> {
  toViewModel(source: TStudentLearningState): StudentHomeViewModel;
}

export const STUDENT_HOME_API_ADAPTER_STATUS = "NOT_CONNECTED" as const;
