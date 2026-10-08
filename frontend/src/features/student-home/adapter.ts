import type { StudentLearningStateRead } from "@/lib/api/contracts";
import { ApiContractError } from "@/lib/api/validation";

import type { StudentHomeActionType, StudentHomeViewModel } from "./types";

/**
 * Boundary for the future API-V1 adapter.
 * The source shape stays generic until StudentLearningStateRead is integrated.
 */
export interface StudentHomeAdapter<TStudentLearningState> {
  toViewModel(source: TStudentLearningState): StudentHomeViewModel;
}

const actionTypes: StudentHomeActionType[] = ["CONTINUE_REPAIR", "CONTINUE_VERIFICATION", "CONTINUE_ASSIGNMENT", "COMPLETE_OVERDUE_ASSIGNMENT", "CONTINUE_PRACTICE", "REVIEW_DUE", "TODAY_TASK", "LEARNING_PRIORITY", "IDLE"];

function percent(value: number | null): number | undefined {
  return value === null ? undefined : Math.round(Math.min(1, Math.max(0, value)) * 100);
}

function avatarLabel(fullName: string): string {
  const words = fullName.trim().split(/\s+/u).filter(Boolean);
  return words.slice(-2).map((word) => word[0]?.toLocaleUpperCase("vi") ?? "").join("") || "—";
}

export function toStudentHomeViewModel(source: StudentLearningStateRead, fullName: string): StudentHomeViewModel {
  if (!actionTypes.includes(source.current_action.action_type as StudentHomeActionType)) {
    throw new ApiContractError("Unknown StudentCurrentActionType", "response.current_action.action_type");
  }
  const focus = source.available_subjects.find((subject) => subject.id === source.focus_subject_id) ?? source.available_subjects[0];
  const mastery = percent(source.mastery_summary.average_problem_type_mastery ?? source.mastery_summary.average_concept_mastery);
  return {
    student: { displayName: fullName, avatarLabel: avatarLabel(fullName) },
    subject: { id: focus?.id ?? "", name: focus?.name ?? "Chưa có môn học" },
    currentAction: { type: source.current_action.action_type as StudentHomeActionType, targetName: source.current_action.target_name ?? undefined, reasonCode: source.current_action.reason_code ?? undefined },
    mastery: { score: mastery, label: mastery === undefined ? "Chưa đủ dữ liệu" : "Độ vững hiện tại" },
    review: { dueCount: source.review.due_now_count },
    assignments: { activeCount: source.assignments.overdue_count + source.assignments.in_progress_count + source.assignments.pending_count },
    momentum: {},
    knowledgeRegions: [],
    priorities: source.priority_targets.map((priority) => ({
      id: priority.problem_type_id ?? priority.concept_id ?? `${priority.target_type}:${priority.target_code}`,
      targetName: priority.target_name,
      reasonCode: priority.reason_code,
      mastery: percent(priority.mastery_score),
    })),
  };
}

export const studentHomeAdapter: StudentHomeAdapter<StudentLearningStateRead> = { toViewModel: (source) => toStudentHomeViewModel(source, "Học sinh") };
export const STUDENT_HOME_API_ADAPTER_STATUS = "CONNECTED" as const;
